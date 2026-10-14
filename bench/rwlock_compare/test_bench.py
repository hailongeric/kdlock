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
