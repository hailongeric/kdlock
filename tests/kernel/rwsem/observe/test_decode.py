#!/usr/bin/env python3
"""Synthetic ABI/ordering fixtures; run only in the designated VM."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('rwsem_observe', Path(__file__).with_name('collect.py'))
obs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(obs)


def event(pair, api, kind, ns, result=0, tid=10, start=1000, cpu=0, lock=4096):
    return dict(sequence=0, time_ns=ns, lock=lock, pairing_id=pair,
                task_start_boottime_ns=start, result=result, tid=tid, tgid=tid,
                cpu=cpu, event=kind, api=api, reserved=0)


def snapshot(events, **overrides):
    header = dict(abi=1, header_bytes=obs.H.size, event_bytes=obs.E.size,
                  symbol_bytes=obs.S.size, symbol_count=11, capacity=100,
                  reserved=len(events), count=len(events), overflow=0, missed=0,
                  inflight=0, errors=0, armed=0, stopped=1, start_ns=1, stop_ns=120,
                  proxy_proof=0, duration_ms=10, cutoff_ns=100)
    header.update(overrides)
    data = obs.H.pack(*(header[n] for n in obs.HEADER_FIELDS))
    for i, name in enumerate(obs.BASE_SYMBOLS):
        data += obs.S.pack(i+1, obs.CATEGORIES[i], obs.RETURNS[i], 1, ('kd_'+name).encode())
    for i, row in enumerate(events):
        row = dict(row, sequence=i+1)
        data += obs.E.pack(*(row[n] for n in obs.EVENT_FIELDS))
    return data


class DecodeTests(unittest.TestCase):
    def test_write_downgrade_read_tail_and_no_proxy_claim(self):
        rows = [event(1, 1, 1, 10), event(1, 1, 2, 20),
                event(2, 9, 4, 40), event(2, 9, 5, 45),
                event(3, 11, 6, 70), event(3, 11, 7, 75)]
        d = obs.decode(snapshot(rows))
        self.assertTrue(d['passed'])
        self.assertFalse(d['proxy_proof'])
        self.assertIsNone(d['delegation_episodes'])
        self.assertIsNone(d['critical_section_ratio'])
        self.assertEqual([(x['mode'], x['duration_ns']) for x in d['body_intervals']], [('write', 20), ('read', 25)])
        self.assertEqual(d['body_censoring']['open_at_final_drain'], 0)

    def test_failed_killable_and_trylock_have_no_body(self):
        rows = [event(1, 2, 1, 10), event(1, 2, 3, 20, -4),
                event(2, 8, 1, 30), event(2, 8, 3, 40, 0)]
        d = obs.decode(snapshot(rows))
        self.assertTrue(d['passed'])
        self.assertEqual(d['body_intervals'], [])
        self.assertEqual(d['api_pairs'][0]['result'], -4)

    def test_trylock_success_uses_nonzero_convention(self):
        d = obs.decode(snapshot([event(1, 8, 1, 10), event(1, 8, 2, 20, 1),
                                 event(2, 11, 6, 30), event(2, 11, 7, 35)]))
        self.assertTrue(d['passed'])
        self.assertEqual(d['body_intervals'][0]['duration_ns'], 10)

    def test_misses_and_inflight_fail_without_discarding_events(self):
        rows = [event(1, 1, 1, 10)]
        d = obs.decode(snapshot(rows, missed=2, inflight=1))
        self.assertFalse(d['passed'])
        self.assertFalse(d['capture_complete'])
        self.assertEqual(len(d['events']), 1)
        self.assertTrue(any('incomplete API pair' in x for x in d['issues']))

    def test_overflow_fails_even_when_retained_pairs_are_valid(self):
        d = obs.decode(snapshot([event(1, 1, 1, 10), event(1, 1, 2, 20)],
                                capacity=2, reserved=4, count=2, overflow=2))
        self.assertFalse(d['capture_complete'])
        self.assertEqual(len(d['api_pairs']), 1)

    def test_body_cutoff_is_distinct_from_missing_api_events(self):
        d = obs.decode(snapshot([event(1, 1, 1, 10), event(1, 1, 2, 20),
                                 event(2, 10, 6, 110), event(2, 10, 7, 115)]))
        self.assertTrue(d['capture_complete'])
        self.assertEqual(d['body_censoring']['completed_intervals_crossing_cutoff'], 1)
        self.assertEqual(d['body_intervals'][0]['observed_duration_in_window_ns'], 80)
        self.assertTrue(d['api_pairs'][1]['crosses_cutoff'])

    def test_cross_task_release_is_not_guessed_as_ownership_transfer(self):
        d = obs.decode(snapshot([event(1, 5, 1, 10), event(1, 5, 2, 20),
                                 event(2, 11, 6, 30, tid=11), event(2, 11, 7, 40, tid=11)]))
        self.assertTrue(d['capture_complete'])
        self.assertEqual(d['body_intervals'], [])
        self.assertEqual(d['body_censoring']['unmatched_release'], 1)
        self.assertEqual(d['body_censoring']['open_at_final_drain'], 1)

    def test_task_start_lifetime_prevents_tid_reuse_pairing(self):
        d = obs.decode(snapshot([event(1, 5, 1, 10), event(1, 5, 2, 20),
                                 event(2, 11, 6, 30, start=2000), event(2, 11, 7, 40, start=2000)]))
        self.assertEqual(d['body_censoring']['unmatched_release'], 1)
        self.assertEqual(d['body_intervals'], [])

    def test_migration_between_entry_and_return_is_retained(self):
        d = obs.decode(snapshot([event(1, 2, 1, 10), event(1, 2, 2, 20, cpu=32)]))
        self.assertTrue(d['passed'])
        self.assertEqual([x['cpu'] for x in d['events']], [0, 32])

    def test_empty_window_is_not_an_execution_pass(self):
        d = obs.decode(snapshot([]))
        self.assertTrue(d['capture_complete'])
        self.assertFalse(d['passed'])
        self.assertFalse(d['observed'])

    def test_contradictory_return_and_pair_identity_are_rejected(self):
        for rows in ([event(1, 2, 1, 10), event(1, 2, 2, 20, -4)],
                     [event(1, 1, 1, 10), event(1, 1, 2, 20, tid=11)],
                     [event(1, 1, 2, 10), event(1, 1, 1, 20)]):
            with self.assertRaises(ValueError):
                obs.decode(snapshot(rows))

    def test_record_shape_and_capability_must_match(self):
        good = snapshot([event(1, 1, 1, 10), event(1, 1, 2, 20)])
        for data in (good[:-1], good+b'x', snapshot([], proxy_proof=1), snapshot([], armed=1),
                     snapshot([], cutoff_ns=121)):
            with self.assertRaises(ValueError):
                obs.decode(data)


if __name__ == '__main__':
    unittest.main()
