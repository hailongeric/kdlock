"""Plot the complete verified fresh promoted/recovery MM pair."""
from pathlib import Path
import json,os
os.environ['MPLCONFIGDIR']='/tmp/kdlock-reader-plot-config-20261101'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/bench/reader-recovery-20261101/mm')
v=json.loads((root/'validation.json').read_bytes());assert v['validated'] and v['pairs']==42
rows=json.loads((root/'comparisons.json').read_bytes());workers=[*range(1,9),*range(12,61,4)]
fig,axes=plt.subplots(2,2,figsize=(16,9),layout='constrained')
for col,model in enumerate(['threads','processes']):
 points=[r for r in rows if r['model']==model];assert [p['workers'] for p in points]==workers
 top,bottom=axes[:,col];x=list(range(len(points)))
 for name,label,color in [('baseline','Promoted 1b6f256b','#235789'),('candidate','Reader restoration 66c68c17','#c85a17')]:top.plot(x,[p[name]/1000 for p in points],marker='o',markersize=3,label=label,color=color)
 top.set_title('mmap1_'+model);top.set_ylabel('Thousand mmap/munmap pairs per second');top.set_ylim(bottom=0);top.legend(frameon=False);top.grid(axis='y',alpha=.2)
 change=[p['change_pct'] for p in points];lo=min([0,*change]);hi=max([0,*change]);span=hi-lo;bottom.set_ylim(lo-.16*span,hi+.10*span);bottom.bar(x,change,color=['#c85a17' if d<0 else '#235789' for d in change]);bottom.axhline(0,color='black',linewidth=.7);bottom.set_ylabel('Recovery versus promoted (%)');bottom.grid(axis='y',alpha=.2)
 for i,p in enumerate(points):
  if p['workers'] in [20,32,60]:bottom.annotate(f"{p['change_pct']:+.2f}%",(i,p['change_pct']),xytext=(0,5 if p['change_pct']>=0 else -12),textcoords='offset points',ha='center',fontsize=8)
 for ax in [top,bottom]:ax.set_xticks(x,workers,fontsize=8);ax.set_xlabel('Workers')
fig.suptitle('Fresh mmap1 comparison: all 42 paired points\nOne round per point; no variance estimate; no historical f7a84065 timing pooled',fontsize=14)
for ext in ['png','svg']:
 p=root/('mmap1-comparison.'+ext);assert p.is_file();fig.savefig(p,dpi=160)
 if ext=='svg':p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')
plt.close(fig)
print(root/'mmap1-comparison.png')
