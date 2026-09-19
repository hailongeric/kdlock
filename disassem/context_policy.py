"""Conservative admission rules, not a complete kernel-context analysis."""

# Reading map: symbol/range resolution -> abstract register/memory transfer ->
# JIT-episode reachability -> whole-emission bans and lock-boundary checks.
# Unknown pointers and concurrent mutation remain outside the static proof;
# increasing analysis precision is not a substitute for a runtime address check.
from bisect import bisect_right
from collections import defaultdict, deque
from collections.abc import Mapping
from copy import copy, deepcopy
from fnmatch import translate as translate_glob
from itertools import pairwise, product
import re
from struct import unpack

import context_memory
import diagnostics
import indirect_jump
import normal
from device_session import PERCPU_ALIGNMENT, PERCPU_MODULE_BYTES
from miasm.analysis.machine import Machine
from miasm.arch.x86.regs import all_regs_ids, regs64_expr
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import (
    ExprCompose,
    ExprCond,
    ExprId,
    ExprInt,
    ExprLoc,
    ExprMem,
    ExprOp,
    ExprSlice,
)
from miasm.expression.simplifications import expr_simp
from miasm.ir.ir import IRBlock
from miasm.ir.symbexec import SymbolicExecutionEngine
from miasm_compat import expr_args, expr_int_value, expr_op, expr_ptr

NATIVE_ONLY_EXIT = 2
MAX_LOCK_DEPTH = 8
CONTROL_SYMBOLS = (
    "_raw_spin_lock",
    "_raw_spin_unlock",
    "mutex_lock",
    "mutex_unlock",
)
PERCPU_METADATA_SYMBOLS = (
    "__per_cpu_start",
    "__per_cpu_end",
    "__per_cpu_offset",
    "nr_cpu_ids",
    "__cpu_possible_mask",
)
MAX_PERCPU_CPUS = 8192
MAX_PERCPU_STATIC_BYTES = 16 * 1024 * 1024
KERNEL_ADDRESS_MIN = 0xFF00000000000000
ADDRESS_LIMIT = 1 << 64
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

# Resolve names against the running kernel, including compiler-generated clones.
# Unknown callees deliberately remain eligible for the existing CALL-miss path.
CONTEXT_SYMBOLS = (
    "schedule*",
    "__schedule*",
    "*cond_resched*",
    "preempt_*",
    "__preempt_*",
    "migrate_disable",
    "migrate_enable",
    "local_irq_*",
    "raw_local_irq_*",
    "local_bh_*",
    "__local_bh_*",
    # These wrappers change IRQ/BH state even when the caller has no GS operand.
    "_raw_*_irq*",
    "_raw_*_bh",
    "__raw_*_irq*",
    "__raw_*_bh",
    "irq_enter*",
    "irq_exit*",
    "nmi_enter*",
    "nmi_exit*",
    "rcu_*",
    "__rcu_*",
    "synchronize_*rcu*",
    "call_rcu*",
    "get_current",
    "get_current_task",
    "current_task",
    "__per_cpu_offset",
    "this_cpu_off",
    "cpu_number",
)

# One anchored union preserves fnmatchcase's whole-name/case-sensitive policy
# while avoiding a Python glob loop for every kallsyms entry. Compile only the
# fixed rules, never cache live symbol addresses or admission verdicts. Keep
# each stdlib-translated branch intact, including its flags and end anchor.
_CONTEXT_SYMBOL_RE = re.compile("|".join(map(translate_glob, CONTEXT_SYMBOLS)))


def is_context_symbol(name):
    base = name.split(".", 1)[0]
    return _CONTEXT_SYMBOL_RE.match(base) is not None


def resolve_control_symbols(lookup):
    symbols = {name: lookup(name) for name in CONTROL_SYMBOLS}
    missing = [name for name, address in symbols.items() if not address]
    if missing:
        raise ValueError("unavailable lock symbol addresses: " + ", ".join(missing))
    if len(set(symbols.values())) != len(symbols):
        raise ValueError("ambiguous lock symbol addresses")
    return symbols


class ContextSymbols(Mapping):
    """Exact names plus conservative intervals, not ELF object-size claims."""

    def __init__(self, names, ends, *, percpu=None):
        self._names = names
        self._ends = ends
        self._starts = sorted(names)
        # Keep whole per-CPU intervals separate: a shorter named symbol inside
        # one must not truncate the surrounding static area's coverage.
        self._percpu = percpu

    def __getitem__(self, address):
        return self._names[address]

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)

    def resolve(self, address, size=1):
        if address is None:
            return None
        if self._percpu is not None:
            symbol = self._percpu.resolve(address, size)
            if symbol:
                return symbol
        index = bisect_right(self._starts, address) - 1
        if index >= 0:
            start = self._starts[index]
            if address < self._ends[start]:
                return self._names[start]
        # A multi-byte operand can start outside a symbol and still touch it.
        index += 1
        if index < len(self._starts) and self._starts[index] < address + size:
            return self._names[self._starts[index]]
        return None


def load_static_percpu_ranges(metadata, read_memory, *, module_bytes=0):
    """Resolve fixed x86-64 core/module arenas, not allocation/object validity.

    The supported guest initializes possible CPUs/offsets at boot; offsets are
    ro_after_init. Use every possible CPU, including offline ones. The injected
    reader is the production device-lease/pinned kcore boundary, never an
    unleased fallback. Snapshot comparison detects inconsistent collection,
    not an allocator lifetime guarantee or a runtime address guard. Version 2
    supplies the boot-reserved module extent after the aligned core section;
    never expand to unit_size, whose tail may have returned to ordinary memory.
    """
    if type(module_bytes) is not int or module_bytes not in (0, PERCPU_MODULE_BYTES):
        raise ValueError("invalid module per-CPU range capability")
    missing = set(PERCPU_METADATA_SYMBOLS) - metadata.keys()
    if missing:
        raise ValueError(
            "unavailable static per-CPU metadata: " + ", ".join(sorted(missing))
        )
    start, end = metadata["__per_cpu_start"], metadata["__per_cpu_end"]
    size = end - start
    # __per_cpu_start == 0 is valid on x86-64. Do not treat section offsets as
    # actual low-memory intervals, which would also reject ordinary immediates.
    if not 0 <= start < end < ADDRESS_LIMIT or not 0 < size <= MAX_PERCPU_STATIC_BYTES:
        raise ValueError("invalid static per-CPU section bounds")
    module_offset = (size + PERCPU_ALIGNMENT - 1) // PERCPU_ALIGNMENT * PERCPU_ALIGNMENT
    span = module_offset + module_bytes if module_bytes else size
    snapshots = []

    def read_field(name, length):
        address = metadata[name]
        if not KERNEL_ADDRESS_MIN <= address < address + length <= ADDRESS_LIMIT:
            raise ValueError(f"invalid static per-CPU metadata address: {name}")
        raw = read_memory(address, length)
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != length:
            raise ValueError(f"incomplete static per-CPU metadata read: {name}")
        raw = bytes(raw)
        snapshots.append((name, address, raw))
        return raw

    nr_cpus = int.from_bytes(read_field("nr_cpu_ids", 4), "little")
    if not 0 < nr_cpus <= MAX_PERCPU_CPUS:
        raise ValueError("invalid or excessive static per-CPU CPU count")
    mask = int.from_bytes(
        read_field("__cpu_possible_mask", ((nr_cpus + 63) // 64) * 8), "little"
    ) & ((1 << nr_cpus) - 1)
    if not mask:
        raise ValueError("empty possible CPU mask for static per-CPU areas")
    offsets = unpack(f"<{nr_cpus}Q", read_field("__per_cpu_offset", nr_cpus * 8))
    for name, address, raw in snapshots:
        if read_memory(address, len(raw)) != raw:
            raise ValueError(
                f"static per-CPU metadata changed during inspection: {name}"
            )

    ranges = []
    for cpu, offset in enumerate(offsets):
        if not mask & (1 << cpu):
            continue
        base = (start + offset) % ADDRESS_LIMIT
        if not KERNEL_ADDRESS_MIN <= base < base + span <= ADDRESS_LIMIT:
            raise ValueError(f"invalid static per-CPU runtime range: cpu={cpu}")
        ranges.append((base, base + size, f"kernel_percpu_cpu_{cpu}"))
        if module_bytes:
            module_start = base + module_offset
            ranges.append(
                (module_start, module_start + module_bytes, f"module_percpu_cpu_{cpu}")
            )
    ranges.sort()
    if any(left[1] > right[0] for left, right in pairwise(ranges)):
        raise ValueError("overlapping static per-CPU runtime ranges")
    diagnostics.warn(
        "STATIC_PERCPU_SCREENING",
        "extend_static_ranges",
        "core static/module reserved arenas only; dynamic allocations, object "
        "lifetimes and unknown pointers are not validated",
        cpus=mask.bit_count(),
        bytes_per_cpu=size + module_bytes,
        core_bytes=size,
        module_bytes=module_bytes,
    )
    return ContextSymbols(
        {base: name for base, _, name in ranges},
        {base: limit for base, limit, _ in ranges},
    )


def load_context_symbols(
    path="/proc/kallsyms", *, read_memory=None, percpu_module_bytes=0
):
    # Name-only parsing remains useful for byte fixtures. Production always
    # supplies its leased reader and negotiated module extent. A standalone
    # capability value cannot replace the CPU metadata or its read lifetime.
    if percpu_module_bytes and read_memory is None:
        raise ValueError("module per-CPU ranges require the leased memory reader")
    symbols = {}
    owners = {}
    metadata = {}
    addresses = defaultdict(set)
    with open(path, encoding="ascii", errors="replace") as source:
        for line in source:
            fields = line.split()
            if len(fields) < 3:
                continue
            address = int(fields[0], 16)
            owner = fields[3] if len(fields) > 3 else ""
            if (
                read_memory is not None
                and not owner
                and fields[2] in PERCPU_METADATA_SYMBOLS
            ):
                name = fields[2]
                if name in metadata and metadata[name] != address:
                    raise ValueError(f"ambiguous static per-CPU metadata: {name}")
                metadata[name] = address
            if address:
                addresses[owner].add(address)
            if is_context_symbol(fields[2]):
                if not address:
                    raise ValueError(f"unavailable context symbol address: {fields[2]}")
                symbols[address] = fields[2]
                owners[address] = owner
    if not symbols:
        raise ValueError(f"no context-sensitive symbols resolved from {path}")
    boundaries = {owner: sorted(values) for owner, values in addresses.items()}
    ends = {}
    for address in symbols:
        values = boundaries[owners[address]]
        index = bisect_right(values, address)
        # Aliases do not truncate a range; module boundaries never extend it.
        # With no visible successor we know only the exact symbol address.
        ends[address] = values[index] if index < len(values) else address + 1
    percpu = (
        load_static_percpu_ranges(
            metadata, read_memory, module_bytes=percpu_module_bytes
        )
        if read_memory is not None
        else None
    )
    return ContextSymbols(symbols, ends, percpu=percpu)


def static_address(expr, db, next_rip):
    if isinstance(expr, ExprInt):
        return expr_int_value(expr)
    if isinstance(expr, ExprLoc):
        return db.get_location_offset(expr.loc_key) if db is not None else None
    if isinstance(expr, ExprId) and str(expr).upper() == "RIP":
        return next_rip
    if isinstance(expr, ExprOp) and expr_op(expr) in {"+", "-"}:
        values = [static_address(arg, db, next_rip) for arg in expr_args(expr)]
        if values and all(value is not None for value in values):
            if expr_op(expr) == "+":
                return sum(values) & ((1 << 64) - 1)
            if len(values) == 2:
                return (values[0] - values[1]) & ((1 << 64) - 1)
    return None


class RegisterConstants:
    """Block-local address facts, not runtime memory or flags emulation."""

    def __init__(self):
        self.lifter = Machine("x86_64").lifter(LocationDB())
        self.location = self.lifter.loc_db.add_location()
        self.registers = frozenset(regs64_expr) - {ExprId("RIP", 64)}
        self.values = {}
        self.lifted = {}

    def resolve(self, expr):
        normalized = self.lifter.expr_fix_regs_for_mode(expr, 64)
        return SymbolicExecutionEngine(self.lifter, self.values).eval_expr(normalized)

    def resolve_many(self, expr, *, allow_wide=False):
        return (self.resolve(expr),)

    def assignments(self, line):
        key = id(line)
        if key in self.lifted:
            return self.lifted[key][1]
        try:
            # The lifter mutates decode metadata; never change codegen inputs.
            assignments, extra = self.lifter.instr2ir(deepcopy(line))
            if extra:
                result = None
            else:
                block = IRBlock(self.lifter.loc_db, self.location, [assignments])
                result = self.lifter.irbloc_fix_regs_for_mode(block, 64)[0]
        except (NotImplementedError, ValueError, KeyError, TypeError):
            result = None
        self.lifted[key] = (line, result)
        return result

    def update(self, line):
        if line.breakflow() or line.is_subcall():
            self.values.clear()
            return
        assignments = self.assignments(line)
        if assignments is None:
            # Forget facts for unmodelled instructions; do not silently retain
            # stale register values or introduce a new opcode refusal policy.
            self.values.clear()
            return
        engine = SymbolicExecutionEngine(self.lifter, self.values)
        updates = engine.eval_assignblk(assignments)
        for register, value in updates.items():
            if register not in self.registers:
                continue
            if isinstance(value, ExprInt):
                self.values[register] = value
            else:
                self.values.pop(register, None)


class ContextFlowLimit(ValueError):
    def __init__(self, detail, offset=0, instruction=None, *, diagnostic_fields=None):
        super().__init__(detail)
        self.offset = offset
        self.instruction = instruction
        self.diagnostic_fields = diagnostic_fields

    def report(self, offset=None, instruction=None):
        if self.diagnostic_fields is None:
            return
        diagnostics.set_instruction(
            self.offset if offset is None else offset,
            self.instruction if instruction is None else instruction,
        )
        diagnostics.warn(
            "CONTEXT_ADDRESS_WIDENED",
            "reject_entry",
            "analysis uncertainty, not evidence of a runtime context access",
            **self.diagnostic_fields,
        )


def known_bits(value):
    """Proven zero/one bits, without assumptions about flags or runtime data."""
    mask = (1 << value.size) - 1
    if isinstance(value, ExprInt):
        return mask ^ int(value), int(value)
    if isinstance(value, ExprSlice):
        zero, one = known_bits(value.arg)
        return (zero >> value.start) & mask, (one >> value.start) & mask
    if isinstance(value, ExprCompose):
        zero = one = offset = 0
        for part in value.args:
            part_zero, part_one = known_bits(part)
            zero |= part_zero << offset
            one |= part_one << offset
            offset += part.size
        return zero, one
    if isinstance(value, ExprOp) and value.op == "&":
        zero, one = 0, mask
        for part in value.args:
            part_zero, part_one = known_bits(part)
            zero |= part_zero
            one &= part_one
        return zero, one
    return 0, 0


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
                 entry_spill_guards=False):
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
        self.mutex_calls = set()
        self.mutex_stack_bytes = mutex_stack_bytes
        self.call_entries = {}
        self.scoped_calls = scoped_calls
        self.return_targets = {}
        self.entry_spill_guards = entry_spill_guards
        self.memory.allow_checked_entry_spills = entry_spill_guards

    def snapshot(self):
        return (dict(self.values), dict(self.origins), self.memory.snapshot(),
                self.memory.entry_spills_blocked, self.memory.checked_spill_windows)

    def restore(self, state):
        self.values, self.origins = dict(state[0]), dict(state[1])
        self.memory.restore(state[2])
        self.memory.entry_spills_blocked = state[3]
        self.memory.checked_spill_windows = state[4]

    def merge_state(self, left, right):
        origins = {
            reg: origin
            for reg, origin in left[1].items()
            if right[1].get(reg) == origin
        }
        windows = left[4] | right[4]
        blocked = left[3] or right[3] or len(windows) > 64
        return (
            self.merge(left[0], right[0]),
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
        values, origins = dict(self.values), dict(self.origins)
        self.update_effects(
            line, symbols, checked_mutex_stack=id(line) in self.mutex_calls,
            clobber_lock=lock_pointers,
            readonly_call=id(line) in self.readonly_calls,
        )
        for reg in saved:
            for output, before in ((self.values, values), (self.origins, origins)):
                if reg in before:
                    output[reg] = before[reg]
                else:
                    output.pop(reg, None)

    def update_effects(self, line, symbols=None, *, checked_mutex_stack=False,
                       clobber_lock=None, readonly_call=False):
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
            # CALL writes its return address before any callee can clobber it.
            self.update_assignments(entry)
            if line.is_subcall():
                self.call_entries[id(line)] = self.snapshot()
                if (clobber_lock is not None or readonly_call) and line.name.upper() == "CALL":
                    if clobber_lock is not None:
                        self.memory.store([(clobber_lock,
                            frozenset({context_memory.wide_value(32)}), 32)])
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
        if symbols is None:
            return
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

    def update_assignments(self, assignments, registers=None):
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
                    origins[reg].add(
                        value if self.memory.address(value) is not None else None
                    )
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


def context_reference(expr, db, next_rip, symbols, size=1):
    # A GS displacement names origin-CPU storage, not a linear kernel address.
    # Lowering adds the pinned waiter's GS base (or supplies logical current).
    # Do not mistake an offset equal to current_task for an absolute reference;
    # ordinary linear per-CPU aliases still go through the checks below.
    if (
        isinstance(expr, ExprOp)
        and expr_op(expr) == "segm"
        and str(expr_args(expr)[0]).upper() == "GS"
    ):
        return None
    address = static_address(expr, db, next_rip)
    if isinstance(symbols, ContextSymbols):
        symbol = symbols.resolve(address, size)
    else:
        # Plain mappings carry exact addresses, but operand overlap still counts.
        symbol = next(
            (
                name
                for start, name in symbols.items()
                if address is not None and address <= start < address + size
            ),
            None,
        )
    if symbol:
        return symbol
    # An unknown index does not hide a known base, e.g. offset_table[RAX].
    # This deliberately does not infer values from earlier register writes.
    if address is None and isinstance(expr, ExprOp):
        for arg in expr_args(expr):
            symbol = context_reference(arg, db, next_rip, symbols, size)
            if symbol:
                return symbol
    return None


def instruction_rejection(
    line, offset, db, symbols, lock_kind=None, lock_symbols=None, constants=None
):
    """Return (reason, symbol), preserving all ordinary codegen semantics."""
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
    if line.name.upper() in {"CLI", "STI"}:
        return "IRQ state modification requires native context", ""

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
