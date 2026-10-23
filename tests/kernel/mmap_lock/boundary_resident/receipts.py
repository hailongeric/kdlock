#!/usr/bin/env python3
"""Bind original private-page ownership to real retained-boundary removal."""
from pathlib import Path
import re
import runpy

edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
compare_native,compare_success=edge['compare_native'],edge['compare_success']


def validate(row,log,*,shared=False):
    result=edge['validate'](row,log,private=True,shared=shared)
    mode,native,target=row['mode'],row['native'],row['slice']
    transitions=list(re.finditer(r'KD_MM_TEST edge_private_busy mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=10 before_locked=0 after_locked=1 table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=([0-9a-f]+) anon_after=([0-9a-f]+) private_pfn=([0-9a-f]+) refs=2 mapcount=1 result=0',log))
    require(len(transitions)==(mode=='change-busy'), 'queued target eligibility change missing/duplicated')
    if mode=='change-busy':
        g=0 if native else 1;o=row['origins'][g];index=g*3+target
        c,m=row['change'],row['change_more'];r=transitions[0].groups()
        require(c['done']==c['after_private']==1 and c['result']==c['before_zero']==c['zero_pfn']==0 and
                c['index']==index and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
                (native or c['admission']==-1) and c['actor']>0 and len(c['page'])==1, 'change was not while exact queued readers held ownership')
        expected=dict(row['pages_before'][index]);expected['locked']=1
        require(c['page'][0]==expected and row['pages_before'][index]['locked']==0, 'busy control changed page identity or acquired another reference')
        table=row['walks_before'][g]['table_pfn'][target]
        require(m==dict(mode=10,before_none=0,after_zero=0,table_before=table,table_after=table,
                       anon_before=o['original_anon'],anon_after=o['original_anon']), 'busy transition changed table or ancestry')
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:6]))==(index,c['actor'],c['pending'],c['readers'],c['admission']) and
                tuple(int(x,16) for x in r[6:])==(table,table,o['original_anon'],o['original_anon'],expected['pfn']), 'queued control receipt not bound to actual target')
        require(c['actor']==o['tid'] if native else all(c['actor']!=x['tid'] for x in row['origins']), 'wrong control task')
        if not native:
            ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
            require(ack and ack.group(3)==str(o['tid']) and transitions[0].end()<ack.start(), 'busy target failed to hand back before effects')
    result['controlled_target_busy']=mode=='change-busy'
    result['probe_holds_dropped_before_body']=bool(row['free_first'])
    return result
