"""Focused functional-mode guards; run only in the designated VM."""
import copy
import datetime
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import run
import capture_host


class FunctionalSmoke(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime.now(datetime.timezone.utc)
        args = ['qemu-system-x86_64', '-smp', '64,maxcpus=64,sockets=2,cores=32,threads=1',
                '-m', '24G', '-object', 'memory-backend-ram,id=mem0,size=12G,host-nodes=0,policy=bind',
                '-object', 'memory-backend-ram,id=mem1,size=12G,host-nodes=1,policy=bind',
                '-numa', 'node,nodeid=0,cpus=0-31,memdev=mem0',
                '-numa', 'node,nodeid=1,cpus=32-63,memdev=mem1',
                '-monitor', 'unix:/tmp/qemu-monitor.sock,server,nowait']
        tasks = [dict(tid=100+cpu, start_ticks=100, comm=f'CPU {cpu}/KVM', affinity=[cpu])
                 for cpu in range(64)]
        tasks.append(dict(tid=10, start_ticks=90, comm='qemu-system-x86', affinity=[63]))
        self.host = dict(schema=2, capture_kind=capture_host.KIND, host_boot_id='host-boot',
                         captured_utc=self.now.isoformat(), pins_verified=True, frequency_verified=True,
                         snapshot_listed=True, no_turbo='1', monitor_path='/tmp/qemu-monitor.sock',
                         snapshots='ID TAG VM SIZE\n1 snapshot 12 GiB\n(qemu) ',
                         cpufreq={f'policy{cpu}': dict(scaling_driver='intel_cpufreq',
                             scaling_governor='performance', scaling_min_freq='2000000',
                             scaling_max_freq='2000000', affected_cpus=str(cpu)) for cpu in range(64)},
                         numa={'node0': '0-31', 'node1': '32-63'}, recovery_snapshot='snapshot',
                         qemu=[dict(pid=10, start_ticks=90, args=args, tasks=tasks,
                                    numa_maps='1000 bind:0 anon=100 N0=100 kernelpagesize_kB=4\n'
                                              '2000 bind:1 anon=100 N1=100 kernelpagesize_kB=4')])

    def test_extra_io_worker_is_unscored(self):
        host = copy.deepcopy(self.host)
        host['qemu'][0]['tasks'].append(dict(tid=1000, start_ticks=110, comm='worker', affinity=[63]))
        receipt = run.functional_host(self.host, host, self.now)
        self.assertEqual(receipt['observed_threads'], 66)
        self.assertFalse(receipt['performance_accepted'])
        self.assertEqual(receipt['timing_gate'], 'NOT_APPLICABLE')

    def test_changed_safety_conditions_are_refused(self):
        mutations = [lambda h: h.update(snapshot_listed=False),
                     lambda h: h['qemu'][0]['tasks'][0].update(tid=12),
                     lambda h: h['qemu'][0]['tasks'][0].update(affinity=[1]),
                     lambda h: h['qemu'][0]['tasks'][0].update(start_ticks=101),
                     lambda h: h['qemu'][0].update(pid=11),
                     lambda h: h['qemu'][0].update(start_ticks=91),
                     lambda h: h['qemu'][0].update(numa_maps='1000 bind:1 kernelpagesize_kB=4'),
                     lambda h: h['qemu'][0]['tasks'].append(dict(tid=1000, start_ticks=110, comm='worker', affinity=[0])),
                     lambda h: h['qemu'][0]['tasks'].append(dict(tid=1000, start_ticks=110, comm='unexpected', affinity=[63])),
                     lambda h: h['qemu'][0]['tasks'].append(h['qemu'][0]['tasks'][0]),
                     lambda h: h.update(cpufreq={}),
                     lambda h: h['cpufreq']['policy0'].update(scaling_min_freq='1999999'),
                     lambda h: h.update(no_turbo='0'),
                     lambda h: h.update(host_boot_id='different-boot'),
                     lambda h: h.update(schema=1),
                     lambda h: h.update(snapshots='ID TAG VM SIZE\n1 snapshot-old 12 GiB\n'),
                     lambda h: h.update(captured_utc=(self.now-datetime.timedelta(seconds=301)).isoformat())]
        for mutate in mutations:
            host = copy.deepcopy(self.host)
            mutate(host)
            with self.assertRaises(ValueError):
                run.functional_host(self.host, host, self.now)

    def test_explicit_snapshot_must_match_actual_table(self):
        with self.assertRaises(ValueError):
            run.functional_host(self.host, self.host, self.now, 'other-snapshot')
        self.assertEqual(capture_host.snapshot_names('ID TAG SIZE\n1 snapshot-old 12G\n'
                         'error: snapshot\n(qemu) '), ['snapshot-old'])
        observed = ('List of snapshots present on all disks:\n'
                    'ID TAG VM SIZE DATE VM CLOCK ICOUNT\n'
                    '-- snapshot 23.4 GiB 2026-10-27 08:31:29 282:37:35.610\n')
        host = copy.deepcopy(self.host)
        host['snapshots'] = observed
        self.assertEqual(capture_host.snapshot_names(observed), ['snapshot'])
        run.functional_host(host, host, self.now, 'snapshot')
        self.assertEqual(capture_host.snapshot_names('-- snapshot failed\n'
                         'error: snapshot\ninfo snapshots\n'), [])

    def test_invalid_reference_policy_cannot_be_waived(self):
        for change in (lambda h: h.update(schema=1), lambda h: h.update(no_turbo='0'),
                       lambda h: h['cpufreq']['policy0'].update(scaling_governor='ondemand')):
            reference = copy.deepcopy(self.host)
            change(reference)
            with self.assertRaises(ValueError):
                run.functional_host(reference, reference, self.now)

    def test_closed_monitor_does_not_loop(self):
        class ClosedMonitor:
            def settimeout(self, timeout):
                pass

            def recv(self, count):
                return b''

        with self.assertRaises(ValueError):
            capture_host.read_prompt(ClosedMonitor(), float('inf'))

    def test_process_start_parser_handles_parenthesized_comm(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'stat'
            fields = ['R'] + ['0'] * 18 + ['123456']
            path.write_text('10 (worker (pool) name) ' + ' '.join(fields) + '\n')
            self.assertEqual(capture_host.start_ticks(path), 123456)

    def test_all_child_plans_are_functional(self):
        for task in run.plan(Path('/tmp/kd-basic-plan-only'), run.FAMILIES):
            self.assertIn('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build', task['argv'])
            self.assertIn('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027', task['argv'])
            data = subprocess.check_output([*task['argv'], '--dry-run'], text=True)
            rows = json.loads(data)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['functional'])
            self.assertEqual(rows[0]['duration_ms'], 0)
            self.assertEqual(rows[0]['threads'], 16)
            self.assertEqual(rows[0]['workload'], 'cacheline')
            self.assertEqual(rows[0]['cachelines'], 16 if task['family'] == 'rwsem' else 1)
            if task['family'] == 'mutex':
                self.assertIn('public', task['argv'])
            if task['family'] in ('rwlock', 'rwsem'):
                self.assertTrue(rows[0]['require_jit'])
                self.assertEqual(rows[0]['write_percent'], 100 if task['family'] == 'rwsem' else 20)

    def test_selected_kernel_paths_reach_every_child(self):
        for task in run.plan(Path('/tmp/kd-basic-plan-only'), run.FAMILIES,
                             Path('/selected/build'), Path('/selected/bundle')):
            self.assertIn('/selected/build', task['argv'])
            self.assertIn('/selected/bundle', task['argv'])

    def test_local_or_partial_execution_cannot_pass(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            (out/'one').mkdir()
            (out/'plan.json').write_text(json.dumps([dict(name='one', functional=True)]))
            row = dict(execution_status='OK', drained=True, jit_bodies=2, jit_completions=2,
                       measurement=dict(complete=True, data_ok=True, completed=10))
            path = out/'one/session.json'
            path.write_text(json.dumps(row))
            self.assertEqual(run.session_result(out, 'spin')['execution'], 'RETURNED_JIT')
            for entries, completed in [(0, 0), (2, 0), (1, 2), (None, None)]:
                row.update(jit_bodies=entries, jit_completions=completed)
                path.write_text(json.dumps(row))
                with self.assertRaises(ValueError):
                    run.session_result(out, 'spin')


if __name__ == '__main__':
    unittest.main()
