"""VM-only acceptance checks for the opt-in retained continuation probe."""
from copy import deepcopy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
import bench_runtime as rt
from handoff_mode import (decode_snapshot, decoded_source_blocks, validate_root,
                         decoded_ret_successors, source_call_return_offset)
from helper_mode import ARGUMENTS, expected_result


class HandoffProofTests(unittest.TestCase):
    def fixture(self):
        row = dict(origin=11, executor=22, identity=0x100, generation=7,
                   object=0x9000, depth=0, entry=0x8000, may_delegate=True,
                   image_generation=5, ip=0x1000, sp=0x2000)
        events = [dict(row, event=event) for event in ('enter', 'handoff_ready', 'handoff_finished')]
        slot = dict(calls=1, pid=11, entry_sp=0x2000, return_word=0x8015,
                    arguments=[0, *ARGUMENTS], result=expected_result(0), after=1)
        observation = dict(wrapper=0x1000, leaves=[0x1100, 0x1200, 0x1300], body=0x1400, slots=[slot])
        return events, observation, dict(entry=0x8000, generation=5)

    def test_exact_cold_wrapper_and_indirect_leaf(self):
        events, observation, image = self.fixture()
        for target in (0x1000, 0x1100):
            events[1]['ip'] = target
            root, point = validate_root(events, 11, 0, observation, image, {0x8015})
            self.assertEqual((root['executor'], point['ip']), (22, target))

    def test_returned_body_is_separate_from_handback(self):
        events, observation, image = self.fixture()
        events = [events[0], dict(events[0], event='returned')]
        root, point = validate_root(events, 11, 0, observation, image, {0x8015})
        self.assertEqual(root['executor'], 22)
        self.assertIsNone(point)

    def test_RET_exports_the_source_return_word_after_one_pop(self):
        events, observation, image = self.fixture()
        events[1].update(ip=observation['slots'][0]['return_word'], sp=0x2008)
        self.assertEqual(validate_root(events, 11, 0, observation, image, {0x8015})[1]['sp'], 0x2008)
        events[1]['sp'] = 0x2010
        with self.assertRaises(rt.Failure):
            validate_root(events, 11, 0, observation, image, {0x8015})
        self.assertEqual(decoded_ret_successors({0x3000: 'loc_3000\nRET        ',
                                                0x4000: 'loc_4000\nMOV EAX, 1\nRET'}), {0x3001})

    def test_rejects_packet_identity_replay_and_incomplete_terminal(self):
        events, observation, image = self.fixture()
        mutations = (
            lambda e, o: e[1].update(sp=0x2008),
            lambda e, o: e[1].update(ip=0x9999),
            lambda e, o: e[1].update(image_generation=4),
            lambda e, o: e[2].update(generation=8),
            lambda e, o: o['slots'][0].update(calls=2),
            lambda e, o: o['slots'][0].update(return_word=0x8016),
            lambda e, o: o['slots'][0].update(arguments=[1, *ARGUMENTS]),
            lambda e, o: e.pop(),
            lambda e, o: e.append(dict(e[0], event='returned')),
        )
        for index, change in enumerate(mutations):
            with self.subTest(index=index):
                changed_events, changed_observation = deepcopy(events), deepcopy(observation)
                change(changed_events, changed_observation)
                with self.assertRaises(rt.Failure):
                    validate_root(changed_events, 11, 0, changed_observation, image, {0x8015})

    def test_snapshot_size_and_source_entries(self):
        words = [1, 0x1000, 0x1100, 0x1200, 0x1300, 0x1400, 0] + [0] * 96
        state = decode_snapshot(struct.pack('=103Q', *words))
        self.assertEqual((state['body'], len(state['slots'])), (0x1400, 8))
        with self.assertRaises(rt.Failure):
            decode_snapshot(b'\0' * 816)

    def test_missing_callee_label_is_not_decoded_source_coverage(self):
        assembly = ('loc_1000:\nPUSHFQ\nMOVABS R14, 0x1000\nJMP exit\n'
                    '/*\nloc_1100\nMOV EAX, 1\nRET\n */ \nloc_1100:\nMOV EAX, 1\n')
        self.assertEqual(set(decoded_source_blocks(assembly)), {0x1100})

    def test_absolute_address_is_separate_from_actual_CALL_return_word(self):
        self.assertIsNone(source_call_return_offset(11, 0, bytes.fromhex('48c7850000000000000000'), 7))
        self.assertEqual(source_call_return_offset(4, -4, bytes.fromhex('e800000000'), 1), 5)
        with self.assertRaises(rt.Failure):
            source_call_return_offset(4, -4, bytes.fromhex('9000000000'), 1)
        with self.assertRaises(rt.Failure):
            source_call_return_offset(4, 0, bytes.fromhex('e800000000'), 1)


if __name__ == '__main__':
    unittest.main()
