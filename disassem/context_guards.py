"""Entry-time disjointness preconditions, not assumed object/stack privacy.

Guards compare saved entry-register values without dereferencing their targets.
Caller-clobber guards may also read untouched initial stack words, after checking
every source word against the saved SP/BP bounds before any dereference.
They must run before any translated instruction; a failed guard is unstarted
work, never permission to replay an already executed critical section.

The kernel validates the first dispatch's logical scope: a non-root entry must
inherit a published parent's admitted CALL continuation. In-place code version
replacement is still a separate, explicitly deferred limitation.
"""

from collections import defaultdict

MASK = (1 << 64) - 1
# Keep in sync with KD_EXE_ENTRY_REFUSED, a runtime-only wrapper result.
ENTRY_REFUSED = 6
REGISTER_OFFSETS = {
    name: offset * 8
    for offset, name in enumerate(
        (
            "R15",
            "R14",
            "R13",
            "R12",
            "RBP",
            "RBX",
            "R11",
            "R10",
            "R9",
            "R8",
            "RAX",
            "RCX",
            "RDX",
            "RSI",
            "RDI",
        )
    )
} | {"RSP": 0x98}


def signed_offset(offset):
    offset &= MASK
    return offset - (1 << 64) if offset >> 63 else offset


def merge_ranges(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1] = result[-1][0], max(result[-1][1], end)
        else:
            result.append((start, end))
    return result


class EntryGuards:
    """Collect all speculative alias separations, bounded independently of IR."""

    MAX_RANGES = 1024
    MAX_GUARDS = 256

    def __init__(self):
        self.ranges = defaultdict(lambda: (set(), set()))
        self.range_count = 0
        self.failed = False
        self.spills = {}
        self.scaled_spills = {}

    def base_name(self, base):
        if base is None:
            return ""
        text = str(base)
        if not text.startswith("kd_entry_"):
            return None
        name = text.removeprefix("kd_entry_")
        return name if name in REGISTER_OFFSETS or name in self.spills or name in self.scaled_spills else None

    def stack_value(self, address):
        """Name an untouched entry stack word; emit bounds before dereference.

        Only the caller-clobber analysis requests these identities. They are
        conditional entry inputs, never a new captured GPR or an assumed
        private stack. The memory analysis must prove no earlier write aliases
        the source word before requesting this identity.
        """
        if address is None:
            return None
        base, offset = self.base_name(address[0]), signed_offset(address[1])
        if base not in {"RBP", "RSP"} or not -16384 <= offset <= 16384:
            return None
        slot = (base, offset)
        for name, previous in self.spills.items():
            if previous == slot:
                return name
        if len(self.spills) >= 64:
            self.failed = True
            return None
        name = f"SPILL_{len(self.spills)}"
        self.spills[name] = slot
        return name

    def scaled_stack_value(self, source, shift):
        """Track a compiler's power-of-two array index from one initial slot.

        The runtime predicate performs the identical modulo-64-bit shift.
        Do not infer a range for the index or assume its target is disjoint.
        """
        if source not in self.spills or not 0 < shift < 64:
            return None
        for name, value in self.scaled_spills.items():
            if value == (source, shift):
                return name
        if len(self.scaled_spills) >= 64:
            self.failed = True
            return None
        name = f"SCALED_{len(self.scaled_spills)}"
        self.scaled_spills[name] = source, shift
        return name

    def register_dependencies(self):
        names = {name for condition in self.conditions() for name in (condition[0], condition[3]) if name}
        return (names - self.spills.keys() - self.scaled_spills.keys()) | ({"RSP", "RBP"} if self.spills else set())

    def separate(self, left, right, left_size=1, right_size=1):
        if self.failed or left is None or right is None or left[0] == right[0]:
            return False
        a, b = self.base_name(left[0]), self.base_name(right[0])
        if a is None or b is None or min(left_size, right_size) <= 0:
            return False
        x, y = signed_offset(left[1]), signed_offset(right[1])
        if a > b:
            a, b, x, y, left_size, right_size = b, a, y, x, right_size, left_size
        first, second = self.ranges[a, b]
        before = len(first) + len(second)
        first.add((x, x + left_size))
        second.add((y, y + right_size))
        # Byte-wise spill proofs repeatedly add overlapping subranges. Count
        # their exact union, as emission already does, instead of exhausting
        # the bound on redundant encodings of the same address conditions.
        for ranges in (first, second):
            merged = merge_ranges(ranges)
            ranges.clear()
            ranges.update(merged)
        self.range_count += len(first) + len(second) - before
        if self.range_count > self.MAX_RANGES:
            self.failed = True
            return False
        return True

    def conditions(self):
        if self.failed:
            raise ValueError("entry disjointness guard collection exhausted")
        conditions = []
        for (a, b), (left, right) in sorted(self.ranges.items()):
            # Cross products can strengthen the conditions, never omit a
            # recorded separation. Keep gaps so unrelated objects stay distinct.
            for x, end_x in merge_ranges(left):
                for y, end_y in merge_ranges(right):
                    if max(end_x - x, end_y - y) >= 1 << 31:
                        raise ValueError("entry guard range exceeds encoding limit")
                    conditions.append((a, x, end_x - x, b, y, end_y - y))
                    if len(conditions) > self.MAX_GUARDS:
                        raise ValueError("entry disjointness guard count exhausted")
        return conditions

    def accepts(self, registers, memory=None):
        """Reference predicate uses x86 modulo-64-bit addresses, including wrap."""
        registers = dict(registers)
        for name, (base, offset) in self.spills.items():
            address = (registers[base] + offset) & MASK
            if not registers["RSP"] <= address <= registers["RBP"] - 8:
                return False
            if memory is None:
                raise ValueError("stack-value predicates require entry memory")
            registers[name] = memory[address]
        for name, (source, shift) in self.scaled_spills.items():
            registers[name] = (registers[source] << shift) & MASK
        for a, x, n, b, y, m in self.conditions():
            left, right = registers[a] if a else 0, registers[b] if b else 0
            delta = (left + x - right - y) & MASK
            if delta < m or (-delta & MASK) < n:
                return False
        return True

    def emit(self, output, entry):
        """Borrow R11 only before execution, restoring its packet-base role.

        No virtual spills run during these predicates. Both accepted and refused
        edges must restore R11 before the body or full-exit materialization.
        """
        conditions = self.conditions()
        if not conditions and not self.spills:
            return
        output.write("/* Verify entry alias premises before any JIT body label. */\n")
        output.write("MOV R14, Stack_PT_REG\nMOV R14, [R14 + 0x80]\n")
        output.write(f"MOVABS R15, 0x{entry:x}\nCMP R14, R15\n")
        output.write("JNE kd_entry_guards_done\n")
        # Validate every source slot before loading any spill value. SP/BP are
        # the only register inputs; the original waiter is already off-stack.
        for base, offset in self.spills.values():
            output.write(f"MOV R14, Stack_PT_REG\nMOV R14, [R14 + {REGISTER_OFFSETS[base]}]\n")
            output.write(f"LEA R14, [R14 + {offset}]\n")
            output.write("MOV R15, Stack_PT_REG\nMOV R15, [R15 + 0x98]\n")
            output.write("CMP R14, R15\nJB kd_entry_guard_refused\n")
            output.write("LEA R11, [R14 + 8]\nCMP R11, R14\nJB kd_entry_guard_refused\n")
            output.write("MOV R15, Stack_PT_REG\nMOV R15, [R15 + 0x20]\n")
            output.write("CMP R11, R15\nJA kd_entry_guard_refused\n")
        for a, x, n, b, y, m in conditions:
            for name, register in ((a, "R14"), (b, "R15")):
                shift = 0
                if name in self.scaled_spills:
                    name, shift = self.scaled_spills[name]
                if name in self.spills:
                    base, offset = self.spills[name]
                    output.write(f"MOV {register}, Stack_PT_REG\nMOV {register}, [{register} + {REGISTER_OFFSETS[base]}]\n")
                    output.write(f"MOV {register}, [{register} + {offset}]\n")
                elif name:
                    output.write(f"MOV {register}, Stack_PT_REG\n")
                    output.write(
                        f"MOV {register}, [{register} + {REGISTER_OFFSETS[name]}]\n"
                    )
                else:
                    output.write(f"MOV {register}, 0\n")
                if shift:
                    output.write(f"SHL {register}, {shift}\n")
            output.write("SUB R14, R15\n")
            output.write(f"MOVABS R11, 0x{(x - y) & MASK:x}\nADD R14, R11\n")
            output.write(f"CMP R14, {m}\nJB kd_entry_guard_refused\n")
            output.write(f"NEG R14\nCMP R14, {n}\nJB kd_entry_guard_refused\n")
        output.write("JMP kd_entry_guards_done\nkd_entry_guard_refused:\n")
        output.write("MOV R14, Stack_PT_REG\nMOV R14, [R14 + 0x80]\n")
        output.write(f"MOV Stack_IJ, {ENTRY_REFUSED}\nMOV REG_BANK, Stack_PT_REG\nJMP exit\n")
        # The existing dispatcher still expects PT_REG (R14) to be a pointer.
        output.write("kd_entry_guards_done:\nMOV REG_BANK, Stack_PT_REG\nMOV R14, Stack_PT_REG\n")
