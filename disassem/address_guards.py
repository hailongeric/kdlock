"""Checked disjointness for pointer loads after source-stack writes.

The ordinary byte/alias analysis remains authoritative. This optional retry can
replace only stack-store alias alternatives by a predicate at the actual load.
It never declares a widened register or opaque memory value safe. A failed
predicate resumes the original waiter before that MOV, without replaying work.
"""

from dataclasses import dataclass, field
from io import StringIO

from miasm.expression.expression import ExprId, ExprInt, ExprMem, ExprOp

from context_guards import merge_ranges, signed_offset
from context_registers import ContextFlowLimit


EXIT = 9
REQUIREMENT = 2
TAG = 0x4b44414700000000


@dataclass
class GuardSite:
    line: object
    memory: object
    ranges: set = field(default_factory=set)


class AddressGuards:
    MAX_SITES = 64
    MAX_RANGES = 64
    MAX_DISPLACEMENT = 16384

    def __init__(self):
        self.sites = {}

    def stack_aliases(self, line, memory, tracker):
        """Return cells excluded by a real predicate, or no precision change.

        Only the explicit 64-bit MOV source can request this predicate. A known
        same-location load must keep its actual stored value. Runtime checks
        exclude complete read/write overlap, including modulo-address wrap.
        """
        model = tracker.memory
        if (line is None or line.name.upper() != "MOV" or len(line.args) != 2
                or not isinstance(line.args[0], ExprId)
                or not isinstance(line.args[1], ExprMem)
                or line.args[1].size != 64 or memory.size != 64
                or model.default != frozenset({None}) or not model.cells):
            return frozenset()
        operand = line.args[1]
        raw = bytes(line.b)
        if not (3 <= len(raw) <= 8 and 0x48 <= raw[0] <= 0x4f
                and raw[1] == 0x8b and raw[2] >> 6 != 3):
            return frozenset()
        if any(str(reg).upper() in {"FS", "GS", "RIP"}
               for reg in operand.ptr.get_r(mem_read=True)):
            return frozenset()
        terms = (operand.ptr.args if isinstance(operand.ptr, ExprOp)
                 and operand.ptr.op == "+" else (operand.ptr,))
        if (sum(isinstance(part, ExprId) for part in terms) != 1
                or not all(isinstance(part, (ExprId, ExprInt)) for part in terms)):
            return frozenset()
        # Origin facts exist only for exact base+offset identities; resolving a
        # second memory expression here could recursively request a new guard.
        frames = {}
        for name in ("RSP", "RBP"):
            reg = ExprId(name, 64)
            if tracker.values.get(reg, tracker.UNKNOWN) != tracker.UNKNOWN:
                continue
            origin = tracker.origins.get(reg)
            address = model.address(origin) if origin is not None else None
            if address is not None:
                frames[name] = address
        if not frames:
            return frozenset()
        keys, ranges = set(), set()
        for pointer in model.cells:
            # Keep definite overlap and existing disjointness untouched.
            relations = [model.relation(model.offset(memory.ptr, i), pointer)
                         for i in range(8)]
            if True in relations or all(value is False for value in relations):
                continue
            address = model.address(pointer)
            if address is None:
                continue
            for name, frame in frames.items():
                if address[0] != frame[0]:
                    continue
                delta = signed_offset(address[1] - frame[1])
                if abs(delta) > self.MAX_DISPLACEMENT:
                    continue
                keys.add(pointer)
                ranges.add((name, delta, delta + 1))
                break
        if not keys:
            return frozenset()
        previous = self.sites.get(line.offset)
        if previous is not None and (
                bytes(previous.line.b) != bytes(line.b)
                or previous.memory != operand):
            raise ContextFlowLimit("inconsistent address guard source", line.offset)
        ranges |= previous.ranges if previous is not None else set()
        merged = set()
        for name in ("RSP", "RBP"):
            merged.update((name, left, right) for left, right in merge_ranges(
                (left, right) for base, left, right in ranges if base == name))
        if ((previous is None and len(self.sites) >= self.MAX_SITES)
                or len(merged) > self.MAX_RANGES):
            raise ContextFlowLimit("address guard collection exceeds its budget",
                                   line.offset)
        self.sites[line.offset] = GuardSite(line, operand, merged)
        return frozenset(keys)

    def validate(self, blocks, databases, terminal_calls=(), flag_dead_calls=()):
        import guard_flags

        for offset in sorted(self.sites):
            reason = guard_flags.prove_flags_dead(
                blocks, databases, offset, terminal_calls=terminal_calls,
                flag_dead_calls=flag_dead_calls)
            if reason is not None:
                raise ContextFlowLimit(reason, offset, self.sites[offset].line)

    def emit(self, line, reg_map):
        """Check an actual read address before executing its original MOV."""
        from conflict import block_init, reverse_reg, spill_register
        from normal import process_normal

        site = self.sites.get(line.offset)
        if site is None:
            return ""
        index = sorted(self.sites).index(line.offset)
        failed = f"kd_address_guard_failed_{line.offset:x}"
        done = f"kd_address_guard_done_{line.offset:x}"
        code = "/* Checked source-stack alias exclusion; no body replay. */\n"
        # Normalize the same shared register bank used by block boundaries.
        # Physical SP/BP may have moved inside the scratch pool. Save both
        # before restoring their stable positions, without whole-packet copies.
        for physical, logical in reg_map.items():
            if logical and logical not in {"T1", "T2", "IP", "FS", "GS", "CT"}:
                code += spill_register(reg_map, physical)
        code += "MOV R12, Stack_RBP\nMOV R13, Stack_RSP\nPUSHFQ\n"
        reg_map.clear()
        reg_map.update(block_init())
        reg_map.dirty.clear()
        for base, start, end in sorted(site.ranges):
            code += process_normal("LEA", [ExprId("RT1", 64), site.memory],
                                   line.offset + line.l, reg_map)
            pointer = "R" + reverse_reg(reg_map, ExprId("RT1", 64))
            if pointer != "R14":
                code += f"MOV R14, {pointer}\n"
            # LEA lowering restores stable SP/BP. Scratch registers loaded
            # solely to compute this address are unchanged source values.
            reg_map.clear()
            reg_map.update(block_init())
            reg_map.dirty.clear()
            code += f"LEA R15, [{'R13' if base == 'RSP' else 'R12'} + {start}]\n"
            code += f"SUB R14, R15\nCMP R14, {end - start}\nJB {failed}\n"
            code += f"NEG R14\nCMP R14, 8\nJB {failed}\n"
        code += f"POPFQ\nJMP {done}\n{failed}:\n"
        # The source flags-dead proof authorizes this one native continuation.
        # Remove the executor's saved flags word and preserve exact source SP.
        code += "LEA RSP, [RSP + 8]\n"
        code += f"MOVABS R14, 0x{TAG | index:x}\nMOV QWORD PTR[REG_BANK + KD_REG_ORIG_AX], R14\n"
        code += f"MOVABS R14, 0x{line.offset:x}\nMOV Stack_IJ, {EXIT}\nJMP full_exit\n"
        code += done + ":\n"
        return code

    def metadata(self):
        """Emit the immutable provider-validated source-site directory."""
        output = StringIO()
        output.write("kd_address_guard_records:\n")
        for offset in sorted(self.sites):
            raw = bytes(self.sites[offset].line.b)
            output.write(f".quad 0x{offset:x}\n.byte {len(raw)}, 1\n.zero 6\n")
            output.write(".byte " + ", ".join(str(byte) for byte in raw) + "\n")
            output.write(f".zero {16 - len(raw)}\n")
        output.write('.ascii "KDAG0001"\n.long kd_address_guard_records - main\n')
        output.write(f".long {len(self.sites)}\n")
        return output.getvalue()
