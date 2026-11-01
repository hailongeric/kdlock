"""Offline plots of retained matched records; no workload execution."""
import argparse,csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--candidate',default='82203677');a=p.parse_args()
rows=list(csv.DictReader((a.folder/'points.csv').open()))
for r in rows:
 for k in ('cachelines','write_percent','workers'):r[k]=int(r[k])
 for k in ('native_before_ops_s','tclock_before_ops_s','kd_before_ops_s','kd_after_ops_s'):r[k]=float(r[k])/1e6
series=[('native_before_ops_s','Linux Native','#7a7a7a'),('tclock_before_ops_s','TCLock','#d99426'),('kd_before_ops_s','KD 87a3a41f','#4e79a7'),('kd_after_ops_s','KD '+a.candidate,'#198a72')]
fig,axes=plt.subplots(2,2,figsize=(12,7.5),layout='constrained')
for ax,family in zip(axes.flat,('mutex','spin','rwlock','rwsem')):
 w=100 if family in ('mutex','spin') else 20
 chosen=[]
 for n in (20,32):
  for place in ('contiguous','split'+str(n)):
   chosen.append(next(r for r in rows if (r['family'],r['cachelines'],r['write_percent'],r['workers'],r['placement'])==(family,16,w,n,place)))
 for i,(key,label,color) in enumerate(series):
  ax.bar([j+(i-1.5)*.19 for j in range(4)],[r[key] for r in chosen],width=.18,label=label,color=color)
 ax.set_xticks(range(4),['20 same','20 split','32 same','32 split']);ax.set_title(f'{family}: c16, {w}% writes');ax.set_ylabel('Whole-run Mops/s');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.legend(*axes[0,0].get_legend_handles_labels(),loc='lower center',ncol=4,bbox_to_anchor=(.5,-.035),fontsize=9)
fig.suptitle('Equal worker counts: one NUMA node versus two\nOne round per point; Native/TCLock retained baseline arms',fontsize=13)
fig.savefig(a.folder/'same-vs-split.png',dpi=170,bbox_inches='tight');fig.savefig(a.folder/'same-vs-split.svg',bbox_inches='tight');plt.close(fig)
keys=sorted({(r['family'],r['cachelines'],r['write_percent']) for r in rows})
fig,axes=plt.subplots(3,4,figsize=(17,10),layout='constrained')
for ax,key in zip(axes.flat,keys):
 chosen=sorted([r for r in rows if (r['family'],r['cachelines'],r['write_percent'])==key and r['placement']=='contiguous'],key=lambda r:r['workers'])
 for field,label,color in series:ax.plot([r['workers'] for r in chosen],[r[field] for r in chosen],'-o',label=label,color=color,ms=3,lw=1.5)
 # Open rings make zero returned-body KD observations explicit.
 for field,count,color in [('kd_before_ops_s','before_jit_completions','#4e79a7'),('kd_after_ops_s','after_jit_completions','#198a72')]:
  zero=[r for r in chosen if r[count]=='0']
  ax.scatter([r['workers'] for r in zero],[r[field] for r in zero],s=45,facecolors='none',edgecolors=color,linewidths=1.2,zorder=5)
 ax.axvspan(32.5,61,color='#e5e5e5',alpha=.5);ax.set_xlim(0,61);ax.set_title(f'{key[0]} c{key[1]:02d} w{key[2]:03d}');ax.grid(alpha=.18);ax.set_ylabel('Mops/s');ax.set_xlabel('Workers')
fig.legend(*axes[0,0].get_legend_handles_labels(),loc='lower center',ncol=4,bbox_to_anchor=(.5,-.03),fontsize=9)
fig.suptitle('Contiguous CPU grid; shaded points use both nodes\nOpen rings: no returned JIT bodies. Spin uses post64; other families use post256. Compare within panels.',fontsize=13)
fig.savefig(a.folder/'worker-grid.png',dpi=160,bbox_inches='tight');fig.savefig(a.folder/'worker-grid.svg',bbox_inches='tight');plt.close(fig)
