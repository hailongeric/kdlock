"""JIT-episode reachability and whole-emission admission policy.

Symbol resolution lives in context_symbols; abstract transfer lives in
context_values. These public reexports preserve the translator-facing API.
Unknown pointers and concurrent mutation remain outside the static proof.
"""
from collections import defaultdict, deque
from copy import copy

import context_memory  # Preserve the admission API used by guard consumers.
import indirect_jump
import instruction_policy
import native_escape
from context_symbols import (
    CONTEXT_SYMBOLS, CONTROL_SYMBOLS, MAX_PERCPU_CPUS, MAX_PERCPU_STATIC_BYTES,
    ContextSymbols, is_context_symbol, load_context_symbols,
    load_static_percpu_ranges, resolve_control_symbols,
)
from context_values import (
    ContextFlowLimit, FlowConstants, RegisterConstants, context_reference,
    known_bits, static_address,
)
from miasm.expression.expression import ExprId, ExprInt, ExprLoc, ExprMem, ExprOp
from miasm.ir.ir import IRBlock
from miasm_compat import expr_args, expr_op, expr_ptr

NATIVE_ONLY_EXIT = 2
MAX_LOCK_DEPTH = 8
IMPLICIT_SOURCE_MEMORY = {
    "MOVSB",
    "MOVSW",
    "MOVSD",
    "MOVSQ",
    "LODSB",
    "LODSW",
    "LODSD",
    "LODSQ",
    "CMPSB",
    "CMPSW",
    "CMPSD",
    "CMPSQ",
    "OUTSB",
    "OUTSW",
    "OUTSD",
    "XLAT",
    "XLATB",
}


def jit_phase_blocks(blocks, databases, roots, resumable_targets):
    """Select code that can execute before this JIT episode ends.

    A missing direct callee transfers the saved CALL state to the original
    waiter permanently for this episode. Lock controls and allowlisted hostcalls
    resume JIT; decoded callees and indirect calls retain conservative return
    edges. Recompute this scope on every translation, including learned targets.
    """
    roots = set(roots)
    if roots - blocks.keys() or (blocks and not roots):
        raise ContextFlowLimit("missing or invalid JIT phase roots")
    successors, exits = {}, set()
    for start, block in blocks.items():
        db = databases.get(block)
        if db is None:
            raise ContextFlowLimit("missing JIT phase location database", start)
        targets = {db.get_location_offset(edge.loc_key) for edge in block.bto}
        for index, line in enumerate(block.lines):
            if line.name.upper() != "CALL" or not line.args:
                continue
            target = static_address(line.args[0], db, line.offset + line.l)
            direct = isinstance(line.args[0], (ExprLoc, ExprInt))
            if direct and target is None:
                raise ContextFlowLimit("unresolved direct CALL target", line.offset)
            if direct and target not in blocks and target not in resumable_targets:
                if index != len(block.lines) - 1:
                    raise ContextFlowLimit(
                        "native CALL is not a block terminator", line.offset
                    )
                exits.add(start)
                targets.clear()
                break
            targets.add(line.offset + line.l)
            if target in blocks:
                targets.add(target)
        successors[start] = targets & blocks.keys()
    reached, pending = set(), sorted(roots)
    while pending:
        start = pending.pop()
        if start in reached:
            continue
        reached.add(start)
        pending.extend(successors[start] - reached)
    selected, selected_dbs = {}, {}
    for start in sorted(reached):
        original = block = blocks[start]
        if start in exits:
            # Keep a suffix reached by another JIT branch, but remove this
            # native-only edge so its clobbered state cannot reenter analysis.
            block = copy(block)
            block.bto = set()
        selected[start] = block
        selected_dbs[block] = databases[original]
    return selected, selected_dbs, exits & reached


def call_return_edges(blocks, successors, calls, max_visits):
    """Associate decoded RETs with all possible direct-call continuations.

    Follow each callee's ordinary CFG, including nested CALL fall-through but
    not the nested callee edge. Shared tails/recursion may join callers; this
    is a conservative effect flow, not a balanced-stack or termination proof.
    """
    callers = defaultdict(set)
    for edges in calls.values():
        for _, callee, continuation in edges:
            if continuation in blocks:
                callers[callee].add(continuation)
    returns = defaultdict(set)
    visits = 0
    for callee, continuations in sorted(callers.items()):
        pending = [callee]
        seen = set()
        while pending:
            start = pending.pop()
            if start in seen:
                continue
            seen.add(start)
            visits += 1
            lines = blocks[start].lines
            is_return = bool(lines) and lines[-1].name.upper() == "RET"
            if is_return:
                visits += len(continuations)
            if visits > max_visits:
                raise ContextFlowLimit(
                    "CALL/RET CFG analysis exceeds its work budget", start
                )
            if is_return:
                returns[start].update(continuations)
            else:
                pending.extend(sorted(successors[start] - seen, reverse=True))
    return returns


def constant_blocks(
    blocks,
    databases,
    max_visits=65536,
    *,
    roots=None,
    control_targets=(),
    clobber_targets=(),
    readonly_targets=(),
    mutex_targets=(),
    mutex_stack_bytes=0,
    native_exits=(),
    guards=None,
    scoped_calls=False,
    entry_spill_guards=False,
):
    """Seed real entries, then propagate to previously unvisited successors.

    By default callees retain independent unknown inputs plus direct-call inputs.
    The guarded single-entry alternative propagates only real CALL/RET effects;
    its return edges must also match emission before the image can be published.
    """
    strict_roots = roots is not None
    roots = set(blocks if roots is None else roots)
    if roots - blocks.keys() or (blocks and not roots):
        raise ContextFlowLimit("missing or invalid CFG analysis roots")
    # An entry predicate describes one saved register packet. Independently
    # seeded/learned callees need their own admission contract, not these bases.
    if guards is not None and (not strict_roots or len(roots) != 1):
        raise ContextFlowLimit("entry guards require one explicit CFG root")
    if scoped_calls and guards is None:
        raise ContextFlowLimit("scoped CALL analysis requires entry predicates")
    successors = {}
    calls = defaultdict(list)
    callees = set()
    control_calls = set()
    clobber_calls = set()
    readonly_calls = set()
    mutex_calls = set()
    for start, block in blocks.items():
        db = databases.get(block)
        if db is None:
            if strict_roots:
                raise ContextFlowLimit("missing CFG location database", start)
            successors[start] = set()
            continue
        targets = {db.get_location_offset(edge.loc_key) for edge in block.bto}
        offset = start
        for index, line in enumerate(block.lines):
            offset += line.l
            if scoped_calls:
                # An indirect target may enter with another packet. Do not let
                # it inherit one root's predicates or assume a balanced return.
                name = line.name.upper()
                if (name.startswith("J") or name == "CALL") and (
                    not line.args or not isinstance(line.args[0], (ExprLoc, ExprInt))
                ):
                    raise ContextFlowLimit(
                        "scoped CALL graph has indirect control", line.offset
                    )
                if name == "RET" and line.args:
                    raise ContextFlowLimit(
                        "scoped CALL graph requires plain RET", line.offset
                    )
            if line.name.upper() != "CALL" or not line.args or start in native_exits:
                continue
            # Endpoint calls may lack a decoder edge, yet a nested unlock has
            # a selected continuation. Do not create new code beyond the scope.
            callee = static_address(line.args[0], db, offset)
            if callee in clobber_targets:
                clobber_calls.add(id(line))
            if callee in readonly_targets:
                readonly_calls.add(id(line))
            if callee in readonly_targets or ((guards is not None or callee in clobber_targets) and callee in control_targets):
                control_calls.add(id(line))
                if callee in mutex_targets:
                    mutex_calls.add(id(line))
            if callee in blocks and callee not in control_targets:
                if scoped_calls and index != len(block.lines) - 1:
                    raise ContextFlowLimit(
                        "decoded CALL is not a block terminator", line.offset
                    )
                if not scoped_calls:
                    roots.add(callee)
                callees.add(callee)
                calls[start].append((line, callee, offset))
                targets.discard(callee)
            targets.add(offset)
        successors[start] = targets & blocks.keys()
    if guards is not None and callees and not scoped_calls:
        raise ContextFlowLimit("entry guards do not cover independently seeded callees")
    returns = call_return_edges(blocks, successors, calls, max_visits)
    if scoped_calls:
        # A corrupted virtual return slot can select another caller. Keep the
        # complete emitted whitelist even when sequential memory facts later
        # prove that a particular packet cannot take some of its edges.
        emitted = {}
        try:
            indirect_jump.find(blocks, databases, emitted, max_visits=max_visits)
        except indirect_jump.ReturnFlowError as error:
            raise ContextFlowLimit(str(error), error.offset) from error
        expected = {
            block.lines[-1].offset + block.lines[-1].l: set(returns[start])
            for start, block in blocks.items()
            if block.lines and block.lines[-1].name.upper() == "RET"
        }
        if expected != {source: set(targets) for source, targets in emitted.items()}:
            raise ContextFlowLimit("scoped RET effects differ from generated dispatch")
        # RET ownership uses lexical fall-through above. Execution cannot take
        # that edge until the callee actually returns; a native miss is terminal.
        for start, edges in calls.items():
            for _, _, continuation in edges:
                successors[start].discard(continuation)
        # Reject disconnected learned text before value-based RET refinement.
        # A connected continuation may subsequently prove unreachable (e.g. a
        # callee overwrites its return slot); that is not an independent seed.
        reachable, todo = set(), list(roots)
        work = 0
        while todo:
            start = todo.pop()
            if start in reachable:
                continue
            reachable.add(start)
            edges = (
                successors[start]
                | returns[start]
                | {callee for _, callee, _ in calls[start]}
            )
            work += len(edges) + 1
            if work > max_visits:
                raise ContextFlowLimit(
                    "scoped reachability exceeds its work budget", start
                )
            todo.extend(sorted(edges - reachable, reverse=True))
        if blocks.keys() - reachable:
            raise ContextFlowLimit(
                "unreached selected CFG blocks", min(blocks.keys() - reachable)
            )
    tracker = FlowConstants(
        guards, scoped_calls=scoped_calls, mutex_stack_bytes=mutex_stack_bytes,
        entry_spill_guards=entry_spill_guards,
    )
    tracker.control_calls = control_calls
    tracker.clobber_calls = clobber_calls
    tracker.readonly_calls = readonly_calls
    tracker.mutex_calls = mutex_calls
    initial = tracker.snapshot()

    def state_key(start, state, *, unknown_return=False):
        # This is a bounded disjunction of proven RSP facts, not a shadow call
        # stack. Rewritten returns and arbitrary RSP changes remain real data.
        # Joining different depths at a shared thunk would erase the relation
        # between its return slot, saved registers and caller continuation.
        # An unknown RET can form cycles through every whitelisted caller.
        # Merge those destinations normally instead of allocating a partition
        # for each hypothetical pop depth. Keep all register/memory values in
        # the merge; this changes precision, not possible targets or effects.
        if not scoped_calls or unknown_return:
            return start, None, None
        stack = ExprId("RSP", 64)
        return start, state[0].get(stack, tracker.UNKNOWN), state[1].get(stack)

    # Independently learned callee inputs are not equal to the caller's entry
    # register identities. Numeric alternatives from real CALL edges still join.
    incoming, partitions = {}, defaultdict(set)
    for start in sorted(roots):
        state = (
            dict(initial[0]),
            {} if start in callees and not scoped_calls else dict(initial[1]),
            initial[2],
            initial[3],
            initial[4],
        )
        key = state_key(start, state)
        incoming[key] = state
        partitions[start].add(key)
    pending = deque(incoming)
    queued = set(pending)
    seen = set()
    visits = 0
    while pending:
        key = pending.popleft()
        queued.remove(key)
        start = key[0]
        visits += 1
        if visits > max_visits:
            raise ContextFlowLimit(
                "register-address CFG analysis exceeds its work budget", start
            )
        block = blocks[start]
        tracker.restore(incoming[key])
        tracker.call_entries.clear()
        tracker.return_targets.clear()
        seen.add(start)
        yield start, block, tracker
        return_edges = returns[start]
        possible = None
        if scoped_calls and block.lines:
            possible = tracker.return_targets.get(id(block.lines[-1]))
            if possible is not None:
                return_edges = return_edges & possible
        outgoing = [
            (target, tracker.snapshot())
            for target in sorted(successors[start] | return_edges)
        ]
        for line, callee, _ in calls[start]:
            state = tracker.call_entries.get(id(line))
            if state is None:
                raise ContextFlowLimit("missing decoded CALL input state", start, line)
            outgoing.append((callee, state))
        for target, state in outgoing:
            key = state_key(
                target,
                state,
                unknown_return=possible is None and target in return_edges,
            )
            merged = (
                state
                if key not in incoming
                else tracker.merge_state(incoming[key], state)
            )
            if key in incoming and merged == incoming[key]:
                continue
            if key not in incoming:
                if scoped_calls and (
                    len(partitions[target]) >= tracker.MAX_STACK_PARTITIONS
                    or len(incoming) >= max_visits
                ):
                    raise ContextFlowLimit(
                        "register-address CFG partitions exceed their work budget",
                        target,
                    )
                partitions[target].add(key)
            incoming[key] = merged
            if key not in queued:
                pending.append(key)
                queued.add(key)
    unreached = blocks.keys() - seen
    if unreached and not scoped_calls:
        raise ContextFlowLimit("unreached selected CFG blocks", min(unreached))
    if guards is not None:
        # Earlier propagation may already rely on collected separations. A
        # successful policy result therefore requires the entire guard set to
        # fit, even if a caller never reaches the assembly emitter.
        try:
            guards.conditions()
        except ValueError as error:
            raise ContextFlowLimit(str(error)) from error


def instruction_rejection(
    line, offset, db, symbols, lock_kind=None, lock_symbols=None, constants=None,
    *, native_escapes=False,
):
    """Return (reason, symbol) before any stateful instruction reaches lowering."""
    reason = instruction_policy.rejection(line)
    if reason and not (native_escapes and native_escape.descriptor(line)):
        return reason, ""
    if line.name.upper() == "NOP":
        return None
    # miasm exposes no operands for string/XLAT instructions. Their segment
    # override is still real memory access and must not bypass admission.
    if line.name.upper() in IMPLICIT_SOURCE_MEMORY:
        for byte in bytes(getattr(line, "b", b"")):
            if byte in {0x64, 0x65}:
                return "implicit FS/GS memory access requires native context", ""
            if (
                byte not in {0x26, 0x2E, 0x36, 0x3E, 0x66, 0x67, 0xF0, 0xF2, 0xF3}
                and not 0x40 <= byte <= 0x4F
            ):
                break
    # Covers direct calls/tail calls and statically addressed context data.
    # Register-derived pointers and unresolved indirect calls are not proven safe.
    for arg in line.args:
        expr = expr_ptr(arg) if isinstance(arg, ExprMem) else arg
        expressions = (expr,)
        if constants and (
            isinstance(arg, ExprMem)
            or (
                line.name.upper() in {"CALL", "JMP"}
                and isinstance(arg, (ExprId, ExprOp))
            )
        ):
            # A destination GPR is not an address read. Substitute only memory
            # pointers and indirect control targets, never arbitrary operands.
            try:
                # LEA has no memory effect. Keep known-symbol checks, but let
                # widened arithmetic propagate until an actual address use.
                expressions = constants.resolve_many(
                    expr, allow_wide=line.name.upper() == "LEA"
                )
            except ContextFlowLimit as error:
                error.report(offset, line)
                return str(error), ""
        # LEA only forms an address; MOVZX's source width is not its destination's.
        size = (
            (arg.size + 7) // 8
            if isinstance(arg, ExprMem) and line.name.upper() != "LEA"
            else 1
        )
        for expr in expressions:
            address = static_address(expr, db, offset + line.l)
            # Include address-taking and tail calls: neither can hide a known
            # foreign backend behind an ordinary CALL-miss continuation.
            if lock_symbols and address in lock_symbols:
                kind, name = lock_symbols[address]
                # Its C result is meaningful only before its synthetic root
                # continuation; the nested void-control model cannot supply it.
                if name == "kd_mutex_outer_contended_clobber_v1":
                    return "outer-only mutex entry requires native execution", name
                if kind != lock_kind:
                    return (
                        f"{kind} lock reference in {lock_kind} entry requires native execution",
                        name,
                    )
            symbol = context_reference(expr, db, offset + line.l, symbols, size)
            if symbol:
                return "context-sensitive symbol requires native execution", symbol
    return None


def critical_section_blocks(
    blocks, databases, entry, locks, unlocks, extra_targets, *, native_exits=()
):
    """Exclude the caller's post-unlock code, but scan discovered callees in full.

    Lock depth is only a conservative lexical boundary, not an ownership proof.
    Callees and dynamically learned targets have unknown entry depth and cannot
    use an unlock to cut off their admission scan. Runtime still validates locks.
    """
    pending = deque([(entry, 1)])
    pending.extend((target, None) for target in extra_targets if target != entry)
    visited = set()
    lengths = {}
    while pending:
        start, depth = pending.popleft()
        if (start, depth) in visited or start not in blocks:
            continue
        visited.add((start, depth))
        block = blocks[start]
        db = databases[block]
        offset = start
        stopped = False
        used = 0
        for line in block.lines:
            used += 1
            next_ip = offset + line.l
            if line.name == "CALL" and line.args:
                # Native continuation owns the remaining lexical lock scope.
                # Its later unlocks cannot extend this version's JIT boundary.
                if start in native_exits:
                    stopped = True
                    break
                target = static_address(line.args[0], db, next_ip)
                if target in locks and depth is not None:
                    depth += 1
                    if depth > MAX_LOCK_DEPTH:
                        return blocks, (
                            offset,
                            "unbounded or excessive lexical lock nesting",
                        )
                elif target in unlocks and depth is not None:
                    depth -= 1
                    if depth == 0:
                        stopped = True
                        break
                elif target in blocks and target not in locks | unlocks:
                    pending.append((target, None))
                pending.append((next_ip, depth))
            offset = next_ip
        lengths[start] = max(lengths.get(start, 0), used)
        if not stopped:
            pending.extend(
                (db.get_location_offset(edge.loc_key), depth) for edge in block.bto
            )

    selected = {start: blocks[start] for start in lengths}
    for start, block in selected.items():
        block.lines = block.lines[: lengths[start]]
        db = databases[block]
        block.bto = {
            edge
            for edge in block.bto
            if db.get_location_offset(edge.loc_key) in selected
        }
    return selected, None
