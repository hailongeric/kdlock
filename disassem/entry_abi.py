"""Prove that a minimal entry never observes an uncaptured GPR value.

This is a separate definite-value check, not a replacement for context admission.
Undefined bits may be overwritten or copied through scratch registers, but may
not affect memory, control flow, or lock arguments. Partial writes retain their
undefined high bits. CALL continuations follow the actual caller contract.
"""
from collections import deque

from miasm.expression.expression import ExprCompose, ExprCond, ExprId, ExprInt, ExprLoc, ExprMem, ExprOp, ExprSlice
from miasm.expression.simplifications import expr_simp

from context_policy import FlowConstants, ContextFlowLimit, static_address

GPRS = {"RAX", "RBX", "RCX", "RDX", "RSI", "RDI", "RBP", "RSP"} | {f"R{i}" for i in range(8, 16)}
PRESERVED = {"RBX", "RBP", "RSP", "R12", "R13", "R14", "R15"}
MASK = (1 << 64) - 1


def merge(left, right):
    return {key: left.get(key, 0) | right.get(key, 0) for key in left.keys() | right.keys()}


def check_minimal_entry(blocks, databases, entry, clobber_targets, lock_targets, jump_table,
                        *, abi=2, cookie_targets=frozenset()):
    """Return a refusal reason, or None after bounded conservative propagation."""
    tracker = FlowConstants()
    defined = PRESERVED | {"RAX"} if abi == 4 else {"RSP", "RBP"}
    incoming = {entry: {ExprId(name, 64): MASK for name in GPRS - defined}}
    pending = deque([entry])
    work = 0

    def taint(expr, state):
        # The lifter may allocate a fallthrough LocKey that equals the input
        # decoder's branch key. Inspect conditions before simplification so a
        # coincident key cannot erase a real dependency on uncaptured flags.
        if isinstance(expr, ExprCond) and taint(expr.cond, state):
            return (1 << expr.size) - 1
        expr = expr_simp(expr)
        if isinstance(expr, ExprId):
            return state.get(expr, 0)
        if isinstance(expr, (ExprInt, ExprLoc)):
            return 0
        if isinstance(expr, ExprMem):
            if taint(expr.ptr, state):
                raise ValueError("memory address depends on an uncaptured GPR")
            return 0
        if isinstance(expr, ExprSlice):
            return (taint(expr.arg, state) >> expr.start) & ((1 << expr.size) - 1)
        if isinstance(expr, ExprCompose):
            mask, shift = 0, 0
            for arg in expr.args:
                mask |= taint(arg, state) << shift
                shift += arg.size
            return mask
        if isinstance(expr, ExprCond):
            if taint(expr.cond, state):
                return (1 << expr.size) - 1
            return taint(expr.src1, state) | taint(expr.src2, state)
        if isinstance(expr, ExprOp):
            masks = [taint(arg, state) for arg in expr.args]
            # The x86 lifter uses extensions for 32-bit GPR writes (including
            # CMOV) and MOVZX/MOVSX. Extension preserves low-bit dependencies;
            # it cannot taint an already-defined low byte merely because some
            # other source bits were not captured by the minimal entry ABI.
            if len(expr.args) == 1 and expr.size >= expr.args[0].size:
                source_bits = expr.args[0].size
                source_mask = (1 << source_bits) - 1
                if expr.op == f"zeroExt_{expr.size}":
                    return masks[0] & source_mask
                if expr.op == f"signExt_{expr.size}":
                    high = ((1 << expr.size) - 1) ^ source_mask
                    return (masks[0] & source_mask) | (
                        high if masks[0] & (1 << (source_bits - 1)) else 0)
            if expr.op in {"&", "|", "^"}:
                result = 0
                for mask in masks:
                    result |= mask
                if expr.op == "&":
                    for arg in expr.args:
                        if isinstance(arg, ExprInt):
                            result &= int(arg)
                elif expr.op == "|":
                    for arg in expr.args:
                        if isinstance(arg, ExprInt):
                            result &= ~int(arg)
                return result
            if expr.op in {"<<", ">>"} and isinstance(expr.args[1], ExprInt):
                shift = int(expr.args[1])
                return ((masks[0] << shift) if expr.op == "<<" else (masks[0] >> shift)) & ((1 << expr.size) - 1)
            return (1 << expr.size) - 1 if any(masks) else 0
        raise ValueError(f"unsupported entry-value expression {type(expr).__name__}")

    def assignments_step(assignments, state):
        after = dict(state)
        for destination, source in assignments.items():
            mask = taint(source, state)
            if isinstance(destination, ExprMem):
                if taint(destination.ptr, state) or mask:
                    raise ValueError("memory store depends on an uncaptured GPR")
            elif str(destination) in {"RIP", "IRDst"}:
                if mask:
                    raise ValueError("control flow depends on an uncaptured GPR")
            else:
                after[destination] = mask
        return after

    def step(line, state):
        plan = tracker.instruction_plan(line)
        if plan is None:
            raise ValueError("instruction has no entry-value proof")
        first, graph, _ = plan
        if graph is None:
            return assignments_step(first, state)
        states, todo, result = {tracker.location: state}, deque([tracker.location]), None
        visits = 0
        while todo:
            key = todo.popleft()
            visits += 1
            if visits > 1024:
                raise ValueError("instruction entry-value proof exceeds budget")
            block, successors = graph[key]
            out = states[key]
            for assignments in block:
                out = assignments_step(assignments, out)
            # A conditional IR edge can carry tainted flags despite a constant
            # destination in each arm; include the original branch expression.
            if taint(block.dst, out):
                raise ValueError("conditional instruction uses an uncaptured GPR")
            for target in successors:
                if target is None:
                    result = out if result is None else merge(result, out)
                else:
                    updated = out if target not in states else merge(states[target], out)
                    if target not in states or updated != states[target]:
                        states[target] = updated
                        todo.append(target)
        return result

    def enqueue(target, state):
        if target not in blocks:
            return
        joined = state if target not in incoming else merge(incoming[target], state)
        if target not in incoming or joined != incoming[target]:
            incoming[target] = joined
            pending.append(target)

    try:
        while pending:
            start = pending.popleft()
            state = dict(incoming[start])
            block = blocks[start]
            edges = {databases[block].get_location_offset(edge.loc_key) for edge in block.bto}
            for line in block.lines:
                work += 1
                if work > 65536:
                    raise ValueError("entry-value CFG proof exceeds budget")
                target = static_address(line.args[0], databases[block], line.offset + line.l) if line.args else None
                before = state
                if line.name.upper() == "CALL" and target in lock_targets:
                    required = {"RDI"} | ({"RSI", "RDX", "RCX"} if target in clobber_targets else set())
                    if target in cookie_targets:
                        required.add("RSI")
                    if any(state.get(ExprId(reg, 64), 0) for reg in required):
                        raise ValueError("lock metadata depends on an uncaptured GPR")
                state = step(line, state)
                if line.name.upper() == "CALL":
                    enqueue(target, state)
                    edges.discard(target)
                    edges.add(line.offset + line.l)
                    # A native ABI return defines its volatile values; they are
                    # unspecified but captured on subsequent full exits. Only
                    # the new lock contract discards all GPR entry facts.
                    saved = {"RBP", "RSP"} if target in clobber_targets else PRESERVED
                    state = {ExprId(reg, 64): before.get(ExprId(reg, 64), 0) for reg in saved}
                    if target in clobber_targets:
                        state.update({ExprId(reg, 64): MASK for reg in GPRS - saved})
                elif line.name.upper() == "RET":
                    edges.update(jump_table.get(line.offset + line.l, ()))
            for edge in edges:
                enqueue(edge, state)
    except (ValueError, ContextFlowLimit) as error:
        return f"minimal entry unavailable at 0x{line.offset:x}: {error}"
    return None
