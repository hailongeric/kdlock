"""Render audited statistics without running workloads."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

p=argparse.ArgumentParser()
p.add_argument('--report', type=Path, required=True)
a=p.parse_args()
stats=json.loads((a.report/'statistics.json').read_text())
index={(x['group'],x['threads'],x['arm']):x for x in stats}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
series=[('baseline','kdlock','KD before','#89939c'),('final','kdlock','KD after','#bd4a18'),('final','native','Native','#283c63'),('final','tclock','TCLock','#008678')]
for metric,label in [('peak','Warmed peak'),('whole','Whole run')]:
 fig,axes=plt.subplots(2,2,figsize=(11,7.2),layout='constrained')
 for ax,(kind,workload) in zip(axes.flat,[('spin','cacheline'),('spin','rcuht'),('mutex','cacheline'),('mutex','rcuht')]):
  for i,(prefix,arm,title,color) in enumerate(series):
   rows=[index[(f'{prefix}-{kind}-{workload}',n,arm)] for n in [16,36]]
   mid=np.array([r[f'{metric}_median_ops_s']/1e6 for r in rows]);lo=np.array([r[f'{metric}_min_ops_s']/1e6 for r in rows]);hi=np.array([r[f'{metric}_max_ops_s']/1e6 for r in rows])
   ax.bar(np.arange(2)+(i-1.5)*.19,mid,.18,color=color,label=title,yerr=np.array([mid-lo,hi-mid]),error_kw={'elinewidth':1,'capsize':3})
  ax.set_title(kind.capitalize()+' / '+('one cacheline' if workload=='cacheline' else 'hash'))
  ax.set_xticks([0,1],['16 workers\n16 + 0 NUMA','36 workers\n32 + 4 NUMA'])
  ax.set_ylim(bottom=0)
  ax.set_ylabel('Mops/s')
  ax.grid(axis='y',alpha=.17)
  ax.set_axisbelow(True)
 axes[0,0].legend(ncol=2,fontsize=9)
 fig.suptitle(label+' throughput on 10.176.26.71\nThree-round medians; whiskers show observed min–max',fontsize=13)
 for ext in ('png','svg'):
  target=a.report/f'{metric}-throughput.{ext}'
  fig.savefig(target,dpi=170)
  if ext=='svg':
   target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines())+'\n')
 plt.close(fig)
