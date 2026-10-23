#!/usr/bin/env python3
"""Negative controls for exact split and resource-retirement evidence."""
import copy
import unittest
from receipts import validate


def sample(mode='middle'):
    cancel=mode=='cancel';refuse=mode=='refusal';n=2 if cancel else 3 if refuse else 16
    sl=0 if mode=='prefix' else 2 if mode=='suffix' else 1
    c=dict(calls=n,removed=1 if cancel or refuse else 16,delegated=0 if cancel or refuse else 15,
           native=2 if refuse else 0,post_ban=int(refuse),handbacks=int(refuse),acks=int(refuse),
           cancelled=int(cancel),refused=int(refuse),failed=0,native_only=int(refuse))
    clean=dict(c,calls=n+n*3,native=c['native']+n*3,native_only=1,refused=1,post_ban=c['post_ban']+n*3-(not refuse))
    origins=[dict(tid=i+1,start=0x10000+i*0x10000+sl*4096,end=0x10000+i*0x10000+(sl+1)*4096,
                  old_start=0x10000+i*0x10000,old_end=0x10000+i*0x10000+3*4096) for i in range(n)]
    removed=1 if cancel else n
    row=dict(mode=mode,groups=n,slice=sl,idle=1,errors=0,checks=999,mm=42,gate=43,reader_peak=2,cleanup_calls=n*3,
             counts=c,after_cleanup=clean,pages_before=1000,pages_after=1000-removed,maps_before=100,maps_after=100+(removed if sl==1 else 0),
             origins=origins,cleanup_tid=999,late_fault_blocked=1,late_fault_code=1,late_fault_stack='kd_mmap_down_read do_user_addr_fault',cancel_result=[0,-4],cancel_tid=[1,2])
    logs=[]
    for i,o in enumerate(origins):
        core=f"mm=2a id={i+1} origin={i+1} executor=1 start={o['start']:x} end={o['end']:x}"
        if not cancel and not refuse and i:
            logs += ['KD_MM_UNMAP done '+core+' result=0', 'KD_MM_PARTIAL done '+core+f" old_start={o['old_start']:x} old_end={o['old_end']:x} splits={2 if sl==1 else 1} maps_before=100 maps_after={101 if sl==1 else 100} pages_before=1000 pages_after=999 tables_unchanged=1"]
        if refuse and i==1:logs += ['KD_MM_UNMAP handback '+core,'KD_MM_UNMAP ack '+core]
        if not refuse or i<2:
            used=0 if (cancel or refuse) and i==1 else 3 if sl==1 else 1
            logs += [f"KD_MM_SPLIT retire mm=2a origin={i+1} start={o['start']:x} end={o['end']:x} vma0={i*2+100:x} vma1={i*2+101:x} consumed={used} freed={3^used}"]
    if not refuse:
        logs += [f"KD_MM_SPLIT retire mm=2a origin=999 start={origins[0]['old_start']:x} end={origins[0]['old_end']:x} vma0=fff0 vma1=fff1 consumed=0 freed=3"]
    return row,'\n'.join(logs)


class Receipts(unittest.TestCase):
    def test_supported_and_refusal_shapes(self):
        for mode in ('prefix','suffix','middle','refusal','cancel'):
            with self.subTest(mode=mode):validate(*sample(mode))
    def test_missing_or_duplicate_execution(self):
        r,m=sample()
        for altered in (m.replace('KD_MM_PARTIAL done','OTHER done',1),m+'\n'+m.splitlines()[1]):
            with self.assertRaises(AssertionError):validate(r,altered)
    def test_wrong_executor_or_mapping(self):
        r,m=sample()
        for a,b in [('origin=2 executor=1','origin=2 executor=2'),('old_start=20000','old_start=21000')]:
            with self.assertRaises(AssertionError):validate(r,m.replace(a,b))
    def test_bad_accounting(self):
        r,m=sample()
        with self.assertRaises(AssertionError):validate(r,m.replace('maps_after=101','maps_after=102',1))
        r['pages_after']+=1
        with self.assertRaises(AssertionError):validate(r,m)
    def test_retirement_mismatch(self):
        r,m=sample('refusal')
        for a,b in [('consumed=0 freed=3','consumed=1 freed=2'),('KD_MM_UNMAP ack','OTHER ack'),('vma0=66 vma1=67','vma0=66 vma1=66')]:
            with self.assertRaises(AssertionError):validate(r,m.replace(a,b))
    def test_cancel_or_reader_failure(self):
        r,m=sample('cancel');r['cancel_result'][1]=0
        with self.assertRaises(AssertionError):validate(r,m)
        r,m=sample();r['reader_peak']=1
        with self.assertRaises(AssertionError):validate(r,m)


if __name__=='__main__':unittest.main()
