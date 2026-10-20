"""Guest-only focused tests for mix/oracles, plans, reporting and boot evidence."""
import copy
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import boot_policy
from oracle import jit_evidence, post_work_checksum, validate, writes_for
import run
import client
import session
import bench_session
from protocol import RUN_FORMAT


def fixture(workload='cacheline', percent=50):
    args = run.parser().parse_args(['--functional', '--repeats', '1', '--backends', 'kdlock',
        '--workloads', workload, '--cachelines', '4', '--write-percent', str(percent), '--threads', '2'])
    spec = run.make_plan(args)[0]
    spec['iterations'] = 100
    snap = dict(values=[0] * 16, lock_addr=4096, gate_addr=4100, entry=8192, version=1,
                backend=2, workload=int(workload == 'rcuht'), lines=spec['cachelines'],
                post_work_rounds=4, cnts=0, gate=0, active=0)
    workers = [dict(cpu=i, observed_cpu=i, completed=100, reads=100 - percent, writes=percent,
                    read_errors=0, read_hits=0, checksum=post_work_checksum(100, 4), cpu_ns=10, active_started_ns=101,
                    kernel_finished_ns=199, finished_ns=200) for i in range(2)]
    after = copy.deepcopy(snap)
    after['values'] = ([2 * percent] * 4 + [0] * 12 if workload == 'cacheline' else
                       [2 * percent, percent, percent, 0] + [0] * 12)
    return spec, dict(schema=1, complete=True, data_ok=True, started_ns=100, finished_ns=201,
                     wall_ns=101, workers=workers, before=snap, after=after, completed=200,
                     reads=200 - 2 * percent, writes=2 * percent)


class BenchTests(unittest.TestCase):
    def test_list_report_requires_returned_evidence_and_preserves_local_controls(self):
        for family, arms in (('rwlock', ['native', 'tclock', 'kdlock']),
                             ('rwsem', ['native', 'kdlock'])):
            args = run.parser().parse_args(['--lock-kind', family, '--workloads', 'list',
                '--backends', *arms, '--threads', '8', '--write-percent', '20'])
            plan = run.make_plan(args)
            for bodies, completions, expected in ((10, 10, 'PASS'), (10, 0, 'INCOMPLETE'),
                                                 (10, None, 'INCOMPLETE'), (0, 0, 'PASS')):
                with self.subTest(family=family, bodies=bodies, completions=completions), \
                     tempfile.TemporaryDirectory() as temporary:
                    out = Path(temporary)
                    run.write_json(out/'plan.json', plan)
                    for spec in plan:
                        _, measurement = fixture('cacheline', 20)
                        kd = spec['arm'] == 'kdlock'
                        measurement['wall_ns'] = 100 if kd else 200
                        measurement['peak'] = dict(throughput_ops_s=2000 if kd else 1000)
                        evidence = jit_evidence(0, bodies if kd else 0, measurement['writes'],
                            backend=spec['arm'], delegate=kd,
                            completed=completions if kd else 0)
                        folder = out/spec['name']
                        folder.mkdir()
                        run.write_json(folder/'session.json', dict(spec, execution_status='OK',
                            drained=True, measurement=measurement, **evidence))
                    result = run.report(out)
                    self.assertEqual(result['status'], expected)
                    records = json.loads((out/'records.json').read_text())
                    kd_records = [r for r in records if r['arm'] == 'kdlock']
                    self.assertEqual(len(kd_records), 3)
                    self.assertTrue(all('whole_ops_s' in r for r in kd_records))
                    self.assertEqual({r['score_eligible'] for r in kd_records}, {expected == 'PASS'})
                    if completions == 0 and bodies:
                        # Even a manually supplied full three-round summary
                        # cannot turn entry-only evidence into parity success.
                        summary = json.loads((out/'summary.json').read_text())
                        summary.append(dict(summary[0], variant=kd_records[0]['variant'],
                                            jit_status='PARTIAL_JIT', score_eligible=True))
                        self.assertEqual(run.assess(plan, summary)['status'], 'INCOMPLETE')

    def test_list_variants_keep_size_hint_and_lock_family_identity(self):
        for family, arms in (('rwlock', ['native', 'tclock', 'kdlock']),
                             ('rwsem', ['native', 'kdlock'])):
            args = run.parser().parse_args(['--lock-kind', family, '--functional',
                '--repeats', '1', '--workloads', 'list', 'list-prefetch',
                '--list-nodes', '16', '128', '--backends', *arms,
                '--threads', '8', '--write-percent', '20'])
            plan = run.make_plan(args)
            self.assertEqual(len(plan), 4 * len(arms))
            self.assertEqual(len({r['variant'] for r in plan}), len(plan))
            self.assertEqual({r['list_nodes'] for r in plan}, {16, 128})
            self.assertTrue(all(r['cachelines'] == r['list_nodes'] and
                                r['workload'] in r['name'] for r in plan))
        args = run.parser().parse_args(['--lock-kind', 'rwsem', '--workloads', 'list'])
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_list_oracle_checks_writer_totals_read_consistency_and_identity(self):
        for workload, code in (('list', 4), ('list-prefetch', 5)):
            for nodes in (16, 128):
                for percent in (0, 20, 100):
                    spec, measurement = fixture('cacheline', percent)
                    spec.update(workload=workload, list_nodes=nodes, cachelines=nodes)
                    for label in ('before', 'after'):
                        measurement[label].update(workload=code, lines=nodes, values=[0]*16)
                    measurement['after']['values'][0] = 2 * percent
                    validate(measurement, spec)
                    for mutate in (
                            lambda m: m['after']['values'].__setitem__(0, 2*percent+1),
                            lambda m: m['after']['values'].__setitem__(1, 1),
                            lambda m: m['after'].__setitem__('lines', 128 if nodes == 16 else 16),
                            lambda m: m['workers'][0].__setitem__('read_errors', 1)):
                        bad = copy.deepcopy(measurement)
                        mutate(bad)
                        with self.assertRaises(ValueError):
                            validate(bad, spec)

    def test_cold_normal_image_does_not_finish_helper_learning(self):
        # Reproduce a NORMAL CALL-miss image that has never executed. Only a
        # later complete returned body can make preparation successful.
        for complete_second_wave in (False, True):
            with self.subTest(complete_second_wave=complete_second_wave), tempfile.TemporaryDirectory() as tmp:
                params = Path(tmp)
                for name in ('bench_jit_bodies', 'bench_jit_completions'):
                    (params / name).write_text('0')
                candidate = object.__new__(session.RWSession)
                candidate.record = dict(helper_waves=2, helper_cpus=[0, 1],
                    helper_iterations_per_worker=240000, threads=1, cpus=[0])
                candidate.daemon = SimpleNamespace(pid=123)
                candidate.pause_daemon = lambda: None
                candidate.save = lambda: None
                phases = []

                def phase(label, spec):
                    phases.append(label)
                    self.assertEqual(spec['threads'], 2)
                    self.assertEqual(spec['cpus'], [0, 1])
                    self.assertEqual(spec['iterations'], 240000)
                    if len(phases) == 2 and complete_second_wave:
                        for name in ('bench_jit_bodies', 'bench_jit_completions'):
                            (params / name).write_text('1')
                    return dict(reads=100)

                candidate.phase = phase
                with patch.object(session, 'KD_PARAMS', params), \
                     patch.object(session, 'status', return_value=dict(frames=0, writers=1)), \
                     patch.object(session, 'registry', return_value=[dict(status=0)]), \
                     patch.object(session.os, 'kill'):
                    if complete_second_wave:
                        candidate.learn_helpers()
                    else:
                        with self.assertRaises(run.Failure):
                            candidate.learn_helpers()
                self.assertEqual(phases, ['learning-0', 'learning-1'])
                self.assertEqual(candidate.record['threads'], 1)
                self.assertEqual(candidate.record['cpus'], [0])

    def test_single_worker_taskname_has_separate_learning_cohort(self):
        args = run.parser().parse_args(['--lock-kind', 'spin', '--workloads', 'taskname',
            '--backends', 'kdlock', '--write-percent', '0', '--threads', '1', '--collector-cpu', '63'])
        plan = run.make_plan(args)
        for spec in plan:
            self.assertEqual(spec['cpus'], [0])
            self.assertEqual(spec['threads'], 1)
            self.assertEqual(spec['helper_cpus'], list(range(8)))
            self.assertEqual(spec['helper_waves'], 8)
            self.assertFalse(spec['require_jit'])
        args.collector_cpu = 7
        with self.assertRaises(run.Failure):
            run.make_plan(args)
        args.collector_cpu = 63
        args.cpus = [0]
        with self.assertRaises(run.Failure):
            run.make_plan(args)
        args.helper_waves = 0
        self.assertEqual(run.make_plan(args)[0]['helper_cpus'], [])

    def test_snapshot_plan_and_evidence(self):
        args = run.parser().parse_args(['--lock-kind', 'spin', '--workloads', 'taskname', 'argbounds',
            '--write-percent', '0', '--threads', '1', '8', '--collector-cpu', '63', '--require-jit'])
        plan = run.make_plan(args)
        self.assertEqual(len(plan), 36)
        self.assertTrue(all(s['cachelines'] == 0 and s['entry_abi'] == 1 for s in plan))
        self.assertTrue(all(s['require_jit'] == (s['arm'] == 'kdlock' and s['threads'] > 1) for s in plan))
        row = jit_evidence(2, 8, 10, backend='kdlock', delegate=True, operation='snapshot')
        self.assertEqual(row['jit_snapshot_share'], .6)
        self.assertNotIn('jit_writer_share', row)
        partial = jit_evidence(0, 10, 20, backend='kdlock', delegate=True, operation='snapshot', completed=0)
        self.assertEqual(partial['jit_status'], 'PARTIAL_JIT')
        with self.assertRaises(ValueError):
            jit_evidence(0, 10, 20, backend='kdlock', delegate=True, completed=11)
        args.lock_kind = 'rwlock'
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_snapshot_oracle_and_mutations(self):
        for workload, number in (('taskname', 2), ('argbounds', 3)):
            spec, m = fixture('cacheline', 20)
            spec.update(workload=workload, cachelines=0, lock_kind='spin')
            for snap in (m['before'], m['after']):
                snap.update(workload=number, lines=0)
            m['after']['values'] = [40] + [0] * 15
            validate(m, spec)
            for change in (lambda b: b['workers'][0].__setitem__('read_errors', 1),
                           lambda b: b['after']['values'].__setitem__(0, 39),
                           lambda b: b['after'].__setitem__('gate', 1)):
                bad = copy.deepcopy(m)
                change(bad)
                with self.assertRaises(ValueError):
                    validate(bad, spec)

    def test_rwsem_plan_uses_only_local_sleeping_backends(self):
        args = run.parser().parse_args(['--lock-kind', 'rwsem', '--workloads', 'cacheline',
            '--cachelines', '1', '8', '--backends', 'native', 'kdlock', '--threads', '8',
            '--write-percent', '0', '20', '100', '--delegate', 'off'])
        plan = run.make_plan(args)
        self.assertEqual(len(plan), 36)
        self.assertTrue(all(s['lock_kind'] == 'rwsem' and not s['delegate'] and
                            not s['require_jit'] and s['entry_abi'] is None and
                            s['caller_abi'] == 'c' for s in plan))
        candidate = object.__new__(session.RWSession)
        for spec in plan:
            candidate.record = spec
            self.assertFalse(candidate.has_entry())
            self.assertEqual(spec['rwsem_writer_shell'], 'ordinary-local')
            if spec['arm'] == 'kdlock':
                self.assertTrue(spec['variant'].endswith('-local'))
        args.require_jit = True
        with self.assertRaises(run.Failure):
            run.make_plan(args)
        args.require_jit = False
        args.backends.append('tclock')
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_rwsem_delegation_plan_and_standard_grid(self):
        threads = [*range(1, 9), *range(12, 61, 4)]
        args = run.parser().parse_args(['--lock-kind', 'rwsem', '--workloads', 'cacheline', 'rcuht',
            '--cachelines', '1', '8', '--backends', 'native', 'kdlock', '--threads',
            *map(str, threads), '--collector-cpu', '63', '--require-jit'])
        plan = run.make_plan(args)
        self.assertEqual(len(plan), 756)
        self.assertEqual(sorted({s['threads'] for s in plan}), threads)
        self.assertEqual({s['write_percent'] for s in plan}, {1, 20})
        self.assertEqual({s['duration_ms'] for s in plan}, {2000})
        candidate = object.__new__(session.RWSession)
        for spec in plan:
            kd = spec['arm'] == 'kdlock'
            self.assertEqual(spec['delegate'], kd)
            self.assertEqual(spec['entry_abi'], 2 if kd else None)
            self.assertEqual(spec['caller_abi'], 'clobber' if kd else 'c')
            self.assertEqual(spec['require_jit'], kd and spec['threads'] > 1)
            self.assertEqual(spec['delegation_batch_limit'], 1024 if kd else None)
            candidate.record = spec
            self.assertEqual(candidate.has_entry(), kd)
        args.write_percent = [0]
        with self.assertRaises(run.Failure):
            run.make_plan(args)
        args.require_jit = False
        for spec in run.make_plan(args):
            candidate.record = spec
            self.assertFalse(candidate.has_entry())

    def test_rwsem_publication_requires_mutex_kind_and_abi2(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = object.__new__(session.RWSession)
            candidate.path = Path(tmp)
            candidate.record = dict(lock_kind='rwsem', caller_abi='clobber', entry_abi=2,
                                    entry_range=[0x2000, 0x2001])
            folder = candidate.path / 'workspace/daemon/0x2000/0/asm'
            folder.mkdir(parents=True)
            (folder / 'jit.bin').write_bytes(b'\x90\xc3')
            (folder / 'jit.S').write_text('MOV             Stack_JIT_WITNESS, 1\nloc_2000:\n')
            (folder / 'bin.txt').write_text('nop\nret\n')
            entry = dict(entry=0x2000, tgid=0, pid=0, lock_kind=2, entry_abi=2,
                         status=0, code=1, requirements=0)
            state = dict(state=0, frames=0, writers=0)
            with patch.object(bench_session, 'registry', return_value=[entry]), \
                    patch.object(bench_session, 'status', return_value=state):
                before = candidate.publication()
                self.assertEqual(before['entry']['lock_kind'], 2)
                (folder / 'bin.txt').write_text('changed image inspection\n')
                self.assertNotEqual(before, candidate.publication())
                entry['lock_kind'] = 1
                with self.assertRaises(run.Failure):
                    candidate.publication()
                entry['lock_kind'], entry['entry_abi'] = 2, 3
                with self.assertRaises(run.Failure):
                    candidate.publication()
    def test_snapshot_plan_rejects_mixed_shells_and_ineligible_jit(self):
        for argv in (['--lock-kind', 'spin', '--workloads', 'taskname', 'cacheline'],
                     ['--lock-kind', 'spin', '--workloads', 'cacheline'],
                     ['--workloads', 'argbounds'],
                     ['--lock-kind', 'spin', '--workloads', 'argbounds',
                      '--require-jit', '--write-percent', '100']):
            with self.subTest(argv=argv), self.assertRaises(run.Failure):
                run.make_plan(run.parser().parse_args(argv))

    def test_default_rcuht_matrix(self):
        plan = run.make_plan(run.parser().parse_args([]))
        self.assertEqual(len(plan), 270)
        self.assertEqual({s['workload'] for s in plan}, {'rcuht'})
        self.assertEqual({s['write_percent'] for s in plan}, {1, 20})
        self.assertEqual(sorted({s['threads'] for s in plan}), run.FULL_THREADS)

    def test_parity_requires_both_metrics_and_both_comparators(self):
        plan = run.make_plan(run.parser().parse_args(['--threads', '16', '--write-percent', '20']))
        summary = [dict(variant=f'rcuht-c00-{arm}', write_percent=20, threads=16,
                        complete=True, valid_rounds=3, jit_status='PASS' if arm == 'kdlock' else 'NATIVE',
                        best_peak_ops_s=rate, whole_median_ops_s=rate)
                   for arm, rate in (('native', 10), ('tclock', 11), ('kdlock', 12))]
        self.assertEqual(run.assess(plan, summary)['status'], 'PASS')
        for metric in ('best_peak_ops_s', 'whole_median_ops_s'):
            slower = copy.deepcopy(summary)
            slower[2][metric] = 10.5
            self.assertEqual(run.assess(plan, slower)['status'], 'FAIL')
        summary[2]['complete'] = False
        summary[2]['valid_rounds'] = 2
        self.assertEqual(run.assess(plan, summary)['status'], 'INCOMPLETE')
        summary.append(dict(summary[2], jit_status='NO_JIT', valid_rounds=1))
        self.assertEqual(run.assess(plan, summary)['status'], 'INCOMPLETE')

    def test_parity_rejects_controls_without_comparators(self):
        args = run.parser().parse_args(['--require-parity', '--backends', 'kdlock'])
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_rwsem_parity_requires_native_and_kd_for_both_metrics(self):
        args = run.parser().parse_args(['--lock-kind', 'rwsem', '--backends', 'native', 'kdlock',
            '--threads', '8', '--write-percent', '20', '--require-parity'])
        plan = run.make_plan(args)
        summary = [dict(variant=f'rwsem-rcuht-c00-{arm}', write_percent=20, threads=8,
                        complete=True, valid_rounds=3, jit_status='NATIVE',
                        best_peak_ops_s=rate, whole_median_ops_s=rate)
                   for arm, rate in (('native', 10), ('kdlock', 12))]
        result = run.assess(plan, summary)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['points'][0]['lock_kind'], 'rwsem')
        self.assertEqual(result['points'][0]['comparators'], ['native'])
        self.assertEqual(set(result['points'][0]['ratios']), {'native'})
        for metric in ('best_peak_ops_s', 'whole_median_ops_s'):
            slower = copy.deepcopy(summary)
            slower[1][metric] = 9
            self.assertEqual(run.assess(plan, slower)['status'], 'FAIL')
        partial = copy.deepcopy(summary)
        partial[1].update(complete=False, valid_rounds=2)
        self.assertEqual(run.assess(plan, partial)['status'], 'INCOMPLETE')
        for backend in ('native', 'kdlock'):
            args.backends = [backend]
            with self.assertRaises(run.Failure):
                run.make_plan(args)
        args.backends = ['native', 'kdlock']
        args.functional, args.repeats = True, 1
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_spin_and_rwlock_parity_still_require_tclock(self):
        for extra in ([], ['--lock-kind', 'spin', '--workloads', 'argbounds']):
            args = run.parser().parse_args(['--backends', 'native', 'kdlock',
                '--threads', '8', '--write-percent', '20', '--require-parity', *extra])
            with self.assertRaises(run.Failure):
                run.make_plan(args)
            args.require_parity = False
            plan = run.make_plan(args)
            summary = [dict(variant=spec['variant'], write_percent=20, threads=8,
                            complete=True, valid_rounds=3, jit_status='NATIVE',
                            best_peak_ops_s=10, whole_median_ops_s=10)
                       for spec in plan[:2]]
            result = run.assess(plan, summary)
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertEqual(result['points'][0]['comparators'], ['native', 'tclock'])

    def test_mix_matches_scheduler(self):
        for percent in (0, 1, 10, 20, 50, 99, 100):
            for worker in range(64):
                mix, writes = worker * 17 % 100, 0
                for count in range(1, 514):
                    mix += percent
                    if mix >= 100:
                        writes += 1
                        mix -= 100
                    self.assertEqual(writes, writes_for(count, worker, percent))

    def test_cacheline_oracle_rejects_corruption(self):
        spec, m = fixture()
        self.assertIsNone(validate(m, spec))
        for field, change in (('lost', -1), ('duplicate', 1)):
            bad = copy.deepcopy(m)
            bad['after']['values'][0] += change
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(bad, spec)
        for modify in (lambda x: x['after']['values'].__setitem__(15, 1),
                       lambda x: x['workers'][0].__setitem__('read_errors', 1),
                       lambda x: x['after'].__setitem__('cnts', 512),
                       lambda x: x['workers'][1].__setitem__('observed_cpu', 0),
                       lambda x: x['workers'][0].__setitem__('checksum', 0),
                       lambda x: x['workers'][0].__setitem__('completed', 99)):
            bad = copy.deepcopy(m)
            modify(bad)
            with self.assertRaises(ValueError):
                validate(bad, spec)

    def test_hash_and_read_only(self):
        for workload in ('cacheline', 'rcuht'):
            for percent in (0, 1, 20, 50, 100):
                spec, m = fixture(workload, percent)
                validate(m, spec)
        spec, m = fixture('rcuht')
        m['after']['values'][1] -= 1
        with self.assertRaises(ValueError):
            validate(m, spec)

    def test_jit_uses_writers_not_total_operations(self):
        row = jit_evidence(500, 509, 10, backend='kdlock', delegate=True)
        self.assertEqual(row['jit_writer_share'], .9)
        self.assertEqual(jit_evidence(0, 0, 10, backend='kdlock', delegate=True)['jit_status'], 'NO_JIT')
        self.assertEqual(jit_evidence(0, 0, 0, backend='kdlock', delegate=True)['jit_status'], 'NATIVE')
        for before, after, writes, backend, delegate in ((0, 11, 10, 'kdlock', True),
                (10, 9, 10, 'kdlock', True), (0, 1, 10, 'native', False), (0, 1, 10, 'kdlock', False)):
            with self.assertRaises(ValueError):
                jit_evidence(before, after, writes, backend=backend, delegate=delegate)

    def test_post_work_amount(self):
        self.assertEqual(post_work_checksum(1, 1), 1015568748)
        for rounds in (1, 4, 64, 256):
            state = 1
            for count in range(1, 20):
                for _ in range(rounds):
                    state = (state * 1664525 + 1013904223) % 2**64
                self.assertEqual(post_work_checksum(count, rounds), state)

    def test_peak_read_write_split_uses_worker_phase(self):
        from test_peak import fixture as timed_fixture
        timed_spec, timed = timed_fixture()
        spec, m = fixture()
        spec.update(duration_ms=1000, peak_window_ms=300, peak_settle_ms=100,
                    sample_ms=100, collector_cpu=30, cpus=[2, 7], write_percent=10)
        for field in ('started_ns', 'finished_ns', 'wall_ns', 'deadline_ns', 'duration_ns',
                      'peak_window_ns', 'peak_settle_ns', 'sample_period_ns', 'collector_cpu',
                      'collector_observed_cpu', 'collector_error', 'progress_batch', 'samples', 'workers'):
            m[field] = timed[field]
        for i, worker in enumerate(m['workers']):
            worker['writes'] = writes_for(worker['completed'], i, 10)
            worker['reads'] = worker['completed'] - worker['writes']
            worker.update(read_hits=0, read_errors=0, checksum=post_work_checksum(worker['completed'], 4))
        for field in ('completed', 'reads', 'writes'):
            m[field] = sum(w[field] for w in m['workers'])
        m['after']['values'] = [m['writes']] * 4 + [0] * 12
        peak = validate(m, spec)
        self.assertEqual(peak['writes'], 231)
        self.assertEqual(peak['reads'] + peak['writes'], peak['completed'])
        self.assertAlmostEqual(peak['read_ops_s'] + peak['write_ops_s'], peak['throughput_ops_s'])

    def test_plan_and_invalid_geometry(self):
        args = run.parser().parse_args(['--workloads', 'cacheline', '--cachelines', '1',
                                       '--write-percent', '50', '--threads', '16'])
        plan = run.make_plan(args)
        self.assertEqual(len(plan), 9)
        self.assertEqual([s['arm'] for s in plan[:6]], ['native', 'tclock', 'kdlock', 'kdlock', 'tclock', 'native'])
        self.assertEqual(len({s['name'] for s in plan}), 9)
        args.collector_cpu = 0
        with self.assertRaises(run.Failure):
            run.make_plan(args)

    def test_fixed_client_does_not_abort_released_waiters(self):
        spec, example = fixture()
        original_barrier = threading.Barrier
        main_thread = threading.current_thread()

        class DelayedExitBarrier:
            def __init__(self, parties):
                self.barrier = original_barrier(parties)

            def wait(self, **kwargs):
                self.barrier.wait(**kwargs)
                if threading.current_thread() is not main_thread:
                    # Model a worker that has been released but is still
                    # returning through Barrier._wait when main proceeds.
                    time.sleep(.01)
                    if self.barrier.broken:
                        raise threading.BrokenBarrierError

            def abort(self):
                self.barrier.abort()

        def ioctl(device, request, buffer, mutate):
            values = list(struct.unpack(RUN_FORMAT, buffer))
            start = time.monotonic_ns()
            completed, worker = values[2], values[3]
            writes = writes_for(completed, worker, spec['write_percent'])
            values[5:] = [completed, completed - writes, writes, 0, 0,
                          post_work_checksum(completed, 4), start, time.monotonic_ns(),
                          spec['cpus'][worker], 0]
            buffer[:] = struct.pack(RUN_FORMAT, *values)

        libc = SimpleNamespace(prctl=lambda *args: 0, sched_getcpu=lambda: spec['collector_cpu'])
        with patch.object(client.threading, 'Barrier', DelayedExitBarrier), \
             patch.object(client.os, 'sched_setaffinity'), \
             patch.object(client.ctypes, 'CDLL', return_value=libc), \
             patch.object(client, 'open', side_effect=lambda *a, **k: io.BytesIO(), create=True), \
             patch.object(client, 'snapshot', side_effect=[example['before'], example['after']]), \
             patch.object(client, 'configure'), patch.object(client.fcntl, 'ioctl', side_effect=ioctl):
            result = client.run(spec)
        self.assertTrue(result['data_ok'], result.get('validation_error'))
        self.assertEqual(result['completed'], spec['iterations'] * spec['threads'])

    def test_failed_and_not_run_retained_without_scores(self):
        spec, m = fixture()
        spec.update(functional=False, duration_ms=2000)
        m['peak'] = dict(throughput_ops_s=1000)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            plan = [dict(spec, name=f'case{i}') for i in range(4)]
            (out / 'plan.json').write_text(json.dumps(plan))
            for i, status, drain in ((0, 'OK', True), (1, 'DATA_ERROR', True), (2, 'OK', False)):
                folder = out / f'case{i}'
                folder.mkdir()
                (folder / 'session.json').write_text(json.dumps(dict(plan[i], execution_status=status,
                    drained=drain, measurement=m, jit_status='PASS')))
            run.report(out)
            summary = json.loads((out / 'summary.json').read_text())
            self.assertEqual(summary[0]['valid_rounds'], 1)
            self.assertFalse(summary[0]['complete'])
            records = json.loads((out / 'records.json').read_text())
            self.assertEqual(len(records), 4)
            self.assertTrue(all('peak_ops_s' not in r for r in records[1:]))

    def test_narrow_kcore_mapping(self):
        data = bytearray(512)
        ident = b'\x7fELF\x02\x01' + bytes(10)
        struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, ident, 4, 62, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
        struct.pack_into('<IIQQQQQQ', data, 64, 1, 4, 256, 4096, 0, 256, 256, 4096)
        struct.pack_into('<QQ', data, 264, 1234, 5678)
        self.assertEqual(struct.unpack('<QQ', boot_policy.read_virtual(io.BytesIO(data), 4104, 16)), (1234, 5678))
        with self.assertRaises(ValueError):
            boot_policy.read_virtual(io.BytesIO(data), 0, 16)
        self.assertEqual(boot_policy.member_offset('struct pv_lock_ops     lock; /* 632 32 */',
                                                   'struct pv_lock_ops lock;'), 632)
        layout = ('void (*queued_spin_lock_slowpath)(struct qspinlock *, u32); /* 0 8 */\n'
                  'struct paravirt_callee_save queued_spin_unlock; /* 8 8 */')
        self.assertEqual(boot_policy.dispatch_offsets(layout), [0, 8])
        with self.assertRaises(ValueError):
            boot_policy.dispatch_offsets(layout.replace('/* 8 8 */', '/* 16 8 */'))


if __name__ == '__main__':
    unittest.main()
