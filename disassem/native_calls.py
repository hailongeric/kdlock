"""Direct original-API calls inside one immutable spin wrapper invocation.

The provider relocates only the generated E8 slots before publication. No
helper instructions, source CALL bytes, strings or destinations are inspected.
The existing typed API summaries and caller guarantees still govern admission.
"""

import conflict

REQUIREMENT = 16
LIMIT_EXIT = 10
MAX_SITES = 64
SERVICES = {4: ("strcmp", "Stack_STRCMP_LEFT", 128),
            5: ("strscpy_pad", "Stack_PAD_LEFT", 16)}


class NativeCalls:
    def __init__(self, services):
        self.services = services
        self.sites = []

    def emit(self, line, continuation, target, reg_map):
        service = self.services[target]
        symbol, counter, _ = SERVICES[service.service_id]
        if len(self.sites) >= MAX_SITES:
            raise ValueError("direct string call directory exceeds 64 sites")
        # Ordinary lowering restores these fixed caches after every source
        # instruction. Refuse a broken mapping instead of guessing a waiter SP.
        if reg_map.get("13") != "SP" or reg_map.get("12") != "BP":
            raise ValueError("direct string CALL requires canonical virtual SP/BP")
        name = f"kd_native_call_{line.offset:x}"
        self.sites.append((name, service.service_id, continuation))
        code = conflict.release_conflict(reg_map)
        # Every logical special GPR is now in its authoritative packet slot.
        # Native C preserves physical R12/R13, including the virtual SP/BP.
        reg_map.clear()
        reg_map.update(conflict.block_init())
        reg_map.dirty.clear()
        code += f"""/* KD_DIRECT_STRING id={service.service_id} symbol={symbol} */
MOVABS R14, 0x{continuation:x}
LEA R13, [R13 - 8]
MOV QWORD PTR[R13], R14
/* RCX is saved before using its flag-neutral zero branch. Keep the short
 * branch local; neither path leaves a temporary value in logical RCX. */
MOV R14, RCX
MOV RCX, {counter}
JRCXZ {name}_limit
LEA RCX, [RCX - 1]
MOV {counter}, RCX
MOV RCX, R14
JMP {name}_invoke
{name}_limit:
MOV RCX, R14
MOVABS R14, 0x{target:x}
MOV Stack_IJ, {LIMIT_EXIT}
JMP full_exit
{name}_invoke:
/* Preserve the current adapter's logical GPR contract, especially the
 * physical R11 packet pointer. The direct wrapper aligned RSP once; these
 * eight pushes preserve that alignment. Every temporary is popped before
 * continuing or exiting, and source stack instructions use virtual R13. */
PUSH RCX
PUSH RDX
PUSH RSI
PUSH RDI
PUSH R8
PUSH R9
PUSH R10
PUSH R11
{name}:
.byte 0xe8
.long 0
POP R11
POP R10
POP R9
POP R8
POP RDI
POP RSI
POP RDX
POP RCX
"""
        if service.service_id == 4:
            # Match the existing unsigned-int adapter; pad returns a full long.
            code += "MOV EAX, EAX\n"
        code += f"""/* Consume the actual source CALL word once, with a one-target
 * return whitelist. No fixed fallthrough substitutes for its contents.
 * Subtract the expected address with LEA, keeping all helper result flags.
 * The actual return stays in R14 for the existing bad-return exit. */
MOV R14, QWORD PTR[R13]
LEA R13, [R13 + 8]
MOV R15, RCX
MOVABS RCX, 0x{(-continuation) & ((1 << 64) - 1):x}
LEA RCX, [R14 + RCX]
JRCXZ {name}_returned
MOV RCX, R15
MOV Stack_IJ, 2
JMP full_exit
{name}_returned:
MOV RCX, R15
JMP loc_{continuation:x}
"""
        return code

    def metadata(self):
        lines = [".balign 8", "kd_native_call_sites:"]
        for name, service, continuation in self.sites:
            lines += [f".long {name} - main", f".long {service}",
                      f".quad 0x{continuation:x}"]
        lines += ['.ascii "KDNC0001"', '.long kd_native_call_sites - main',
                  f'.long {len(self.sites)}']
        return "\n".join(lines) + "\n"
