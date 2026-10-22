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
            subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(src),str(out),'--no-plots'],check=True)
            counts=json.loads((out/'coverage.json').read_text())
            self.assertEqual(counts,dict(completed=8,failed=1,unsupported=882,missing=7047))
            rows=list(csv.DictReader((out/'aggregate.csv').open()))
            kd=next(r for r in rows if r['implementation']=='kdlock')
            self.assertEqual(kd['execution'],'local-zero-delegation')
            self.assertEqual(float(kd['median_ops_s']),200)
            self.assertEqual(float(kd['kd_speedup_native']),1)
            self.assertEqual(kd['kd_speedup_tclock'],'')
            self.assertEqual(len(list(csv.DictReader((out/'runs.csv').open()))),7938)

if __name__=='__main__':unittest.main()
