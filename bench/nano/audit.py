#!/usr/bin/env python3
"""Replay saved nano correctness evidence in the idle VM; no live module calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(base, source):
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(source/'bench/spin_cacheline'),str(source/'bench/rwlock_compare')]
    from bench_runtime import validate_measurement, FAULT
    from oracle import validate as validate_rw
    inputs={}; sources=0; binaries=0; valid=0; failed=[]; incomplete=[]
    for block in sorted(p.parent for p in base.glob('*/plan.json')):
        manifest=block/'source-sha256.json'
        if manifest.exists():
            frozen=json.loads(manifest.read_text())
            assert any(p.endswith('.inc') for p in frozen), 'private .inc inputs missing'
            for relative,expected in frozen.items():
                path=block/'source'/relative
                assert path.is_file() and digest(path)==expected, 'source bytes differ: '+str(path)
                assert relative not in inputs or inputs[relative]==expected, 'source changed between blocks: '+relative
                inputs[relative]=expected;sources+=1
        binary_manifest=block/'binary-sha256.json'
        if binary_manifest.exists():
            for original,expected in json.loads(binary_manifest.read_text()).items():
                # The spin/mutex runner retains global binaries in binaries/;
                # private variant and rw builds remain inside their block.
                original=Path(original)
                path=original if original.is_relative_to(block) else block/'binaries'/original.name
                assert path.is_file() and digest(path)==expected, 'binary bytes differ: '+str(path)
                binaries+=1
        for spec in json.loads((block/'plan.json').read_text()):
            path=block/spec['name']/'session.json'
            if not path.exists(): incomplete.append(str(path.relative_to(base)));continue
            r=json.loads(path.read_text());m=r.get('measurement',{})
            accepted=(r.get('execution_status')=='OK' or (r.get('execution_status')=='NO_JIT' and r.get('jit_bodies')==0))
            if not accepted or not r.get('drained') or r.get('cleanup_error'):
                detail=dict(session=str(path.relative_to(base)),status=r.get('execution_status'),drained=r.get('drained'),error=r.get('error'))
                if path.with_name('measure.json').is_file():
                    raw=json.loads(path.with_name('measure.json').read_text())
                    detail.update(client_complete=raw.get('complete'),client_data_ok=raw.get('data_ok'),completed=raw.get('completed'))
                    detail['post_finish_sample_mismatches']=[dict(sample=i,worker=j,
                        sample_begin=s['started_ns'],sample_end=s['finished_ns'],kernel_finished=w['kernel_finished_ns'],
                        observed=v,final=w['completed'],gap=w['completed']-v)
                        for i,s in enumerate(raw.get('samples',[]))
                        for j,(v,w) in enumerate(zip(s['completed'],raw['workers']))
                        if s['started_ns']>=w['kernel_finished_ns'] and v!=w['completed']]
                failed.append(detail);continue
            assert m.get('data_ok') is True and m.get('complete') is True
            assert all(r[k]==v for k,v in spec.items()), 'session plan differs'
            assert r['cpus']==list(range(r['threads'])) and r['collector_cpu']==63
            raw=json.loads(path.with_name('measure.json').read_text())
            for key,value in raw.items():
                assert m[key]==value, 'client/session measurement differs: '+key
            if r['lock_kind'] in ('rwlock','rwsem'):
                peak=validate_rw(raw,r)
            else:
                peak=validate_measurement(raw,r,r['iterations'])
            assert peak==m['peak'], 'saved peak does not replay'
            assert not FAULT.search(path.with_name('kernel.log').read_text()), 'kernel fault recorded'
            if r['arm']=='kdlock':
                assert r['published_before']==r['published_after'], 'publication changed'
                retired=r['retired']
                assert retired['state']==2 and retired['frames']==retired['writers']==retired['modules']==0
                entries=r['jit_bodies'];complete=r['jit_completions']
                assert entries==r['jit_after']-r['jit_before']
                before=r.get('jit_completions_before',r.get('jit_complete_before'))
                after=r.get('jit_completions_after',r.get('jit_complete_after'))
                assert complete==after-before
                eligible=m['writes'] if r['lock_kind'] in ('rwlock','rwsem') else m['completed']
                assert 0<=complete<=entries<=eligible
            valid+=1
    return dict(validated_sessions=valid,failed_sessions=failed,missing_sessions=incomplete,
                checked_source_files=sources,checked_binaries=binaries,consistent_sources=len(inputs),
                scope='Saved client oracles, exact totals, worker placement, publication and retirement receipts, counters, logs, retained input bytes. Does not rerun measured operations.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path)
    p.add_argument('--source',type=Path,default=Path('/root/host_fs/kdlock'));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit(a.input.resolve(),a.source.resolve());a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('failed_sessions','missing_sessions')}))

if __name__=='__main__': main()
