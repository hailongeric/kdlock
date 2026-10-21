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
