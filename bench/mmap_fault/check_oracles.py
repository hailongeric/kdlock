#!/usr/bin/env python3
"""Guest-only rejection checks using the retained, actually returned client data."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mf_timing',ROOT/'bench/mmap_fault/timing.py')
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)


def main():
    timing.guest()
    base=Path(sys.argv[1]);state=timing.load(base/'result.json')
    timing.rt.require(state['passed'] and state['drained'],'completed preparation required')
    row=next(r for r in state['sessions'] if r['workload']=='fault' and r['threads']==16 and r['arm']=='kdlock')
    source=base/row['name']/'client.jsonl'
    rows=[json.loads(line) for line in source.read_text().splitlines()]
    timing.validate(rows,row)
    cases={
        'missing_fault':lambda x:x[1]['after'].__setitem__('faults',0),
        'reader_became_writer':lambda x:x[1]['after'].__setitem__('writes',1),
        'missing_reader_release':lambda x:x[1]['after'].__setitem__('read_ends',0),
        'duplicate_pid':lambda x:x[0]['pids'].__setitem__(1,x[0]['pids'][0]),
        'missing_join':lambda x:x[1].__setitem__('joined',15),
        'wrong_cpu':lambda x:x[1]['workers'][0].__setitem__('observed_cpu',63),
        'missing_latency':lambda x:x[1]['workers'][0]['latency_ns'].pop(),
        'early_finish':lambda x:x[1]['workers'][0].__setitem__('kernel_finished_ns',x[1]['started_ns']),
        'false_mmap':lambda x:x[1].__setitem__('workload','mmap'),
    }
    rejected=[]
    for name,mutate in cases.items():
        candidate=copy.deepcopy(rows);mutate(candidate)
        try:timing.validate(candidate,row)
        except (timing.rt.Failure,ValueError):rejected.append(name)
        else:raise AssertionError('invalid receipt accepted: '+name)
    print(json.dumps(dict(passed=True,positive_receipts=1,rejected=rejected,
        source=str(source),source_sha256=timing.rt.digest(source),script_sha256=timing.rt.digest(Path(__file__)),
        runner_sha256=timing.rt.digest(ROOT/'bench/mmap_fault/timing.py'))))


if __name__=='__main__':main()
