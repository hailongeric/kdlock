"""Bounded register/value transfer across CFG edges for context admission.

Numeric alternatives, symbolic entry identities and byte-memory facts remain
separate. Budget exhaustion refuses analysis; it must not drop an alternative.
Scalar/block-local helpers are reexported from context_registers for callers.
"""
from collections import deque
from copy import deepcopy
from itertools import product

import context_memory
import context_edges
from context_registers import (
    ContextFlowLimit, RegisterConstants, context_reference, known_bits, static_address,
)
from miasm.arch.x86.regs import all_regs_ids
from miasm.expression.expression import ExprCond, ExprId, ExprInt, ExprLoc, ExprMem
from miasm.expression.simplifications import expr_simp
from miasm.ir.ir import IRBlock
from miasm_compat import expr_ptr


class FlowConstants(RegisterConstants):
    """May-constants across CFG edges; unknown runtime values remain unknown.

    A domain is a set of constants plus an optional unknown value (None).
    A None domain is wider: a bounded analysis overflow that must not silently
    erase an address alternative. Branch conditions/flags are not assumed true.
    """

    MAX_VALUES = 64
    MAX_COMBINATIONS = 256
    MAX_IR_BLOCKS = 64
    MAX_IR_VISITS = 1024
    MAX_STACK_PARTITIONS = 64
    UNKNOWN = frozenset({None})

    def __init__(self, guards=None, *, scoped_calls=False, mutex_stack_bytes=0,
                 entry_spill_guards=False, address_guards=None):
        super().__init__()
        self.instruction_lifted = {}
        self.unknown = {
            reg: ExprId(f"kd_unknown_{reg}", reg.size) for reg in self.registers
        }
        self.wide = {reg: ExprId(f"kd_wide_{reg}", reg.size) for reg in self.registers}
        self.wide_ids = frozenset(self.wide.values())
        # Exact symbolic identities are separate from numeric may-constants.
        # Joining different identities forgets equality, never assumes disjointness.
        self.origins = {
            reg: ExprId(f"kd_entry_{reg}", reg.size) for reg in self.registers
        }
        self.memory = context_memory.MemoryValues(
            frozenset(self.origins.values()), guards
        )
        if entry_spill_guards:
            # Caller-owned spills add byte/alias work to the same CFG proof.
            # The measured nested register oracle needs ~1.92M operations;
            # retain a finite 4M ceiling without changing any address rule or
            # the legacy budget. An exhausted proof still refuses admission.
            self.memory.MAX_WORK *= 4
            # The two-root workload has 292 simultaneously tracked bytes once
            # scalar indices spill. Keep the byte domain bounded at 512.
            self.memory.MAX_BYTES *= 2
        self.control_calls = set()
        self.clobber_calls = set()
        self.readonly_calls = set()
        # Legacy provider/fixture compatibility only: the current coordinator
        # does not select string-service C-object/control-scratch contracts.
        # Ordinary decoded CALLs retain their complete instruction effects.
        self.audited_c_calls = set()
        # Legacy typed-writing fixtures still model a bounded RDI destination
        # and invalidate every written byte; no current callee gets this summary.
        self.writer_calls = {}
        self.mutex_calls = set()
        self.mutex_stack_bytes = mutex_stack_bytes
        self.call_entries = {}
        self.scoped_calls = scoped_calls
        self.return_targets = {}
        self.entry_spill_guards = entry_spill_guards
        self.memory.allow_checked_entry_spills = entry_spill_guards
        self.current_line = None
        self.address_guards = address_guards
        if address_guards is not None:
            self.memory.load_guard = lambda memory: address_guards.stack_aliases(
                self.current_line, memory, self)

    def snapshot(self):
        return (dict(self.values), dict(self.origins), self.memory.snapshot(),
                self.memory.entry_spills_blocked, self.memory.checked_spill_windows)

    def restore(self, state):
        self.values, self.origins = dict(state[0]), dict(state[1])
        self.memory.restore(state[2])
        self.memory.entry_spills_blocked = state[3]
        self.memory.checked_spill_windows = state[4]

    def successor_state(self, block, database, target):
        # Scoped CALL analysis has one actual source packet and preserves the
        # decoded CALL/RET effects. Refine only its ordinary numeric branch
        # alternatives; independent callee roots retain their existing policy.
        if self.scoped_calls:
            return context_edges.refine(self, block, database, target)
        return self.snapshot()

    def merge_state(self, left, right):
        values = self.merge(left[0], right[0])
        origins = {
            reg: origin
            for reg, origin in left[1].items()
            if right[1].get(reg) == origin
        }
        windows = left[4] | right[4]
        blocked = left[3] or right[3] or len(windows) > 64
        return (
            values,
            origins,
            self.memory.merge(left[2], right[2]),
            blocked,
            frozenset() if blocked else windows,
        )

    def clobber(self, *, checked_windows=(), window_bytes=0):
        self.values.clear()
        self.origins.clear()
        self.memory.clobber(checked_windows=checked_windows, window_bytes=window_bytes)

    def wide_dependency(self, value):
        return bool(
            value.get_r(mem_read=True) & self.wide_ids
        ) or context_memory.is_wide(value)

    def finite_values(self, value):
        # Masked array indices can be finite even after a memory domain widens.
        # Enumerate a superset of all possible results; no branch is selected.
        zero, one = known_bits(value)
        unknown = ((1 << value.size) - 1) & ~(zero | one)
        if (1 << unknown.bit_count()) > self.MAX_VALUES:
            return (value,)
        values = [one]
        while unknown:
            bit = unknown & -unknown
            values += [candidate | bit for candidate in values]
            unknown ^= bit
        return tuple(ExprInt(candidate, value.size) for candidate in values)

    def join(self, left, right):
        if left is None or right is None:
            return None
        merged = left | right
        return merged if len(merged) <= self.MAX_VALUES else None

    def merge(self, left, right):
        result = {}
        for reg in left.keys() | right.keys():
            domain = self.join(
                left.get(reg, self.UNKNOWN), right.get(reg, self.UNKNOWN)
            )
            if domain != self.UNKNOWN:
                result[reg] = domain
        return result

    def environments(self, expressions, registers=None):
        tracked = self.registers if registers is None else registers
        used = set()
        for expr in expressions:
            used.update(expr.get_r(mem_read=True) & tracked)
        registers = sorted(used, key=str)
        choices = []
        combinations = 1
        for reg in registers:
            domain = self.values.get(reg, self.UNKNOWN)
            values = (
                (self.wide[reg],)
                if domain is None
                else tuple(
                    self.origins.get(reg, self.unknown[reg]) if value is None else value
                    for value in sorted(
                        domain, key=lambda value: -1 if value is None else int(value)
                    )
                )
            )
            choices.append(values)
            combinations *= len(values)
        if combinations > self.MAX_COMBINATIONS:
            choices = [
                (self.wide[reg],) if len(values) > 1 else values
                for reg, values in zip(registers, choices)
            ]
        for values in product(*choices):
            yield dict(zip(registers, values))

    def resolve_many(self, expr, registers=None, *, allow_wide=False):
        try:
            return self._resolve_many(expr, registers, allow_wide=allow_wide)
        except context_memory.AuditedScratchAccess as error:
            line = self.current_line
            raise ContextFlowLimit(str(error), getattr(line, "offset", 0), line) from error

    def _resolve_many(self, expr, registers=None, *, allow_wide=False):
        expr = self.lifter.expr_fix_regs_for_mode(expr, 64)
        results = set()
        for values in self.environments((expr,), registers):
            for value in context_memory.evaluate(
                self.lifter, expr, values, self.memory
            ):
                for candidate in self.finite_values(value):
                    if self.wide_dependency(candidate) and not allow_wide:
                        raise ContextFlowLimit(
                            "bounded register-address alternatives require native execution "
                            "(including memory-forwarded values)",
                            diagnostic_fields=self.address_failure_details(
                                expr, candidate, values
                            ),
                        )
                    results.add(candidate)
        return sorted(results, key=str)

    def address_failure_details(self, expression, candidate, values):
        # Observe only the failed environment; do not re-evaluate IR or spend
        # analysis budget. Bound text independently of the admission limits.
        def describe(value):
            text = str(value)
            return text if len(text) <= 240 else text[:237] + "..."

        return {
            "address_expression": describe(expression),
            "address_candidate": describe(candidate),
            "register_inputs": {
                str(reg): describe(value)
                for reg, value in sorted(values.items(), key=lambda item: str(item[0]))
            },
            "wide_registers": sorted(
                str(reg) for reg, value in values.items() if self.wide_dependency(value)
            ),
            "memory_cells": len(self.memory.cells),
            "memory_wide_cells": sum(
                domain is None for domain in self.memory.cells.values()
            ),
            "memory_words": len(self.memory.words),
            "memory_default_wide": self.memory.default is None,
            "analysis_work": self.memory.work,
            "analysis_work_limit": self.memory.MAX_WORK,
            "analysis_work_exceeded": self.memory.work > self.memory.MAX_WORK,
        }

    def update(self, line, symbols=None):
        try:
            return self._update(line, symbols)
        except context_memory.AuditedScratchAccess as error:
            raise ContextFlowLimit(str(error), line.offset, line) from error

    def _update(self, line, symbols=None):
        self.current_line = line
        if id(line) not in self.control_calls:
            return self.update_effects(line, symbols)
        # Model the original lock CALL boundary, not an arbitrary native C
        # callee. The handler consumes the CALL stack and keeps saved GPRs;
        # a remote child executes the selected original successor instructions.
        saved = {
            ExprId(name, 64)
            for name in ("RBX", "RBP", "RSP", "R12", "R13", "R14", "R15")
        }
        if id(line) in self.clobber_calls:
            saved = {ExprId(name, 64) for name in ("RBP", "RSP")}
        # Mutex keeps its checked-stack/opaque-memory effect: native mutex
        # acquisition can write much more than a 32-bit spin word. Its new
        # ABI drops register facts without weakening that memory contract.
        # The versioned spin control handler changes its lock word and consumes
        # the virtual CALL, without running an opaque callee on the logical
        # stack. Model those writes through the existing alias/guard rules.
        # In particular, a lock may alias a saved pointer; do not preserve that
        # pointer just because the caller ABI spills it to memory.
        lock_pointers = (
            frozenset(self.resolve_many(ExprId("RDI", 64), allow_wide=True))
            if id(line) in self.clobber_calls and id(line) not in self.mutex_calls else None
        )
        writer_bytes = self.writer_calls.get(id(line), 0)
        writer_pointers = (
            frozenset(self.resolve_many(ExprId("RDI", 64), allow_wide=True))
            if writer_bytes else None
        )
        values, origins = dict(self.values), dict(self.origins)
        self.update_effects(
            line, symbols, checked_mutex_stack=id(line) in self.mutex_calls,
            clobber_lock=lock_pointers,
            readonly_call=id(line) in self.readonly_calls,
            audited_call=id(line) in self.audited_c_calls,
            writer_pointers=writer_pointers, writer_bytes=writer_bytes,
        )
        for reg in saved:
            for output, before in ((self.values, values), (self.origins, origins)):
                if reg in before:
                    output[reg] = before[reg]
                else:
                    output.pop(reg, None)

    def update_effects(self, line, symbols=None, *, checked_mutex_stack=False,
                       clobber_lock=None, readonly_call=False,
                       writer_pointers=None, writer_bytes=0, audited_call=False):
        plan = self.instruction_plan(line)
        if plan is None:
            self.clobber()
            return
        entry, graph, temporaries = plan
        if graph is None:
            self.check_memory(line, entry, symbols)
            if self.scoped_calls and line.name.upper() == "RET":
                # Refine only the exact 64-bit pop emitted by special_inst.
                # Read the old stack through the ordinary alias/clobber model;
                # an unknown/partial/widened value permits every RET target.
                stack = ExprId("RSP", 64)
                pc = ExprId("RIP", 64)
                returned = ExprMem(stack, 64)
                if (
                    not line.args
                    and expr_simp(entry.get(pc, pc)) == returned
                    and expr_simp(entry.get(stack, stack))
                    == expr_simp(stack + ExprInt(8, 64))
                ):
                    values = self.resolve_many(returned, allow_wide=True)
                    if values and all(isinstance(value, ExprInt) for value in values):
                        self.return_targets[id(line)] = frozenset(map(int, values))
            # Only a genuine lifted CALL may create/replace a control token.
            # Other stores retain the original conservative byte model.
            stack = ExprId("RSP", 64)
            pushed = expr_simp(stack - ExprInt(8, 64))
            call_return = (
                line.name.upper() == "CALL" and line.is_subcall()
                and expr_simp(entry.get(stack, stack)) == pushed
                and {
                    expr_simp(reg): static_address(value, self.lifter.loc_db, None)
                    for reg, value in entry.items() if isinstance(reg, ExprMem)
                } == {ExprMem(pushed, 64): line.offset + line.l}
            )
            if audited_call:
                if not call_return:
                    raise ContextFlowLimit("unrecognized audited C CALL store", line.offset, line)
                # Known caller arguments cannot name the imminent control
                # token. Ordinary unknown valid C objects use the explicit
                # caller contract; no helper or runtime memory is inspected.
                tokens = {ExprMem(pointer, 64): frozenset()
                          for pointer in self.resolve_many(pushed)}
                for name in ("RDI", "RSI"):
                    for pointer in self.resolve_many(ExprId(name, 64)):
                        extent = writer_bytes or 256
                        self.memory.check_control_access(
                            ExprMem(pointer, extent * 8))
                        self.memory.check_control_access(
                            ExprMem(pointer, extent * 8), words=tokens)
            # Lowering still writes the original return word. The audited C
            # effect keeps that word in separate exact control provenance.
            self.update_assignments(entry, call_return=call_return,
                                    audited_call=audited_call)
            if line.is_subcall():
                self.call_entries[id(line)] = self.snapshot()
                if (clobber_lock is not None or readonly_call or writer_pointers is not None) and line.name.upper() == "CALL":
                    if clobber_lock is not None:
                        self.memory.store([(clobber_lock,
                            frozenset({context_memory.wide_value(32)}), 32)])
                    if writer_pointers is not None:
                        if not 0 < writer_bytes <= 64:
                            raise ContextFlowLimit("invalid typed writer extent", line.offset)
                        # Model the real virtual CALL word first, then every
                        # destination byte. Unknown contents are ordinary data,
                        # not a reason to retain old values or drop aliases.
                        # Small chunks respect the existing memory-access bound;
                        # simultaneous writes retain every possible destination.
                        self.memory.store([
                            (frozenset(self.memory.offset(pointer, index)
                                       for pointer in writer_pointers),
                             frozenset({ExprId("kd_writer_data", min(8, writer_bytes - index) * 8)}),
                             min(8, writer_bytes - index) * 8)
                            for index in range(0, writer_bytes, 8)
                        ])
                    self.values.clear()
                    self.origins.clear()
                    return
                windows = ()
                stack = ExprId("RSP", 64)
                pushed = expr_simp(stack - ExprInt(8, 64))
                # Derive the checkpoint start from the actual post-push
                # packet, not a pre-CALL memory snapshot. A CALL write may
                # already have changed/aliased a tracked word. Unrecognized
                # IR keeps the old clobber even for a registered mutex target.
                if (
                    checked_mutex_stack
                    and self.mutex_stack_bytes
                    and line.name.upper() == "CALL"
                    and expr_simp(entry.get(stack, stack)) == pushed
                    and {
                        expr_simp(reg): static_address(value, self.lifter.loc_db, None)
                        for reg, value in entry.items()
                        if isinstance(reg, ExprMem)
                    }
                    == {ExprMem(pushed, 64): line.offset + line.l}
                ):
                    windows = self.resolve_many(stack + ExprInt(8, 64), allow_wide=True)
                self.clobber(
                    checked_windows=windows, window_bytes=self.mutex_stack_bytes
                )
            return
        for reg in temporaries:
            self.unknown[reg] = ExprId(f"kd_unknown_{reg}", reg.size)
            self.wide[reg] = ExprId(f"kd_wide_{reg}", reg.size)
        self.wide_ids = frozenset(self.wide.values())
        tracked = self.registers | temporaries
        incoming = {self.location: self.snapshot()}
        pending = deque([self.location])
        queued = {self.location}
        outgoing = None
        visits = 0
        while pending:
            key = pending.popleft()
            queued.remove(key)
            visits += 1
            if visits > self.MAX_IR_VISITS:
                raise ContextFlowLimit(
                    "instruction IR analysis exceeds its work budget", line.offset
                )
            block, successors = graph[key]
            self.restore(incoming[key])
            for assignments in block:
                self.check_memory(line, assignments, symbols, tracked)
                self.update_assignments(assignments, tracked)
            for target in successors:
                if target is None:
                    outgoing = (
                        self.snapshot()
                        if outgoing is None
                        else self.merge_state(outgoing, self.snapshot())
                    )
                    continue
                merged = (
                    self.snapshot()
                    if target not in incoming
                    else self.merge_state(incoming[target], self.snapshot())
                )
                if target in incoming and merged == incoming[target]:
                    continue
                incoming[target] = merged
                if target not in queued:
                    pending.append(target)
                    queued.add(target)
        # Instruction-local temporaries never become cross-instruction facts.
        self.restore(outgoing)
        self.values = {
            reg: v for reg, v in self.values.items() if reg in self.registers
        }
        self.origins = {
            reg: v for reg, v in self.origins.items() if reg in self.registers
        }
        if line.is_subcall():
            self.call_entries[id(line)] = self.snapshot()
            self.clobber()

    def check_memory(self, line, assignments, symbols, registers=None):
        if symbols is None and self.memory.control_words == {}:
            return
        symbols = symbols or {}
        accesses = set()
        for destination, source in assignments.items():
            # Include stores, address-dereferences and branch-condition loads,
            # not just memory on the RHS of a tracked GPR assignment.
            for expression in (destination, source):
                accesses.update(
                    value
                    for value in expression.get_r(mem_read=True)
                    if isinstance(value, ExprMem)
                )
        for memory in sorted(accesses, key=str):
            try:
                pointers = self.resolve_many(expr_ptr(memory), registers)
            except ContextFlowLimit as error:
                error.offset = line.offset
                error.instruction = line
                raise
            for pointer in pointers:
                # A genuine CALL's implicit push may replace an older token;
                # an explicit source load/store may not observe that scratch.
                pushed = expr_simp(ExprId("RSP", 64) - ExprInt(8, 64))
                implicit_call_store = (line.name.upper() == "CALL" and line.is_subcall()
                    and memory in assignments and memory.size == 64
                    and expr_simp(memory.ptr) == pushed
                    and expr_simp(assignments.get(ExprId("RSP", 64), ExprId("RSP", 64))) == pushed
                    and static_address(assignments[memory], self.lifter.loc_db, None)
                    == line.offset + line.l)
                if not implicit_call_store:
                    self.memory.check_control_access(ExprMem(pointer, memory.size))
                symbol = context_reference(
                    pointer,
                    self.lifter.loc_db,
                    line.offset + line.l,
                    symbols,
                    (memory.size + 7) // 8,
                )
                if symbol:
                    raise ContextFlowLimit(
                        f"context-sensitive symbol requires native execution: {symbol} "
                        f"(IR memory access, {memory.size} bits)",
                        line.offset,
                        line,
                    )

    def instruction_plan(self, line):
        key = id(line)
        if key in self.instruction_lifted:
            return self.instruction_lifted[key][1]
        conditional_move = line.name.upper().startswith("CMOV")
        try:
            assignments, extra = self.lifter.instr2ir(deepcopy(line))
        except (NotImplementedError, ValueError, KeyError, TypeError) as error:
            if conditional_move:
                raise ContextFlowLimit(
                    "unrecognized conditional-move IR requires native execution",
                    getattr(line, "offset", 0) or 0,
                ) from error
            # Preserve the existing policy for genuinely unliftable opcodes.
            self.instruction_lifted[key] = (line, None)
            return None
        try:
            entry = IRBlock(self.lifter.loc_db, self.location, [assignments])
            entry = self.lifter.irbloc_fix_regs_for_mode(entry, 64)
            if not extra:
                if conditional_move:
                    raise ValueError("missing conditional-move assignment block")
                result = entry[0], None, frozenset()
            else:
                result = self.instruction_graph(line, entry, extra)
        except (NotImplementedError, ValueError, KeyError, TypeError) as error:
            raise ContextFlowLimit(
                f"unrecognized instruction IR requires native execution: {error}",
                getattr(line, "offset", 0) or 0,
            ) from error
        self.instruction_lifted[key] = (line, result)
        return result

    def instruction_graph(self, line, entry, extra):
        if len(extra) + 1 > self.MAX_IR_BLOCKS:
            raise ValueError("instruction IR exceeds its block budget")
        blocks = {entry.loc_key: entry}
        for block in extra:
            if block.loc_key in blocks:
                raise ValueError("duplicate instruction IR block")
            blocks[block.loc_key] = self.lifter.irbloc_fix_regs_for_mode(block, 64)
        graph = {}
        temporaries = set()
        architectural = frozenset(all_regs_ids) | {self.lifter.IRDst}
        for key, block in blocks.items():
            targets = set()
            pending = [block.dst]
            visits = 0
            while pending:
                destination = pending.pop()
                visits += 1
                if visits > self.MAX_IR_BLOCKS * 2:
                    raise ValueError("instruction IR exceeds its edge budget")
                # Never select one arm using flags, count values or runtime data.
                if isinstance(destination, ExprCond):
                    pending.extend((destination.src1, destination.src2))
                elif isinstance(destination, ExprLoc):
                    target = destination.loc_key
                    if target in blocks:
                        targets.add(target)
                    elif (
                        self.lifter.loc_db.get_location_offset(target)
                        == line.offset + line.l
                    ):
                        targets.add(None)
                    else:
                        raise ValueError("unknown instruction IR exit")
                else:
                    raise TypeError("non-local instruction IR successor")
            graph[key] = block, sorted(targets, key=str)
            for assignments in block:
                temporaries.update(
                    reg
                    for reg in assignments
                    if isinstance(reg, ExprId) and reg not in architectural
                )
        reachable = set()
        pending = [entry.loc_key]
        while pending:
            target = pending.pop()
            if target in reachable:
                continue
            reachable.add(target)
            if target is not None:
                pending.extend(graph[target][1])
        if reachable != set(blocks) | {None}:
            raise ValueError("instruction IR has unreachable blocks or no normal exit")
        return entry[0], graph, frozenset(temporaries)

    def update_assignments(self, assignments, registers=None, *, call_return=False,
                           audited_call=False):
        tracked = self.registers if registers is None else registers
        writes = {
            reg: value
            for reg, value in assignments.items()
            if reg in tracked or isinstance(reg, ExprMem)
        }
        memory_destinations = [reg for reg in writes if isinstance(reg, ExprMem)]
        rmw = None
        if len(memory_destinations) == 1:
            destination = memory_destinations[0]
            # The access was already checked. An identity write cannot move
            # values between aliases; another parallel write could overlap it.
            if expr_simp(writes[destination]) == expr_simp(destination):
                del writes[destination]
            else:
                rmw = context_memory.rmw_operation(destination, writes[destination])
        domains = {reg: frozenset() for reg in writes if reg in tracked}
        origins = {reg: set() for reg in domains}
        memory_writes = {
            reg: (frozenset(), frozenset())
            for reg in writes
            if isinstance(reg, ExprMem)
        }
        expressions = list(writes.values()) + [reg.ptr for reg in memory_writes]
        # Evaluate all destinations against the same old state (XCHG/aliases).
        for values in self.environments(expressions, tracked):
            for reg, expr in writes.items():
                resolved = {
                    candidate
                    for value in context_memory.evaluate(
                        self.lifter, expr, values, self.memory
                    )
                    for candidate in self.finite_values(value)
                }
                if isinstance(reg, ExprMem):
                    pointers, contents = memory_writes[reg]
                    pointers = self.memory.join(
                        pointers,
                        frozenset(
                            context_memory.evaluate(
                                self.lifter, reg.ptr, values, self.memory
                            )
                        ),
                    )
                    contents = self.memory.join(
                        contents,
                        frozenset(
                            context_memory.wide_value(reg.size)
                            if self.wide_dependency(value)
                            else value
                            for value in resolved
                        ),
                    )
                    memory_writes[reg] = pointers, contents
                    continue
                for value in resolved:
                    if self.entry_spill_guards and isinstance(value, ExprMem):
                        origin = self.memory.entry_stack_value(value)
                        if origin is not None:
                            value = origin
                    if self.entry_spill_guards:
                        origin = self.memory.scaled_entry_value(value)
                        if origin is not None:
                            value = origin
                    domain = (
                        None
                        if self.wide_dependency(value)
                        else frozenset({value if isinstance(value, ExprInt) else None})
                    )
                    domains[reg] = self.join(domains[reg], domain)
                    origins[reg].add(value if self.memory.address(value) is not None else None)
        self.memory.store(
            [
                (
                    (context_memory.wide_value(reg.ptr.size),)
                    if pointers is None
                    else pointers,
                    (context_memory.wide_value(reg.size),)
                    if contents is None
                    else contents,
                    reg.size,
                )
                for reg, (pointers, contents) in memory_writes.items()
            ],
            rmw=rmw,
            call_return=call_return,
            audited_call=audited_call,
        )
        for reg, domain in domains.items():
            if domain == self.UNKNOWN:
                self.values.pop(reg, None)
            else:
                self.values[reg] = domain
            if len(origins[reg]) == 1 and None not in origins[reg]:
                self.origins[reg] = next(iter(origins[reg]))
            else:
                self.origins.pop(reg, None)
