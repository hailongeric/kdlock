"""Focused functional-mode guards; run only in the designated VM."""
import copy
import datetime
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import run


class FunctionalSmoke(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime.now(datetime.timezone.utc)
        self.host = dict(captured_utc=self.now.isoformat(), pins_verified=True, snapshot_listed=True,
                         cpufreq={'policy': 'fixed'}, numa={'node0': '0-31'}, recovery_snapshot='snapshot',
                         qemu=[dict(pid=10, args=['qemu'], tasks=[dict(tid=10, comm='CPU 0/KVM', affinity=[0])],
                                    numa_maps='1000 bind:0 anon=100 N0=100 kernelpagesize_kB=4')])

    def test_extra_io_worker_is_unscored(self):
        host = copy.deepcopy(self.host)
        host['qemu'][0]['tasks'].append(dict(tid=11, comm='worker', affinity=[63]))
        receipt = run.functional_host(self.host, host, self.now)
        self.assertEqual(receipt['observed_threads'], 2)
        self.assertFalse(receipt['performance_accepted'])
        self.assertEqual(receipt['timing_gate'], 'NOT_APPLICABLE')

    def test_changed_safety_conditions_are_refused(self):
        mutations = [lambda h: h.update(snapshot_listed=False),
                     lambda h: h['qemu'][0]['tasks'][0].update(tid=12),
                     lambda h: h['qemu'][0]['tasks'][0].update(affinity=[1]),
                     lambda h: h['qemu'][0].update(pid=11),
                     lambda h: h['qemu'][0].update(numa_maps='1000 bind:1 kernelpagesize_kB=4'),
                     lambda h: h['qemu'][0]['tasks'].append(dict(tid=11, comm='worker', affinity=[0])),
                     lambda h: h['qemu'][0]['tasks'].append(dict(tid=11, comm='unexpected', affinity=[63])),
                     lambda h: h['qemu'][0]['tasks'].append(h['qemu'][0]['tasks'][0]),
                     lambda h: h.update(cpufreq={}),
                     lambda h: h.update(captured_utc=(self.now-datetime.timedelta(seconds=301)).isoformat())]
        for mutate in mutations:
            host = copy.deepcopy(self.host)
            mutate(host)
            with self.assertRaises(ValueError):
                run.functional_host(self.host, host, self.now)

    def test_all_child_plans_are_functional(self):
        for task in run.plan(Path('/tmp/kd-basic-plan-only'), run.FAMILIES):
            data = subprocess.check_output([*task['argv'], '--dry-run'], text=True)
            rows = json.loads(data)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['functional'])
            self.assertEqual(rows[0]['duration_ms'], 0)
            self.assertEqual(rows[0]['threads'], 16)
            self.assertEqual(rows[0]['workload'], 'list')
            if task['family'] == 'mutex':
                self.assertIn('public', task['argv'])
            if task['family'] in ('rwlock', 'rwsem'):
                self.assertTrue(rows[0]['require_jit'])

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
