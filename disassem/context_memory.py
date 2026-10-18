"""Bounded sequential memory facts for admission, never runtime memory reads.

Cells hold byte-value alternatives. None in a domain is ordinary unknown data;
a None domain is analysis exhaustion. Address identity uses only constants and
one unchanged entry-register base plus a constant displacement. Other addresses
may alias every cell, including cells based on a different entry register.
"""

from itertools import product

from miasm.expression.expression import ExprCompose, ExprId, ExprInt, ExprMem, ExprOp
from miasm.expression.simplifications import expr_simp
from miasm.ir.symbexec import SymbolicExecutionEngine

UNKNOWN = frozenset({None})
WIDE_PREFIX = "kd_memory_wide_"
CALL_ALIAS_PREFIX = "kd_call_alias_"
CALL_ALIAS_OP = "kd_call_alias"
ADDRESS_MASK = (1 << 64) - 1
MAX_CALL_PATTERNS = 256


class AuditedScratchAccess(ValueError):
    """A selected C caller explicitly observes an API's temporary CALL word."""


def is_wide(value):
    return any(
        isinstance(item, ExprId) and str(item).startswith(WIDE_PREFIX)
        for item in value.get_r(mem_read=True)
    )


def wide_value(size, name="budget"):
    return ExprId(WIDE_PREFIX + str(name), size)


def has_call_alias(value):
    """Partial original CALL-word overlap, distinct from unconstrained data."""
    return any(isinstance(item, ExprId) and str(item).startswith(CALL_ALIAS_PREFIX)
               for item in value.get_r(mem_read=True))


def call_alias_value(size, name="load", patterns=()):
    """Analysis-only unknown with exact partial-word masks and constant adds.

    Each (mask, bits, offset) describes ((unknown & ~mask) | bits) + offset,
    modulo 2**64. There is also an ordinary untouched-memory alternative.
    Keeping the constants inside a tagged expression lets snapshots/copies
    carry them without a side table or a new runtime check.
    """
    patterns = tuple(sorted(set(patterns)))
    if size != 64 or len(patterns) > MAX_CALL_PATTERNS:
        return wide_value(size, "call_patterns")
    return ExprOp(CALL_ALIAS_OP, ExprId(CALL_ALIAS_PREFIX + str(name), size),
                  *(ExprInt(part, size) for pattern in patterns for part in pattern))


def call_alias_patterns(value):
    """Return preserved patterns for a copy/constant add; None means unsupported."""
    if value.size != 64 or not isinstance(value, ExprOp):
        return None
    if value.op == CALL_ALIAS_OP:
        identity, *parts = value.args
        if (not isinstance(identity, ExprId)
                or not str(identity).startswith(CALL_ALIAS_PREFIX)
                or len(parts) % 3 or len(parts) > 3 * MAX_CALL_PATTERNS
                or not all(isinstance(part, ExprInt) for part in parts)):
            return None
        return tuple(tuple(map(int, parts[i:i + 3]))
                     for i in range(0, len(parts), 3))
    if value.op == "+":
        dynamic = [part for part in value.args if not isinstance(part, ExprInt)]
        if len(dynamic) != 1:
            return None
        patterns = call_alias_patterns(dynamic[0])
        if patterns is not None:
            amount = sum(int(part) for part in value.args if isinstance(part, ExprInt))
            return tuple((mask, bits, (offset + amount) & ADDRESS_MASK)
                         for mask, bits, offset in patterns)
    return None


def merge_call_aliases(values, size, name):
    """Canonical union preserves every partial pattern through register joins."""
    patterns = set()
    for value in values:
        if value is not None and is_wide(value):
            return wide_value(size, "call_patterns")
        if value is None or not has_call_alias(value):
            continue
        found = call_alias_patterns(value)
        if found is None:
            return wide_value(size, "call_operation")
        patterns.update(found)
        if len(patterns) > MAX_CALL_PATTERNS:
            return wide_value(size, "call_patterns")
    return call_alias_value(size, name, patterns)


def ordinary_call_pointer(value):
    """Only copies and constant byte offsets retain opaque pointer use.

    Known bases and contiguous high-prefix ranges remain available to context
    screening after an offset. Masks, slices, multiplication and combinations
    of opaque values need exhaustive enumeration or the fail-closed wide domain.
    """
    return call_alias_patterns(value) is not None


def call_alias_ranges(value, size=1):
    """Known bases/ranges under the existing context-screening policy.

    A high known prefix and unknown low bytes form an exact contiguous range.
    A low known residue with unknown high bytes does NOT justify a huge range
    hull: those high bits are ordinary unknown pointer input. Its zero-unknown
    known base is still checked, including subsequent constant offsets.
    """
    patterns = call_alias_patterns(value)
    if patterns is None:
        return ()
    ranges = set()
    limit = ADDRESS_MASK + 1
    for mask, bits, offset in patterns:
        unknown = ADDRESS_MASK ^ mask
        start = (bits + offset) & ADDRESS_MASK
        lengths = [size]
        if unknown & (unknown + 1) == 0:
            lengths.append(unknown + size)
        for length in lengths:
            if length >= limit:
                return ((0, limit),)
            if start + length <= limit:
                ranges.add((start, length))
            else:
                ranges.add((start, limit - start))
                ranges.add((0, start + length - limit))
        if offset:
            if offset + size <= limit:
                ranges.add((offset, size))
            else:
                ranges.add((offset, limit - offset))
                ranges.add((0, offset + size - limit))
    return tuple(sorted(ranges))


def rmw_operation(destination, source):
    """Recognize a single same-location IR operation, not an opcode whitelist."""
    destination, source = expr_simp(destination), expr_simp(source)
    if not isinstance(destination, ExprMem):
        return None
    if not isinstance(source, ExprOp) or source.op not in {"+", "&", "|", "^"}:
        return None
    if len(source.args) != 2:
        return None
    for old, constant in (source.args, source.args[::-1]):
        if old == destination and isinstance(constant, ExprInt):
            return source.op, int(constant)
    return None


def rmw_word_values(value, word_bytes, write_bytes, start, operation, amount):
    """Possible old-word values after one RMW placement; neighboring bytes unknown."""
    if start is None:
        return {value}
    low, high = max(0, start), min(word_bytes, start + write_bytes)
    if low >= high:
        return {value}
    shift, prefix = low * 8, (low - start) * 8
    mask = (1 << ((high - low) * 8)) - 1
    old = (value >> shift) & mask
    amount &= (1 << (write_bytes * 8)) - 1
    constant = (amount >> prefix) & mask
    if operation == "+":
        # Unknown lower bytes can carry zero or one into the known overlap.
        # Higher bytes never carry downward; negative adds encode subtraction.
        carries = (0, 1) if amount & ((1 << prefix) - 1) else (0,)
        parts = {(old + constant + carry) & mask for carry in carries}
    elif operation == "&":
        parts = {old & constant}
    elif operation == "|":
        parts = {old | constant}
    elif operation == "^":
        parts = {old ^ constant}
    else:
        raise ValueError("unsupported IR RMW operation")
    return {(value & ~(mask << shift)) | (part << shift) for part in parts}


class MemoryValues:
    MAX_BYTES = 256
    MAX_VALUES = 64
    MAX_COMBINATIONS = 256
    MAX_ACCESS_BYTES = 16
    MAX_WORK = 1_000_000
    MAX_WORDS = 32

    def __init__(self, bases, guards=None):
        self.bases = bases
        self.guards = guards
        self.cells = {}
        self.default = UNKNOWN
        self.words = {}
        # A separate may-write record survives joins with the untouched path.
        # None means an ordinary write, opaque effect or exhausted proof has
        # invalidated this narrow provenance; {} means no source CALL yet.
        # This is not a private-stack assumption: every possible overlap still
        # reaches the original emitted load and original CALL store.
        self.call_words = {}
        # Typed C APIs have an explicit caller contract: ordinary C objects do
        # not observe their temporary return token below pre-CALL SP. Keep that
        # token exact and separate, rather than mixing its bytes into every
        # unknown object load. This is not enabled for ordinary assembly CALLs.
        # None records exhausted control provenance and must fail closed.
        self.control_words = {}
        self.work = 0
        # FlowConstants carries this bit in its CFG snapshot and joins it by
        # OR: an opaque write/callee forbids further initial-stack identities.
        # UNKNOWN byte data alone cannot distinguish untouched from overwritten.
        self.entry_spills_blocked = False
        self.allow_checked_entry_spills = False
        self.checked_spill_windows = frozenset()
        self.load_guard = None

    def spend(self, amount):
        # Work is translation-local, not path-local: restoring a CFG snapshot
        # must not replenish an exhausted analysis budget.
        self.work += amount
        return self.work <= self.MAX_WORK

    def snapshot(self):
        return (dict(self.cells), self.default, dict(self.words),
                None if self.call_words is None else dict(self.call_words),
                None if self.control_words is None else dict(self.control_words))

    def entry_stack_value(self, memory):
        """Keep an initial spill identity only when every prior store is disjoint.

        Unknown writes, overwritten slots and widened paths cannot acquire a
        fresh entry identity. Collected alias premises are checked before body.
        """
        if (self.guards is None or memory.size != 64 or self.default != UNKNOWN
                or self.entry_spills_blocked):
            return None
        address = self.address(memory.ptr)
        if address is None or self.guards.base_name(address[0]) not in {"RSP", "RBP"}:
            return None
        if any(not self.checked_coverage(address, window, 8, size)
               for window, size in self.checked_spill_windows):
            return None
        if not self.spend(8 * len(self.cells)):
            return None
        for i in range(8):
            pointer = self.offset(memory.ptr, i)
            if any(self.relation(pointer, written) is not False for written in self.cells):
                return None
        name = self.guards.stack_value(address)
        if name is None:
            return None
        value = ExprId("kd_entry_" + name, 64)
        self.bases = self.bases | {value}
        return value

    def restore(self, state):
        self.cells, self.default = dict(state[0]), state[1]
        self.words = dict(state[2])
        self.call_words = (dict(state[3]) if len(state) > 3 and state[3] is not None
                           else None)
        self.control_words = (dict(state[4]) if len(state) > 4 and state[4] is not None
                              else ({} if len(state) < 5 else None))

    def merge_control(self, left, right):
        a, b = (state[4] if len(state) > 4 else {} for state in (left, right))
        if a is None or b is None:
            return None
        keys = a.keys() | b.keys()
        if not keys:
            return {}
        if len(keys) > self.MAX_WORDS or not self.spend(len(keys)):
            return None
        result = {}
        for key in keys:
            values = a.get(key, frozenset()) | b.get(key, frozenset())
            if len(values) > self.MAX_VALUES:
                return None
            result[key] = values
        return result

    def check_control_access(self, memory, *, words=None):
        """Refuse a statically identifiable observer; do not test runtime aliases.

        Different/unknown object bases use the audited caller promise. Matching
        bases retain exact whole/partial/modular overlap detection, independent
        of entry guards. Ordinary CALLs and their data aliases are unchanged.
        """
        words = self.control_words if words is None else words
        if words is None:
            raise AuditedScratchAccess("audited C CALL control provenance exhausted")
        if not words:
            return
        if not self.spend(len(words)):
            raise AuditedScratchAccess("audited C CALL control analysis exceeds its budget")
        address = self.address(memory.ptr)
        for word in words:
            base = self.address(word.ptr)
            if address is None or base is None or address[0] != base[0]:
                continue
            if self.placements(memory, word.ptr, word.size, use_guards=False) != [None]:
                raise AuditedScratchAccess(
                    "audited C caller explicitly observes temporary CALL control scratch")

    def store_control_return(self, writes):
        """Retain an exact token without declaring ordinary caller data written."""
        if self.control_words is None or len(writes) != 1:
            raise AuditedScratchAccess("unproved audited C CALL control word")
        pointers, values, width = writes[0]
        if (width != 64 or len(pointers) != 1 or not values
                or len(values) > self.MAX_VALUES
                or any(not isinstance(value, ExprInt) for value in values)):
            raise AuditedScratchAccess("unproved audited C CALL control word")
        pointer = next(iter(pointers))
        base = self.address(pointer)
        if base is None or not self.spend(len(self.cells) + len(self.words) + 8):
            raise AuditedScratchAccess("unproved audited C CALL stack identity")
        word = ExprMem(pointer, 64)
        for old in self.control_words:
            if (self.address(old.ptr) is not None
                    and self.address(old.ptr)[0] == base[0]
                    and self.address(old.ptr) != base
                    and self.placements(old, pointer, 64, use_guards=False) != [None]):
                raise AuditedScratchAccess("overlapping audited C CALL control slots")
        # An exact overwrite supersedes an older token at that slot. Do not
        # restore a whole memory snapshot or erase aliases at other bases.
        def covered(address, size):
            location = self.address(address)
            return (location is not None and location[0] == base[0]
                    and ((location[1] - base[1]) & ADDRESS_MASK) + size <= 8)
        self.cells = {key: value for key, value in self.cells.items()
                      if not covered(key, 1)}
        self.words = {key: value for key, value in self.words.items()
                      if self.placements(key, pointer, 64, use_guards=False) == [None]
                      or self.address(key.ptr) is None
                      or self.address(key.ptr)[0] != base[0]}
        if self.call_words is not None:
            partial = any(self.address(key.ptr) is not None
                          and self.address(key.ptr)[0] == base[0]
                          and self.placements(key, pointer, 64, use_guards=False) != [None]
                          and not covered(key.ptr, key.size // 8)
                          for key in self.call_words)
            self.call_words = (None if partial else
                {key: value for key, value in self.call_words.items()
                 if not covered(key.ptr, key.size // 8)})
        self.control_words[word] = frozenset(map(int, values))
        if len(self.control_words) > self.MAX_WORDS:
            raise AuditedScratchAccess("audited C CALL control records exceed their budget")

    def control_return_may_read(self, memory):
        """Plain RET may consume a full token, without producing a data value.

        This map is a may-write union, so presence never proves what every path
        will pop. A possible token keeps the complete emitted RET whitelist.
        Explicit data loads still use check_control_access and remain refused.
        """
        if memory.size != 64 or self.control_words is None:
            raise AuditedScratchAccess("unproved audited C RET control access")
        if not self.control_words:
            return False
        if not self.spend(len(self.control_words)):
            raise AuditedScratchAccess("audited C RET control analysis exceeds its budget")
        address = self.address(memory.ptr)
        possible = False
        for word in self.control_words:
            base = self.address(word.ptr)
            if address is None or base is None or address[0] != base[0]:
                possible = True
            elif address == base:
                possible = True
            elif self.placements(memory, word.ptr, word.size, use_guards=False) != [None]:
                raise AuditedScratchAccess("plain RET partially overlaps audited C control scratch")
        return possible

    def replace_control_return(self, writes):
        """An ordinary CALL really overwrites any fully covered older token."""
        if not self.control_words:
            return
        if len(writes) != 1:
            return
        pointers, _, width = writes[0]
        if width != 64 or len(pointers) != 1:
            return
        pointer = next(iter(pointers))
        base = self.address(pointer)
        if base is None:
            return
        for old in self.control_words:
            if (self.address(old.ptr) is not None
                    and self.address(old.ptr)[0] == base[0]
                    and self.address(old.ptr) != base
                    and self.placements(old, pointer, 64, use_guards=False) != [None]):
                raise AuditedScratchAccess("ordinary CALL partially overwrites audited control scratch")
        self.control_words = {
            word: values for word, values in self.control_words.items()
            if self.address(word.ptr) != base}

    def merge_calls(self, left, right):
        if len(left) < 4 or len(right) < 4 or left[3] is None or right[3] is None:
            return None
        keys = left[3].keys() | right[3].keys()
        if len(keys) > 1:
            return None
        result = {}
        for key in keys:
            values = left[3].get(key, frozenset()) | right[3].get(key, frozenset())
            if len(values) >= self.MAX_VALUES or not self.spend(len(values) + 1):
                return None
            result[key] = values
        return result

    def scaled_entry_value(self, value):
        """Name the exact scaled value, so its writes still need alias guards."""
        if self.guards is None or not isinstance(value, ExprOp) or value.op != '<<':
            return None
        if len(value.args) != 2 or not isinstance(value.args[1], ExprInt):
            return None
        name = self.guards.scaled_stack_value(
            self.guards.base_name(value.args[0]), int(value.args[1]))
        if name is None:
            return None
        origin = ExprId('kd_entry_' + name, 64)
        self.bases = self.bases | {origin}
        return origin

    def join(self, left, right):
        if left is None or right is None:
            return None
        merged = left | right
        return merged if len(merged) <= self.MAX_VALUES else None

    def address(self, value):
        value = expr_simp(value)
        if value.size != 64:
            return None
        if isinstance(value, ExprInt):
            return None, int(value)
        if value in self.bases:
            return value, 0
        if isinstance(value, ExprOp) and value.op == "+":
            bases = [part for part in value.args if part in self.bases]
            offsets = [int(part) for part in value.args if isinstance(part, ExprInt)]
            if len(bases) == 1 and len(bases) + len(offsets) == len(value.args):
                return bases[0], sum(offsets) & ((1 << 64) - 1)
        return None

    @staticmethod
    def offset(pointer, index):
        return expr_simp(pointer + ExprInt(index, pointer.size))

    def relation(self, left, right):
        """Return definite equality/disjointness, or None for possible aliasing."""
        a, b = self.address(left), self.address(right)
        if a is not None and b is not None and a[0] == b[0]:
            return a[1] == b[1]
        if self.guards is not None and self.guards.separate(a, b):
            return False
        return None

    def byte_at(self, pointer):
        if pointer in self.cells:
            return self.cells[pointer]
        result = self.default
        for address, domain in self.cells.items():
            if self.relation(pointer, address) is not False:
                result = self.join(result, domain)
        return result

    def merge(self, left, right):
        control = self.merge_control(left, right)
        keys = left[0].keys() | right[0].keys()
        if len(keys) > self.MAX_BYTES:
            return {}, None, {}, None, control
        if left == right:
            if not self.spend(len(keys) + len(left[2]) + 1):
                return {}, None, {}, None, control
            calls = self.merge_calls(left, right)
            return dict(left[0]), left[1], self.bounded_words(left[2]), calls, control
        # Exact cells use a dictionary lookup; only missing cells scan aliases.
        # Restore each side once instead of copying both maps for every byte.
        cost = (
            2 * len(keys)
            + len(left[0].keys() - right[0].keys()) * len(right[0])
            + len(right[0].keys() - left[0].keys()) * len(left[0])
        )
        if not self.spend(cost):
            return {}, None, {}, None, control
        old = self.snapshot()
        self.restore(left)
        values = {key: self.byte_at(key) for key in keys}
        self.restore(right)
        result = {key: self.join(values[key], self.byte_at(key)) for key in keys}
        self.restore(old)
        default = self.join(left[1], right[1])
        if default is None:
            result = {
                key: domain for key, domain in result.items() if domain is not None
            }
        words = {}
        for memory in sorted(left[2].keys() & right[2].keys(), key=str):
            a, b = left[2][memory], right[2][memory]
            if not self.spend(len(a) + len(b)):
                return {}, None, {}, None, control
            domain = a | b
            if len(domain) <= self.MAX_VALUES:
                words[memory] = domain
        return result, default, self.bounded_words(words), self.merge_calls(left, right), control

    def checked_coverage(self, address, window, size, window_bytes):
        if address is None or window is None:
            return False
        if address[0] == window[0]:
            return ((address[1] - window[1]) & ((1 << 64) - 1)) + size <= window_bytes
        return (self.allow_checked_entry_spills and self.guards is not None
                and self.guards.inside_checked_window(address, window, size, window_bytes))

    def clobber(self, *, checked_windows=(), window_bytes=0):
        self.call_words = None
        # Only the negotiated mutex boundary compares these bytes before
        # returning to JIT. Membership requires exact or entry-guarded address coverage
        # for EVERY possible RSP, not just an entry disjointness
        # predicate or an assumption that the waiter's stack is private.
        windows = tuple(self.address(pointer) for pointer in checked_windows)
        if (
            not 0 < window_bytes <= self.MAX_BYTES
            or not windows
            or len(windows) > self.MAX_VALUES
            or any(window is None for window in windows)
        ):
            windows = ()
        if self.allow_checked_entry_spills and windows and not self.entry_spills_blocked:
            # A spill first read after B may still be the entry value only if
            # EVERY prior native checkpoint covered it. CFG joins union these
            # obligations; opaque calls/writes keep the irreversible block bit.
            self.checked_spill_windows |= frozenset((window, window_bytes) for window in windows)
            if len(self.checked_spill_windows) > 64:
                self.entry_spills_blocked = True
        else:
            self.entry_spills_blocked = True
        if self.entry_spills_blocked:
            self.checked_spill_windows = frozenset()
        if windows and not self.spend(
            len(windows) * (len(self.cells) + len(self.words))
        ):
            self.cells, self.default, self.words = {}, None, {}
            return

        def covered(pointer, size):
            if not windows:
                return False
            address = self.address(pointer)
            return address is not None and all(
                self.checked_coverage(address, window, size, window_bytes)
                for window in windows
            )

        # A call/unmodelled instruction might leave an old value unchanged.
        self.cells = {
            address: domain if covered(address, 1) else self.join(domain, UNKNOWN)
            for address, domain in self.cells.items()
        }
        # An unknown callee can change only part of a word, not merely select
        # one complete old/new value. Preserve complete words only when every
        # byte is checked; partial coverage still uses the byte fallback.
        self.words = {
            memory: domain
            for memory, domain in self.words.items()
            if covered(memory.ptr, memory.size // 8)
        }

    def bounded_words(self, words):
        if (
            len(words) > self.MAX_WORDS
            or sum(key.size // 8 for key in words) > self.MAX_BYTES
        ):
            return {}
        return dict(words)

    def word_load(self, memory):
        values = self.words.get(memory)
        shift = 0
        if values is None:
            if not self.spend(len(self.words)):
                return (wide_value(memory.size),)
            address = self.address(memory.ptr)
            for key in sorted(self.words, key=lambda item: (item.size, str(item.ptr))):
                domain = self.words[key]
                base = self.address(key.ptr)
                if address is None or base is None or address[0] != base[0]:
                    continue
                offset = (address[1] - base[1]) & ((1 << 64) - 1)
                if offset * 8 + memory.size <= key.size:
                    values, shift = domain, offset * 8
                    break
        if values is None:
            return None
        if not self.spend(memory.size // 8 + len(values)):
            return (wide_value(memory.size),)
        mask = (1 << memory.size) - 1
        projected = {(value >> shift) & mask for value in values}
        if len(projected) > self.MAX_COMBINATIONS:
            return (wide_value(memory.size),)
        return tuple(ExprInt(value, memory.size) for value in sorted(projected))

    def load(self, memory):
        self.check_control_access(memory)
        result = self.load_unchecked(memory)
        if self.load_guard is None or not any(is_wide(value) for value in result):
            return result
        excluded = self.load_guard(memory)
        if not excluded:
            return result
        # The emitted predicate excludes these exact stack aliases for this
        # load only. Keep every other cell and the global uncertainty default;
        # neither the next instruction nor another path inherits disjointness.
        cells = self.cells
        self.cells = {key: value for key, value in cells.items() if key not in excluded}
        try:
            return self.load_unchecked(memory)
        finally:
            self.cells = cells

    def load_unchecked(self, memory):
        size = (memory.size + 7) // 8
        if memory.size % 8 or size > self.MAX_ACCESS_BYTES:
            return (wide_value(memory.size),)
        values = self.word_load(memory)
        if values is not None:
            return values
        values = self.call_alias_load(memory)
        if values is not None:
            return values
        pointers = [self.offset(memory.ptr, i) for i in range(size)]
        if not self.spend(
            sum(
                1 if pointer in self.cells else len(self.cells) + 1
                for pointer in pointers
            )
        ):
            return (wide_value(memory.size),)
        domains = [self.byte_at(pointer) for pointer in pointers]
        if all(domain == UNKNOWN for domain in domains):
            return (memory,)
        combinations = 1
        for domain in domains:
            if domain is None:
                return (wide_value(memory.size),)
            combinations *= len(domain)
        if combinations > self.MAX_COMBINATIONS or not self.spend(combinations):
            return (wide_value(memory.size),)
        results = set()
        for pieces in product(*domains):
            if all(piece is None for piece in pieces):
                results.add(memory)
            elif any(piece is None for piece in pieces):
                # Unmodelled bytes can form a new address, not just an old/new
                # whole-word candidate. Do not silently forget this dependency.
                results.add(wide_value(memory.size))
            else:
                results.add(expr_simp(ExprCompose(*pieces)))
        return tuple(sorted(results, key=str))

    def call_alias_load(self, memory):
        """Keep original-load provenance for one possible source CALL word.

        Partial masks retain their known bases and high-prefix ranges through
        copies/dereferences/constant offsets. Bit extraction, stores and control
        uses cannot erase this provenance. A full overlap retains every numeric
        return address. This remains screening, not arbitrary pointer validation.
        No byte is omitted from lowering and no overlap is ruled out.
        """
        if (memory.size != 64 or not self.call_words or len(self.call_words) != 1
                or self.default != UNKNOWN):
            return None
        word, values = next(iter(self.call_words.items()))
        base = self.address(word.ptr)
        if base is None or not values or len(values) >= self.MAX_VALUES:
            return None
        if len(values) + 1 > self.MAX_COMBINATIONS:
            return (wide_value(memory.size),)
        if not self.spend(len(self.cells) + len(values) + 1):
            return (wide_value(memory.size),)
        # Only the recorded CALL bytes may have introduced precision. Even a
        # wide cell left by an exhausted merge prevents this refinement.
        for pointer, domain in self.cells.items():
            address = self.address(pointer)
            if (domain is None or address is None or address[0] != base[0]
                    or ((address[1] - base[1]) & ((1 << 64) - 1)) >= 8):
                return None
        # This refinement preserves aliases; it must not create an entry
        # predicate merely because both addresses have entry identities.
        starts = self.placements(memory, word.ptr, 64, use_guards=False)
        if starts == [None]:
            return None
        patterns = set()
        for start in starts:
            if start is None or start == 0:
                continue
            low, high = max(0, start), min(8, start + 8)
            mask = ((1 << ((high - low) * 8)) - 1) << (low * 8)
            for value in values:
                bits = ((value >> (max(0, -start) * 8)) << (low * 8)) & mask
                patterns.add((mask, bits, 0))
        if (len(patterns) > MAX_CALL_PATTERNS
                or not self.spend(len(starts) * len(values) + len(patterns))):
            return (wide_value(memory.size, "call_patterns"),)
        result = [call_alias_value(64, patterns=patterns)]
        if 0 in starts:
            result.extend(ExprInt(value, 64) for value in sorted(values))
        return tuple(result)

    def placements(self, memory, pointer, width, *, use_guards=True):
        address, base = self.address(pointer), self.address(memory.ptr)
        size, written = memory.size // 8, width // 8
        if use_guards and self.guards is not None and self.guards.separate(
            address, base, written, size
        ):
            return [None]
        if address is None or base is None or address[0] != base[0]:
            return [None, *range(1 - written, size)]
        delta = (address[1] - base[1]) & ((1 << 64) - 1)
        if delta < size:
            return [delta]
        backwards = (-delta) & ((1 << 64) - 1)
        return [-backwards] if backwards < written else [None]

    def written_words(self, old, writes, rmw):
        if not self.spend(len(old) * sum(len(pointers) for pointers, _, _ in writes)):
            return {}
        words = {
            memory: domain
            for memory, domain in old.items()
            if all(
                self.placements(memory, pointer, width) == [None]
                for pointers, _, width in writes
                for pointer in pointers
            )
        }
        for index, (pointers, values, width) in enumerate(writes):
            if len(pointers) != 1 or not values or len(values) > self.MAX_VALUES:
                continue
            pointer = next(iter(pointers))
            if self.address(pointer) is None or not all(
                isinstance(value, ExprInt) for value in values
            ):
                continue
            memory = ExprMem(pointer, width)
            if any(
                self.placements(memory, other, size) != [None]
                for other_index, (destinations, _, size) in enumerate(writes)
                if other_index != index
                for other in destinations
            ):
                continue
            if not self.spend(len(values)):
                return {}
            words[memory] = frozenset(int(value) for value in values)
        if rmw is not None and len(writes) == 1:
            operation, amount = rmw
            pointers, _, width = writes[0]
            for memory, domain in old.items():
                updated = set()
                for pointer in pointers:
                    starts = self.placements(memory, pointer, width)
                    if not self.spend(len(starts) * len(domain)):
                        return {}
                    for start, value in product(starts, domain):
                        updated.update(
                            rmw_word_values(
                                value,
                                memory.size // 8,
                                width // 8,
                                start,
                                operation,
                                amount,
                            )
                        )
                if updated and len(updated) <= self.MAX_VALUES:
                    words[memory] = frozenset(updated)
                else:
                    words.pop(memory, None)
        return self.bounded_words(words)

    def store(self, writes, *, rmw=None, call_return=False, audited_call=False):
        """Apply one parallel IR assignment, resolving all writes in the old state.

        Each write is (possible pointers, possible values, bit width). Only a
        proven covering write removes an old byte; possible aliases are weak
        updates. Partial writes are combined at byte granularity on reload.
        """
        expanded = []
        keys = set(self.cells)
        default = self.default
        if not writes:
            return
        if audited_call:
            if not call_return:
                raise AuditedScratchAccess("audited C effect lacks an original CALL store")
            self.store_control_return(writes)
            return
        if call_return:
            self.replace_control_return(writes)
        else:
            for pointers, _, width in writes:
                for pointer in pointers:
                    self.check_control_access(ExprMem(pointer, width))
        self.record_call_write(writes, call_return)
        old_words, self.words = self.words, {}
        candidates = sum(
            len(pointers) * ((width + 7) // 8) for pointers, _, width in writes
        )
        value_bytes = sum(
            len(values) * ((width + 7) // 8) for _, values, width in writes
        )
        if not self.spend(candidates + value_bytes):
            self.cells, self.default = {}, None
            self.call_words = None
            return
        for pointers, values, width in writes:
            size = (width + 7) // 8
            if (
                width % 8
                or size > self.MAX_ACCESS_BYTES
                or len(pointers) > self.MAX_VALUES
                or len(values) > self.MAX_VALUES
            ):
                self.cells, self.default = {}, None
                self.call_words = None
                return
            byte_values = []
            for i in range(size):
                domain = frozenset()
                for value in values:
                    part = (
                        None
                        if is_wide(value) or has_call_alias(value)
                        else frozenset(
                            {
                                expr_simp(value[i * 8 : (i + 1) * 8])
                                if isinstance(value, ExprInt)
                                or self.address(value) is not None
                                else None
                            }
                        )
                    )
                    domain = self.join(domain, part)
                byte_values.append(domain)
            alternatives = []
            any_byte = frozenset()
            for domain in byte_values:
                any_byte = self.join(any_byte, domain)
            for pointer in pointers:
                address = self.address(pointer)
                alternatives.append(address)
                if address is None:
                    self.entry_spills_blocked = True
                    default = self.join(default, any_byte)
                else:
                    keys.update(self.offset(pointer, i) for i in range(size))
            expanded.append((alternatives, byte_values, any_byte))
        cost = len(keys) * (sum(len(pointers) for pointers, _, _ in writes) + 1) + len(
            keys - self.cells.keys()
        ) * len(self.cells)
        if len(keys) > self.MAX_BYTES or not self.spend(cost):
            self.cells, self.default = {}, None
            self.call_words = None
            return
        updated = {}
        for key in keys:
            location = self.address(key)
            definite = False
            changes = frozenset()
            for alternatives, byte_values, any_byte in expanded:
                covers = []
                for address in alternatives:
                    if (
                        location is not None
                        and address is not None
                        and location[0] == address[0]
                    ):
                        # With one proven base, at most one byte can hit this
                        # cell, including a write wrapping the x86 address width.
                        delta = (location[1] - address[1]) & ((1 << 64) - 1)
                        covered = delta < len(byte_values)
                        covers.append(covered)
                        if covered:
                            changes = self.join(changes, byte_values[delta])
                    elif self.guards is not None and self.guards.separate(
                        location, address, right_size=len(byte_values)
                    ):
                        # This is conditional disjointness: every such decision
                        # checks the entire write, not only its first byte.
                        covers.append(False)
                    else:
                        covers.append(False)
                        changes = self.join(changes, any_byte)
                definite |= bool(covers) and all(covers)
            updated[key] = (
                changes if definite else self.join(self.byte_at(key), changes)
            )
        # A wide fallback already represents every wide byte. Retaining those
        # entries adds merge work but no fact; exact overwrites remain explicit.
        if default is None:
            updated = {
                key: domain for key, domain in updated.items() if domain is not None
            }
        self.cells, self.default = updated, default
        self.words = self.written_words(old_words, writes, rmw)

    def record_call_write(self, writes, call_return):
        if self.call_words is None:
            return
        if not call_return or len(writes) != 1:
            self.call_words = None
            return
        pointers, values, width = writes[0]
        if (width != 64 or len(pointers) != 1 or not values
                or any(not isinstance(value, ExprInt) for value in values)):
            self.call_words = None
            return
        pointer = next(iter(pointers))
        word = ExprMem(pointer, 64)
        if (self.address(pointer) is None
                or (self.call_words and word not in self.call_words)):
            self.call_words = None
            return
        domain = self.call_words.get(word, frozenset()) | frozenset(map(int, values))
        self.call_words = {word: domain} if len(domain) < self.MAX_VALUES else None


class MemoryChoice(Exception):
    def __init__(self, memory, values):
        super().__init__(str(memory))
        self.memory, self.values = memory, values


class MemoryEngine(SymbolicExecutionEngine):
    def __init__(self, lifter, values, memory, choices, widened):
        super().__init__(lifter, values)
        self.memory, self.choices = memory, choices
        self.widened = widened

    def mem_read(self, memory):
        if memory in self.choices:
            return self.choices[memory]
        values = self.memory.load(memory)
        # Distinct unresolved cells are not the same symbolic value. Within an
        # assignment, two reads of the same cell do share the old value.
        if any(is_wide(value) for value in values):
            wide = self.widened.setdefault(
                memory, wide_value(memory.size, len(self.widened))
            )
            values = tuple(wide if is_wide(value) else value for value in values)
        if any(has_call_alias(value) for value in values):
            # Separate reads must not cancel as the same arbitrary value.
            opaque = self.widened.setdefault(
                ("call_alias", memory), merge_call_aliases(
                    values, memory.size, len(self.widened)))
            values = tuple(opaque if has_call_alias(value) else value for value in values)
        if len(values) == 1:
            return values[0]
        raise MemoryChoice(memory, values)


def evaluate(lifter, expression, registers, memory):
    """Enumerate demanded memory values, with bounded forks including nested loads."""
    pending = [{}]
    results = set()
    widened = {}
    visits = 0
    while pending:
        choices = pending.pop()
        visits += 1
        if visits > memory.MAX_COMBINATIONS:
            return (wide_value(expression.size),)
        try:
            result = MemoryEngine(
                lifter, registers, memory, choices, widened
            ).eval_expr(expression)
        except MemoryChoice as demand:
            if visits + len(pending) + len(demand.values) > memory.MAX_COMBINATIONS:
                return (wide_value(expression.size),)
            pending.extend(choices | {demand.memory: value} for value in demand.values)
        else:
            results.add(result)
    return tuple(sorted(results, key=str))
