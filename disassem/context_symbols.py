"""Context symbol intervals and leased static per-CPU metadata resolution.

No runtime-address or object-lifetime guarantee is provided by these ranges.
"""
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Mapping
from fnmatch import translate as translate_glob
from itertools import pairwise
import re
from struct import unpack

import diagnostics
from device_session import PERCPU_ALIGNMENT, PERCPU_MODULE_BYTES

CONTROL_SYMBOLS = (
    "_raw_spin_lock",
    "_raw_spin_unlock",
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

# Resolve names against the running kernel, including compiler-generated clones.
# Unknown callees deliberately remain eligible for the existing CALL-miss path.
CONTEXT_SYMBOLS = (
    # A KD-only build has no interoperable Linux mutex object. Never learn
    # native mutex calls as ordinary remote services or control endpoints.
    "mutex_*", "__mutex_*", "atomic_dec_and_mutex_lock",
    "kd_mutex_lock_clobber_v1", "kd_mutex_unlock_clobber_v1",
    # Conventional C entry points deliberately remain local. Only the explicit
    # DIRECT clobber controls can acquire/release through the nested ledger.
    "kd_mutex_lock", "kd_mutex_unlock", "kd_mutex_api_lock", "kd_mutex_api_unlock",
    # Return-valued or task-signal/I/O APIs stay on the original task.
    "kd_mutex_lock_interruptible", "kd_mutex_lock_killable", "kd_mutex_lock_io",
    "kd_mutex_trylock", "kd_atomic_dec_and_mutex_lock",
    # A delegated body has no rwsem mode/owner ledger or cancellation,
    # downgrade or non-owner-release protocol. Refuse native rwsem operations
    # before ordinary CALL-miss learning can import their implementations.
    "init_rwsem", "__init_rwsem", "rwsem_*", "__rwsem_*",
    "down_read", "down_read_*", "__down_read", "__down_read_*",
    "down_write", "down_write_*", "__down_write", "__down_write_*",
    "up_read", "up_read_*", "__up_read", "__up_read_*",
    "up_write", "up_write_*", "__up_write", "__up_write_*",
    "downgrade_write", "downgrade_write_*", "__downgrade_write",
    # Per-CPU rwsems are a separate protocol, also outside this ledger.
    "percpu_init_rwsem", "__percpu_init_rwsem", "percpu_free_rwsem",
    "percpu_down_*", "percpu_up_*", "__percpu_down_*", "__percpu_up_*",
    "percpu_rwsem_*", "__percpu_rwsem_*",
    # KD's explicit outer-writer pair reserves admission and drains readers
    # before publishing on the embedded mutex. That does not authorize calls
    # to ordinary rwsem APIs or phase helpers inside an enclosing JIT body.
    "kd_down_*", "kd_up_*", "kd_downgrade_write", "kd_rwsem_*",
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
    # Explicit KD variants are native-only context boundaries, not ordinary
    # lock endpoints or learnable native CALL-miss continuations.
    "kd_spin_*_irq*",
    "__kd_spin_*_irq*",
    "kd_spin_*_bh",
    "__kd_spin_*_bh",
    # Local rwlock variants have no translated mode/context ownership ledger.
    "kd_read_*_irq*", "__kd_read_*_irq*",
    "kd_write_*_irq*", "__kd_write_*_irq*",
    "kd_read_*_bh", "kd_write_*_bh",
    "kd_read_trylock", "kd_write_trylock",
    "__kd_read_*_pinned", "__kd_write_*_pinned",
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
    # Equivalent out-of-line helpers must not hide processor-context effects.
    "stac", "clac", "smap_*", "uaccess_*", "__uaccess_*", "user_access_*",
    "get_user", "put_user", "__get_user*", "__put_user*",
    "copy_from_user*", "copy_to_user*", "_copy_from_user*", "_copy_to_user*",
    "__copy_from_user*", "__copy_to_user*", "raw_copy_from_user*", "raw_copy_to_user*",
    "copy_user_*", "clear_user", "__clear_user", "strnlen_user", "strncpy_from_user",
    "rdmsr*", "wrmsr*", "native_read_msr*", "native_write_msr*",
    "native_read_cr*", "native_write_cr*", "native_get_debugreg", "native_set_debugreg",
    "kernel_fpu_*",
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
