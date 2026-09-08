import unittest
from unittest.mock import patch

from miasm.expression.expression import ExprCompose, ExprId, ExprInt, ExprMem, ExprOp
from miasm.ir.ir import AssignBlock
from miasm.ir.symbexec import SymbolicExecutionEngine
from test_jit_diagnostics import decode, render, translator

policy = translator.context_policy
context_memory = policy.context_memory


class MemoryValueTests(unittest.TestCase):
    def setUp(self):
        self.rbp, self.rdi = ExprId("entry_rbp", 64), ExprId("entry_rdi", 64)
        self.memory = context_memory.MemoryValues(frozenset({self.rbp, self.rdi}))
        self.slot = self.memory.offset(self.rbp, -8)
        self.lifter = policy.FlowConstants().lifter

    def store(self, pointer, value, bits=64):
        value = ExprInt(value, bits) if isinstance(value, int) else value
        self.memory.store([({pointer}, {value}, bits)])

    def load(self, pointer=None, bits=64):
        return self.memory.load(
            ExprMem(self.slot if pointer is None else pointer, bits)
        )

    def test_exact_byte_widths_and_partial_overwrite(self):
        for bits in (8, 16, 32, 64):
            with self.subTest(bits=bits):
                self.store(self.slot, 0x1122334455667788)
                self.store(self.slot, 0x30, bits)
                expected = (0x1122334455667788 & ~((1 << bits) - 1)) | 0x30
                self.assertEqual(self.load(), (ExprInt(expected, 64),))

    def test_identity_is_not_register_spelling_or_distinct_bases(self):
        equivalent = self.memory.offset(self.memory.offset(self.rbp, -16), 8)
        self.assertTrue(self.memory.relation(self.slot, equivalent))
        self.assertFalse(self.memory.relation(self.slot, self.rbp))
        self.assertIsNone(self.memory.relation(self.slot, self.rdi))
        self.assertIsNone(self.memory.relation(self.slot, ExprInt(0x1000, 64)))
        unknown = ExprId("unmodelled_rbp", 64)
        self.assertIsNone(self.memory.address(unknown))
        self.assertIsNone(self.memory.relation(unknown, unknown))

    def test_equivalent_full_overwrite_kills_old_value(self):
        self.store(self.slot, 0x2FF8)
        self.store(self.memory.offset(self.memory.offset(self.rbp, -16), 8), 0)
        self.assertEqual(self.load(), (ExprInt(0, 64),))

    def test_possible_alias_write_retains_old_value(self):
        self.store(self.slot, 0x2FF8)
        self.store(self.rdi, 0)
        self.assertIn(ExprInt(0x2FF8, 64), self.load())

    def test_partial_alias_may_construct_an_address(self):
        self.store(self.slot, 0x2000)
        self.store(self.rdi, 0x30, 8)
        self.assertTrue(
            ExprInt(0x3000, 64) in self.load()
            or any(context_memory.is_wide(value) for value in self.load())
        )

    def test_unknown_pointer_load_does_not_forget_written_candidates(self):
        self.store(self.slot, 0x2FF8)
        unknown = ExprId("runtime_pointer", 64)
        self.assertTrue(
            any(context_memory.is_wide(value) for value in self.load(unknown))
        )

    def test_unlocated_store_taints_later_load_but_exact_overwrite_recovers(self):
        self.store(ExprId("runtime_pointer", 64), 0x2FF8)
        self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))
        self.store(self.slot, 0)
        self.assertEqual(self.load(), (ExprInt(0, 64),))

    def test_missing_and_written_unknown_values_remain_runtime_unknown(self):
        self.assertEqual(self.load(), (ExprMem(self.slot, 64),))
        self.store(self.slot, ExprId("runtime_value", 64))
        self.assertEqual(self.load(), (ExprMem(self.slot, 64),))

    def test_saved_symbolic_pointer_can_be_reconstructed(self):
        pointer = self.memory.offset(self.rbp, -24)
        self.store(self.slot, pointer)
        self.assertEqual(self.load(), (pointer,))

    def test_merge_and_clobber_do_not_drop_the_unchanged_path(self):
        self.store(self.slot, 0x2FF8)
        left = self.memory.snapshot()
        self.store(self.slot, 0)
        right = self.memory.snapshot()
        current = self.memory.snapshot()
        merged = self.memory.merge(left, right)
        self.assertEqual(self.memory.snapshot(), current)
        self.memory.restore(merged)
        self.assertIn(ExprInt(0x2FF8, 64), self.load())
        self.assertIn(ExprInt(0, 64), self.load())
        self.memory.clobber()
        self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))

    def test_cell_and_value_limits_preserve_exhaustion(self):
        with patch.object(self.memory, "MAX_BYTES", 4):
            self.store(self.slot, 0x2FF8)
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))
            self.store(self.slot, 0, 32)
            self.assertEqual(self.load(bits=32), (ExprInt(0, 32),))
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))
        self.memory = context_memory.MemoryValues(frozenset({self.rbp, self.rdi}))
        with patch.object(self.memory, "MAX_VALUES", 1):
            self.store(self.slot, 0x2FF8)
            self.store(self.rdi, 0)
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))

    def test_parallel_overlapping_stores_keep_all_possible_new_bytes(self):
        self.memory.store(
            [
                ({self.slot}, {ExprInt(0x2FF8, 64)}, 64),
                ({self.slot}, {ExprInt(0, 64)}, 64),
            ]
        )
        self.assertIn(ExprInt(0x2FF8, 64), self.load())
        self.assertIn(ExprInt(0, 64), self.load())

    def test_overlapping_pointer_alternatives_cover_only_the_shared_byte(self):
        self.store(self.slot, 0x112233)
        self.memory.store(
            [({self.slot, self.memory.offset(self.slot, 1)}, {ExprInt(0xAABB, 16)}, 16)]
        )
        for index, expected in enumerate(({0x33, 0xBB}, {0xAA, 0xBB}, {0x11, 0xAA})):
            with self.subTest(index=index):
                self.assertEqual(
                    self.memory.byte_at(self.memory.offset(self.slot, index)),
                    frozenset(ExprInt(value, 8) for value in expected),
                )

    def test_distinct_bases_keep_every_possible_written_byte(self):
        self.store(self.slot, 0x1122334455667788)
        old = self.memory.snapshot()
        self.store(self.rdi, 0xAA00, 16)
        for index in range(8):
            key = self.memory.offset(self.slot, index)
            self.assertEqual(
                self.memory.byte_at(key),
                old[0][key] | {ExprInt(0, 8), ExprInt(0xAA, 8)},
            )

    def test_wide_fallback_compaction_preserves_exact_overwrites(self):
        self.store(self.slot, 0x2FF8)
        known = self.memory.snapshot()
        self.memory.store([({self.rdi}, {context_memory.wide_value(64)}, 64)])
        widened = self.memory.snapshot()
        self.assertEqual(widened[0][self.slot], None)
        self.memory.default = None
        self.store(self.memory.offset(self.slot, 16), 0x30, 8)
        self.assertNotIn(self.slot, self.memory.cells)
        self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))
        self.assertEqual(
            self.load(self.memory.offset(self.slot, 16), 8), (ExprInt(0x30, 8),)
        )
        merged = self.memory.merge(known, ({}, None, {}))
        self.assertEqual(merged, ({}, None, {}))
        self.memory.restore(merged)
        self.store(self.slot, 0x2FF8)
        self.assertEqual(self.load(), (ExprInt(0x2FF8, 64),))

    def test_work_budget_cannot_be_reset_by_restoring_a_branch(self):
        self.store(self.slot, 0x2FF8)
        saved = self.memory.snapshot()
        with patch.object(self.memory, "MAX_WORK", self.memory.work):
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))
            self.memory.restore(saved)
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))

    def test_equal_merge_is_linear_but_still_obeys_the_work_budget(self):
        self.store(self.slot, 0x2FF8)
        saved = self.memory.snapshot()
        before = self.memory.work
        self.assertEqual(self.memory.merge(saved, saved), saved)
        self.assertEqual(self.memory.work - before, len(saved[0]) + len(saved[2]) + 1)
        with patch.object(self.memory, "MAX_WORK", self.memory.work):
            self.assertEqual(self.memory.merge(saved, saved), ({}, None, {}))
        with patch.object(self.memory, "MAX_BYTES", len(saved[0]) - 1):
            self.assertEqual(self.memory.merge(saved, saved), ({}, None, {}))
        self.assertEqual(self.memory.snapshot(), saved)

    def test_merge_keeps_missing_cell_aliases_and_does_not_mutate_inputs(self):
        self.store(self.slot, 0x2FF8)
        left = self.memory.snapshot()
        self.memory.restore(({}, context_memory.UNKNOWN, {}))
        self.store(self.rdi, 0x30, 8)
        right = self.memory.snapshot()
        expected = {}
        for key in left[0].keys() | right[0].keys():
            self.memory.restore(left)
            a = self.memory.byte_at(key)
            self.memory.restore(right)
            expected[key] = self.memory.join(a, self.memory.byte_at(key))
        merged = self.memory.merge(left, right)
        self.assertEqual(merged, (expected, context_memory.UNKNOWN, {}))
        self.assertEqual(self.memory.snapshot(), right)
        self.memory.restore(merged)
        self.assertTrue(
            ExprInt(0x3000, 64) in self.load()
            or any(context_memory.is_wide(value) for value in self.load())
        )

    def test_exact_load_charges_probes_without_unneeded_alias_scans(self):
        self.store(self.slot, 0x2FF8)
        for offset in range(16, 128, 8):
            self.store(self.memory.offset(self.rbp, offset), 0)
        before = self.memory.work
        self.assertEqual(self.load(), (ExprInt(0x2FF8, 64),))
        self.assertEqual(self.memory.work - before, 9)

    def test_oversized_store_domains_do_not_drop_candidates(self):
        with patch.object(self.memory, "MAX_VALUES", 1):
            self.memory.store(
                [({self.slot}, {ExprInt(0, 64), ExprInt(0x2FF8, 64)}, 64)]
            )
            self.assertTrue(any(context_memory.is_wide(value) for value in self.load()))

    def test_byte_addresses_wrap_in_the_x86_width(self):
        pointer = ExprInt((1 << 64) - 1, 64)
        self.store(pointer, 0x1234, 16)
        self.assertEqual(self.load(ExprInt(0, 64), 8), (ExprInt(0x12, 8),))

    def test_nested_loads_use_the_original_memory_state(self):
        self.store(ExprInt(0x1000, 64), 0x2000)
        self.store(ExprInt(0x2000, 64), 0x2FF8)
        expression = ExprMem(ExprMem(ExprInt(0x1000, 64), 64), 64)
        self.assertEqual(
            context_memory.evaluate(self.lifter, expression, {}, self.memory),
            (ExprInt(0x2FF8, 64),),
        )

    def test_distinct_wide_reads_cannot_cancel_as_one_symbol(self):
        self.memory.default = None
        a, b = ExprMem(self.rbp, 64), ExprMem(self.rdi, 64)
        values = context_memory.evaluate(self.lifter, a - b, {}, self.memory)
        self.assertTrue(all(context_memory.is_wide(value) for value in values))
        self.assertNotIn(ExprInt(0, 64), values)
        self.assertEqual(
            context_memory.evaluate(self.lifter, a - a, {}, self.memory),
            (ExprInt(0, 64),),
        )

    def test_concrete_alias_offsets_against_miasm_memory(self):
        # Concrete execution is independent of the abstract byte/alias model.
        for seed in (0, 0x2FF8, 0x2000, 0x1122334455667788):
            for bits in (8, 16, 32, 64):
                for delta in range(-8, 9):
                    for known_alias in (False, True):
                        with self.subTest(
                            seed=seed, bits=bits, delta=delta, known=known_alias
                        ):
                            self.memory = context_memory.MemoryValues(
                                frozenset({self.rbp, self.rdi})
                            )
                            self.store(self.slot, seed)
                            pointer = (
                                self.memory.offset(self.slot, delta)
                                if known_alias
                                else self.rdi
                            )
                            self.store(pointer, 0x30, bits)
                            engine = SymbolicExecutionEngine(self.lifter)
                            target = ExprMem(ExprInt(0x1000, 64), 64)
                            engine.apply_change(target, ExprInt(seed, 64))
                            engine.apply_change(
                                ExprMem(ExprInt(0x1000 + delta, 64), bits),
                                ExprInt(0x30, bits),
                            )
                            actual = engine.eval_expr(target)
                            values = self.load()
                            if known_alias:
                                self.assertEqual(values, (actual,))
                            else:
                                self.assertTrue(
                                    actual in values
                                    or any(
                                        context_memory.is_wide(value)
                                        for value in values
                                    )
                                )

    def test_wide_read_identity_survives_demand_forks(self):
        a, b = ExprMem(self.rbp, 64), ExprMem(self.rdi, 64)

        def choices(memory):
            wide = context_memory.wide_value(64)
            return (ExprInt(0, 64), wide) if memory == a else (wide,)

        with patch.object(self.memory, "load", side_effect=choices):
            values = context_memory.evaluate(self.lifter, a - b, {}, self.memory)
        self.assertTrue(all(context_memory.is_wide(value) for value in values))
        self.assertNotIn(ExprInt(0, 64), values)


class RmwWordTests(unittest.TestCase):
    def setUp(self):
        self.base = ExprInt(0x1000, 64)
        self.pointer = ExprId("entry_pointer", 64)
        self.memory = context_memory.MemoryValues(frozenset({self.pointer}))
        self.target = ExprMem(self.base, 64)

    def store(self, value, pointer=None, width=64):
        self.memory.store(
            [
                (
                    {self.base if pointer is None else pointer},
                    {ExprInt(value, width)},
                    width,
                )
            ]
        )

    def rmw(self, operation, amount, pointer=None, width=64):
        self.memory.store(
            [
                (
                    {self.pointer if pointer is None else pointer},
                    {context_memory.wide_value(width)},
                    width,
                )
            ],
            rmw=(operation, amount),
        )

    def test_ir_recognition_requires_same_location_and_constant(self):
        for operation in ("+", "&", "|", "^"):
            expression = ExprOp(operation, self.target, ExprInt(1, 64))
            self.assertEqual(
                context_memory.rmw_operation(self.target, expression), (operation, 1)
            )
            other = ExprMem(self.pointer, 64)
            self.assertIsNone(context_memory.rmw_operation(other, expression))
        self.assertIsNone(
            context_memory.rmw_operation(self.target, self.target + self.pointer)
        )
        self.assertIsNone(
            context_memory.rmw_operation(self.pointer, self.pointer + ExprInt(1, 64))
        )

    def test_unknown_rmw_preserves_complete_placement_candidates(self):
        self.store(0x2000)
        self.rmw("+", 1)
        expected = {0x2000, *(0x2000 + (1 << shift) for shift in range(0, 64, 8))}
        self.assertEqual(
            {int(value) for value in self.memory.load(self.target)}, expected
        )
        self.assertTrue(any(domain is None for domain in self.memory.cells.values()))

    def test_known_overlap_wrap_and_partial_load(self):
        base = ExprInt((1 << 64) - 4, 64)
        self.store(0x2000, base)
        self.rmw("+", 1, ExprInt(0, 64), 32)
        self.assertEqual(
            self.memory.load(ExprMem(base, 64)), (ExprInt(0x100002000, 64),)
        )
        self.assertEqual(
            self.memory.load(ExprMem(ExprInt(0, 64), 32)), (ExprInt(1, 32),)
        )

    def test_subtraction_and_unknown_prefix_carry_are_retained(self):
        self.store(0x3000)
        self.rmw("+", (1 << 64) - 1, self.memory.offset(self.base, -1))
        self.assertEqual(
            {int(value) for value in self.memory.load(self.target)}, {0x2FFF, 0x3000}
        )

    def test_distinct_base_can_alias_but_same_base_disjoint_store_preserves(self):
        self.store(0x2000)
        self.rmw("+", 1)
        known = self.memory.load(self.target)
        self.store(0, self.memory.offset(self.base, 16))
        self.assertEqual(self.memory.load(self.target), known)
        self.store(0, self.pointer, 8)
        self.assertNotIn(self.target, self.memory.words)
        self.assertTrue(
            any(
                context_memory.is_wide(value) for value in self.memory.load(self.target)
            )
        )

    def test_partial_plain_write_and_call_discard_word_refinement(self):
        for clobber in (False, True):
            with self.subTest(clobber=clobber):
                self.setUp()
                self.store(0x2FFF)
                self.rmw("+", 1)
                if clobber:
                    self.memory.clobber()
                else:
                    self.store(0, self.base, 8)
                self.assertNotIn(self.target, self.memory.words)
                self.assertTrue(
                    any(
                        context_memory.is_wide(value)
                        for value in self.memory.load(self.target)
                    )
                )

    def test_merge_preserves_complete_words_and_restoration_does_not_reset_work(self):
        self.store(0x2000)
        left = self.memory.snapshot()
        self.store(0x2FFF)
        right = self.memory.snapshot()
        self.memory.restore(self.memory.merge(left, right))
        self.rmw("+", 1, self.base)
        self.assertEqual(
            {int(value) for value in self.memory.load(self.target)}, {0x2001, 0x3000}
        )
        work = self.memory.work
        self.memory.restore(left)
        self.assertEqual(self.memory.work, work)
        self.assertEqual(self.memory.load(self.target), (ExprInt(0x2000, 64),))

    def test_missing_incoming_fact_falls_back_without_dropping_old_values(self):
        self.store(0x2FFF)
        self.memory.restore(
            self.memory.merge(self.memory.snapshot(), ({}, context_memory.UNKNOWN, {}))
        )
        self.assertFalse(self.memory.words)
        self.assertTrue(
            any(
                context_memory.is_wide(value) for value in self.memory.load(self.target)
            )
        )

    def test_refinement_obeys_word_value_byte_and_work_limits(self):
        self.store(0x2000)
        with patch.object(self.memory, "MAX_WORDS", 1):
            self.store(0x2FFF, self.memory.offset(self.base, 16))
            self.assertFalse(self.memory.words)
            self.assertEqual(self.memory.load(self.target), (ExprInt(0x2000, 64),))
        self.store(0x2000)
        with patch.object(self.memory, "MAX_VALUES", 1):
            self.rmw("+", 1)
            self.assertFalse(self.memory.words)
            self.assertTrue(
                any(
                    context_memory.is_wide(value)
                    for value in self.memory.load(self.target)
                )
            )
        self.store(0x2000)
        with patch.object(self.memory, "MAX_WORK", self.memory.work):
            self.assertTrue(
                any(
                    context_memory.is_wide(value)
                    for value in self.memory.load(self.target)
                )
            )
        with patch.object(self.memory, "MAX_BYTES", 7):
            self.store(0x2000)
            self.assertFalse(self.memory.words)

    def test_rmw_math_against_independent_miasm_byte_memory(self):
        lifter = policy.FlowConstants().lifter
        for word_bytes, write_bytes in (
            (8, 1),
            (8, 2),
            (8, 4),
            (8, 8),
            (1, 8),
            (2, 8),
            (4, 8),
        ):
            word_mask = (1 << (word_bytes * 8)) - 1
            write_mask = (1 << (write_bytes * 8)) - 1
            for seed in (0, 0x2000 & word_mask, 0x2FFF & word_mask, word_mask):
                for start in range(-write_bytes, word_bytes + 1):
                    for operation in ("+", "&", "|", "^"):
                        for amount in (1, 0x3080 & write_mask, write_mask):
                            for fill in (0, 127, 255):
                                engine = SymbolicExecutionEngine(lifter)
                                pointer = ExprInt(0x1000 + start, 64)
                                for offset in range(write_bytes):
                                    engine.apply_change(
                                        ExprMem(
                                            ExprInt(0x1000 + start + offset, 64), 8
                                        ),
                                        ExprInt(fill, 8),
                                    )
                                target = ExprMem(self.base, word_bytes * 8)
                                engine.apply_change(
                                    target, ExprInt(seed, word_bytes * 8)
                                )
                                location = ExprMem(pointer, write_bytes * 8)
                                result = engine.eval_expr(
                                    ExprOp(
                                        operation,
                                        location,
                                        ExprInt(amount, write_bytes * 8),
                                    )
                                )
                                engine.apply_change(location, result)
                                actual = int(engine.eval_expr(target))
                                expected = context_memory.rmw_word_values(
                                    seed,
                                    word_bytes,
                                    write_bytes,
                                    start,
                                    operation,
                                    amount,
                                )
                                self.assertIn(
                                    actual,
                                    expected,
                                    (
                                        word_bytes,
                                        write_bytes,
                                        seed,
                                        start,
                                        operation,
                                        amount,
                                        fill,
                                    ),
                                )


class MemoryAdmissionTests(unittest.TestCase):
    SYMBOLS = policy.ContextSymbols({0x3000: "__per_cpu_offset"}, {0x3000: 0x3100})
    SEED = "48b8f82f000000000000488945f8"
    ACCESS = "488b75f84883c61048adc3"

    def assert_status(self, raw, expected):
        assembly, log, status = render(raw, symbols=self.SYMBOLS, return_status=True)
        self.assertEqual(status, expected, log)
        self.assertEqual(bool(assembly), expected == 0)
        if expected:
            self.assertIn("CONTEXT_NATIVE_ONLY", log)

    def test_independent_corpus_is_a_production_gate(self):
        import test_context_spill_audit

        for case in test_context_spill_audit.audit.CASES:
            with self.subTest(case=case.name):
                self.assertTrue(test_context_spill_audit.audit.audit(case)["ok"])

    def test_call_does_not_erase_memory_dependencies_in_jit_successor(self):
        raw = self.SEED + "e800400000" + self.ACCESS
        # A missing ordinary CALL is terminal, but a resumable lock control
        # must still expose the old spill to admission after returning to JIT.
        self.assert_status(raw, 0)
        assembly, log, status = render(
            raw,
            symbols=self.SYMBOLS,
            kernel_symbols={"_raw_spin_lock": 0x5013},
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_call_write_survives_fact_clobber(self):
        tracker = policy.FlowConstants()
        tracker.update(decode("e83b000000"))
        slot = tracker.memory.offset(ExprId("kd_entry_RSP", 64), -8)
        values = tracker.memory.load(ExprMem(slot, 64))
        self.assertTrue(
            ExprInt(5, 64) in values
            or any(context_memory.is_wide(value) for value in values)
        )

    def test_single_identity_memory_write_preserves_facts(self):
        for raw in ("48830700", "48830f00", "488327ff", "48832f00", "48833700"):
            with self.subTest(raw=raw):
                tracker = policy.FlowConstants()
                for seed in ("b805100000", "488945f8"):
                    tracker.update(decode(seed))
                before = tracker.memory.snapshot()
                tracker.update(decode(raw))
                self.assertEqual(tracker.memory.snapshot(), before)

    def test_identity_store_does_not_bypass_memory_access_checks(self):
        self.assert_status("48830c250030000000c3", 2)
        self.assert_status("6548830f00c3", 2)
        tracker = policy.FlowConstants()
        tracker.origins[ExprId("RDI", 64)] = ExprInt(0x3000, 64)
        with self.assertRaisesRegex(policy.ContextFlowLimit, "IR memory access"):
            tracker.update(decode("48830f00"), self.SYMBOLS)

    def test_parallel_alias_write_must_keep_identity_alternative(self):
        tracker = policy.FlowConstants()
        rbp, rdi = ExprId("RBP", 64), ExprId("RDI", 64)
        tracker.origins[rdi] = tracker.origins[rbp]
        slot = ExprMem(rbp, 64)
        tracker.update_assignments(AssignBlock({slot: ExprInt(0x2FF8, 64)}))
        tracker.update_assignments(
            AssignBlock({slot: slot, ExprMem(rdi, 64): ExprInt(0, 64)})
        )
        values = tracker.memory.load(ExprMem(ExprId("kd_entry_RBP", 64), 64))
        self.assertIn(ExprInt(0x2FF8, 64), values)
        self.assertIn(ExprInt(0, 64), values)

    def test_nonidentity_memory_write_is_not_discarded(self):
        tracker = policy.FlowConstants()
        for raw in ("b800200000", "488945f8", "488345f810"):
            tracker.update(decode(raw))
        values = tracker.memory.load(
            ExprMem(tracker.memory.offset(ExprId("kd_entry_RBP", 64), -8), 64)
        )
        self.assertEqual(values, (ExprInt(0x2010, 64),))

    def test_wide_lea_is_arithmetic_until_the_result_is_used_as_an_address(self):
        prefix = "c60701488b45f8488d14c0"
        self.assert_status(prefix + "c3", 0)
        self.assert_status(prefix + "488b1ac3", 2)
        self.assert_status("b8f82f0000488d5010c3", 2)

    def test_masked_wide_index_checks_all_possible_table_entries(self):
        prefix = "c60701488b45f883e003"
        self.assert_status(prefix + "488b1cc500200000c3", 0)
        self.assert_status(prefix + "488b1cc5f02f0000c3", 2)
        self.assert_status("c60701488b45f883e07f488b1cc500200000c3", 2)

    def test_finite_bit_bounds_preserve_width_and_all_unknown_bits(self):
        tracker = policy.FlowConstants()
        for width in (8, 16, 32, 64):
            wide = context_memory.wide_value(width)
            mask = (1 << (width - 1)) | 1
            self.assertEqual(
                {
                    int(value)
                    for value in tracker.finite_values(wide & ExprInt(mask, width))
                },
                {0, 1, 1 << (width - 1), mask},
            )
        narrow = context_memory.wide_value(64)[0:32] & ExprInt(3, 32)
        extended = ExprCompose(narrow, ExprInt(0, 32))
        self.assertEqual(
            set(tracker.finite_values(extended)),
            {ExprInt(value, 64) for value in range(4)},
        )
        with patch.object(tracker, "MAX_VALUES", 2):
            self.assertEqual(tracker.finite_values(extended), (extended,))

    def test_internal_cmpxchg_paths_retain_old_memory(self):
        prefix = self.SEED + "31c031db480fb15df8"
        self.assert_status(prefix + self.ACCESS, 2)
        self.assert_status(prefix + "48c745f800000000" + self.ACCESS, 0)

    def test_unliftable_clobber_retains_memory_uncertainty(self):
        tracker = policy.FlowConstants()
        for raw in ("b8f82f0000", "488945f8"):
            tracker.update(decode(raw))
        with patch.object(tracker.lifter, "instr2ir", side_effect=NotImplementedError):
            tracker.update(decode("90"))
        tracker.update(decode("488b75f8"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RSI", 64))

    def test_exhausted_memory_can_be_discarded_only_by_a_proven_overwrite(self):
        with patch.object(context_memory.MemoryValues, "MAX_BYTES", 4):
            self.assert_status(self.SEED + self.ACCESS, 2)
            self.assert_status(self.SEED + "31f6" + "4883c61048adc3", 0)


if __name__ == "__main__":
    unittest.main()
