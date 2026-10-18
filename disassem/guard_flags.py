"""Prove that a guarded source boundary has no live arithmetic-flag input.

A progressed spin address guard cannot use the mutex flags-restoration contract.
Its comparisons and waiter restoration may replace CF/PF/AF/ZF/SF/OF. Check the
original source instructions, never generated guard/dispatch instructions: every
path must overwrite each affected flag before reading it, or reach an explicit
terminal clobber CALL. CALL itself does not define flags. Missing helper text,
unknown control flow, unsupported IR and nonconverging proofs fail closed.
"""

from collections import defaultdict, deque

from miasm.expression.expression import ExprId, ExprMem

from context_registers import ContextFlowLimit, static_address
from context_values import FlowConstants
import indirect_jump
from native_escape import ARITHMETIC_FLAGS


FLAGS = frozenset(ExprId(name, 1) for name in ARITHMETIC_FLAGS)


class FlagProofError(ValueError):
    pass


def prove_flags_dead(blocks, databases, source_ip, *, terminal_calls=(), flag_dead_calls=(),
                     max_visits=65536):
    """Return None on proof, otherwise a refusal reason for this exact PC.

    ``terminal_calls`` must contain only selected outer clobber-unlock endpoints
    whose caller contract discards condition flags. Ordinary and nested CALLs
    are not terminal merely because their C ABI does not return flags.
    ``flag_dead_calls`` contains only exact original helpers independently
    proved to overwrite incoming flags before any possible observation.
    """
    tracker = FlowConstants()
    instructions = {}
    terminal_calls = frozenset(terminal_calls)
    flag_dead_calls = frozenset(flag_dead_calls)
    work = 0

    def spend():
        nonlocal work
        work += 1
        if work > max_visits:
            raise FlagProofError("flag-dead proof exceeds its work budget")

    def reads(expression, dirty):
        used = expression.get_r(mem_read=True) & dirty
        if used:
            raise FlagProofError("source reads incoming arithmetic flags: "
                                 + ",".join(sorted(map(str, used))))

    def assignments_step(assignments, dirty):
        # An IR assignment block is parallel: inspect every source before
        # removing flags defined by this block. A memory destination also reads
        # its address, unlike a plain flag/register destination.
        for destination, source in assignments.items():
            reads(source, dirty)
            if isinstance(destination, ExprMem):
                reads(destination.ptr, dirty)
        return dirty.difference(assignments)

    def instruction_step(line, dirty):
        plan = tracker.instruction_plan(line)
        if plan is None:
            raise FlagProofError("instruction has no arithmetic-flag proof")
        first, graph, _ = plan
        if graph is None:
            return assignments_step(first, dirty)
        states = {tracker.location: dirty}
        pending = deque([tracker.location])
        outputs = set()
        while pending:
            spend()
            key = pending.popleft()
            block, successors = graph[key]
            after = states[key]
            for assignments in block:
                after = assignments_step(assignments, after)
            reads(block.dst, after)
            for target in successors:
                if target is None:
                    outputs.update(after)
                    continue
                merged = states.get(target, frozenset()) | after
                if target not in states or merged != states[target]:
                    states[target] = merged
                    pending.append(target)
        return frozenset(outputs)

    try:
        intervals = []
        for start, block in blocks.items():
            if not block.lines or block not in databases:
                raise FlagProofError("incomplete source graph for flag-dead proof")
            for index, line in enumerate(block.lines):
                intervals.append((line.offset, line.offset + line.l))
                instructions[line.offset] = line, block, index
        # Distinct starting PCs can still decode overlapping byte ranges.
        # Require one instruction stream before trusting its flag definitions
        # or choosing the exact native continuation at a guarded source PC.
        end = -1
        for start, stop in sorted(intervals):
            if start < end or stop <= start:
                raise FlagProofError("overlapping source instructions in flag-dead proof")
            end = stop
        if source_ip not in instructions:
            raise FlagProofError("guard PC is not a selected source instruction")
        returns = {}
        indirect_jump.find(blocks, databases, returns, max_visits=max_visits)

        def successors(line, block, index):
            name = line.name.upper()
            db = databases[block]
            target = (static_address(line.args[0], db, line.offset + line.l)
                      if line.args else None)
            if name == "CALL":
                if (target in terminal_calls
                        and line.offset + line.l not in instructions):
                    return ()
                if target not in instructions:
                    raise FlagProofError("unproved helper CALL in flag-dead proof")
                # Include both the actual helper and its continuation. This
                # deliberately overapproximates CALL effects: a callee cannot
                # erase a flag dependency in its caller by ABI assumption.
                return target, line.offset + line.l
            if name == "RET":
                if line.args:
                    raise FlagProofError("non-plain RET in flag-dead proof")
                targets = returns.get(line.offset + line.l, ())
                if not targets:
                    raise FlagProofError("unproved return continuation in flag-dead proof")
                return targets
            if name.startswith("J") and target is None:
                raise FlagProofError("indirect control in flag-dead proof")
            if index + 1 < len(block.lines):
                return (block.lines[index + 1].offset,)
            targets = tuple(db.get_location_offset(edge.loc_key) for edge in block.bto)
            if not targets:
                raise FlagProofError("unterminated source path in flag-dead proof")
            return targets

        initial = source_ip, FLAGS
        pending = deque([initial])
        graph = {}
        while pending:
            spend()
            state = pending.popleft()
            if state in graph:
                continue
            offset, dirty = state
            if offset not in instructions:
                raise FlagProofError("missing source successor in flag-dead proof")
            line, block, index = instructions[offset]
            after = instruction_step(line, dirty)
            if (line.name.upper() == "CALL" and line.args
                    and static_address(line.args[0], databases[block], line.offset + line.l)
                    in flag_dead_calls):
                # Only independently proved original helper text can discharge
                # this dependency. An ordinary CALL/C ABI is insufficient.
                after = frozenset()
            following = (set() if not after else
                         {(target, after) for target in successors(line, block, index)})
            graph[state] = following
            pending.extend(following - graph.keys())

        # A cycle can otherwise look successful simply because no new state
        # was enqueued. Require every path to reach a proven overwrite/terminal
        # boundary; retain a conservative refusal for cycles carrying flags.
        predecessors = defaultdict(set)
        outstanding = {}
        ready = deque()
        for state, following in graph.items():
            outstanding[state] = len(following)
            if not following:
                ready.append(state)
            for successor in following:
                predecessors[successor].add(state)
        complete = set()
        while ready:
            state = ready.popleft()
            complete.add(state)
            for parent in predecessors[state]:
                outstanding[parent] -= 1
                if not outstanding[parent]:
                    ready.append(parent)
        if initial not in complete:
            raise FlagProofError("source cycle retains incoming arithmetic flags")
    except (FlagProofError, ContextFlowLimit, indirect_jump.ReturnFlowError,
            KeyError, TypeError, ValueError) as error:
        return f"flag-dead guard unavailable at 0x{source_ip:x}: {error}"
    return None
