"""Admission for x86 state that the delegated register packet does not carry.

Only the scalar instruction families below may reach lowering. This is separate
from address/alias and entry-value proofs: a known GPR input does not authorize
RDMSR, POPFQ, or another access to the physical executor's context. New decoder
mnemonics fail closed until their explicit and implicit state has been reviewed.

native_escape.py separately recognizes a small exact-byte set that can become
terminal waiter-return markers in negotiated mutex images. This policy still
rejects copying those instructions into generated code.
"""
from miasm.expression.expression import ExprId, ExprMem


SCALAR_INSTRUCTIONS = frozenset("""
    MOV MOVABS MOVSX MOVZX MOVSXD MOVBE LEA XCHG XADD
    CMPXCHG CMPXCHG8B CMPXCHG16B
    ADD ADC ADCX ADOX SUB SBB MUL IMUL DIV IDIV INC DEC NEG
    AND OR XOR NOT TEST CMP SHL SAL SHR SAR SHLD SHRD ROL ROR RCL RCR
    BT BTC BTR BTS BSF BSR BSWAP POPCNT LZCNT TZCNT
    ANDN BEXTR BLSI BLSMSK BLSR BZHI MULX PDEP PEXT RORX SARX SHLX SHRX
    CBW CWDE CDQE CWD CDQ CQO CLC STC CMC
    MOVSB MOVSW MOVSD MOVSQ LODSB LODSW LODSD LODSQ
    STOSB STOSW STOSD STOSQ CMPSB CMPSW CMPSD CMPSQ
    SCASB SCASW SCASD SCASQ XLAT XLATB
    CALL RET PUSH POP LEAVE JMP JCXZ JECXZ JRCXZ
    NOP ENDBR64 PAUSE LFENCE MFENCE SFENCE
    PREFETCHNTA PREFETCHT0 PREFETCHT1 PREFETCHT2 PREFETCHW PREFETCHWT1
""".split()) | frozenset(
    prefix + condition
    for prefix in ("J", "CMOV", "SET")
    for condition in "O NO B C NAE NB NC AE E Z NE NZ BE NA NBE A S NS P PE NP PO L NGE NL GE LE NG NLE G".split()
)

GPRS = frozenset("""
    RAX EAX AX AL AH RBX EBX BX BL BH RCX ECX CX CL CH RDX EDX DX DL DH
    RSI ESI SI SIL RDI EDI DI DIL RBP EBP BP BPL RSP ESP SP SPL RIP EIP IP
""".split()) | frozenset(f"R{i}{suffix}" for i in range(8, 16)
                       for suffix in ("", "D", "W", "B"))
SEGMENTS = frozenset({"CS", "DS", "ES", "SS", "FS", "GS"})
LEGACY_PREFIXES = frozenset({0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65,
                             0x66, 0x67, 0xF0, 0xF2, 0xF3})


def opcode_bytes(raw):
    """Strip prefixes at one instruction boundary, never scan operand bytes."""
    raw = bytes(raw or b"")[:15]
    index = 0
    while index < len(raw) and (raw[index] in LEGACY_PREFIXES
                               or 0x40 <= raw[index] <= 0x4F):
        index += 1
    return raw[:index], raw[index:]


def segment_encoding_policy_error(raw):
    prefixes, opcode = opcode_bytes(raw)
    # Miasm 0.1.5 misidentifies SWAPGS and two FSGSBASE encodings. Redundant
    # legacy/REX prefixes must not turn them into an admitted scalar operation.
    if opcode.startswith(b"\x0f\x01\xf8"):
        return "direct FS/GS base access is unsupported"
    if (0xF3 in prefixes and opcode.startswith(b"\x0f\xae")
            and len(opcode) >= 3 and opcode[2] & 0xE0 == 0xC0):
        return "direct FS/GS base access is unsupported"
    return None


def encoding_rejection(raw):
    """Recognize sensitive encodings even when decoding fails or misnames them.

    Accept a bounded lookahead at an undecodable instruction start as well as
    decoded bytes. A partial prefix/opcode needs more text, not a guessed ban.
    """
    reason = segment_encoding_policy_error(raw)
    if reason:
        return reason
    prefixes, opcode = opcode_bytes(raw)
    if not opcode:
        return None
    if ((0xF2 in prefixes or 0xF3 in prefixes)
            and (0xF0 in prefixes or opcode[0] in {0x86, 0x87})) or (
            0xF3 in prefixes and opcode[0] in {0x88, 0x89, 0xC6, 0xC7}):
        return "transactional acquire/release prefix requires native context"
    if 0xF2 in prefixes and (opcode[0] in {0xC2, 0xC3, 0xE8, 0xE9, 0xEB, 0xFF}
            or 0x70 <= opcode[0] <= 0x7F
            or len(opcode) >= 2 and opcode[0] == 0x0F and 0x80 <= opcode[1] <= 0x8F):
        return "bounds-prefixed control transfer requires native context"
    if opcode[0] in {0xFA, 0xFB}:
        return "IRQ state modification requires native context"
    if opcode[0] in {0x9C, 0x9D, 0x9E, 0x9F, 0xFC, 0xFD, 0xCF}:
        return "processor flags access requires native context"
    if opcode[0] in {0x8C, 0x8E}:
        return "direct segment register access requires native context"
    if opcode[0] in {0xCC, 0xCD, 0xCE, 0xF1, 0xF4}:
        return "interrupt or halt instruction requires native context"
    if opcode[:3] in {b"\x0f\x01\xca", b"\x0f\x01\xcb",
                     b"\x0f\x01\xee", b"\x0f\x01\xef"}:
        return "user-memory-access state requires native context"
    if len(opcode) >= 2 and opcode[0] == 0x0F and opcode[1] in {
            0x00, 0x01, 0x05, 0x06, 0x07, 0x08, 0x09,
            0x20, 0x21, 0x22, 0x23, 0x24, 0x26,
            0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37, 0xA2, 0xAA}:
        # Descriptor/control/debug registers, MSRs, counters, CPUID, system
        # transitions, TLB/cache control and the 0F 01 system instruction group.
        return "processor control/state instruction requires native context"
    if opcode[0] == 0x9B or 0xD8 <= opcode[0] <= 0xDF:
        return "FPU state is not virtualized"
    return None


def rejection(line):
    reason = encoding_rejection(getattr(line, "b", b""))
    if reason:
        return reason
    name = line.name.upper()
    if name not in SCALAR_INSTRUCTIONS:
        return f"instruction {name} has no delegated CPU-state contract"
    if name == "NOP":
        # Alignment NOPs may carry pseudo memory/segment operands.
        return None
    for arg in line.args:
        for reg in arg.get_r(mem_read=True):
            if not isinstance(reg, ExprId) or str(reg).upper() in GPRS:
                continue
            # Segment memory is checked/lowered separately; direct access to a
            # segment register never gets this exception. MOVSD's XMM operands
            # also cannot borrow the scalar string instruction's allowance.
            if isinstance(arg, ExprMem) and str(reg).upper() in SEGMENTS:
                continue
            return f"hardware register {reg} is not virtualized"
    return None
