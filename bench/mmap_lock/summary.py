#!/usr/bin/env python3
"""Summarize six separately booted plain blocks; never supply missing p95."""
import argparse
import json
from pathlib import Path
import plain


def summarize(runs):
    rows=[];boots=[];inputs=set()
    order=[(0,'native'),(0,'kd'),(1,'kd'),(1,'native'),(2,'native'),(2,'kd')]
    plain.rt.require(len(runs)==6,'six separate boot blocks required')
    for block,((name,run),(repeat,mode)) in enumerate(zip(runs,order)):
        plain.rt.require(run['action']=='measure' and run['passed'] and run['drained'] and
            run['final_idle'] and run['kernel_mmap_mode']==mode and len(run['sessions'])==4,
            'complete ordered plain block required')
        boots.append(run['boot_id']);inputs.add(run['inputs_sha256'])
        plain.rt.require({(s['task'],s['threads']) for s in run['sessions']}==
                         {(t,n) for t in ('mmap','fault') for n in (1,16)},'task/count grid differs')
        for s in run['sessions']:
            plain.rt.require(s['passed'] and s['drained'] and s['observation']=='plain' and
                             s['repeat']==repeat and s['kernel_mmap_mode']==mode,'plain session differs')
            m=s['measurement']
            plain.rt.require(m['completed_operation_p95_ns'] is None and m['latency_samples']==0,
                             'plain result contains latency samples')
            rows.append(dict(run=name,block=block,boot_id=run['boot_id'],repeat=repeat,mode=mode,
                task=s['task'],threads=s['threads'],whole_ops_s=m['whole_ops_s'],
                peak_ops_s=m['peak']['throughput_ops_s'],endpoint=run['host_endpoint']))
    plain.rt.require(len(set(boots))==6 and len(inputs)==1,'distinct boots and one frozen input set required')
    groups=[];ratios=[]
    for task in ('mmap','fault'):
        for n in (1,16):
            selected=[r for r in rows if r['task']==task and r['threads']==n]
            for mode in plain.MODES:
                group=[r for r in selected if r['mode']==mode]
                groups.append(dict(task=task,threads=n,mode=mode,
                    whole_ops_s=plain.common.distribution([r['whole_ops_s'] for r in group]),
                    peak_ops_s=plain.common.distribution([r['peak_ops_s'] for r in group])))
            for repeat in range(3):
                pair={r['mode']:r for r in selected if r['repeat']==repeat}
                ratios.append(dict(task=task,threads=n,repeat=repeat,
                    whole_kd_native=pair['kd']['whole_ops_s']/pair['native']['whole_ops_s'],
                    peak_kd_native=pair['kd']['peak_ops_s']/pair['native']['peak_ops_s']))
    return dict(rows=rows,groups=groups,paired_ratios=ratios,accepted=False,
        endpoints_passed=all(r['endpoint']=='PASS' for r in rows),
        cv_definition='100 * population standard deviation / arithmetic mean',
        p95_status='DEFERRED',sampling_cost_status='DEFERRED',
        limits='Three repetitions are descriptive. Callback/progress overhead remains unisolated. '
               'Fault cycles include PTE reset. Seven mutex causes remain unresolved.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('receipts',type=Path,nargs=6)
    a=p.parse_args();print(json.dumps(summarize([(str(path),plain.common.load(path)) for path in a.receipts]),indent=2))
