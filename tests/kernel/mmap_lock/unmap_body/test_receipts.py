#!/usr/bin/env python3
"""Guest-only negative controls for real removal and exact ACK evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('unmap_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture():
    origins = lambda first: [dict(tid=100+i, start=(first+i)*4096, end=(first+i+3)*4096) for i in range(16)]
    a = dict(calls=16, removed=16, delegated=15, native=0, post_ban=0,
             handbacks=0, acks=0, cancelled=0, refused=0, native_only=0, failed=0, origins=origins(100))
    b = dict(a, calls=32, native=16, handbacks=15, acks=15, refused=1, native_only=1, origins=origins(200))
    c = dict(b, calls=48, native=32, post_ban=16, origins=origins(300))
    return dict(mode='body', errors=0, checks=300000, idle=1, groups=48,
                mm=0xabc, gate=0xdef, reader_peak=2, pending_peak=16, completed=48,
                cleanup_calls=144, late_fault_blocked=1, late_fault_tid=999, late_fault_code=1,
                late_fault_stack='kd_mmap_down_read\ndo_user_addr_fault', phases=[a, b, c],
                after_cleanup=dict(c, calls=192, native=176, post_ban=160))


DONE = ''.join(f'KD_MM_UNMAP done mm=abc id={i+1} origin={100+i} executor=100 '
               f'start={(100+i)*4096:x} end={(103+i)*4096:x} result=0\n' for i in range(1, 16))
ACKS = ''.join(f'KD_MM_UNMAP {kind} mm=abc id={i+17} origin={100+i} executor=100 '
               f'start={(200+i)*4096:x} end={(203+i)*4096:x}\n'
               for i in range(1, 16) for kind in ('handback', 'ack'))


class Receipts(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(runner.validate(fixture(), DONE + ACKS)['actual_remote_vma_removals'], 15)

    def test_requires_actual_mapping_and_other_task(self):
        for log in (ACKS, DONE.replace('executor=100', 'executor=101', 1) + ACKS,
                    DONE.replace('mm=abc', 'mm=abd', 1) + ACKS,
                    DONE.replace('start=65000', 'start=66000', 1) + ACKS):
            with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_requires_exact_ack_identity(self):
        for log in (DONE + ACKS.replace('KD_MM_UNMAP ack', 'omitted', 1),
                    DONE + ACKS.replace('ack mm=abc id=18', 'ack mm=abc id=19', 1)):
            with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_requires_readers_fault_and_cleanup(self):
        for key, value in [('reader_peak', 1), ('idle', 0), ('cleanup_calls', 143),
                           ('late_fault_blocked', 0), ('late_fault_code', 0), ('late_fault_stack', ''), ('errors', 1)]:
            row = fixture(); row[key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + ACKS)

    def test_requires_sticky_refusal(self):
        for key, value in [('delegated', 16), ('native_only', 0), ('post_ban', 15), ('acks', 14)]:
            row = copy.deepcopy(fixture()); row['phases'][2][key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + ACKS)


if __name__ == '__main__':
    unittest.main()
