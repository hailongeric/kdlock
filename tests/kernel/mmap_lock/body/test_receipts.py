#!/usr/bin/env python3
"""Negative controls for actual body/ACK/executor receipts; run only in the VM."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('body_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture():
    a = dict(calls=2048, supported=2048, delegated=1, handbacks=0, native=0,
             post_ban=0, cancelled=0, acks=0, native_only=0, tids=list(range(100, 116)))
    b = dict(a, calls=2064, handbacks=15, native=16, acks=15, native_only=1)
    c = dict(b, calls=2576, native=528, post_ban=512)
    return dict(mm=0xabc, lock=0xdef, errors=0, checks=53, completed=2576,
                reader_peak=2, pending_peak=16, idle=1, unmapped=16, phases=[a, b, c])


LOG = 'KD_MM_BODY done mm=abc origin=100 executor=101 start=10000 end=13000 behavior=16 result=0\n'


class Receipts(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(runner.validate(fixture(), LOG)['returned_compiled_bodies'], 1)

    def test_incomplete_effect_or_drain(self):
        for key, value in [('errors', 1), ('completed', 2575), ('reader_peak', 1),
                           ('pending_peak', 15), ('idle', 0), ('unmapped', 15)]:
            with self.subTest(key=key):
                row = fixture(); row[key] = value
                with self.assertRaises(Exception): runner.validate(row, LOG)

    def test_not_publication_or_local_execution(self):
        for log in ['', LOG.replace('executor=101', 'executor=100'),
                    LOG.replace('mm=abc', 'mm=abd'), LOG.replace('result=0', 'result=-1'),
                    LOG.replace('origin=100', 'origin=999')]:
            with self.subTest(log=log):
                with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_handback_ack_and_sticky_ban(self):
        for phase, key, value in [(0, 'delegated', 0), (1, 'acks', 14),
                                  (1, 'native_only', 0), (2, 'delegated', 2),
                                  (2, 'handbacks', 16), (2, 'post_ban', 511),
                                  (2, 'calls', 2575)]:
            with self.subTest(phase=phase, key=key):
                row = copy.deepcopy(fixture()); row['phases'][phase][key] = value
                with self.assertRaises(Exception): runner.validate(row, LOG)


if __name__ == '__main__':
    unittest.main()
