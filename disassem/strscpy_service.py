"""Exact bounded strscpy_pad service for an audited caller-owned local buffer.

The original helper runs after a separate provider capability checks count,
stack bounds, stable source bytes, complete helper text and the CALL token.
This is a writing C-API contract: discarded helper stack scratch is not an
observable API result. Its destination effects must never be marked readonly.
"""
from pathlib import Path
import re
import struct

from miasm.expression.expression import ExprId, ExprInt

from context_guards import signed_offset
from context_registers import context_reference, static_address


REQUIREMENT = 8
SPEC = ("STRSCPY_PAD", 5, "strscpy_pad")
ARGUMENTS = ("RDI", "RSI", "RDX")
_header = (Path(__file__).resolve().parent.parent / "include/kd_strscpy_contract.h").read_text()


def _number(name):
    match = re.search(r"^#define " + re.escape(name) + r" ([0-9]+)U$", _header, re.M)
    if match is None:
        raise ValueError("missing strscpy contract constant " + name)
    return int(match.group(1))


def _template(name, size):
    match = re.search(r"#define " + re.escape(name) + r" \{(.*?)\}", _header, re.S)
    if match is None:
        raise ValueError("missing strscpy contract template " + name)
    raw = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", match.group(1)))
    if len(raw) != size:
        raise ValueError("inconsistent strscpy contract template " + name)
    return raw


MAX_BYTES = _number("KD_STRSCPY_BYTES")
SIZES = {
    "strscpy_pad": _number("KD_STRSCPY_PAD_CODE_BYTES"),
    "strscpy": _number("KD_STRSCPY_CODE_BYTES"),
    "__memset": _number("KD_STRSCPY_MEMSET_ENTRY_BYTES"),
    "memset_erms": _number("KD_STRSCPY_MEMSET_ERMS_BYTES"),
    "its_return_thunk": 1,
}
TEMPLATES = {
    "strscpy_pad": _template("KD_STRSCPY_PAD_CODE_TEMPLATE", SIZES["strscpy_pad"]),
    "strscpy": _template("KD_STRSCPY_CODE_TEMPLATE", SIZES["strscpy"]),
    "__memset": _template("KD_STRSCPY_MEMSET_ENTRY_TEMPLATE", SIZES["__memset"]),
    "memset_erms": _template("KD_STRSCPY_MEMSET_ERMS_TEMPLATE", SIZES["memset_erms"]),
    "its_return_thunk": b"\xc3",
}
RELOCATIONS = {
    "strscpy_pad": (
        (_number("KD_STRSCPY_PAD_CALL1_DISP"), "strscpy"),
        (_number("KD_STRSCPY_PAD_CALL2_DISP"), "__memset"),
        (_number("KD_STRSCPY_PAD_RETURN_DISP"), "its_return_thunk"),
    ),
    "strscpy": tuple((_number("KD_STRSCPY_RETURN%d_DISP" % index), "its_return_thunk")
                     for index in (1, 2, 3)),
    "memset_erms": ((_number("KD_STRSCPY_MEMSET_RETURN_DISP"), "its_return_thunk"),),
}


def matches_text(raw, addresses):
    """Check all reachable helper text, exact branches and every external edge."""
    if set(raw) != set(SIZES) or any(not addresses.get(name) for name in SIZES):
        return False
    for name, size in SIZES.items():
        data = raw[name]
        if data is None or len(data) != size:
            return False
        normalized = bytearray(data)
        for offset, target_name in RELOCATIONS.get(name, ()):
            target = (addresses[name] + offset + 4 + struct.unpack_from("<i", data, offset)[0]) & ((1 << 64) - 1)
            if target != addresses[target_name]:
                return False
            normalized[offset:offset + 4] = b"\0" * 4
        if name == "__memset":
            target = (addresses[name] + 6 + struct.unpack_from("<b", data, 5)[0]) & ((1 << 64) - 1)
            if target != addresses["memset_erms"]:
                return False
            normalized[5] = 0
        if normalized != TEMPLATES[name]:
            return False
    return True


def verified(address, symbol_lookup, reader):
    addresses = {name: symbol_lookup(name, 0) for name in SIZES}
    if not address or addresses["strscpy_pad"] != address or not all(addresses.values()):
        return False
    raw = {name: reader(addresses[name], size) for name, size in SIZES.items()}
    # The exact pad prologue reads no arithmetic flags before its strscpy CALL.
    # With the mandatory static AND runtime RDX=64 check, strscpy's TEST/JZ
    # cannot take the zero-count exit; its following CMP RDX,INT_MAX defines
    # all six arithmetic flags before any remaining incoming flag is read.
    # This argument-conditioned fact is not a universal flags-dead helper for
    # arbitrary source guards. Keep pad out of flag_dead_calls: their generic
    # proof conservatively retains TEST's undefined AF on the zero-count path.
    return matches_text(raw, addresses)


def targets(resolved):
    return {address for address, spec in resolved.items() if tuple(spec) == SPEC}


def writer_targets(resolved):
    return {address: MAX_BYTES for address in targets(resolved)}


def argument_rejection(line, db, constants, checked_targets, symbols,
                       lock_kind=None, lock_symbols=None):
    if line.name.upper() != "CALL" or not line.args:
        return None
    target = static_address(line.args[0], db, line.offset + line.l)
    if target not in checked_targets:
        return None
    raw = bytes(line.b)
    if len(raw) != 5 or raw[0] != 0xe8:
        return "typed strscpy_pad requires an exact direct source CALL", ""
    count = constants.resolve_many(ExprId("RDX", 64))
    if count != [ExprInt(MAX_BYTES, 64)]:
        return "typed strscpy_pad requires the exact count 64", ""
    destinations = constants.resolve_many(ExprId("RDI", 64))
    frames = constants.resolve_many(ExprId("RBP", 64))
    if len(destinations) != 1 or len(frames) != 1:
        return "typed strscpy_pad requires one known local destination", ""
    destination, frame = map(constants.memory.address, (destinations[0], frames[0]))
    if (destination is None or frame is None or destination[0] != frame[0]
            or not -16384 <= signed_offset(destination[1] - frame[1]) <= -MAX_BYTES):
        return "typed strscpy_pad destination is not a bounded current-frame span", ""
    # The provider checks the actual lower bound against current SP and the
    # logical task-stack allocation before writing. Static context screening
    # still covers both entire possible memory spans; runtime bounds cannot
    # hide a known task/CPU-sensitive address or a widened argument.
    for name, expressions in (("destination", destinations),
                              ("source", constants.resolve_many(ExprId("RSI", 64)))):
        for expr in expressions:
            symbol = context_reference(expr, db, line.offset + line.l, symbols, MAX_BYTES)
            if symbol:
                return "context-sensitive strscpy_pad %s requires native execution" % name, symbol
            address = static_address(expr, db, line.offset + line.l)
            if lock_symbols and address in lock_symbols:
                kind, symbol = lock_symbols[address]
                if kind != lock_kind:
                    return f"{kind} lock reference in {lock_kind} entry requires native execution", symbol
    return None
