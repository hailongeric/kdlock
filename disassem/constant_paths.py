"""Remove only source branches proved impossible from the admitted root.

The proof tracks exact register/flag constants, never memory contents. Direct
callees inherit their actual argument facts; every CALL continuation forgets all
facts. Joins keep only identical constants. RETs conservatively reach every
original CALL continuation, including callers on otherwise unreachable paths;
no balanced-stack assumption is used. Unknown/indirect entry history disables
specialization. Ordinary instruction/context admission still checks every
remaining path, and emission uses the same rewritten graph.
"""

from collections import deque
from copy import copy

from miasm.expression.expression import ExprId, ExprInt, ExprLoc
from miasm.ir.symbexec import SymbolicExecutionEngine

from context_registers import ContextFlowLimit, static_address
from context_values import FlowConstants
import instruction_policy


GPRS = frozenset(('RAX', 'RBX', 'RCX', 'RDX', 'RSI', 'RDI', 'RSP', 'RBP',
                  *(f'R{i}' for i in range(8, 16))))
FLAG_NAMES = frozenset(('cf', 'pf', 'af', 'zf', 'nf', 'of', 'df'))
EXACT_INSTRUCTIONS = frozenset('''
    MOV MOVABS MOVZX MOVSX MOVSXD LEA XCHG
    ADD SUB CMP TEST AND OR XOR NOT INC DEC NEG
    PUSH POP LEAVE CALL RET JMP NOP ENDBR64
'''.split())


def _branch(line, state):
    """Evaluate architectural conditions, independent of lifter LocKey names."""
    name = line.name.upper()
    if instruction_policy.rejection(line):
        return None
    if name in {'JCXZ', 'JECXZ', 'JRCXZ'}:
        value = state.get(ExprId('RCX', 64))
        bits = {'JCXZ': 16, 'JECXZ': 32, 'JRCXZ': 64}[name]
        return None if value is None else int(value) & ((1 << bits) - 1) == 0
    conditions = {
        'O': ('of', lambda of: of), 'NO': ('of', lambda of: not of),
        'B': ('cf', lambda cf: cf), 'C': ('cf', lambda cf: cf),
        'NAE': ('cf', lambda cf: cf), 'NB': ('cf', lambda cf: not cf),
        'NC': ('cf', lambda cf: not cf), 'AE': ('cf', lambda cf: not cf),
        'E': ('zf', lambda zf: zf), 'Z': ('zf', lambda zf: zf),
        'NE': ('zf', lambda zf: not zf), 'NZ': ('zf', lambda zf: not zf),
        'BE': ('cf zf', lambda cf, zf: cf or zf),
        'NA': ('cf zf', lambda cf, zf: cf or zf),
        'NBE': ('cf zf', lambda cf, zf: not cf and not zf),
        'A': ('cf zf', lambda cf, zf: not cf and not zf),
        'S': ('nf', lambda nf: nf), 'NS': ('nf', lambda nf: not nf),
        'P': ('pf', lambda pf: pf), 'PE': ('pf', lambda pf: pf),
        'NP': ('pf', lambda pf: not pf), 'PO': ('pf', lambda pf: not pf),
        'L': ('nf of', lambda nf, of: nf != of),
        'NGE': ('nf of', lambda nf, of: nf != of),
        'NL': ('nf of', lambda nf, of: nf == of),
        'GE': ('nf of', lambda nf, of: nf == of),
        'LE': ('zf nf of', lambda zf, nf, of: zf or nf != of),
        'NG': ('zf nf of', lambda zf, nf, of: zf or nf != of),
        'NLE': ('zf nf of', lambda zf, nf, of: not zf and nf == of),
        'G': ('zf nf of', lambda zf, nf, of: not zf and nf == of),
    }
    item = conditions.get(name[1:]) if name.startswith('J') else None
    if item is None:
        return None
    names, evaluate = item
    values = [state.get(ExprId(flag, 1)) for flag in names.split()]
    if any(value is None for value in values):
        return None
    return bool(evaluate(*(int(value) for value in values)))


def specialize(blocks, databases, entry, *, indirect_history=None,
               max_visits=65536):
    """Return (blocks, databases, rewritten_branch_pcs); failure changes nothing.

    The caller must already enforce one logical root per execution episode.
    No initial register, flag, stack byte or helper ABI value is assumed.
    Incomplete feasible text is retained for the ordinary fetch/admission pass.
    """
    original = blocks, databases, ()
    if indirect_history or entry not in blocks:
        return original
    tracker = FlowConstants()
    continuations = set()
    intervals = []
    for block in blocks.values():
        if block not in databases:
            return original
        for line in block.lines:
            intervals.append((line.offset, line.offset + line.l))
            if line.name.upper() == 'CALL':
                continuations.add(line.offset + line.l)
            if ((line.name.upper().startswith('J') or line.name.upper() == 'CALL')
                    and (not line.args or not isinstance(line.args[0], (ExprInt, ExprLoc)))):
                return original
    # Alternate instruction streams or unsplit overlapping decoder blocks
    # cannot share one rewritten source address under different input facts.
    end = -1
    for start, stop in sorted(intervals):
        if start < end or stop <= start:
            return original
        end = stop
    continuations &= blocks.keys()

    def step(line, state):
        name = line.name.upper()
        if (name not in EXACT_INSTRUCTIONS and not name.startswith('J')):
            # Decoder/lifter support alone does not prove defined outputs.
            # MUL/DIV/bit scans/shifts can leave architectural flags or result
            # bits undefined. Do not retain stale facts across these families.
            return {}
        plan = tracker.instruction_plan(line)
        if plan is None or plan[1] is not None:
            # Unmodelled/conditional internal IR cannot supply a branch fact.
            # Forget all facts rather than hide any original source path.
            return {}
        engine = SymbolicExecutionEngine(tracker.lifter, state)
        after = dict(state)
        for destination, source in plan[0].items():
            if (not isinstance(destination, ExprId)
                    or str(destination) not in GPRS | FLAG_NAMES):
                continue
            value = engine.eval_expr(source)
            if isinstance(value, ExprInt):
                after[destination] = value
            else:
                after.pop(destination, None)
        if name in {'AND', 'OR', 'XOR', 'TEST'}:
            after.pop(ExprId('af', 1), None)
        return after

    def outgoing(start, before):
        block = blocks[start]
        if not block.lines:
            return (), None
        db = databases[block]
        edges = {db.get_location_offset(edge.loc_key) for edge in block.bto}
        state, selected = dict(before), None
        calls = []
        for index, line in enumerate(block.lines):
            name = line.name.upper()
            if name == 'CALL':
                if index != len(block.lines) - 1:
                    raise ContextFlowLimit('nonterminal CALL in constant-path proof')
                target = static_address(line.args[0], db, line.offset + line.l)
                calls = [(target, step(line, state)), (line.offset + line.l, {})]
                edges.clear()
                break
            if name == 'RET':
                # Source return slots can alias stores. Do not assume matching
                # caller/callee frames or use the callee's register facts here.
                return tuple((target, {}) for target in continuations), None
            condition = _branch(line, state)
            if condition is not None and index == len(block.lines) - 1:
                target = static_address(line.args[0], db, line.offset + line.l)
                fallthrough = line.offset + line.l
                if edges == {target, fallthrough}:
                    selected = target if condition else fallthrough
                    edges = {selected}
            state = step(line, state)
        return tuple(calls) + tuple((target, state) for target in edges), selected

    try:
        incoming, pending = {entry: {}}, deque([entry])
        visits = 0
        while pending:
            start = pending.popleft()
            visits += 1
            if visits > max_visits:
                return original
            for target, state in outgoing(start, incoming[start])[0]:
                if target not in blocks:
                    continue
                previous = incoming.get(target)
                joined = (dict(state) if previous is None else
                          {reg: value for reg, value in previous.items()
                           if state.get(reg) == value})
                if previous is None or joined != previous:
                    incoming[target] = joined
                    pending.append(target)
        rewritten, result, result_dbs = [], {}, {}
        for start in sorted(incoming):
            block = blocks[start]
            _, selected = outgoing(start, incoming[start])
            if selected is not None:
                # Replace the proved conditional with its sole feasible edge;
                # source offsets/lengths remain the original instruction's.
                replacement = copy(block.lines[-1])
                replacement.name = 'JMP'
                db = databases[block]
                replacement.args = [ExprLoc(db.get_or_create_offset_location(selected), 64)]
                changed = copy(block)
                changed.lines = block.lines[:-1] + [replacement]
                changed.bto = {edge for edge in block.bto
                               if db.get_location_offset(edge.loc_key) == selected}
                rewritten.append(block.lines[-1].offset)
                result[start] = changed
                result_dbs[changed] = db
            else:
                result[start] = block
                result_dbs[block] = databases[block]
        # Reachability alone is not a reason to remove independently learned
        # text: apply this pass only when at least one source branch was proved.
        return (result, result_dbs, tuple(rewritten)) if rewritten else original
    except (ContextFlowLimit, KeyError, TypeError, ValueError):
        return original
