"""Guest-only returning-primitive observation and normal retirement checks."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

from source_text import ROOT

sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
import helper_mode as helper
import bench_session


class HelperObservations(unittest.TestCase):
    def events(self):
        value = helper.expected_result(1)
        lines = []
        for stage, task, ax in (('request', 20, 0), ('enter', 10, 0),
                                ('done', 10, value), ('resume', 20, value)):
            lines.append(f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
                         f'identity=100 generation=7 sequence=3 target=200 return=400 '
                         f'image_generation=44 ax={ax:x} flags=202')
        return helper.primitive_events('\n'.join(lines))

    def validate(self, rows):
        return helper.validate_transaction(rows, dict(identity=0x100, generation=7, executor=20),
                                           10, 0x200, 44, helper.expected_result(1))

    def test_exact_transaction_and_full_ax(self):
        self.assertEqual(helper.expected_result(1), 0x993F730E40218045)
        self.assertEqual(len(self.validate(self.events())), 4)
        for index, field, value in ((1, 'task', 20), (3, 'executor', 21),
                                     (3, 'image_generation', 45), (3, 'return', 0x408),
                                     (3, 'sequence', 4), (3, 'ax', 0x40218045),
                                     (3, 'flags', 0x203), (2, 'identity', 0x101)):
            rows = self.events()
            rows[index][field] = value
            with self.subTest(field=field), self.assertRaises(helper.rt.Failure):
                self.validate(rows)
        with self.assertRaises(helper.rt.Failure):
            self.validate(self.events()[:-1])

    def test_registration_arity_and_unique_target(self):
        table = ('a 1000 6 1 1 jit_test_call_scalar\n'
                 'b 2000 6 1 1 jit_test_call_wait\n')
        rows, _ = helper.call_table(table)
        self.assertEqual(rows['jit_test_call_scalar']['cookie'], 10)
        for changed in (table.replace(' 6 ', ' 7 ', 1), table.replace('b 2000', '0 2000'),
                        table.replace('b 2000', 'b 1000'), table + table.splitlines()[0] + '\n'):
            with self.assertRaises(helper.rt.Failure):
                helper.call_table(changed)

    def test_snapshot_exact_offsets_and_size(self):
        words = [1, 1, 0] + [0] * 184
        row = [0x1000, 1, 10, 0x1800, 0x1000, 0x5000, 0, 0,
               1, *helper.ARGUMENTS, helper.expected_result(1), helper.expected_result(1),
               1, 2, 1, 1, 1, 1, 1]
        self.assertEqual(len(row), 23)
        words[26:49] = row
        data = struct.pack('=187Q', *words)
        decoded = helper.decode_helper_snapshot(data)['slots'][1]
        self.assertEqual(decoded['arguments'], [1, *helper.ARGUMENTS])
        self.assertEqual(decoded['body_result'], helper.expected_result(1))
        self.assertEqual(decoded['child_released'], 1)
        with self.assertRaises(helper.rt.Failure):
            helper.decode_helper_snapshot(data[:-8])

    def test_optional_hook_follows_source_retire_before_unload(self):
        session = bench_session.Session.__new__(bench_session.Session)
        session.loaded_kd = session.loaded_source = True
        session.workload_module = Path('/unused/jit_continuation_test.ko')
        session.record = {}
        order = []
        session.faults = session.stop_daemon = session.save = lambda: None
        session.counts = lambda label: dict(active=0)
        session.run = lambda argv, log: order.append('unload-' + argv[1])
        session.after_source_retire = lambda: order.append('unregister')
        def retire(*args):
            order.append('retire')
        with patch.object(bench_session, 'status', return_value=dict(frames=0, writers=0)), \
             patch.object(bench_session, 'info', return_value=dict(state=2, modules=0, frames=0, writers=0)), \
             patch.object(bench_session.os, 'open', return_value=9), \
             patch.object(bench_session.os, 'close'), \
             patch.object(bench_session.fcntl, 'ioctl', side_effect=retire):
            session.cleanup()
        self.assertEqual(order, ['retire', 'unregister', 'unload-jit_continuation_test', 'unload-kdlock_km'])


if __name__ == '__main__':
    unittest.main()
