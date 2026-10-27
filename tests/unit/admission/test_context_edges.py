"""Check numeric edge projection using decoded x86 comparisons, in the VM."""

import unittest
from unittest.mock import patch

from miasm.expression.expression import ExprId, ExprInt
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, translator
from context_values import FlowConstants
from context_edges import _taken


class NumericEdgeTests(unittest.TestCase):
    def fixture(self, raw, values, *, scoped=True):
        blocks, databases = translator.decode_regions(
            [(bytes.fromhex(raw), 0x1000, [0x1000])],
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"], set(TEST_LOCK_SYMBOLS.values()))
        block = blocks[0x1000]
        tracker = FlowConstants(scoped_calls=scoped)
        for name, domain in values.items():
            tracker.values[ExprId(name, 64)] = (
                None if domain is None else frozenset(
                    None if value is None else ExprInt(value, 64) for value in domain))
        jump = block.lines[-1]
        database = databases[block]
        taken = translator.context_policy.static_address(
            jump.args[0], database, jump.offset + jump.l)
        return tracker, block, database, taken, jump.offset + jump.l

    @staticmethod
    def domain(state, register):
        values = state[0].get(ExprId(register, 64), FlowConstants.UNKNOWN)
        return None if values is None else {None if x is None else int(x) for x in values}

    def test_equality_filters_each_edge_without_changing_tracker(self):
        t, b, db, yes, no = self.fixture("4839c87401c3c3", {"RAX": {1, 2}, "RCX": {2}})
        original = t.snapshot()
        self.assertEqual(self.domain(t.successor_state(b, db, yes), "RAX"), {2})
        self.assertEqual(self.domain(t.successor_state(b, db, no), "RAX"), {1})
        self.assertEqual(t.snapshot(), original)

    def test_projection_retains_cross_product_overapproximation(self):
        t, b, db, yes, _ = self.fixture("4839c87401c3c3", {"RAX": {1, 2}, "RCX": {1, 2}})
        state = t.successor_state(b, db, yes)
        self.assertEqual(self.domain(state, "RAX"), {1, 2})
        self.assertEqual(self.domain(state, "RCX"), {1, 2})

    def test_one_register_has_one_environment_assignment(self):
        t, b, db, yes, no = self.fixture("4839c07501c3c3", {"RAX": {1, 2}})
        self.assertIsNone(t.successor_state(b, db, yes))
        self.assertEqual(self.domain(t.successor_state(b, db, no), "RAX"), {1, 2})

    def test_unknown_and_widened_inputs_preserve_every_edge(self):
        for domain in ({None, 2}, None):
            with self.subTest(domain=domain):
                t, b, db, yes, no = self.fixture("4839c87401c3c3", {"RAX": domain, "RCX": {2}})
                self.assertEqual(self.domain(t.successor_state(b, db, yes), "RAX"), domain)
                self.assertEqual(self.domain(t.successor_state(b, db, no), "RAX"),
                                 None if domain is None else {None})

    def test_signed_and_unsigned_boundaries_use_operand_width(self):
        for compare, width in (("38c8", 8), ("6639c8", 16), ("39c8", 32), ("4839c8", 64)):
            sign, mask = 1 << (width - 1), (1 << width) - 1
            for branch, expected in (("72", set()), ("7c", {sign, mask})):
                with self.subTest(width=width, branch=branch):
                    t, b, db, yes, _ = self.fixture(compare + branch + "01c3c3",
                                                   {"RAX": {0, sign, mask}, "RCX": {0}})
                    state = t.successor_state(b, db, yes)
                    if not expected:
                        self.assertIsNone(state)
                    else:
                        self.assertEqual(self.domain(state, "RAX"), expected)

    def test_partial_register_comparison_keeps_original_full_values(self):
        t, b, db, yes, no = self.fixture("39c87401c3c3",
                                        {"RAX": {1, 0x100000001, 2}, "RCX": {1}})
        self.assertEqual(self.domain(t.successor_state(b, db, yes), "RAX"), {1, 0x100000001})
        self.assertEqual(self.domain(t.successor_state(b, db, no), "RAX"), {2})

    def test_all_byte_comparisons_match_subtraction_flag_reference(self):
        # Independent x86 subtraction flags, including signed overflow and
        # unsigned borrow. The implementation compares operands directly.
        for left in range(256):
            for right in range(256):
                result = (left - right) & 255
                zf, cf = result == 0, left < right
                sf = bool(result & 128)
                of = bool((left ^ right) & (left ^ result) & 128)
                conditions = {"JE": zf, "JNE": not zf,
                              "JB": cf, "JAE": not cf,
                              "JBE": cf or zf, "JA": not cf and not zf,
                              "JL": sf != of, "JGE": sf == of,
                              "JLE": zf or sf != of, "JG": not zf and sf == of}
                for branch, expected in conditions.items():
                    actual = _taken("CMP", branch, left, right, 8)
                    if actual != expected:
                        self.fail((left, right, branch, actual, expected))

    def test_all_byte_masks_match_test_zero_flag(self):
        for left in range(256):
            for right in range(256):
                zero = not any((left & (1 << bit)) and (right & (1 << bit))
                               for bit in range(8))
                for branch, expected in (("JZ", zero), ("JNZ", not zero)):
                    actual = _taken("TEST", branch, left, right, 8)
                    if actual != expected:
                        self.fail((left, right, branch, actual, expected))

    def test_test_mask_uses_and_zero_flag(self):
        t, b, db, yes, no = self.fixture("a9ff0000007401c3c3", {"RAX": {0, 1, 256}})
        self.assertEqual(self.domain(t.successor_state(b, db, yes), "RAX"), {0, 256})
        self.assertEqual(self.domain(t.successor_state(b, db, no), "RAX"), {1})

    def test_intervening_instruction_memory_and_unsupported_flags_do_not_refine(self):
        for raw in ("4839c84883c2017401c3c3", "8038007401c3c3", "4839c87801c3c3"):
            with self.subTest(raw=raw):
                t, b, db, yes, no = self.fixture(raw, {"RAX": {1, 2}, "RCX": {2}})
                before = t.snapshot()
                self.assertEqual(t.successor_state(b, db, yes), before)
                self.assertEqual(t.successor_state(b, db, no), before)

    def test_enumeration_budget_and_independent_roots_keep_original_domain(self):
        for scoped in (True, False):
            t, b, db, yes, no = self.fixture("4839c87401c3c3", {"RAX": {1, 2}, "RCX": {2}}, scoped=scoped)
            before = t.snapshot()
            with patch.object(t, "MAX_COMBINATIONS", 1):
                self.assertEqual(t.successor_state(b, db, yes), before)
                self.assertEqual(t.successor_state(b, db, no), before)
            if not scoped:
                self.assertEqual(t.successor_state(b, db, yes), before)

    def test_edge_filter_preserves_memory_and_control_word_facts(self):
        t, b, db, yes, _ = self.fixture("4839c87401c3c3", {"RAX": {1, 2}, "RCX": {2}})
        t.memory.store([({ExprInt(0x9000, 64)}, {ExprInt(0x1234, 64)}, 64)])
        before = t.snapshot()
        self.assertEqual(t.successor_state(b, db, yes)[1:], before[1:])


if __name__ == "__main__":
    unittest.main()
