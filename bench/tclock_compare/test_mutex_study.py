"""Acceptance must fail on either throughput metric, missing rounds or no JIT."""
import unittest
import copy
import hashlib
from pathlib import Path
import tempfile

from mutex_study import (GRID, evaluate, load_run, metrics, require_fresh,
                         require_owned_evidence, require_post_work_metadata, sample_identities)
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

    def test_post_work_studies_cannot_be_pooled(self):
        for row in self.candidate:
            row['post_work_rounds'] = 8
        with self.assertRaisesRegex(Failure, 'cannot pool different post-work'):
            evaluate(self.baseline, self.candidate)
        for row in self.baseline:
            row['post_work_rounds'] = 8
        self.assertEqual(evaluate(self.baseline, self.candidate)['post_work_rounds'], 8)
        rows = samples(4, 'kdlock')
        rows[0]['post_work_rounds'] = 8
        with self.assertRaisesRegex(Failure, 'cannot pool different post-work'):
            metrics(rows)

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


class PostWorkProvenanceTests(unittest.TestCase):
    def test_requested_rounds_are_bounded_integers(self):
        for rounds in (0, 257, True, '8'):
            with self.subTest(rounds=rounds), self.assertRaisesRegex(Failure, 'requested post-work'):
                load_run('/unused', post_work_rounds=rounds)

    def test_frozen_header_requires_explicit_separate_study(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            run.write_json(folder/'environment.json', dict(
                kernel_identity=dict(ok=True, running_build_id='5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'),
                topology=dict(online_cpus=list(range(64))),
                collector_topology=dict(role_cpus=[63]),
                cmdline='nokaslr nopvspin', preemption='(voluntary)'))
            run.write_json(folder/'binary-sha256.json', {})
            run.write_json(folder/'plan.json', [])
            header = folder/'source'/run.POST_WORK_SOURCE
            header.parent.mkdir(parents=True)
            for rounds in (64, 8):
                header.write_text(f'#define SC_POST_WORK_ROUNDS {rounds}\n')
                run.write_json(folder/'source-sha256.json', {
                    run.POST_WORK_SOURCE: hashlib.sha256(header.read_bytes()).hexdigest()})
                self.assertEqual(load_run(folder, post_work_rounds=rounds), [])
                if rounds == 8:
                    with self.assertRaisesRegex(Failure, 'frozen post-work rounds differ'):
                        load_run(folder)
                else:
                    self.assertEqual(load_run(folder), [])
            # A hash change and a missing hash are independent provenance failures.
            header.write_text('#define SC_POST_WORK_ROUNDS 64\n')
            with self.assertRaisesRegex(Failure, 'changed frozen source'):
                load_run(folder)
            run.write_json(folder/'source-sha256.json', {})
            with self.assertRaisesRegex(Failure, 'post-work source is not hashed'):
                load_run(folder)

    def test_metadata_must_match_with_narrow_legacy_compatibility(self):
        for rounds in (8, 64):
            require_post_work_metadata({}, rounds)
            require_post_work_metadata(dict(post_work_rounds=rounds), rounds)
            for value in (None, '8', True, 64 if rounds == 8 else 8):
                with self.subTest(rounds=rounds, value=value), self.assertRaises(Failure):
                    require_post_work_metadata(dict(post_work_rounds=value), rounds)
        with self.assertRaises(Failure):
            require_post_work_metadata({}, 16)


if __name__ == '__main__':
    unittest.main()
