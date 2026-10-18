"""Proved source-branch specialization never relies on helper/stack privacy."""

import struct
import unittest
from copy import copy

from test_jit_diagnostics import translator
import constant_paths


def call(target, source):
    return b'\xe8' + struct.pack('<i', target - source - 5)


class ConstantPathTests(unittest.TestCase):
    def graph(self, regions):
        return translator.decode_regions(regions, 0, set())

    def specialize(self, raw, **kwargs):
        blocks, databases = self.graph([(bytes.fromhex(raw), 0x1000, [0x1000])])
        return constant_paths.specialize(blocks, databases, 0x1000, **kwargs)

    @staticmethod
    def names(blocks):
        return [line.name.upper() for block in blocks.values() for line in block.lines]

    def test_known_size_excludes_warning_but_unknown_or_large_size_does_not(self):
        # CMP RDX,INT_MAX; JA cold UD2; RET; UD2.
        tail = bytes.fromhex('4881faffffff7f7701c30f0b')
        for prefix, warning in (('ba40000000', False), ('', True),
                                ('baffffffff', True), ('488b1424', True)):
            blocks, _, rewrites = self.specialize((bytes.fromhex(prefix) + tail).hex())
            self.assertEqual('UD2' in self.names(blocks), warning)
            if not warning:
                self.assertTrue(rewrites)

    def test_real_call_arguments_reach_nested_helper(self):
        root = bytes.fromhex('ba40000000') + call(0x2000, 0x1005) + b'\xc3'
        pad = bytes.fromhex('554889e541554989fd4154534889d3')
        pad += call(0x3000, 0x2000 + len(pad)) + bytes.fromhex('5b415c415d5dc3')
        helper = bytes.fromhex('4881faffffff7f7701c30f0b')
        blocks, databases = self.graph([(root, 0x1000, [0x1000]),
            (pad, 0x2000, [0x2000]), (helper, 0x3000, [0x3000])])
        selected, _, rewrites = constant_paths.specialize(blocks, databases, 0x1000)
        self.assertTrue(rewrites)
        self.assertNotIn('UD2', self.names(selected))

    def test_call_continuation_cannot_keep_callee_saved_or_volatile_facts(self):
        for prefix, comparison in (('ba40000000', '4881faffffff7f'),
                                   ('bb40000000', '4881fbffffff7f')):
            root = bytes.fromhex(prefix) + call(0x2000, 0x1005)
            root += bytes.fromhex(comparison + '7701c30f0b')
            blocks, databases = self.graph([(root, 0x1000, [0x1000]),
                                            (b'\xc3', 0x2000, [0x2000])])
            selected, _, _ = constant_paths.specialize(blocks, databases, 0x1000)
            self.assertIn('UD2', self.names(selected))

    def test_ambiguous_join_keeps_both_edges(self):
        # JRCXZ selects count 64 or UINT_MAX. Neither branch assumption can
        # remove a warning reachable through the other actual input.
        raw = 'e307ba40000000eb05baffffffff4881faffffff7f7701c30f0b'
        self.assertIn('UD2', self.names(self.specialize(raw)[0]))

    def test_memory_value_is_never_inferred_from_a_prior_store(self):
        raw = '48c7042440000000488b14244881faffffff7f7701c30f0b'
        self.assertIn('UD2', self.names(self.specialize(raw)[0]))

    def test_indirect_history_and_budget_leave_original_graph(self):
        raw = 'ba400000004881faffffff7f7701c30f0b'
        for kwargs in ({'indirect_history': {0x7777: [0x1000]}}, {'max_visits': 0}):
            blocks, _, rewrites = self.specialize(raw, **kwargs)
            self.assertFalse(rewrites)
            self.assertIn('UD2', self.names(blocks))

    def test_partial_register_and_carry_conditions_remain_exact(self):
        # DL=64 does not define high RDX bits. INC does not define CF.
        for raw in ('b2404881faffffff7f7701c30f0b', 'ffc07201c30f0b'):
            self.assertIn('UD2', self.names(self.specialize(raw)[0]))

    def test_undefined_flags_cannot_keep_a_previous_compare_fact(self):
        # MUL does not define ZF. A lifter that omits that flag assignment
        # must not leave CMP's old equality fact available for pruning JNZ.
        raw = '31c039c0f7e07501c30f0b'
        self.assertIn('UD2', self.names(self.specialize(raw)[0]))

    def test_overlapping_instruction_streams_leave_original_graph(self):
        raw = bytes.fromhex('ba400000004881faffffff7f7701c30f0b')
        blocks, databases = self.graph([(raw, 0x1000, [0x1000])])
        first = blocks[0x1000]
        alternate = copy(first)
        alternate.lines = first.lines[1:]
        blocks[alternate.lines[0].offset] = alternate
        databases[alternate] = databases[first]
        selected, _, rewrites = constant_paths.specialize(blocks, databases, 0x1000)
        self.assertIs(selected, blocks)
        self.assertFalse(rewrites)


if __name__ == '__main__':
    unittest.main()
