"""Refine numeric packet alternatives on an ordinary decoded branch edge.

This is a projection of the existing finite Cartesian domain, not a helper
summary or a runtime-memory assumption. Unknown inputs retain both edges.
Only an adjacent compare and branch can supply a predicate. This keeps the
proof local to exact source operands without adding a cross-block flag domain.
"""

from itertools import product

from miasm.expression.expression import ExprId, ExprInt
from miasm.expression.simplifications import expr_simp

from context_registers import static_address


_EQUAL = {"JE", "JZ"}
_UNEQUAL = {"JNE", "JNZ"}
_UNSIGNED = {
    "JB": "lt", "JC": "lt", "JNAE": "lt",
    "JAE": "ge", "JNB": "ge", "JNC": "ge",
    "JBE": "le", "JNA": "le", "JA": "gt", "JNBE": "gt",
}
_SIGNED = {
    "JL": "lt", "JNGE": "lt", "JGE": "ge", "JNL": "ge",
    "JLE": "le", "JNG": "le", "JG": "gt", "JNLE": "gt",
}


def _taken(operation, branch, left, right, width):
    mask = (1 << width) - 1
    left, right = left & mask, right & mask
    if operation == "TEST":
        equal = (left & right) == 0
        return equal if branch in _EQUAL else not equal
    if branch in _EQUAL:
        return left == right
    if branch in _UNEQUAL:
        return left != right
    if branch in _SIGNED:
        sign = 1 << (width - 1)
        left, right = (left ^ sign) - sign, (right ^ sign) - sign
        relation = _SIGNED[branch]
    else:
        relation = _UNSIGNED[branch]
    return {"lt": left < right, "ge": left >= right,
            "le": left <= right, "gt": left > right}[relation]


def refine(tracker, block, database, target):
    """Return a conservative edge state, or None for a proven impossible edge.

    Projecting accepted environments may lose correlations, which adds possible
    packets rather than removing them. Bounds and memory facts are unchanged.
    An unknown/widened register is never converted into a numeric assumption.
    """
    state = tracker.snapshot()
    if len(block.lines) < 2 or database is None:
        return state
    compare, jump = block.lines[-2:]
    operation, branch = compare.name.upper(), jump.name.upper()
    supported = _EQUAL | _UNEQUAL
    if operation == "CMP":
        supported |= _UNSIGNED.keys() | _SIGNED.keys()
    elif operation != "TEST":
        return state
    if (branch not in supported or len(compare.args) != 2 or len(jump.args) != 1
            or compare.offset + compare.l != jump.offset
            or not all(isinstance(arg, (ExprId, ExprInt)) for arg in compare.args)):
        return state
    taken = static_address(jump.args[0], database, jump.offset + jump.l)
    fallthrough = jump.offset + jump.l
    if taken is None or taken == fallthrough or target not in {taken, fallthrough}:
        return state
    arguments = tuple(tracker.lifter.expr_fix_regs_for_mode(arg, 64)
                      for arg in compare.args)
    width = arguments[0].size
    if width not in {8, 16, 32, 64} or arguments[1].size != width:
        return state
    used = set().union(*(arg.get_r() for arg in arguments))
    if used - tracker.registers:
        return state
    registers = sorted(used, key=str)
    choices, combinations = [], 1
    for register in registers:
        domain = tracker.values.get(register, tracker.UNKNOWN)
        values = (None,) if domain is None else tuple(domain)
        choices.append(values)
        combinations *= len(values)
    if not combinations or combinations > tracker.MAX_COMBINATIONS:
        return state
    accepted = {register: set() for register in registers}
    feasible = False
    for values in product(*choices):
        environment = dict(zip(registers, values))
        possible = True
        if all(value is not None for value in values):
            operands = tuple(expr_simp(arg.replace_expr(environment)) for arg in arguments)
            if all(isinstance(arg, ExprInt) for arg in operands):
                possible = (_taken(operation, branch, *(int(arg) for arg in operands), width)
                            == (target == taken))
        if possible:
            feasible = True
            for register, value in environment.items():
                accepted[register].add(value)
    if not feasible:
        return None
    refined = dict(state[0])
    for register, values in accepted.items():
        if state[0].get(register, tracker.UNKNOWN) is None:
            continue
        domain = frozenset(values)
        if domain == tracker.UNKNOWN:
            refined.pop(register, None)
        else:
            refined[register] = domain
    return (refined, *state[1:])
