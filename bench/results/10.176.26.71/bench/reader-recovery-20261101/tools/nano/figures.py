"""Render observed point changes from the completed, verified Nano report."""
from pathlib import Path
import json,math,os
os.environ['MPLCONFIGDIR']='/tmp/kdlock-reader-plot-config-20261101'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
root=Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/bench/reader-recovery-20261101')
s=json.loads((root/'status.json').read_bytes());assert s['nano_complete'] and s['nano_points_per_arm']==210 and s['nano_arms']==3
out=root/'figures';assert out.is_dir() and {p.name for p in out.iterdir()}=={f'nano-recovery-versus-{arm}.{ext}' for arm in ['promoted','reference'] for ext in ['png','svg']}
workers=[*range(1,9),*range(12,61,4)]
for label,title in [('promoted','promoted e0f9696c (provider 1b6f256b)'),('reference','reference f7a84065')]:
 p=root/'nano/comparison'/('recovery-versus-'+label);summary=json.loads((p/'summary.json').read_bytes());points=json.loads((p/'points.json').read_bytes());assert len(points)==210 and summary['unscored_coordinates']==0
 profiles=summary['profiles'];keys=[(x['lock_kind'],x['workload'],x['write_percent']) for x in profiles]
 labels=[f'{a} {b} w{c}' for a,b,c in keys];fig,axes=plt.subplots(2,1,figsize=(19,10),layout='constrained')
 for ax,metric,name in zip(axes,['whole','peak'],['Whole-window throughput','Qualified peak throughput']):
  values=np.array([[100*(next(x for x in points if (x['lock_kind'],x['workload'],x['write_percent'],x['threads'])==(*key,n))['metrics'][metric]['ratio']-1) for n in workers] for key in keys]);assert np.isfinite(values).all()
  im=ax.imshow(values,cmap='RdBu',vmin=-25,vmax=25,aspect='auto');ax.set_xticks(range(len(workers)),workers);ax.set_yticks(range(len(keys)),labels);ax.set_xlabel('Workers');ax.set_title(name,loc='left',fontsize=12)
  for row in range(len(keys)):
   for col in range(len(workers)):
    value=values[row,col];point=next(x for x in points if (x['lock_kind'],x['workload'],x['write_percent'],x['threads'])==(*keys[row],workers[col]));mark='*' if any(point[k]['execution_class']=='NO_JIT' for k in ['reference_kd','current_kd']) else '';ax.text(col,row,f'{value:+.1f}{mark}',ha='center',va='center',fontsize=7,color='white' if abs(value)>15 else 'black',fontweight='bold' if value < -10 else 'normal')
 fig.colorbar(im,ax=axes,location='right',label='Observed change (%)',extend='both',shrink=.9,pad=.02)
 fig.suptitle('Reader restoration 66c68c17 versus '+title+'\nOne round per point; all 210 points included; bold losses exceed 10%; colors clip at ±25%\n* One or both runs reported NO_JIT; these scores remain included',fontsize=14)
 for ext in ['png','svg']:
  target=out/('nano-recovery-versus-'+label+'.'+ext);fig.savefig(target,dpi=160)
  if ext=='svg':target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines())+'\n')
 plt.close(fig)
print(out)
