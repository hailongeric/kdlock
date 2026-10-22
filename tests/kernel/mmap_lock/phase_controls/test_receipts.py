#!/usr/bin/env python3
"""Reject a missing positive path even if aggregate bookkeeping balances."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode=True
sys.path.insert(0,'/root/host_fs/kdlock/bench/mmap_lock')
import phase_controls as controls


class Receipts(unittest.TestCase):
    def fixture(self):
        cases=[];rows=[]
        for mode in (1,2,3):
            c=dict.fromkeys(controls.phase.NAMES,0)
            for name in ('entries','epilogues','success','initial_fail','reserved','reserved_queued',
                         'gate_return','phase_finish'):c[name]=1
            c.update(phase_prepare=3,queued_fail=2,phase_schedule=2,phase_schedule_return=2,
                phase_blocked_return=2 if mode==1 else 1,phase_blocked_out=2 if mode==1 else 1,
                phase_after_block_reserve=1,phase_after_block_fail=int(mode==1),
                phase_no_switch=int(mode==2),phase_runnable_return=int(mode==3),
                phase_runnable_out=int(mode==3))
            fields=dict.fromkeys(controls.CASE_FIELDS,0)
            fields.update(mode=mode,task=100+mode,tid=200+mode,mm=300,sem=400,schedule_calls=2,
                first_return=1,voluntary=int(mode==1),involuntary=int(mode==3),injected=1,
                self_wake=1,peer_task=500 if mode==3 else 0,peer_wake=int(mode==3),
                peer_done=int(mode==3),joined=1,blocked_before_wake=int(mode==1),counts=c)
            cases.append(fields)
            rows.append(dict(index=mode-1,task=100+mode,tid=200+mode,mm=300,last_sem=400,sequence=1,
                active=0,first_entry_ns=10,last_epilogue_ns=20,counts=dict(c)))
        result=dict(abi=1,checks=60,errors=0,idle=1,scenarios=3,missed=0,cases=cases)
        observation=dict(abi=1,records=3,active=0,errors=0,missed=0,rows=rows,
            counts={k:sum(r['counts'][k] for r in rows) for k in controls.phase.NAMES})
        return result,observation

    def test_valid(self):controls.validate(*self.fixture())

    def test_wrong_exact_identity(self):
        for key in ('task','tid','mm','sem'):
            with self.subTest(key=key):
                r,o=self.fixture();r['cases'][0][key]+=1
                with self.assertRaises(controls.rt.Failure):controls.validate(r,o)

    def test_missing_independent_path_oracle(self):
        for case,key,value in ((0,'blocked_before_wake',0),(0,'voluntary',0),(1,'voluntary',1),
                               (1,'involuntary',1),(2,'voluntary',1),(2,'involuntary',0),
                               (2,'peer_wake',0),(2,'peer_done',0)):
            with self.subTest(case=case,key=key):
                r,o=self.fixture();r['cases'][case][key]=value
                with self.assertRaises(controls.rt.Failure):controls.validate(r,o)

    def test_missing_join_or_injection(self):
        for key in ('joined','injected','self_wake','first_return'):
            r,o=self.fixture();r['cases'][0][key]=0
            with self.assertRaises(controls.rt.Failure):controls.validate(r,o)

    def test_missed_probe_or_unfinished_observer(self):
        for key in ('missed','errors','active'):
            r,o=self.fixture();o[key]=1
            with self.assertRaises(controls.rt.Failure):controls.validate(r,o)
        r,o=self.fixture();r['missed']=1
        with self.assertRaises(controls.rt.Failure):controls.validate(r,o)

    def test_no_substituted_aggregate(self):
        r,o=self.fixture();r['cases'][2]['counts']['phase_runnable_return']=0
        with self.assertRaises(controls.rt.Failure):controls.validate(r,o)


if __name__=='__main__':unittest.main()
