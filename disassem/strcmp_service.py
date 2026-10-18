"""Narrow native strcmp contract for audited stable ordinary kernel strings.

The original helper executes only after bounded runtime NUL checks. This
module recognizes that exact helper, proves its incoming flag independence,
and screens its pointer arguments through the ordinary context-address policy.
Neither the bound nor the held lock proves an arbitrary object's lifetime.
"""
from pathlib import Path
import re
import struct

from miasm.expression.expression import ExprId

from context_registers import context_reference, static_address


REQUIREMENT = 4
SPEC = ("STRCMP", 4, "strcmp")
_header = (Path(__file__).resolve().parent.parent / "include/kd_strcmp_contract.h").read_text()


def _number(name):
    match = re.search(r"^#define " + re.escape(name) + r" ([0-9]+)U$", _header, re.M)
    if match is None:
        raise ValueError("missing strcmp contract constant " + name)
    return int(match.group(1))


MAX_BYTES = _number("KD_STRCMP_MAX_BYTES")
CODE_BYTES = _number("KD_STRCMP_CODE_BYTES")
TAIL_OFFSETS = (_number("KD_STRCMP_TAIL1_DISP"), _number("KD_STRCMP_TAIL2_DISP"))
_template = re.search(r"#define KD_STRCMP_CODE_TEMPLATE \{(.*?)\}", _header, re.S)
if _template is None:
    raise ValueError("missing strcmp code template")
TEMPLATE = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", _template.group(1)))
_returns = re.search(r"#define KD_STRCMP_RETURN_TEMPLATE \{(.*?)\}", _header, re.S)
if _returns is None:
    raise ValueError("missing strcmp return template")
RETURN_TEMPLATE = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", _returns.group(1)))
if len(TEMPLATE) != CODE_BYTES or MAX_BYTES != 256:
    raise ValueError("inconsistent strcmp contract")


def matches_text(raw, address, return_thunk):
    if not address or raw is None or len(raw) != CODE_BYTES:
        return False
    normalized = bytearray(raw)
    for offset in TAIL_OFFSETS:
        if raw[offset - 1:offset + 4] == RETURN_TEMPLATE:
            normalized[offset - 1] = 0xe9
        else:
            target = (address + offset + 4 + struct.unpack_from("<i", raw, offset)[0]) & ((1 << 64) - 1)
            if raw[offset - 1] != 0xe9 or not return_thunk or target != return_thunk:
                return False
        normalized[offset:offset + 4] = b"\0" * 4
    return normalized == TEMPLATE


def verified(address, return_thunk, reader):
    raw = reader(address, CODE_BYTES)
    if not matches_text(raw, address, return_thunk):
        return False
    # Prove the actual original instructions, not a claim based on its C ABI.
    # Missing return-thunk blocks remain absent: the proof must kill every
    # incoming flag before reaching any uncovered successor. Here the first
    # byte CMP does so, before the first conditional branch.
    from translation_scope import decode_regions
    from guard_flags import prove_flags_dead

    blocks, databases = decode_regions([(raw, address, [address])], 0, set())
    blocks = {start: block for start, block in blocks.items() if block.lines}
    databases = {block: databases[block] for block in blocks.values()}
    return prove_flags_dead(blocks, databases, address) is None


def targets(resolved):
    """Only the resolver's capability/text/proof-checked service is eligible."""
    return {address for address, spec in resolved.items() if tuple(spec) == SPEC}


def argument_rejection(line, db, constants, checked_targets, symbols,
                       lock_kind=None, lock_symbols=None):
    if line.name.upper() != "CALL" or not line.args:
        return None
    target = static_address(line.args[0], db, line.offset + line.l)
    if target not in checked_targets:
        return None
    raw = bytes(line.b)
    if len(raw) != 5 or raw[0] != 0xe8:
        return "typed strcmp requires an exact direct source CALL", ""
    for name in ("RDI", "RSI"):
        # Unknown ordinary pointers retain ordinary policy; widened or known
        # context addresses retain refusal. The runtime bounds the loop's
        # actual accesses within the screened span before the native invocation.
        for expr in constants.resolve_many(ExprId(name, 64)):
            symbol = context_reference(expr, db, line.offset + line.l, symbols, MAX_BYTES)
            if symbol:
                return "context-sensitive strcmp argument requires native execution", symbol
            address = static_address(expr, db, line.offset + line.l)
            if lock_symbols and address in lock_symbols:
                kind, symbol = lock_symbols[address]
                if kind != lock_kind:
                    return f"{kind} lock reference in {lock_kind} entry requires native execution", symbol
    return None
