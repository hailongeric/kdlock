#!/usr/bin/env python3
"""Guest-only negative controls for physical-page and exact refusal evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('fault_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture():
    a = dict(calls=256, supported=256, delegated=1, native=0, post_ban=0,
             handbacks=0, acks=0, cancelled=0, refused=0, native_only=0, tids=list(range(100, 116)))
    b = dict(a, calls=272, native=16, handbacks=15, acks=15, refused=1, native_only=1)
    c = dict(b, calls=400, native=144, post_ban=128)
    return dict(mode='body', errors=0, checks=4000000, idle=1, unmapped_pages=512,
                mm=0xabc, gate=0xdef, reader_peak=2, completed=400, delegated_with_readers=1,
                phases=[a, b, c], pages=[dict(address=0x10000+i*4096, pfn=1000+i,
                origin=100+i//16) for i in range(256)])


DONE = 'KD_MM_FAULT done mm=abc id=1 origin=100 executor=101 address=10000 pfn=3e8\n'
ACKS = ''.join(f'KD_MM_FAULT {kind} mm=abc id={i+257} origin={i+100} executor=116 address={0x110000+i*4096:x}\n'
               for i in range(15) for kind in ('handback', 'ack'))


class Receipts(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(runner.validate(fixture(), DONE + ACKS)['actual_remote_page_installations'], 1)

    def test_requires_real_pte_and_other_task(self):
        for log in [ACKS, DONE.replace('executor=101', 'executor=100') + ACKS,
                    DONE.replace('pfn=3e8', 'pfn=3e9') + ACKS,
                    DONE.replace('mm=abc', 'mm=abd') + ACKS]:
            with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_requires_matching_ack_identity(self):
        for log in [DONE + ACKS.replace('KD_MM_FAULT ack', 'omitted', 1),
                    DONE + ACKS.replace('ack mm=abc id=257', 'ack mm=abc id=999', 1)]:
            with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_requires_contents_readers_and_cleanup(self):
        for key, value in [('completed', 399), ('reader_peak', 1), ('idle', 0),
                           ('unmapped_pages', 511), ('delegated_with_readers', 0), ('errors', 1)]:
            row = fixture(); row[key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + ACKS)

    def test_requires_sticky_refusal(self):
        for key, value in [('delegated', 2), ('native_only', 0), ('post_ban', 127), ('acks', 14)]:
            row = copy.deepcopy(fixture()); row['phases'][2][key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + ACKS)


if __name__ == '__main__':
    unittest.main()
