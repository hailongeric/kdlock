"""Entry-time disjointness preconditions, not assumed object/stack privacy.

Guards compare saved entry-register values without dereferencing their targets.
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

    @staticmethod
    def base_name(base):
        if base is None:
            return ""
        text = str(base)
        if not text.startswith("kd_entry_"):
            return None
        name = text.removeprefix("kd_entry_")
        return name if name in REGISTER_OFFSETS else None

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

    def accepts(self, registers):
        """Reference predicate uses x86 modulo-64-bit addresses, including wrap."""
        for a, x, n, b, y, m in self.conditions():
            left, right = registers[a] if a else 0, registers[b] if b else 0
            delta = (left + x - right - y) & MASK
            if delta < m or (-delta & MASK) < n:
                return False
        return True

    def emit(self, output, entry):
        """Use only already-spilled R14/R15 and the non-guest R11 scratch slot."""
        conditions = self.conditions()
        if not conditions:
            return
        output.write("/* Verify entry alias premises before any JIT body label. */\n")
        output.write("MOV R14, Stack_PT_REG\nMOV R14, [R14 + 0x80]\n")
        output.write(f"MOVABS R15, 0x{entry:x}\nCMP R14, R15\n")
        output.write("JNE kd_entry_guards_done\n")
        for a, x, n, b, y, m in conditions:
            for name, register in ((a, "R14"), (b, "R15")):
                if name:
                    output.write(f"MOV {register}, Stack_PT_REG\n")
                    output.write(
                        f"MOV {register}, [{register} + {REGISTER_OFFSETS[name]}]\n"
                    )
                else:
                    output.write(f"MOV {register}, 0\n")
            output.write("SUB R14, R15\n")
            output.write(f"MOVABS R11, 0x{(x - y) & MASK:x}\nADD R14, R11\n")
            output.write(f"CMP R14, {m}\nJB kd_entry_guard_refused\n")
            output.write(f"NEG R14\nCMP R14, {n}\nJB kd_entry_guard_refused\n")
        output.write("JMP kd_entry_guards_done\nkd_entry_guard_refused:\n")
        output.write("MOV R14, Stack_PT_REG\nMOV R14, [R14 + 0x80]\n")
        output.write(f"MOV Stack_IJ, {ENTRY_REFUSED}\nJMP exit\n")
        # The existing dispatcher still expects PT_REG (R14) to be a pointer.
        output.write("kd_entry_guards_done:\nMOV R14, Stack_PT_REG\n")
