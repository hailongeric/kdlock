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


def is_wide(value):
    return any(
        isinstance(item, ExprId) and str(item).startswith(WIDE_PREFIX)
        for item in value.get_r(mem_read=True)
    )


def wide_value(size, name="budget"):
    return ExprId(WIDE_PREFIX + str(name), size)


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
        self.work = 0

    def spend(self, amount):
        # Work is translation-local, not path-local: restoring a CFG snapshot
        # must not replenish an exhausted analysis budget.
        self.work += amount
        return self.work <= self.MAX_WORK

    def snapshot(self):
        return dict(self.cells), self.default, dict(self.words)

    def restore(self, state):
        self.cells, self.default = dict(state[0]), state[1]
        self.words = dict(state[2])

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
        keys = left[0].keys() | right[0].keys()
        if len(keys) > self.MAX_BYTES:
            return {}, None, {}
        if left == right:
            if not self.spend(len(keys) + len(left[2]) + 1):
                return {}, None, {}
            return dict(left[0]), left[1], self.bounded_words(left[2])
        # Exact cells use a dictionary lookup; only missing cells scan aliases.
        # Restore each side once instead of copying both maps for every byte.
        cost = (
            2 * len(keys)
            + len(left[0].keys() - right[0].keys()) * len(right[0])
            + len(right[0].keys() - left[0].keys()) * len(left[0])
        )
        if not self.spend(cost):
            return {}, None, {}
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
                return {}, None, {}
            domain = a | b
            if len(domain) <= self.MAX_VALUES:
                words[memory] = domain
        return result, default, self.bounded_words(words)

    def clobber(self, *, checked_windows=(), window_bytes=0):
        # Only the negotiated mutex boundary compares these bytes before
        # returning to JIT. Membership requires the same exact address base
        # and full coverage for EVERY possible RSP, not an entry disjointness
        # predicate or an assumption that the waiter's stack is private.
        windows = tuple(self.address(pointer) for pointer in checked_windows)
        if (
            not 0 < window_bytes <= self.MAX_BYTES
            or not windows
            or len(windows) > self.MAX_VALUES
            or any(window is None for window in windows)
        ):
            windows = ()
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
                address[0] == base
                and ((address[1] - start) & ((1 << 64) - 1)) + size <= window_bytes
                for base, start in windows
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
        size = (memory.size + 7) // 8
        if memory.size % 8 or size > self.MAX_ACCESS_BYTES:
            return (wide_value(memory.size),)
        values = self.word_load(memory)
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

    def placements(self, memory, pointer, width):
        address, base = self.address(pointer), self.address(memory.ptr)
        size, written = memory.size // 8, width // 8
        if self.guards is not None and self.guards.separate(
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

    def store(self, writes, *, rmw=None):
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
        old_words, self.words = self.words, {}
        candidates = sum(
            len(pointers) * ((width + 7) // 8) for pointers, _, width in writes
        )
        value_bytes = sum(
            len(values) * ((width + 7) // 8) for _, values, width in writes
        )
        if not self.spend(candidates + value_bytes):
            self.cells, self.default = {}, None
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
                return
            byte_values = []
            for i in range(size):
                domain = frozenset()
                for value in values:
                    part = (
                        None
                        if is_wide(value)
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
                    default = self.join(default, any_byte)
                else:
                    keys.update(self.offset(pointer, i) for i in range(size))
            expanded.append((alternatives, byte_values, any_byte))
        cost = len(keys) * (sum(len(pointers) for pointers, _, _ in writes) + 1) + len(
            keys - self.cells.keys()
        ) * len(self.cells)
        if len(keys) > self.MAX_BYTES or not self.spend(cost):
            self.cells, self.default = {}, None
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
