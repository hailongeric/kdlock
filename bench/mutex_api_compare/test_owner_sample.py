"""VM-only checks for sampling attribution, extents and timeout boundaries."""
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import owner_run as plan
import owner_sample as owner
import route_snapshot as counters
import run


def fixture(value=255):
    data=b''.join(owner.RECORD.pack(1000+i*1000,1001+i*1000,1002+i*1000,value)
                  for i in range(1200))
    process=dict(samples=1200,samples_sha256=hashlib.sha256(data).hexdigest(),
                 state='COMPLETE',pins_closed=True,started_ns=0,stopped_ns=1300000,
                 missed_deadlines=0,process_cpu_ns=77)
    measured=dict(started_ns=1000,finished_ns=1201000,wall_ns=1200000,completed=12000)
    delta=dict(counters={n:0 for n in counters.PERCPU},
               native={n:0 for n in counters.GLOBALS if n.startswith('kd_native_')})
    return data,process,measured,delta


class OwnerTests(unittest.TestCase):
    def test_exact_plan_preserves_original_arm_rotations(self):
        original=run.execution_order(); rows=plan.order(original)
        self.assertEqual(len(rows),24);self.assertEqual(len(set(rows)),24)
        for repeat in range(3):
            arms=[r[3] for r in original if r[:3]==('pipecap',1,repeat)]
            selected=[r for r in rows if r[2]//3==repeat]
            modes=plan.MODES[repeat:]+plan.MODES[:repeat]
            self.assertEqual(list(dict.fromkeys(plan.MODES[r[2]%3] for r in selected)),list(modes))
            for mode in modes:
                self.assertEqual([r[3] for r in selected if plan.MODES[r[2]%3]==mode],
                                 [a for a in arms if mode=='plain' or a.endswith('-kd')])
        with self.assertRaises(ValueError):plan.order([])

    def test_original_admission_and_jit_requirements_unchanged(self):
        base=dict(name='test',require_jit=True,threads=1,duration_ms=2000,
                  collector_cpu=63,cpus=[0],warmup_ms=1000,caller_shell='mutex_public_direct')
        for i,mode in enumerate(plan.MODES):
            got=plan.specification(lambda *a,**k:dict(base),
                (None,'pipecap',1,3+i,'public-kd',None,None),{})
            self.assertEqual({k:got[k] for k in base if k!='name'},
                             {k:v for k,v in base.items() if k!='name'})
            self.assertEqual(got['owner_mode'],mode)
            self.assertFalse(got['inclusive_jit_timing']); self.assertFalse(got['score_eligible'])

    def test_unique_live_mapped_byte_required(self):
        base=0xff11000000000000
        core=SimpleNamespace(kernel_floor=0xff00000000000000,
            segments=[dict(address=base,size=32,file_size=16,offset=4096)])
        self.assertEqual(owner.offset_for(core,base+7),4103)
        for address in (base-1,base+16,0):
            with self.assertRaises(ValueError):owner.offset_for(core,address)
        core.segments*=2
        with self.assertRaises(ValueError):owner.offset_for(core,base)

    def test_local_only_estimate_and_reference_separation(self):
        result=owner.analyze(*fixture(), 'sampled')
        self.assertTrue(result['local_only']);self.assertEqual(result['estimated_mean_hold_ns'],100)
        self.assertEqual(result['samples'],1200)
        for counter in ('kd_bench_bodies','kd_mutex_slowpath_count','kd_mutex_origin_acquires',
                        'kd_mutex_nested_lock_count','kd_mutex_handoff_count'):
            args=list(fixture());args[3]['counters'][counter]=1
            self.assertIsNone(owner.analyze(*args,'sampled')['estimated_mean_hold_ns'])
        args=list(fixture());args[3]['native']['kd_native_unlocks']=1
        self.assertFalse(owner.analyze(*args,'sampled')['local_only'])
        self.assertIsNone(owner.analyze(*fixture(0),'reference')['estimated_mean_hold_ns'])

    def test_cannot_interpret_wrong_hash_clock_pin_or_short_coverage(self):
        for changes in (dict(pins_closed=False),dict(state='FAILED'),dict(started_ns=2000),
                        dict(stopped_ns=1000000),dict(samples=1199),dict(samples_sha256='wrong')):
            args=list(fixture());args[1].update(changes)
            with self.assertRaises(ValueError):owner.analyze(*args,'sampled')
        args=list(fixture());args[2]['started_ns']=300000;args[2]['wall_ns']-=299000
        with self.assertRaises(ValueError):owner.analyze(*args,'sampled')
        with self.assertRaises(ValueError):owner.analyze(*fixture(7),'sampled')
        with self.assertRaises(ValueError):owner.analyze(*fixture(255),'reference')

    def test_read_brackets_not_midpoints_define_phase_membership(self):
        args=list(fixture()); rows=list(owner.RECORD.iter_unpack(args[0]))
        rows[0]=(999,999,1001,255)
        args[0]=b''.join(owner.RECORD.pack(*r) for r in rows)
        args[1]['samples_sha256']=hashlib.sha256(args[0]).hexdigest()
        result=owner.analyze(*args,'sampled')
        self.assertEqual(result['samples'],1199)
        self.assertEqual(result['outside_or_boundary_samples'],1)

    def test_timeout_does_not_kill_or_claim_child_completion(self):
        session=Mock();sampler=owner.Sampler(session,'script')
        sampler.process=Mock();sampler.process.poll.return_value=None
        sampler.log=Mock();sampler.expect=Mock(side_effect=ValueError('deadline'))
        with self.assertRaises(ValueError):sampler.finish()
        sampler.process.kill.assert_not_called();sampler.process.terminate.assert_not_called()
        sampler.process.wait.assert_not_called();sampler.log.close.assert_not_called()
        sampler.process.stdin.close.assert_called_once()

    def test_measurement_worker_clock_bounds(self):
        m=dict(started_ns=20,finished_ns=40,workers=[dict(active_started_ns=21,finished_ns=40)])
        plan.validate_measurement_bounds(dict(finished_ns=19),dict(started_ns=41),m)
        with self.assertRaises(ValueError):
            plan.validate_measurement_bounds(dict(finished_ns=22),dict(started_ns=41),m)


if __name__ == '__main__':
    unittest.main()
