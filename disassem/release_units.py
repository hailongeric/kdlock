"""Select one translated unit, ending at every declared release operation.

This is source reachability, not acquisition/release pairing. The runtime
executes the release and uses its exact owner records to finish or continue
at the saved Native instruction under any remaining owners.
"""

from collections import defaultdict, deque
from copy import copy

from context_values import ContextFlowLimit, static_address
from miasm.expression.expression import ExprInt, ExprLoc


def select(blocks, databases, roots, resumable_targets, *, release_targets,
           indirect_history=(), deferred_call_targets=(), nonreturning_targets=(),
           indirect_call_native=False, returning_indirect=False, max_visits=65536):
    roots, resumable = set(roots), set(resumable_targets)
    releases, deferred = set(release_targets), set(deferred_call_targets)
    terminals = releases | set(nonreturning_targets)
    history = dict(indirect_history)
    if roots - blocks.keys() or (blocks and not roots):
        raise ContextFlowLimit("missing or invalid release-unit roots")
    work = 0

    def spend(offset, amount=1):
        nonlocal work
        work += amount
        if work > max_visits:
            raise ContextFlowLimit("release-unit reachability exceeds its work budget", offset)

    # Build private summaries first. A budget refusal must not trim the caller's
    # blocks or leave a partially selected graph visible to another phase.
    successors, calls, lengths, native_exits, clauses = {}, {}, {}, set(), {}
    for start, block in sorted(blocks.items()):
        db = databases.get(block)
        if db is None:
            raise ContextFlowLimit("missing release-unit location database", start)
        edges = {db.get_location_offset(edge.loc_key) for edge in block.bto}
        call, terminal, returns = None, False, False
        for index, line in enumerate(block.lines):
            spend(line.offset)
            name, next_ip = line.name.upper(), line.offset + line.l
            direct = bool(line.args) and isinstance(line.args[0], (ExprLoc, ExprInt))
            target = static_address(line.args[0], db, next_ip) if direct else None
            if name in {"CALL", "JMP"} and direct and target in terminals:
                # Keep the original instruction and CALL word. Its service
                # performs the actual operation before runtime continuation.
                lengths[start], edges, terminal = index + 1, set(), True
                break
            if name == "RET":
                returns = True
                edges.update(history.get(next_ip, ()))
            elif name.startswith("J"):
                edges.update(history.get(next_ip, ()))
            if name != "CALL":
                continue
            if index != len(block.lines) - 1:
                raise ContextFlowLimit("release-unit CALL is not a block terminator", line.offset)
            if direct and target is None:
                raise ContextFlowLimit("unresolved release-unit CALL target", line.offset)
            if direct:
                edges.discard(target)
                if target in blocks:
                    call = ({target}, next_ip, False)
                elif target in resumable and target not in deferred:
                    call = (set(), next_ip, True)
                else:
                    # A deferred callee needs its own bytes before its return
                    # can select/fetch the caller's continuation. A permanent
                    # Native callee already owns that unexecuted suffix.
                    native_exits.add(start)
                    lengths[start], edges, terminal = index + 1, set(), True
                    break
            else:
                known = set(history.get(next_ip, ()))
                callees = (known & blocks.keys()) - terminals
                native_returns = bool(known & (resumable - terminals - deferred - blocks.keys()))
                native_returns = native_returns or returning_indirect
                if not callees and not native_returns:
                    native_exits.add(start)
                    lengths[start], edges, terminal = index + 1, set(), True
                    break
                # A known ordinary target needs its own release-free return
                # path, just like a direct callee. Only the declared returning
                # Native contract can independently justify a successor; an
                # unknown fresh Native CALL owns the remaining invocation.
                call = (callees, next_ip, native_returns)
                edges.update(callees)
            edges.discard(next_ip)
        edges.intersection_update(blocks)
        successors[start] = edges
        if call is not None:
            calls[start] = call
        if terminal:
            clauses[start] = []
        elif returns:
            clauses[start] = [set()]
        elif call is not None:
            callees, continuation, native_returns = call
            clauses[start] = ([{continuation, target} for target in callees]
                              if continuation in blocks else [])
            if native_returns and continuation in blocks:
                clauses[start].append({continuation})
        else:
            clauses[start] = [{target} for target in edges]
            # A declared returning Native tail uses the caller's real word.
            if block.lines:
                line = block.lines[-1]
                if line.name.upper() == "JMP" and line.args:
                    target = static_address(line.args[0], db, line.offset + line.l)
                    native_targets = resumable - terminals - deferred - blocks.keys()
                    indirect = not isinstance(line.args[0], (ExprLoc, ExprInt))
                    if (target in native_targets or indirect and
                            (returning_indirect or
                             set(history.get(line.offset + line.l, ())) & native_targets)):
                        clauses[start].append(set())

    # Least fixed point: a decoded callee returns to its caller only along a
    # release-free path. Cycles without such a RET never invent a continuation.
    waiting, remaining, ready = defaultdict(list), {}, deque()
    for start, alternatives in clauses.items():
        for index, dependencies in enumerate(alternatives):
            key = start, index
            remaining[key] = len(dependencies)
            if not dependencies:
                ready.append(start)
            for dependency in dependencies:
                spend(start)
                waiting[dependency].append(key)
    may_return = set()
    while ready:
        start = ready.popleft()
        if start in may_return:
            continue
        spend(start)
        may_return.add(start)
        for key in waiting[start]:
            spend(start)
            remaining[key] -= 1
            if not remaining[key]:
                ready.append(key[0])

    reached, pending = set(), list(roots)
    while pending:
        start = pending.pop()
        if start in reached:
            continue
        spend(start)
        reached.add(start)
        edges = set(successors[start])
        if start in calls:
            callees, continuation, native_returns = calls[start]
            edges.update(callees)
            if (native_returns or callees & may_return) and continuation in blocks:
                edges.add(continuation)
        pending.extend(edges - reached)

    selected, selected_dbs = {}, {}
    for start in sorted(reached):
        original = blocks[start]
        block = copy(original)
        block.lines = original.lines[:lengths.get(start, len(original.lines))]
        block.bto = {edge for edge in original.bto
                     if databases[original].get_location_offset(edge.loc_key) in reached}
        if start in lengths:
            block.bto = set()
        selected[start], selected_dbs[block] = block, databases[original]
    return selected, selected_dbs, native_exits & reached
