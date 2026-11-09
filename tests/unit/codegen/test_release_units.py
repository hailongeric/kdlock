"""Guest-only decoded and emitted checks for release-delimited ABI2 units.

The compiler ends at every declared release without pairing objects. These
checks establish source scope and unchanged CALL words, not runtime handoff.
"""

import struct
import unittest
from unittest.mock import patch

from test_jit_diagnostics import render, translator


def call(source, target):
    return b'\xe8' + struct.pack('<i', target - source - 5)


def jump(source, target):
    return b'\xe9' + struct.pack('<i', target - source - 5)


class ReleaseUnitTests(unittest.TestCase):
    RELEASE = 0x5000

    def decode(self, *pieces):
        return translator.decode_regions(
            [(raw, address, [address]) for address, raw in pieces],
            0, {self.RELEASE}, unit_releases={self.RELEASE})

    def select(self, blocks, databases, **kwargs):
        return translator.context_policy.jit_phase_blocks(
            blocks, databases, {0x1000}, {self.RELEASE} | set(kwargs.pop('resumable', ())),
            unit_releases={self.RELEASE}, **kwargs)

    @staticmethod
    def pcs(blocks):
        return {line.offset for block in blocks.values() for line in block.lines}

    def test_decoder_stops_before_call_and_jump_release_suffixes(self):
        suffix = bytes.fromhex('b878563412c3')
        for branch in (call, jump):
            with self.subTest(branch=branch.__name__):
                blocks, _ = self.decode((0x1000, branch(0x1000, self.RELEASE) + suffix))
                self.assertIn(0x1000, self.pcs(blocks))
                self.assertNotIn(0x1005, self.pcs(blocks))
                self.assertNotIn(self.RELEASE, self.pcs(blocks))

    def test_first_release_ends_unit_for_any_source_object(self):
        acquire = 0x6000
        for source_object in (1, 2, 0x12345678):
            with self.subTest(source_object=source_object):
                raw = call(0x1000, acquire)
                raw += b'\xbf' + struct.pack('<I', source_object)
                raw += call(0x100a, self.RELEASE) + bytes.fromhex('b878563412c3')
                blocks, databases = self.decode((0x1000, raw))
                selected, _, _ = self.select(blocks, databases, resumable={acquire})
                self.assertEqual(self.pcs(selected), {0x1000, 0x1005, 0x100a})
                self.assertFalse(selected[0x1005].bto)

    def test_release_in_callee_does_not_select_callers_suffix_or_history_island(self):
        root = call(0x1000, 0x2000) + bytes.fromhex('b878563412c3')
        helper = call(0x2000, self.RELEASE) + bytes.fromhex('b821436587c3')
        blocks, databases = self.decode(
            (0x1000, root), (0x2000, helper), (0x3000, b'\xc3'))
        selected, _, _ = self.select(blocks, databases,
            indirect_history={0x2005: [0x1005, 0x3000]})
        self.assertEqual(self.pcs(selected), {0x1000, 0x2000})
        self.assertFalse(selected[0x2000].bto)

    def test_nested_callee_release_stops_every_callers_suffix(self):
        blocks, databases = self.decode(
            (0x1000, call(0x1000, 0x2000) + b'\xc3'),
            (0x2000, call(0x2000, 0x3000) + b'\xc3'),
            (0x3000, call(0x3000, self.RELEASE) + b'\xc3'))
        selected, _, _ = self.select(blocks, databases)
        self.assertEqual(self.pcs(selected), {0x1000, 0x2000, 0x3000})

    def test_returning_branch_keeps_callers_suffix_without_release_branch_suffix(self):
        helper = bytes.fromhex('85c07401c3')
        helper += call(0x2005, self.RELEASE) + bytes.fromhex('b821436587c3')
        blocks, databases = self.decode(
            (0x1000, call(0x1000, 0x2000) + bytes.fromhex('b878563412c3')),
            (0x2000, helper))
        selected, _, _ = self.select(blocks, databases)
        self.assertIn(0x1005, self.pcs(selected))
        self.assertIn(0x2004, self.pcs(selected))
        self.assertIn(0x2005, self.pcs(selected))
        self.assertNotIn(0x200a, self.pcs(selected))
        self.assertFalse(selected[0x2005].bto)

    def test_ordinary_return_retains_actual_call_return_dispatch(self):
        blocks, databases = self.decode(
            (0x1000, call(0x1000, 0x2000) + b'\xc3'), (0x2000, b'\xc3'))
        selected, selected_dbs, _ = self.select(blocks, databases)
        history = {}
        translator.indirect_jump.find(selected, selected_dbs, history)
        self.assertIn(0x1005, self.pcs(selected))
        self.assertEqual(history[0x2001], [0x1005])

    def test_indirect_release_callees_need_a_release_free_return_path(self):
        for targets, second, expected_return in (
                ([0x2000], call(0x3000, self.RELEASE), False),
                ([0x2000, 0x3000, 0x2000], call(0x3000, self.RELEASE), False),
                ([0x2000, 0x3000], b'\xc3', True)):
            with self.subTest(targets=targets, second=second.hex()):
                blocks, databases = self.decode(
                    (0x1000, b'\xff\xd0\xc3'),
                    (0x2000, call(0x2000, self.RELEASE)), (0x3000, second))
                selected, _, _ = self.select(blocks, databases,
                    indirect_call_native=True, returning_indirect=False,
                    indirect_history={0x1002: targets})
                self.assertEqual(0x1002 in self.pcs(selected), expected_return)
                self.assertIn(0x2000, self.pcs(selected))
                self.assertEqual(0x3000 in self.pcs(selected), 0x3000 in targets)

    def test_indirect_native_return_contract_is_distinct_from_fresh_native_exit(self):
        blocks, databases = self.decode(
            (0x1000, b'\xff\xd0\xc3'),
            (0x2000, call(0x2000, self.RELEASE)))
        for history in ({}, {0x1002: [0x2000]}):
            for returning in (False, True):
                with self.subTest(history=history, returning=returning):
                    selected, _, _ = self.select(blocks, databases,
                        indirect_call_native=True, returning_indirect=returning,
                        indirect_history=history)
                    self.assertEqual(0x1002 in self.pcs(selected), returning)

    def test_indirect_ordinary_target_in_deferred_set_is_not_a_native_return(self):
        blocks, databases = self.decode(
            (0x1000, b'\xff\xd0\xc3'),
            (0x2000, call(0x2000, self.RELEASE)))
        selected, _, _ = self.select(blocks, databases,
            resumable={0x2000}, deferred_call_targets={0x2000},
            indirect_call_native=True, returning_indirect=False,
            indirect_history={0x1002: [0x2000]})
        self.assertNotIn(0x1002, self.pcs(selected))
        self.assertIn(0x2000, self.pcs(selected))

    def test_indirect_tail_return_contract_preserves_only_possible_return_paths(self):
        for leaf in (call(0x3000, self.RELEASE), b'\xc3'):
            for returning in (False, True):
                with self.subTest(leaf=leaf.hex(), returning=returning):
                    blocks, databases = self.decode(
                        (0x1000, call(0x1000, 0x2000) + b'\xc3'),
                        (0x2000, b'\xff\xe0'), (0x3000, leaf))
                    selected, _, _ = self.select(blocks, databases,
                        returning_indirect=returning,
                        indirect_history={0x2002: [0x3000, 0x3000]})
                    self.assertEqual(0x1005 in self.pcs(selected),
                                     returning or leaf == b'\xc3')
                    self.assertIn(0x2000, self.pcs(selected))
                    self.assertIn(0x3000, self.pcs(selected))

    def test_release_tail_and_cycle_do_not_invent_a_callee_return(self):
        for helper, history, more in (
                (jump(0x2000, 0x2000), {}, ()),
                (b'\xff\xe0', {0x2002: [0x3000, 0x3000]},
                 ((0x3000, call(0x3000, self.RELEASE)),))):
            with self.subTest(helper=helper.hex()):
                blocks, databases = self.decode(
                    (0x1000, call(0x1000, 0x2000) + b'\xc3'), (0x2000, helper), *more)
                selected, _, _ = self.select(blocks, databases, indirect_history=history)
                self.assertNotIn(0x1005, self.pcs(selected))
                self.assertIn(0x2000, self.pcs(selected))

    def test_deferred_callee_does_not_fetch_callers_continuation_early(self):
        blocks, databases = self.decode(
            (0x1000, call(0x1000, 0x2000) + b'\xc3'))
        with patch.object(translator.memread, 'read') as read, \
                patch.object(translator.memread, 'extend_regions') as extend:
            selected, _, _ = self.select(blocks, databases,
                resumable={0x2000}, deferred_call_targets={0x2000})
        self.assertEqual(self.pcs(selected), {0x1000})
        read.assert_not_called()
        extend.assert_not_called()

    def test_work_refusal_does_not_mutate_decoded_blocks(self):
        blocks, databases = self.decode(
            (0x1000, call(0x1000, 0x2000) + b'\xc3'),
            (0x2000, call(0x2000, self.RELEASE)))
        before = {start: (tuple(block.lines), set(block.bto)) for start, block in blocks.items()}
        with self.assertRaisesRegex(translator.context_policy.ContextFlowLimit, 'work budget'):
            self.select(blocks, databases, max_visits=0)
        self.assertEqual(before,
            {start: (tuple(block.lines), set(block.bto)) for start, block in blocks.items()})

    def test_native_release_descriptors_keep_call_word_and_exclude_suffix(self):
        raw = call(0x1000, self.RELEASE) + bytes.fromhex('64488b042528000000c3')
        for context_kind in (6, 8, 13):
            with self.subTest(context_kind=context_kind):
                assembly, log, status = render(raw.hex(), lock_kind='mutex', abi=2,
                    trusted_source=True, native_escape_capable=True,
                    kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                                    'kd_mutex_direct_unlock_clobber_v1': 0x7100},
                    returning_services={self.RELEASE: dict(cookie=1, nargs=1,
                        result_kind=2, context_kind=context_kind, symbol='native_release')},
                    return_status=True)
                self.assertEqual(status, 0, log)
                self.assertIn(b'0x1005', assembly.lower())
                self.assertIn(b'JMP             loc_5000', assembly)
                self.assertNotIn(b'loc_1005:', assembly)
                self.assertNotIn(b'FS:[', assembly)

    def test_downgrade_and_read_release_end_unit_without_reacquisition(self):
        for operation in (5, 6, 11, 13):
            with self.subTest(operation=operation):
                assembly, log, status = render(
                    (call(0x1000, self.RELEASE) + bytes.fromhex('b878563412c3')).hex(),
                    lock_kind='mutex', abi=2, trusted_source=True,
                    kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                                    'kd_mutex_direct_unlock_clobber_v1': 0x7100},
                    bound_controls={self.RELEASE: dict(operation=operation, flags=0,
                                                       symbol='rwsem_release')},
                    return_status=True)
                self.assertEqual(status, 0, log)
                self.assertIn(b'JMP             loc_5000', assembly)
                self.assertNotIn(b'loc_1005:', assembly)
                self.assertNotIn(b'0x12345678', assembly)

    def test_flat_terminal_clobber_keeps_existing_image_requirements(self):
        options = {}
        assembly, log, status = render(
            (call(0x1000, self.RELEASE) + b'\xc3').hex(), lock_kind='mutex', abi=2,
            trusted_source=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x6000,
                            'kd_mutex_direct_unlock_clobber_v1': self.RELEASE},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 128 | (1 << 13))
        self.assertIn(b'clobber_complete', assembly)
        self.assertNotIn(b'loc_1005:', assembly)

    def test_early_decoder_inner_clobber_stop_requires_retained_service(self):
        acquire = 0x6000
        raw = call(0x1000, acquire) + call(0x1005, self.RELEASE)
        raw += call(0x100a, self.RELEASE) + b'\xc3'
        options = {}
        assembly, log, status = render(raw.hex(), lock_kind='mutex', abi=2,
            trusted_source=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': acquire,
                            'kd_mutex_direct_unlock_clobber_v1': self.RELEASE},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertTrue(options['requirements'] & (1 << 8))
        self.assertIn(b'loc_1005:', assembly)
        self.assertNotIn(b'loc_100a:', assembly)


if __name__ == '__main__':
    unittest.main()
