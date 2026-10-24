#!/usr/bin/env python3
"""Empty target/zero-near proof and exact queued selection of the zero body."""
from pathlib import Path
import re
import runpy
base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/receipts.py'))
compare_native,compare_success=base['compare_native'],base['compare_success']
require,IDENT=base['require'],base['IDENT']

def validate(row,log):
    result=base['validate'](row,log,empty=True,near_zero=True)
    transitions=list(re.finditer(r'KD_MM_TEST shared_empty_change ([^\n]+)',log))
    changing=row['mode']=='change-zero'
    require(len(transitions)==changing, 'exact empty-to-zero transition missing/duplicate')
    if not changing:return result
    g=0 if row['native'] else 1
    o=row['origins'][g];c,m=row['change'],row['change_more'];table=row['walks_before'][g]['table_pfn'][1]
    require(c['done']==1 and c['result']==c['before_zero']==c['after_private']==0 and
        c['index']==g*3+1 and c['pending']==(0 if row['native'] else 3) and
        c['readers']==(1 if row['native'] else 2) and (row['native'] or c['admission']==-1),
        'empty-to-zero change did not precede writer admission')
    require(m==dict(mode=13,before_none=1,after_zero=1,table_before=table,table_after=table,
        anon_before=0,anon_after=0) and table>0 and not c['page'] and c['zero_pfn']>0,
        'read fault acquired ownership or changed table/ancestry')
    require(not any(row['masks']) and all(z==(4 if row['interior_right'] else 1) for z in row['zero_masks']),
        'controlled read fault requires exact original empty-target/zero-near/untouched-far layout')
    fields=dict(re.findall(r'(\w+)=(\S+)',transitions[0].group(1)))
    expected=dict(mm=row['mm'],index=c['index'],actor=c['actor'],pending=c['pending'],readers=c['readers'],
        admission=c['admission'],mode=13,before_none=1,before_zero=0,after_zero=1,after_private=0,
        table_before=table,table_after=table,anon_before=0,anon_after=0,zero_pfn=c['zero_pfn'],
        private_pfn=0,refs=0,mapcount=0,locked=0,result=0)
    hexa={'mm','table_before','table_after','anon_before','anon_after','zero_pfn','private_pfn'}
    require({k:int(v,16 if k in hexa else 10) for k,v in fields.items()}==expected,
        'queued transition receipt not bound to exact observed state')
    require(c['actor']>0 and (c['actor']==o['tid'] if row['native'] else all(c['actor']!=x['tid'] for x in row['origins'])),
        'wrong native read-fault actor')
    if not row['native']:
        bodies=list(re.finditer('KD_MM_BOUNDARY_INTERIOR_ZERO done '+IDENT,log))
        require(len(bodies)==1 and bodies[0].group(3)==str(o['tid']) and transitions[0].end()<bodies[0].start(),
            'exact changed target did not execute through the validated zero path')
        line=log[bodies[0].start():].splitlines()[0]
        require(re.search(r' zero_pfn='+format(c['zero_pfn'],'x')+r' zero_owned=0',line) and
            'zero_tlb_complete=1' in line, 'changed zero identity/translation completion missing')
    return dict(result,controlled_interior_empty_to_zero=True)
