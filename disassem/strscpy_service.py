"""Original strscpy_pad API with an explicit 64-byte caller-memory effect.

Count and destination facts justify that analysis summary; they are not runtime
buffer checks. The original caller guarantees source validity and the live,
disjoint local destination. No helper code, data or special CALL encoding is
inspected. The audited selected caller/helpers neither observe nor retain
pointers into temporary service CALL/control scratch below pre-CALL SP. This
explicit caller promise permits separate control-token and ordinary-object
effects; valid arguments alone do not establish it.
Destination effects must never be marked readonly, including truncation.
"""

from miasm.expression.expression import ExprId, ExprInt

from context_guards import signed_offset
from context_registers import context_reference, static_address


REQUIREMENT = 8
SPEC = ("STRSCPY_PAD", 5, "strscpy_pad")
ARGUMENTS = ("RDI", "RSI", "RDX")
MAX_BYTES = 64


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
    # The audited caller supplies a live local destination disjoint from CALL
    # words and the source, with no source read observing discarded helper
    # stack scratch. Retain screening of the entire possible memory spans; caller
    # promises cannot hide a known task/CPU-sensitive or widened argument.
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
