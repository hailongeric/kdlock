"""VM-only tests of separate joined warmup/measurement observation boundaries."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import rcuht_boundary as diagnostic


def work(measured=False):
    rows=[dict(cpu=i,completed=48000,finished_ns=70+i) for i in range(2)]
    result=dict(workers=rows,completed=96000,started_ns=20,finished_ns=80)
    if measured:
        result['deadline_ns']=60
        for row in rows:row.update(active_started_ns=30,kernel_finished_ns=65)
    return result


class BoundaryTests(unittest.TestCase):
    def test_predecessor_requires_matching_complete_outer(self):
        expected=dict(driver_sha256='new',transition_sha256='boot',original_inputs='frozen')
        previous=dict(expected,passed=True,state='COMPLETE',final_idle=True,sessions=1,
                      order=[['rcuht',2,0,'baseline-kd']])
        records=[dict(drained=True,execution_status='NO_JIT',comparison_arm='baseline-kd')]
        diagnostic.predecessor_identity(previous,expected,records)
        for key,value in (('driver_sha256','old'),('transition_sha256','other'),('passed',False),
                          ('state','FAILED'),('sessions',2),('order',[['rcuht',2,0,'public-kd']])):
            with self.assertRaises(ValueError):diagnostic.predecessor_identity(dict(previous,**{key:value}),expected,records)
        for records in ([],[dict(drained=False,execution_status='OK',comparison_arm='baseline-kd')],
                        [dict(drained=True,execution_status='FAILED',comparison_arm='baseline-kd')]):
            with self.assertRaises(ValueError):diagnostic.predecessor_identity(previous,expected,records)

    def test_endpoint_requires_immediate_bound_capture(self):
        endpoint=dict(passed=True,checked=True,immediate=True,result_sha256='r',host_sha256='h')
        controller=dict(passed=True,guest_returncode=0,host_returncode=0,result_fetch_returncode=0,
            guest_result_path='/run/result.json',guest_result_sha256='r',host_sha256='h',
            guest_exit_observed_monotonic_ns=10,host_capture_started_monotonic_ns=11,
            host_capture_finished_monotonic_ns=12)
        host=dict(pins_verified=True,snapshot_listed=True)
        diagnostic.endpoint_link(endpoint,controller,host,'r','h','/run/result.json')
        diagnostic.endpoint_link(dict(endpoint,passed=False),controller,host,'r','h','/run/result.json')
        for target,key,value in ((0,'checked',False),(0,'immediate',False),(0,'result_sha256','wrong'),
            (1,'host_sha256','wrong'),(1,'guest_result_path','/old/result.json'),
            (1,'host_capture_started_monotonic_ns',9),(1,'host_capture_started_monotonic_ns',2_000_000_000),
            (1,'host_capture_finished_monotonic_ns',9),(2,'pins_verified',False),(2,'snapshot_listed',False)):
            rows=copy.deepcopy([endpoint,controller,host]);rows[target][key]=value
            with self.assertRaises(ValueError):diagnostic.endpoint_link(*rows,'r','h','/run/result.json')

    def test_serial_selection_retains_original_order(self):
        plan=[('rcuht',2,0,'tclock'),('rcuht',2,0,'baseline-kd'),
              ('rcuht',2,0,'public-kd'),('rcuht',2,0,'native')]
        self.assertEqual(diagnostic.selected_plan(plan),plan[1:3])
        for arm in ('baseline-kd','public-kd'):
            self.assertEqual(diagnostic.selected_plan(plan,arm),[r for r in plan if r[3]==arm])
        for bad in (plan[::-1],plan[:2],plan+plan[1:3]):
            with self.assertRaises(ValueError):diagnostic.selected_plan(bad)

    def test_distinct_schema_bounds(self):
        for measured in (False,True):
            diagnostic.bounds(dict(finished_ns=10),dict(started_ns=90),work(measured),
                              'measure' if measured else 'warmup')

    def test_overlap_geometry_and_warmup_are_rejected(self):
        original=work()
        for mutate in (lambda r:r.update(started_ns=9),lambda r:r.update(finished_ns=91),
                       lambda r:r['workers'][0].update(cpu=63),
                       lambda r:r['workers'][0].update(completed=1)):
            bad=copy.deepcopy(original);mutate(bad)
            with self.assertRaises(ValueError):
                diagnostic.bounds(dict(finished_ns=10),dict(started_ns=90),bad,'warmup')

    def test_measurement_must_span_deadline(self):
        broken=work(True);broken['workers'][0]['kernel_finished_ns']=59
        with self.assertRaises(ValueError):
            diagnostic.bounds(dict(finished_ns=10),dict(started_ns=90),broken,'measure')

    def exercise(self, fail_second=False):
        snapshots=[]
        class Failure(Exception):
            def __init__(self,status,message,unsafe=False):
                super().__init__(message);self.status=status;self.unsafe=unsafe
        class Snapshot:
            kallsyms='captured symbols'
            def __init__(self,path):self.count=0;self.closed=False;snapshots.append(self)
            def receipt(self):return dict(bound=True)
            def capture(self):
                self.count+=1
                if fail_second and self.count==2:raise ValueError('unstable counters')
                return [dict(started_ns=0,finished_ns=10),dict(started_ns=90,finished_ns=100),
                        dict(started_ns=100,finished_ns=110),dict(started_ns=190,finished_ns=200)][self.count-1]
            def close(self):self.closed=True
        class Base:
            def phase(self,label,iterations,*,spec=None):
                self.assert_private()
                result=work(label=='measure')
                if label=='measure':
                    for key in ('started_ns','finished_ns','deadline_ns'):result[key]+=100
                    for row in result['workers']:
                        for key in ('finished_ns','active_started_ns','kernel_finished_ns'):row[key]+=100
                return result
            def assert_private(self):
                if 'boundary_diagnostic' in self.record:raise AssertionError('early serialization')
            def measure(self):self.phase('measure',0);self.record['jit_bodies']=3
            def execute(self):self.phase('warmup',48000);self.measure()
            def save(self):pass
        route=SimpleNamespace(Snapshot=Snapshot,difference=lambda a,b:dict(counters=dict(kd_bench_bodies=3)))
        with tempfile.TemporaryDirectory() as directory:
            session=diagnostic.observed_session(Base,route,Failure)()
            session.path=Path(directory);session.record={}
            if fail_second:
                with self.assertRaises(Failure) as caught:session.execute()
                self.assertTrue(caught.exception.unsafe)
                self.assertFalse(session.record['boundary_diagnostic']['phases']['warmup']['complete'])
            else:
                session.execute()
                self.assertEqual(snapshots[0].count,4)
                self.assertIsNotNone(session.record['boundary_diagnostic']['gap'])
            self.assertTrue(snapshots[0].closed)

    def test_four_snapshots_and_private_storage(self):self.exercise()
    def test_partial_failure_retained_without_retry(self):self.exercise(True)


if __name__=='__main__':unittest.main(verbosity=2)
