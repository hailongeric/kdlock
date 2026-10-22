#!/usr/bin/env python3
"""Reject corrupted observation receipts before any live metadata run."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import phase_observation as phase


class ReceiptChecks(unittest.TestCase):
    def fixture(self):
        workers=[];rows=[]
        for i in range(16):
            c=dict.fromkeys(phase.NAMES,0)
            for name in ('entries','epilogues','success','reserved','reserved_initial','gate_return'):
                c[name]=2
            rows.append(dict(index=i,task=100+i,tid=200+i,mm=300,last_sem=400,sequence=2,active=0,
                first_entry_ns=110,last_epilogue_ns=190,counts=c))
            workers.append(dict(identity=dict(tid=200+i,mm=300,mmap_lock=400),completed=1,
                                active_started_ns=100,kernel_finished_ns=200))
        o=dict(abi=1,records=16,active=0,errors=0,missed=0,rows=rows,
               counts={name:sum(r['counts'][name] for r in rows) for name in phase.NAMES})
        return o,dict(workers=workers)

    def test_valid_uncontended(self):
        self.assertEqual(phase.validate_workers(*self.fixture())['acquisition_calls'],32)

    def test_reject_identity_and_window_corruption(self):
        for key,value in [('tid',999),('mm',999),('last_sem',999),('first_entry_ns',99),
                          ('last_epilogue_ns',201),('sequence',3),('active',1)]:
            with self.subTest(key=key):
                o,m=self.fixture();o['rows'][0][key]=value
                with self.assertRaises(phase.rt.Failure):phase.validate_workers(o,m)

    def test_reject_missed_or_partial_acquisition(self):
        for key in ('missed','errors','active'):
            o,m=self.fixture();o[key]=1
            with self.assertRaises(phase.rt.Failure):phase.validate_workers(o,m)
        o,m=self.fixture();o['rows'][0]['counts']['epilogues']-=1
        with self.assertRaises(phase.rt.Failure):phase.validate_workers(o,m)

    def test_reject_unpaired_blocked_return(self):
        o,m=self.fixture()
        for c in (o['counts'],o['rows'][0]['counts']):c['phase_blocked_return']=1
        with self.assertRaises(phase.rt.Failure):phase.validate_workers(o,m)

    def test_reject_wrong_business_denominator(self):
        o,m=self.fixture();m['workers'][0]['completed']=2
        with self.assertRaises(phase.rt.Failure):phase.validate_workers(o,m)


if __name__=='__main__':unittest.main()
