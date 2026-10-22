#!/usr/bin/env python3
"""Focused report accounting checks; execute in the VM only."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class ReportTests(unittest.TestCase):
    def test_missing_unsupported_local_and_failed_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);src=base/'raw';src.mkdir();out=base/'report'
            for arm in ('native','tclock','kdlock'):
                for rep in range(3):
                    dest=src/'spin-cacheline'/f'{arm}-{rep}';dest.mkdir(parents=True)
                    r=dict(lock_kind='spin',workload='cacheline',cachelines=1,threads=1,arm=arm,repeat=rep,
                        execution_status='OK',drained=True,jit_bodies=0,jit_completions=0,
                        measurement=dict(complete=True,data_ok=True,completed=100*(rep+1),wall_ns=1000000000))
                    if arm=='tclock' and rep==2:r['drained']=False
                    (dest/'session.json').write_text(json.dumps(r))
            held=dict(name='held-native',lock_kind='spin',workload='cacheline',cachelines=1,
                threads=2,arm='native',repeat=2)
            (src/'spin-cacheline'/'plan.json').write_text(json.dumps([held]))
            (src/'continuation').mkdir()
            (src/'continuation'/'prefix-finished.json').write_text(json.dumps(dict(
                skipped=[dict(name='held-native',reason='remaining repetition held after failure')])))
            subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(src),str(out),'--no-plots'],check=True)
            counts=json.loads((out/'coverage.json').read_text())
            self.assertEqual(counts,dict(completed=8,failed=1,unsupported=882,missing=7047))
            self.assertEqual(json.loads((out/'coverage-configurations.json').read_text()),
                dict(completed=2,failed=1,unsupported=294,missing=2349))
            with (out/'aggregate.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            kd=next(r for r in rows if r['implementation']=='kdlock')
            self.assertEqual(kd['execution'],'local-zero-delegation')
            self.assertEqual(float(kd['median_ops_s']),200)
            self.assertEqual(float(kd['kd_speedup_native']),1)
            self.assertEqual(kd['kd_speedup_tclock'],'')
            with (out/'runs.csv').open() as stream:
                runs=list(csv.DictReader(stream))
            self.assertEqual(len(runs),7938)
            held_row=next(r for r in runs if r['reason']=='remaining repetition held after failure')
            self.assertEqual(held_row['status'],'missing')

            # Delegation is an observed outcome, not a changed input. Retain
            # all three valid repetitions in the configuration's median.
            for rep in (1,2):
                path=src/'spin-cacheline'/f'kdlock-{rep}'/'session.json'
                r=json.loads(path.read_text())
                r.update(jit_bodies=10*rep,jit_completions=10*rep)
                path.write_text(json.dumps(r))
            subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(src),str(out),'--no-plots'],check=True)
            with (out/'aggregate.csv').open() as stream:
                kd=next(r for r in csv.DictReader(stream) if r['implementation']=='kdlock')
            self.assertEqual(kd['execution'],'mixed-delegation')
            self.assertEqual(kd['repetitions'],'3')
            self.assertEqual(kd['local_repetitions'],'1')
            self.assertEqual(kd['returned_delegation_repetitions'],'2')
            self.assertEqual(float(kd['median_ops_s']),200)
            self.assertEqual(float(kd['kd_speedup_native']),1)

if __name__=='__main__':unittest.main()
