"""Guest-only decoded graphs for explicit indirect CALL and RET learning.

Forward CALL history selects an already decoded callee. Its return edge stays
an independent reached record under the current return-inference contract.
No provider, source-device access or kernel-side execution is involved here.
"""

import unittest
from unittest.mock import patch

from test_jit_diagnostics import translator


class IndirectCallLearningTests(unittest.TestCase):
    @staticmethod
    def decode(*pieces):
        return translator.decode_regions(
            [(bytes.fromhex(raw), address, [address]) for address, raw in pieces],
            0, set())

    @staticmethod
    def find(blocks, databases, history, **kwargs):
        staged = {source: list(targets) for source, targets in history.items()}
        missing = translator.indirect_jump.find(blocks, databases, staged, **kwargs)
        return staged, missing

    def test_forward_call_does_not_infer_the_callee_return(self):
        blocks, databases = self.decode((0x1000, 'ffd0c3'), (0x2000, 'c3'))
        forward = {0x1002: [0x2000, 0x2000]}
        table, missing = self.find(blocks, databases, forward)
        self.assertEqual(missing, [])
        self.assertEqual(table, {0x1002: [0x2000], 0x1003: [], 0x2001: []})
        self.assertEqual(forward, {0x1002: [0x2000, 0x2000]})

        table, missing = self.find(blocks, databases,
            {**forward, 0x2001: [0x1002]})
        self.assertEqual(missing, [])
        self.assertEqual(table[0x2001], [0x1002])

    def test_multiple_callees_and_callers_keep_each_reported_return(self):
        blocks, databases = self.decode(
            (0x1000, 'ffd0c3'), (0x1100, 'ffd0c3'),
            (0x2000, 'c3'), (0x3000, 'c3'))
        forward = {0x1002: [0x2000, 0x3000, 0x2000], 0x1102: [0x2000]}
        reports = {}
        for source, target in ((0x2001, 0x1002), (0x3001, 0x1002),
                               (0x2001, 0x1102), (0x2001, 0x1002)):
            with self.subTest(return_source=source, target=target):
                before, _ = self.find(blocks, databases, {**forward, **reports})
                self.assertEqual(before[0x2001], sorted(set(reports.get(0x2001, []))))
                self.assertEqual(before[0x3001], sorted(set(reports.get(0x3001, []))))
                reports.setdefault(source, []).append(target)
                after, missing = self.find(blocks, databases, {**forward, **reports})
                self.assertEqual(missing, [])
                self.assertEqual(after[0x2001], sorted(set(reports.get(0x2001, []))))
                self.assertEqual(after[0x3001], sorted(set(reports.get(0x3001, []))))
                self.assertEqual(after[0x1002], [0x2000, 0x3000])
                self.assertEqual(after[0x1102], [0x2000])

    def test_nested_calls_report_inner_and_outer_words_separately(self):
        blocks, databases = self.decode(
            (0x1000, 'ffd0c3'), (0x2000, 'ffd3c3'), (0x3000, 'c3'))
        forward = {0x1002: [0x2000], 0x2002: [0x3000]}
        table, _ = self.find(blocks, databases, forward)
        self.assertEqual((table[0x2003], table[0x3001]), ([], []))
        table, _ = self.find(blocks, databases, {**forward, 0x3001: [0x2002]})
        self.assertEqual((table[0x2003], table[0x3001]), ([], [0x2002]))
        table, _ = self.find(blocks, databases,
            {**forward, 0x3001: [0x2002], 0x2003: [0x1002]})
        self.assertEqual((table[0x2003], table[0x3001]), ([0x1002], [0x2002]))

    def test_shared_return_accumulates_explicit_continuations(self):
        blocks, databases = self.decode(
            (0x1000, 'ffd0c3'), (0x1100, 'ffd0c3'),
            (0x2000, 'e9fb1f0000'), (0x3000, 'e9fb0f0000'), (0x4000, 'c3'))
        forward = {0x1002: [0x2000], 0x1102: [0x3000]}
        table, _ = self.find(blocks, databases, forward)
        self.assertEqual(table[0x4001], [])
        table, _ = self.find(blocks, databases,
            {**forward, 0x4001: [0x1102, 0x1002, 0x1002]})
        self.assertEqual(table[0x4001], [0x1002, 0x1102])

    def test_undecoded_and_terminal_targets_add_no_return_edges_or_reads(self):
        blocks, databases = self.decode((0x1000, 'ffd0c3'), (0x2000, 'c3'))
        for target, terminals, expected_missing in (
                (0x9000, (), []), (0x9000, (0x9000,), [0x9000]),
                (0x2000, (0x2000,), [0x2000])):
            with self.subTest(target=target, terminals=terminals), \
                    patch.object(translator.memread, 'read') as read, \
                    patch.object(translator.memread, 'extend_regions') as extend:
                table, missing = self.find(blocks, databases,
                    {0x1002: [target]}, terminal_targets=terminals)
                self.assertEqual(missing, expected_missing)
                self.assertEqual(table[0x1002], [target])
                self.assertEqual(table[0x2001], [])
                read.assert_not_called()
                extend.assert_not_called()

    def test_cycles_and_duplicate_rows_preserve_explicit_return_history(self):
        blocks, databases = self.decode(
            (0x1000, 'ffd0c3'), (0x1100, 'e8fb0e0000c3'),
            (0x2000, '85c07402ffe0c3'))
        # The direct caller supplies 0x1105 through the existing tail walk.
        # The dynamic caller's 0x1002 still comes only from its reported RET.
        history = {0x1002: [0x2000, 0x2000], 0x2006: [0x2000, 0x2000],
                   0x2007: [0x1002, 0x1002]}
        table, missing = self.find(blocks, databases, history, max_visits=64)
        self.assertEqual(missing, [])
        self.assertEqual(table[0x1002], [0x2000])
        self.assertEqual(table[0x2006], [0x2000])
        self.assertEqual(table[0x2007], [0x1002, 0x1105])
        repeated, missing = self.find(blocks, databases, table, max_visits=64)
        self.assertEqual((repeated, missing), (table, []))

    def test_work_boundary_preserves_both_history_kinds_on_refusal(self):
        blocks, databases = self.decode(
            (0x1000, 'ffd0c3'), (0x1100, 'e8fb0e0000c3'), (0x2000, 'c3'))
        history = {0x1002: [0x2000, 0x2000], 0x2001: [0x1002, 0x1002]}
        original = {source: list(targets) for source, targets in history.items()}
        # Five source instructions, one direct-callee visit, one return edge.
        with self.assertRaises(translator.indirect_jump.ReturnFlowError):
            translator.indirect_jump.find(blocks, databases, history, max_visits=6)
        self.assertEqual(history, original)
        missing = translator.indirect_jump.find(blocks, databases, history, max_visits=7)
        self.assertEqual(missing, [])
        self.assertEqual(history[0x1002], [0x2000])
        self.assertEqual(history[0x2001], [0x1002, 0x1105])


if __name__ == '__main__':
    unittest.main(verbosity=2)
