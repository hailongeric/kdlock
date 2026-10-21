#!/usr/bin/env python3
"""VM-only rejection checks using completed positive writer and timing receipts."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
# A copied checker may use the maintained checkout without mutating frozen inputs.
if not (ROOT/'bench/mmap_writer/timing.py').exists():ROOT=Path('/root/host_fs/kdlock')
spec=importlib.util.spec_from_file_location('mw_time_oracles',ROOT/'bench/mmap_writer/timing.py')
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)
rt=timing.rt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--correctness',type=Path,required=True)
    p.add_argument('--timing',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    timing.common.guest();timing.check.idle(a.correctness.parent)
    rt.require(not a.output.exists(),'new oracle evidence path required');a.output.mkdir()
    cr=a.correctness/'02-cycle-16.jsonl';tr=a.timing/'03-mmap-shared-mm-16-sampled-r0/client.jsonl'
    writer=[json.loads(line) for line in cr.read_text().splitlines()]
    measured=[json.loads(line) for line in tr.read_text().splitlines()]
    cvalidate=lambda r:timing.check.validate(r,'cycle',16,5000)
    tvalidate=lambda r:timing.validate(r,timing.spec(16,'sampled',0))
    cvalidate(writer);tvalidate(measured)
    rejected=[]
    def check(name,rows,validate,mutate):
        bad=copy.deepcopy(rows);mutate(bad)
        try:validate(bad)
        except (rt.Failure,ValueError) as error:rejected.append(dict(name=name,error=str(error)));return
        raise RuntimeError('corrupt receipt accepted: '+name)
    def worker(r):return r[1]['workers'][0]
    for name,mutate in [
        ('different_mm',lambda r:worker(r)['identity'].__setitem__('mm',1)),
        ('duplicate_tid',lambda r:worker(r)['identity'].__setitem__('tid',r[1]['workers'][1]['identity']['tid'])),
        ('fault_in_mmap',lambda r:r[1]['after'].__setitem__('faults',1)),
        ('live_vma',lambda r:r[1]['after'].__setitem__('vmas',1)),
        ('unexpected_clone',lambda r:r[1]['after'].__setitem__('clones',1)),
        ('missing_map',lambda r:r[1]['after'].__setitem__('maps',0)),
        ('queue_observer_enabled',lambda r:r[1]['after'].__setitem__('observe',1)),
        ('missing_join',lambda r:r[1].__setitem__('joined',15)),
        ('missing_latency',lambda r:worker(r)['latency_ns'].pop()),
        ('invalid_progress',lambda r:r[1]['samples'][0]['completed'].__setitem__(0,r[1]['completed']+1)),
        ('wrong_cpu',lambda r:worker(r).__setitem__('observed_cpu',63)),
    ]:check(name,measured,tvalidate,mutate)
    def stack(r):return next(v for v in r if v['event']=='writer_stack')
    for name,mutate in [
        ('wrong_lock',lambda r:stack(r).__setitem__('mmap_lock',1)),
        ('wrong_return_pc',lambda r:stack(r).__setitem__('return_offset',1)),
        ('running_task',lambda r:stack(r).__setitem__('state_after','R')),
        ('other_wait',lambda r:stack(r).__setitem__('wchan_before','futex_wait')),
        ('task_rescheduled',lambda r:stack(r).__setitem__('schedstat_after','1 2 3\n')),
        ('missing_writer_proof',lambda r:r.remove(stack(r))),
        ('unbound_stack_pc',lambda r:stack(r).__setitem__('raw_stack','[<0>] vm_mmap_pgoff+0x1/0x170\n')),
    ]:check(name,writer,cvalidate,mutate)
    timing.check.idle(a.correctness.parent)
    result=dict(passed=True,positive_receipts=2,rejected=rejected,idle=True,accepted=False,
                input_hashes={str(p):rt.digest(p) for p in (cr,tr)},script_sha256=rt.digest(Path(__file__)))
    rt.write_json(a.output/'checks.json',result);print(json.dumps(result))

if __name__=='__main__':main()
