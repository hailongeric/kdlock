"""Acceptance must fail on either throughput metric, missing rounds or no JIT."""
from argparse import Namespace
import unittest
import copy
from pathlib import Path
import tempfile

from mutex_study import (GRID, evaluate, metrics, require_fresh,
                         require_owned_evidence, sample_identities)
from bench_runtime import Failure
import run


def samples(threads, arm, rate=100, peak=120, jit=1):
    return [dict(threads=threads, arm=arm, repeat=r, mutex_entry_ratio_limit=2,
                 mutex_routing='adaptive', mutex_acceptance='adaptive-performance',
                 jit_bodies=jit if arm == 'kdlock' else 0,
                 measurement=dict(completed=rate, wall_ns=1000000000,
                     worker_cpu_ns=threads*1000000000, peak=dict(throughput_ops_s=peak),
                     workers=[dict(completed=rate/threads) for _ in range(threads)]))
            for r in range(3)]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [r for t in GRID for r in samples(t, 'kdlock')]
        self.candidate = [r for t in GRID for arm in ('kdlock', 'native') for r in samples(t, arm)]

    def test_complete_and_partial(self):
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'PASS')
        partial = [r for r in self.candidate if r['threads'] == 4]
        self.assertEqual(evaluate(self.baseline, partial)['verdict'], 'INCOMPLETE')

    def test_owned_cabi_stage_identities_cannot_be_pooled(self):
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
            owned_mutex_cabi=True, mutex_acceptance='adaptive-performance'))
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update({key: value for key, value in spec.items()
                            if key not in ('threads', 'repeat', 'arm', 'name')})
        result = evaluate(self.baseline, self.candidate)
        self.assertEqual((result['owned_entry_abi'], result['owned_caller_policy']), (4, 'c_abi_v2'))
        self.assertEqual(result['owned_acquire_policy'], 'linux_local_first')
        self.assertEqual(result['owned_release_policy'], 'guarded_owner_release')
        first = self.candidate[0]
        abi2, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
            mutex_acceptance='adaptive-performance'))
        for changes in (dict(owned_acquire_policy='bounded_native_first'),
                        dict(owned_release_policy='unrecorded'),
                        {key: abi2[key] for key in (*run.OWNED_CALLER_FIELDS,
                            'entry_abi', 'caller_abi', 'caller_shell',
                            'owned_preflight_policy', 'owned_mutex_preflight',
                            'owned_mutex_preflight_spins', 'owned_mutex_preflight_queue')}):
            saved = dict(first)
            first.update(changes)
            with self.subTest(changes=changes), self.assertRaises(Failure):
                evaluate(self.baseline, self.candidate)
            first.clear(); first.update(saved)

    def test_owned_candidate_keeps_implementation_and_threshold_identity(self):
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(mutex_implementation='owned-v1', mutex_entry_ratio_limit=None,
                           owned_mutex_entry_ratio_limit=4, registry_lock_kind=3, entry_abi=2,
                           caller_abi='clobber', caller_shell='owned_mutex_outer_cookie',
                           cookie_storage='owned_acquisition_local', owned_queue_policy='finite_fifo',
                           mutex_wait_counter_scope='owned_delegate_waits')
        result = evaluate(self.baseline, self.candidate)
        self.assertEqual((result['implementation'], result['threshold_field'], result['threshold']),
                         ('owned-v1', 'owned_mutex_entry_ratio_limit', 4))
        self.assertEqual(result['verdict'], 'PASS')
        for key, value in (('owned_queue_policy', 'numa_reorder'),
                           ('caller_shell', 'mutex_outer_cookie'), ('entry_abi', 3)):
            original = self.candidate[0][key]
            self.candidate[0][key] = value
            with self.subTest(key=key), self.assertRaises(Failure):
                evaluate(self.baseline, self.candidate)
            self.candidate[0][key] = original
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(owned_mutex_refill=True, owned_queue_policy='bounded_fifo_refill')
        self.assertEqual(evaluate(self.baseline, self.candidate)['queue_policy'], 'bounded_fifo_refill')
        self.candidate[0].update(owned_mutex_refill=False, owned_queue_policy='finite_fifo')
        with self.assertRaisesRegex(Failure, 'one queue policy'):
            evaluate(self.baseline, self.candidate)
        self.candidate[0]['mutex_implementation'] = 'legacy'
        with self.assertRaisesRegex(Failure, 'one mutex implementation'):
            evaluate(self.baseline, self.candidate)

    def test_preflight_candidates_and_zero_gate_are_not_pooled(self):
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(mutex_implementation='owned-v1', mutex_entry_ratio_limit=None,
                    owned_mutex_entry_ratio_limit=4, registry_lock_kind=3, entry_abi=2,
                    caller_abi='clobber', caller_shell='owned_mutex_outer_cookie',
                    cookie_storage='owned_acquisition_local', owned_queue_policy='finite_fifo',
                    mutex_wait_counter_scope='owned_delegate_waits',
                    owned_preflight_policy='c_abi_v1', owned_mutex_preflight_spins=0)
        result = evaluate(self.baseline, self.candidate)
        self.assertEqual((result['owned_preflight_policy'], result['owned_mutex_preflight_spins']),
                         ('c_abi_v1', 0))
        first = next(r for r in self.candidate if r['arm'] == 'kdlock')
        first['owned_mutex_preflight_spins'] = 64
        with self.assertRaisesRegex(Failure, 'one preflight policy'):
            evaluate(self.baseline, self.candidate)
        del first['owned_preflight_policy'], first['owned_mutex_preflight_spins']
        with self.assertRaisesRegex(Failure, 'one preflight policy'):
            evaluate(self.baseline, self.candidate)

    def test_explicit_capture_first_and_implicit_gate_remain_separate(self):
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(mutex_implementation='owned-v1', mutex_entry_ratio_limit=None,
                           owned_mutex_entry_ratio_limit=4, registry_lock_kind=3, entry_abi=2,
                           caller_abi='clobber', caller_shell='owned_mutex_outer_cookie',
                           cookie_storage='owned_acquisition_local', owned_queue_policy='finite_fifo',
                           mutex_wait_counter_scope='owned_delegate_waits',
                           owned_mutex_preflight=False, owned_preflight_policy='capture_first',
                           owned_mutex_preflight_spins=0, owned_mutex_preflight_queue=False)
        result = evaluate(self.baseline, self.candidate)
        self.assertEqual(result['owned_preflight_policy'],'capture_first')
        self.assertFalse(result['owned_mutex_preflight'])
        first = next(r for r in self.candidate if r['arm'] == 'kdlock')
        first.update(owned_mutex_preflight=True,owned_preflight_policy='c_abi_v1')
        with self.assertRaisesRegex(Failure,'one preflight policy'):
            evaluate(self.baseline,self.candidate)
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(owned_mutex_preflight=True,owned_preflight_policy='c_abi_v1')
        self.assertTrue(evaluate(self.baseline,self.candidate)['owned_mutex_preflight'])
        del first['owned_mutex_preflight']
        with self.assertRaisesRegex(Failure,'one preflight policy'):
            evaluate(self.baseline,self.candidate)

    def test_queued_preflight_candidates_are_not_pooled(self):
        for row in self.candidate:
            if row['arm'] == 'kdlock':
                row.update(mutex_implementation='owned-v1', mutex_entry_ratio_limit=None,
                    owned_mutex_entry_ratio_limit=4, registry_lock_kind=3, entry_abi=2,
                    caller_abi='clobber', caller_shell='owned_mutex_outer_cookie',
                    cookie_storage='owned_acquisition_local', owned_queue_policy='finite_fifo',
                    mutex_wait_counter_scope='owned_delegate_waits',
                    owned_preflight_policy='c_abi_v1', owned_mutex_preflight_spins=64,
                    owned_mutex_preflight_queue=True)
        self.assertTrue(evaluate(self.baseline, self.candidate)['owned_mutex_preflight_queue'])
        first = next(r for r in self.candidate if r['arm'] == 'kdlock')
        first['owned_mutex_preflight_queue'] = False
        with self.assertRaisesRegex(Failure, 'one preflight policy'):
            evaluate(self.baseline, self.candidate)
        del first['owned_mutex_preflight_queue']
        with self.assertRaisesRegex(Failure, 'one preflight policy'):
            evaluate(self.baseline, self.candidate)

    def test_both_metrics_are_independent(self):
        for metric in ('whole', 'peak'):
            with self.subTest(metric=metric):
                broken = [r for r in self.candidate if r['threads'] != 4 or r['arm'] != 'kdlock']
                broken += samples(4, 'kdlock', rate=96 if metric == 'whole' else 100,
                                  peak=115 if metric == 'peak' else 120)
                result = evaluate(self.baseline, broken)
                self.assertEqual(result['verdict'], 'REJECTED')
                self.assertEqual([c['threads'] for c in result['checks'] if not c['passed']], [4])

    def test_regression_requires_jit_in_every_round(self):
        for r in self.candidate:
            if r['threads'] == 60 and r['repeat'] == 1:
                r['jit_bodies'] = 0
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'REJECTED')

    def test_missing_or_duplicate_round_is_not_valid(self):
        rows = samples(4, 'kdlock')
        with self.assertRaises(Failure):
            metrics(rows[:2])
        with self.assertRaises(Failure):
            metrics([rows[0], rows[0], rows[2]])

    def test_primary_native_execution_is_allowed(self):
        for r in self.candidate:
            if r['threads'] <= 28:
                r['jit_bodies'] = 0
        self.assertEqual(evaluate(self.baseline, self.candidate)['verdict'], 'PASS')

    def test_confirmation_cannot_reuse_screen_or_previous_block(self):
        rows = samples(4, 'kdlock')
        for i, row in enumerate(rows):
            row['measurement'].update(started_ns=10*i, finished_ns=10*i+1)
        seen = sample_identities(rows)
        with self.assertRaises(Failure):
            require_fresh(rows, seen)
        for row in rows:
            row['measurement']['started_ns'] += 100
            row['measurement']['finished_ns'] += 100
        require_fresh(rows, seen)
        with self.assertRaises(Failure):
            require_fresh(rows, seen)


class LocalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        from mutex_local_study import evaluate as evaluate_local
        self.evaluate = evaluate_local
        self.rows = [r for t in range(1, 9) for arm in ('kdlock', 'native')
                     for r in samples(t, arm, jit=0)]

    def test_local_scope_allows_self_without_high_thread_grid(self):
        result = self.evaluate(self.rows)
        self.assertTrue(result['passed'])
        self.assertEqual([row['threads'] for row in result['checks']], list(range(1, 9)))

    def test_local_scope_requires_both_native_ratios(self):
        for field in ('whole', 'peak'):
            rows = copy.deepcopy(self.rows)
            for row in rows:
                if row['threads'] == 3 and row['arm'] == 'kdlock':
                    if field == 'whole':
                        row['measurement']['wall_ns'] = 1100000000
                    else:
                        row['measurement']['peak']['throughput_ops_s'] = 115
            result = self.evaluate(rows)
            self.assertFalse(result['passed'])
            self.assertEqual([row['threads'] for row in result['checks'] if not row['passed']], [3])

    def test_local_scope_requires_all_eight_three_round_cohorts(self):
        with self.assertRaises(Failure):
            self.evaluate([row for row in self.rows if row['threads'] != 8])
        with self.assertRaises(Failure):
            self.evaluate(self.rows[:-1])


class OwnedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.log = 'kd_owned_mutex: bodies=9 batches=2 refusals=0 early_releases=0\n'
        (self.folder/'kernel.log').write_text(self.log)
        run.write_json(self.folder/'drain.counts.json', dict(active=0))
        self.record = dict(arm='kdlock', lock_kind='mutex', threads=4,
            mutex_implementation='owned-v1', registry_lock_kind=3, entry_abi=2,
            caller_abi='clobber', caller_shell='owned_mutex_outer_cookie',
            cookie_storage='owned_acquisition_local', owned_queue_policy='finite_fifo',
            mutex_wait_counter_scope='owned_delegate_waits', mutex_routing='adaptive',
            mutex_acceptance='adaptive-performance', mutex_spin_limit=4096,
            mutex_entry_ratio_limit=None, owned_mutex_entry_ratio_limit=256,
            spin_entry_ratio_limit=2, spin_prefetch=2, mutex_wait_mode='blocking',
            jit_bodies=5, execution_class='JIT', jit_acceptance='PASS',
            layout=dict(lock_bytes=32, line_bytes=64, lock_addr=4096, data_addr=8192),
            published_before=dict(entry=dict(lock_kind=3, entry_abi=2, pid=0, status=0, code=12288)),
            parameters=dict(bench_quiet='Y', jit_timing='N', bench_lock_addr='4096',
                spin_entry_ratio_limit='2', spin_prefetch='2', spin_delegate='Y',
                owned_mutex_spin_limit='4096', owned_mutex_entry_ratio_limit='256',
                owned_mutex_self_route='N', mutex_native_route='N',
                owned_mutex_native_after_control='0'),
            owned_observations=dict(bodies=9, batches=2, refusals=0, early_releases=0))

    def test_owned_jit_and_self_classification_and_legacy_compatibility(self):
        require_owned_evidence(self.record, self.folder)
        self.record.update(owned_mutex_refill=True, owned_queue_policy='bounded_fifo_refill')
        self.record['parameters']['owned_mutex_refill'] = 'Y'
        require_owned_evidence(self.record, self.folder)
        self.record['owned_mutex_refill'] = False
        with self.assertRaisesRegex(Failure, 'FIFO policy'):
            require_owned_evidence(self.record, self.folder)
        self.record.update(owned_mutex_refill=True)
        self.record.update(jit_bodies=0, execution_class='KD_SELF', jit_acceptance='ADAPTIVE_SELF')
        require_owned_evidence(self.record, self.folder)
        require_owned_evidence({}, Path('/unused'))
        require_owned_evidence(dict(mutex_implementation='legacy'), Path('/unused'))

    def test_owned_cabi_requires_matching_published_abi_and_stage_readback(self):
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
            owned_mutex_cabi=True, mutex_acceptance='adaptive-performance'))
        record = dict(self.record, **{key: spec[key] for key in
            (*run.OWNED_CALLER_FIELDS, 'entry_abi', 'caller_abi', 'caller_shell',
             'owned_mutex_preflight', 'owned_preflight_policy',
             'owned_mutex_preflight_spins', 'owned_mutex_preflight_queue')})
        record['parameters'] = dict(record['parameters'], owned_mutex_preflight_spins='0',
            owned_mutex_preflight_queue='N', owned_mutex_reuse_spins='0', owned_mutex_protocol='linux_local_first_v1')
        with self.assertRaisesRegex(Failure, 'wrong family/ABI'):
            require_owned_evidence(record, self.folder)
        record['published_before'] = dict(entry=dict(record['published_before']['entry'], entry_abi=4))
        require_owned_evidence(record, self.folder)
        missing = dict(record); del missing['owned_entry_abi']
        with self.assertRaisesRegex(Failure, 'incomplete owned caller'):
            require_owned_evidence(missing, self.folder)
        wrong = copy.deepcopy(record)
        wrong['parameters']['owned_mutex_protocol'] = 'bounded_native_first_v1'
        with self.assertRaisesRegex(Failure, 'provider protocol'):
            require_owned_evidence(wrong, self.folder)
        wrong['parameters']['owned_mutex_protocol'] = 'linux_local_first_v1'
        wrong['parameters']['owned_mutex_native_first_spins'] = '4096'
        with self.assertRaisesRegex(Failure, 'provider protocol'):
            require_owned_evidence(wrong, self.folder)

    def test_changed_owned_identity_and_live_observations_are_rejected(self):
        variants = [dict(registry_lock_kind=2), dict(entry_abi=3),
                    dict(owned_queue_policy='unrecorded'), dict(caller_shell='mutex_outer_cookie'),
                    dict(execution_class='ADAPTIVE_NATIVE'), dict(jit_acceptance='ADAPTIVE_SELF'),
                    dict(owned_mutex_force_full=True), dict(scenario='early')]
        for key, changes in (
                ('layout', dict(lock_bytes=24)), ('layout', dict(lock_addr=4097)),
                ('published_before', dict(entry=dict(lock_kind=2, entry_abi=2, pid=0, status=0, code=1))),
                ('published_before', dict(entry=dict(lock_kind=3, entry_abi=3, pid=0, status=0, code=1))),
                ('parameters', dict(owned_mutex_entry_ratio_limit='2')),
                ('parameters', dict(owned_mutex_self_route='Y')),
                ('owned_observations', dict(bodies=5))):
            variants.append({key: dict(self.record[key], **changes)})
        for changes in variants:
            record = copy.deepcopy(self.record)
            record.update(changes)
            with self.subTest(changes=changes), self.assertRaises(Failure):
                require_owned_evidence(record, self.folder)

    def test_raw_fault_drain_and_provider_receipts_are_required(self):
        for log in ('', self.log * 2, self.log + 'BUG: unexpected lock owner\n'):
            (self.folder/'kernel.log').write_text(log)
            with self.subTest(log=log), self.assertRaises(Failure):
                require_owned_evidence(self.record, self.folder)
        (self.folder/'kernel.log').write_text(self.log)
        run.write_json(self.folder/'drain.counts.json', dict(active=1))
        with self.assertRaisesRegex(Failure, 'workers did not drain'):
            require_owned_evidence(self.record, self.folder)


if __name__ == '__main__':
    unittest.main()
