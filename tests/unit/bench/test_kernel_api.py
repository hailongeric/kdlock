"""Guest-only scored syscall receipt validation and single-round plan checks."""
import copy
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('native_body_api_runner',ROOT/'bench/kernel_api/run.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class Receipts(unittest.TestCase):
    def phase(self):
        row=dict(ok=True,phase='measure',completed=20,collector_cpu=63,
                 collector_observed_cpu=63,collector_error=0,started_ns=1_000_000,
                 deadline_ns=2_001_000_000,finished_ns=2_001_000_002,
                 wall_ns=2_000_000_002,duration_ns=2_000_000_000,
                 workers=[dict(cpu=i,observed_cpu=i,error=0,completed=10,
                               active_started_ns=1_000_001,finished_ns=2_001_000_002)
                          for i in (0,1)])
        return row,dict(cpus=[0,1])

    def test_interval_and_per_worker_conservation(self):
        row,spec=self.phase()
        self.assertEqual(runner.validate_phase(row,spec,True),20e9/2_000_000_002)
        mutations=(lambda r:r.update(completed=21),
                   lambda r:r.update(wall_ns=2_000_000_000),
                   lambda r:r.update(duration_ns=1_000_000_000),
                   lambda r:r.update(collector_observed_cpu=0),
                   lambda r:r['workers'][0].update(error=1),
                   lambda r:r['workers'][0].update(completed=0),
                   lambda r:r['workers'][0].update(observed_cpu=1),
                   lambda r:r['workers'][0].update(finished_ns=2_000_000_000),
                   lambda r:r['workers'][0].update(active_started_ns=999_999))
        for change in mutations:
            damaged=copy.deepcopy(row);change(damaged)
            with self.assertRaises(runner.rt.Failure): runner.validate_phase(damaged,spec,True)

    def test_every_functional_arm_requires_returned_bodies_and_drain(self):
        rows = []
        for spec in runner.plan(True):
            kd = spec['arm'] == 'kd'
            rows.append(dict(spec, passed=True, drained=True, execution_status='COMPLETE',
                             retired=dict(state=2, modules=0, frames=0, writers=0),
                             functional_jit=dict(entered=int(kd)*20, returned=int(kd)*20),
                             warmups=[dict(before=dict(bench_jit_bodies=0,bench_jit_completions=0),
                                           after=dict(bench_jit_bodies=int(kd)*20,bench_jit_completions=int(kd)*20))],
                             binding=dict(backend=int(kd), kind=1 if spec['kind']=='setfd' else 2,
                                          lock=1, object=2, provider=3 if kd else 0)))
        receipt = dict(sessions=rows)
        runner.validate_functional(receipt)
        mutations = (lambda r:r['sessions'].pop(),
                     lambda r:r['sessions'][1].update(drained=False),
                     lambda r:r['sessions'][1].update(warmups=[]),
                     lambda r:r['sessions'][1]['functional_jit'].update(entered=0, returned=0),
                     lambda r:r['sessions'][0]['functional_jit'].update(entered=1, returned=1),
                     lambda r:r['sessions'][3]['functional_jit'].update(returned=19),
                     lambda r:r['sessions'][5]['binding'].update(backend=0),
                     lambda r:r['sessions'][0].update(workers=8))
        for change in mutations:
            damaged=copy.deepcopy(receipt); change(damaged)
            with self.assertRaises(runner.rt.Failure): runner.validate_functional(damaged)

    def test_one_round_per_identity_and_separate_functional_plan(self):
        plan=runner.plan()
        keys={(r['kind'],r['arm'],r['workers'],r['round']) for r in plan}
        self.assertEqual(len(plan),126)
        self.assertEqual(len(keys),len(plan))
        self.assertEqual({r['round'] for r in plan},{0})
        self.assertEqual({r['instrumentation'] for r in plan},{'none'})
        self.assertTrue(all(r['cpus']==list(range(r['workers'])) and 63 not in r['cpus'] for r in plan))
        functional=runner.plan(True)
        self.assertEqual(len(functional),6)
        self.assertEqual({r['workers'] for r in functional},{16})
        self.assertEqual({r['instrumentation'] for r in functional},{'completion'})

if __name__=='__main__': unittest.main()
