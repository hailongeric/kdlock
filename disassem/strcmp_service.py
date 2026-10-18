"""Original strcmp API semantics, with ordinary caller-context admission.

The resolved kernel symbol supplies the original function. Its caller guarantees
valid, terminated, stable ordinary kernel strings, as for a native call. No
helper text, string data or helper-specific CALL encoding is inspected here.
The service changes no caller memory and supplies no source-flags proof.
The separately audited selected caller and its helpers also do not observe,
retain pointers into, or mutate the temporary service CALL/control scratch
below pre-CALL SP. Valid strings alone do not imply that extra caller contract.
"""

from miasm.expression.expression import ExprId

from context_registers import context_reference, static_address


REQUIREMENT = 4
SPEC = ("STRCMP", 4, "strcmp")
# Retain the existing static context-screening extent. This is not a string
# length limit or a validity check; the native caller owns the complete string.
MAX_BYTES = 256


def targets(resolved):
    """Only the resolver's negotiated original API symbol supplies this effect."""
    return {address for address, spec in resolved.items() if tuple(spec) == SPEC}


def argument_rejection(line, db, constants, checked_targets, symbols,
                       lock_kind=None, lock_symbols=None):
    if line.name.upper() != "CALL" or not line.args:
        return None
    target = static_address(line.args[0], db, line.offset + line.l)
    if target not in checked_targets:
        return None
    for name in ("RDI", "RSI"):
        # Unknown ordinary pointers retain ordinary policy; widened or known
        # context addresses retain refusal. Audited callers additionally supply
        # ordinary-memory validity for the complete terminated strings, just
        # as for native strcmp. No source-function inspection supplies a proof.
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
