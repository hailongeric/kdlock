"""Execute bounded entry predicates, never the speculative kernel-text replays."""

import ctypes
import io
import random
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "disassem"))

from context_guards import ENTRY_REFUSED, MASK, REGISTER_OFFSETS, EntryGuards
from miasm.expression.expression import ExprId, ExprInt, ExprMem
from test_jit_body_witness import render, run_image
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, decode, translator
from test_jit_diagnostics import render as translator_render


def address(name, offset=0):
    return ExprId("kd_entry_" + name, 64) if name else None, offset & MASK


def guarded(guards, raw="48c7c02a000000c3"):
    output = io.StringIO()
    guards.emit(output, 0x1000)
    assembly, _ = render(raw)
    return output.getvalue().encode("ascii") + assembly


class EntryGuardTests(unittest.TestCase):
    def test_nested_precision_retry_fetches_and_checks_cold_paths(self):
        def call(name, offset):
            return b"\xe8" + struct.pack("<i", TEST_LOCK_SYMBOLS[name] - offset - 5)

        prefix = bytes.fromhex("4d892c24c645f830498b04244c8930")
        prefix += call("_raw_spin_lock", 0x1000 + len(prefix))
        prefix += b"\xe9" + struct.pack("<i", 0x3000 - (0x1000 + len(prefix) + 5))
        initial = (prefix, 0x1000, [0x1000])
        for unsafe in (False, True):
            cold = bytes.fromhex("65488b042500000000") if unsafe else b""
            cold += call("_raw_spin_unlock", 0x3000 + len(cold))
            cold += call("_raw_spin_unlock", 0x3000 + len(cold))
            # Only the text-read boundary is mocked. Actual CFG scope, flow
            # analysis and emission must include and check the fetched branch.
            with (
                self.subTest(unsafe=unsafe),
                patch.object(
                    translator.memread,
                    "extend_regions",
                    return_value=[initial, (cold, 0x3000, [0x3000])],
                ) as extend,
            ):
                assembly, log, status = render(
                    "", regions=[initial], return_status=True
                )
            extend.assert_called_once()
            self.assertIn("ENTRY_GUARD_WAIT_TEXT", log)
            self.assertEqual(status, 2 if unsafe else 0, log)
            if unsafe:
                self.assertEqual(assembly, b"")
                self.assertIn("GS/current", log)
            else:
                self.assertIn("ENTRY_GUARDED_ADMISSION", log)
                self.assertIn(b"kd_entry_guard_refused", assembly)

    def test_automatic_nested_admission_checks_aliases_before_real_stores(self):
        # A partial alias can corrupt the spilled pointer before its use. The
        # safe packet must really execute; the overlapping packet must perform
        # none of these stores, rather than merely losing its body witness.
        raw = bytes.fromhex("4d892c24c645f830498b04244c8930")
        for name in ("_raw_spin_lock", "_raw_spin_unlock", "_raw_spin_unlock"):
            target = TEST_LOCK_SYMBOLS[name]
            raw += b"\xe8" + struct.pack("<i", target - (0x1000 + len(raw) + 5))
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn("ENTRY_GUARDED_ADMISSION", log)
        self.assertIn(b"kd_entry_guard_refused", assembly)
        for overlap in (False, True):
            with self.subTest(overlap=overlap):
                pointer = ctypes.c_ulong(0x1234)
                destination = ctypes.c_ulong(0x5678)
                unrelated = ctypes.c_ulong(0)
                before = []

                def initialize(
                    regs,
                    _,
                    pointer=pointer,
                    destination=destination,
                    base=pointer if overlap else unrelated,
                    before=before,
                ):
                    regs[3] = ctypes.addressof(pointer)
                    regs[2] = ctypes.addressof(destination)
                    regs[1] = 42
                    regs[4] = ctypes.addressof(base) + 8
                    before.append(list(regs))

                regs, args = run_image(assembly, [0x1000], initialize)[0]
                if overlap:
                    self.assertEqual(args, [ENTRY_REFUSED, 0])
                    self.assertEqual(regs, before[0])
                    self.assertEqual(
                        (pointer.value, destination.value), (0x1234, 0x5678)
                    )
                else:
                    self.assertEqual(args, [1, 1])
                    self.assertEqual(regs[16], TEST_LOCK_SYMBOLS["_raw_spin_lock"])
                    self.assertEqual(pointer.value, ctypes.addressof(destination))
                    self.assertEqual((destination.value, unrelated.value), (42, 0x30))

    def test_guarded_analysis_keeps_explicit_context_rejections(self):
        original = translator.find_segment_policy_error

        def check(*args, **kwargs):
            return original(*args, **kwargs, guards=EntryGuards())

        # Use the real scope and policy; only supply the optional collector.
        # Guard assumptions must not bypass GS, IRQ or known-symbol admission.
        for raw in ("65488b042500000000c3", "fac3", "48c7c000300000488b00c3"):
            with (
                self.subTest(raw=raw),
                patch.object(translator, "find_segment_policy_error", check),
            ):
                assembly, log, status = translator_render(
                    raw, symbols={0x3000: "current_task"}, return_status=True
                )
                self.assertEqual(status, translator.context_policy.NATIVE_ONLY_EXIT)
                self.assertEqual(assembly, b"")
                self.assertIn("CONTEXT_NATIVE_ONLY", log)

    def test_entry_guards_require_one_explicit_root(self):
        policy = translator.context_policy
        for roots in (None, {0x1000, 0x2000}):
            with (
                self.subTest(roots=roots),
                self.assertRaisesRegex(
                    policy.ContextFlowLimit, "one explicit CFG root"
                ),
            ):
                list(
                    policy.constant_blocks(
                        {0x1000: object(), 0x2000: object()},
                        {},
                        roots=roots,
                        guards=EntryGuards(),
                    )
                )

    def test_analysis_refuses_exhausted_guard_collection_before_emission(self):
        original = translator.find_segment_policy_error

        def check(*args, **kwargs):
            return original(*args, **kwargs, guards=EntryGuards())

        # Two distinct stores and a RET need byte/word/stack alias premises.
        # A caller must not receive a successful policy verdict for a guard
        # set that cannot be emitted, even when the assembly is never built.
        raw = "49c704241100000049c7450022000000c3"
        for limit in ("MAX_RANGES", "MAX_GUARDS"):
            with (
                self.subTest(limit=limit),
                patch.object(EntryGuards, limit, 0),
                patch.object(translator, "find_segment_policy_error", check),
            ):
                assembly, log, status = translator_render(raw, return_status=True)
                self.assertEqual(status, translator.context_policy.NATIVE_ONLY_EXIT)
                self.assertEqual(assembly, b"")
                self.assertIn("CONTEXT_NATIVE_ONLY", log)
                if limit == "MAX_GUARDS":
                    self.assertIn("entry disjointness guard count exhausted", log)

    def test_store_guard_covers_every_byte_not_only_the_write_start(self):
        guards = EntryGuards()
        left, right = address("R12")[0], address("R13")[0]
        memory = translator.context_policy.context_memory.MemoryValues(
            frozenset({left, right}), guards
        )
        memory.store([({left}, {ExprInt(0x11, 8)}, 8)])
        memory.store([({right}, {ExprInt(0xAABBCCDDEEFF0011, 64)}, 64)])
        self.assertEqual(memory.load(ExprMem(left, 8)), (ExprInt(0x11, 8),))
        # A one-byte guard would incorrectly admit offsets 1..7 even though
        # the concrete store can overwrite the tracked byte at each offset.
        for offset in range(-2, 10):
            self.assertEqual(
                guards.accepts({"R12": 0x1000 + offset, "R13": 0x1000}),
                not 0 <= offset < 8,
            )

    def test_guards_do_not_hide_unknown_writes_or_callee_memory_clobbers(self):
        policy = translator.context_policy
        guards = EntryGuards()
        left = address("R12")[0]
        memory = policy.context_memory.MemoryValues(frozenset({left}), guards)
        memory.store([({left}, {ExprInt(0x11, 64)}, 64)])
        memory.store([({ExprId("unknown", 64)}, {ExprInt(0x30, 8)}, 8)])
        self.assertTrue(
            any(
                policy.context_memory.is_wide(v) for v in memory.load(ExprMem(left, 64))
            )
            or memory.load(ExprMem(left, 64)) != (ExprInt(0x11, 64),)
        )
        memory.clobber()
        self.assertTrue(
            any(
                policy.context_memory.is_wide(v) for v in memory.load(ExprMem(left, 64))
            )
        )
        self.assertEqual(guards.conditions(), [])

    def test_control_effects_preserve_only_saved_registers_not_memory(self):
        policy = translator.context_policy
        line = decode("e800000000")
        for controlled in (False, True):
            with self.subTest(controlled=controlled):
                constants = policy.FlowConstants(EntryGuards())
                original = dict(constants.origins)
                rsp, r12, rax = (ExprId(name, 64) for name in ("RSP", "R12", "RAX"))
                constants.values[r12] = frozenset({ExprInt(0x1234, 64)})
                constants.values[rax] = frozenset({ExprInt(0x5678, 64)})
                constants.memory.store([({original[rsp]}, {ExprInt(0x11, 64)}, 64)])
                if controlled:
                    constants.control_calls.add(id(line))
                constants.update(line)
                for name in ("RBX", "RBP", "RSP", "R12", "R13", "R14", "R15"):
                    reg = ExprId(name, 64)
                    self.assertEqual(
                        constants.origins.get(reg) == original[reg], controlled
                    )
                self.assertNotIn(rax, constants.origins)
                self.assertEqual(r12 in constants.values, controlled)
                self.assertTrue(
                    any(
                        policy.context_memory.is_wide(v)
                        for v in constants.memory.load(ExprMem(original[rsp], 64))
                    )
                )

    def test_overlap_adjacency_and_modular_wrap(self):
        guards = EntryGuards()
        self.assertTrue(guards.separate(address("R12", -8), address("R13"), 8, 4))
        # Compare against concrete byte sets, independently of interval arithmetic.
        for base in (0, 0x1000, MASK - 4):
            for offset in range(-24, 25):
                registers = {"R12": base, "R13": (base + offset) & MASK}
                left = {(base - 8 + i) & MASK for i in range(8)}
                right = {(registers["R13"] + i) & MASK for i in range(4)}
                self.assertEqual(guards.accepts(registers), not left & right)

    def test_collected_conditions_never_drop_a_requested_separation(self):
        guards = EntryGuards()
        spans = [(0, 8, 16, 4), (4, 8, 18, 4), (64, 4, 128, 8)]
        for x, n, y, m in spans:
            self.assertTrue(guards.separate(address("R12", x), address("R13", y), n, m))
        rng = random.Random(7)
        for _ in range(1000):
            a, b = rng.randrange(256), rng.randrange(256)
            if not guards.accepts({"R12": a, "R13": b}):
                continue
            for x, n, y, m in spans:
                self.assertFalse(
                    set(range(a + x, a + x + n)) & set(range(b + y, b + y + m))
                )

    def test_missing_identity_and_budgets_are_not_assumptions(self):
        guards = EntryGuards()
        self.assertFalse(guards.separate(None, address("R13")))
        self.assertFalse(guards.separate(address("R12"), address("R12", 8)))
        self.assertFalse(guards.separate((ExprId("R12", 64), 0), address("R13")))
        with patch.object(guards, "MAX_RANGES", 1):
            self.assertFalse(guards.separate(address("R12"), address("R13")))
        with self.assertRaises(ValueError):
            guards.conditions()
        guards = EntryGuards()
        guards.separate(address("R12"), address("R13"))
        with self.assertRaises(KeyError):
            guards.accepts({"R12": 0})
        with patch.object(guards, "MAX_GUARDS", 0), self.assertRaises(ValueError):
            guards.conditions()

    def test_real_wrapper_predicate_matches_reference(self):
        guards = EntryGuards()
        guards.separate(address("R12", -8), address("R13"), 8, 4)
        cases = [
            (base, (base + delta) & MASK)
            for base in (0, 0x1000, MASK - 4)
            for delta in range(-16, 17)
        ]
        iterator = iter(cases)

        def initialize(regs, _):
            regs[3], regs[2] = next(iterator)

        results = run_image(guarded(guards), [0x1000] * len(cases), initialize)
        for (a, b), (regs, args) in zip(cases, results):
            accepted = guards.accepts({"R12": a, "R13": b})
            self.assertEqual(args[1], int(accepted))
            self.assertEqual(args[0] == ENTRY_REFUSED, not accepted)
            self.assertEqual(regs[10], 42 if accepted else 0)
            self.assertEqual((regs[3], regs[2]), (a, b))

    def test_failure_keeps_all_registers_stack_and_memory_unchanged(self):
        guards = EntryGuards()
        guards.separate(address("R14"), address("R15"), 8, 8)
        before, stacks = [], []
        destination = ctypes.c_ulong(0x1234)

        def initialize(regs, stack):
            for index in range(15):
                regs[index] = 0x1000 + index
            regs[0] = regs[1]
            regs[14] = ctypes.addressof(destination)
            before.append(list(regs))
            stacks.append(stack)

        # This store must not run on the failed guard path, not merely lack a log.
        results = run_image(guarded(guards, "48c7072a000000c3"), [0x1000], initialize)
        self.assertEqual(results[0][0], before[0])
        self.assertEqual(results[0][1], [ENTRY_REFUSED, 0])
        self.assertEqual(destination.value, 0x1234)
        self.assertEqual(list(stacks[0]), [0] * 8 + [0x4444] + [0] * 7)

    def test_absolute_guard_and_saved_register_offsets(self):
        for name, offset in REGISTER_OFFSETS.items():
            if name == "RSP":
                continue
            with self.subTest(register=name):
                guards = EntryGuards()
                guards.separate(address(name), address("", 0x8000), 8, 8)

                def initialize(regs, _, offset=offset):
                    regs[offset // 8] = 0x8000

                self.assertEqual(
                    run_image(guarded(guards), [0x1000], initialize)[0][1],
                    [ENTRY_REFUSED, 0],
                )

    def test_stack_guard_reads_saved_virtual_rsp_not_wrapper_rsp(self):
        guards = EntryGuards()
        guards.separate(address("RSP", -8), address("R12"), 8, 8)

        def initialize(regs, _):
            regs[3] = regs[19] - 8

        self.assertEqual(
            run_image(guarded(guards), [0x1000], initialize)[0][1], [ENTRY_REFUSED, 0]
        )

    def test_no_guard_and_continuation_dispatch(self):
        self.assertEqual(guarded(EntryGuards()), render("48c7c02a000000c3")[0])
        guards = EntryGuards()
        guards.separate(address("R12"), address("R13"), 8, 8)
        # Non-root entry is a continuation; production must establish prior admission.
        image = guarded(guards, "eb0048c7c02a000000c3")
        result = run_image(image, [0x1002])[0]
        self.assertEqual(result[0][10], 42)
        self.assertEqual(result[1][1], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
