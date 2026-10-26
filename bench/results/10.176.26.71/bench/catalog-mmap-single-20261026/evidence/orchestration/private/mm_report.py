"""Publish one-round MM receipts; no pooling with other kernels or workloads."""
import csv,json,os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/kdlock-catalog-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path('/home/eric/vm/vm-shared/kdlock')
REPORT=ROOT/'bench/results/10.176.26.71/bench/catalog-mmap-single-20261026'
COUNTS=list(range(1,9))+list(range(12,61,4))
def render(label,title,rows,arms,detail):
 out=REPORT/label;out.mkdir(parents=True,exist_ok=True)
 with (out/'table.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 fig,ax=plt.subplots(figsize=(10,5))
 for arm in arms:
  points={r['threads']:r['ops_s']/1e6 for r in rows if r['arm']==arm}
  ax.plot(COUNTS,[points.get(n,float('nan')) for n in COUNTS],marker='o',markersize=3,label=arm)
 ax.set(xlabel='Workers (CPU prefix 0..N−1)',ylabel='Million complete operations / second',title=title+'\nExploratory · one plain round per point')
 ax.grid(alpha=.25);ax.legend();fig.tight_layout()
 fig.savefig(out/'throughput.png',dpi=150);fig.savefig(out/'throughput.svg');plt.close(fig)
 lines=['# '+title,'',detail,'','Exactly one plain round per point. Strict host timing qualification is failed; auxiliary QEMU workers use CPU 63. No variance estimate or latency samples. Rates use complete operations divided by whole wall time. Missing optional positive-cohort peak windows do not invalidate exact aggregate accounting or drain.','','[CSV](table.csv) · [SVG](throughput.svg)','','![Throughput](throughput.png)','','| Workers | '+' | '.join(a+' Mops/s' for a in arms)+' |','| --- | '+' | '.join('---:' for a in arms)+' |']
 for n in COUNTS:
  cells=[]
  for arm in arms:
   found=[r for r in rows if r['arm']==arm and r['threads']==n]
   cells.append(f"{found[0]['ops_s']/1e6:.6f}" if found else 'pending')
  lines.append('| '+str(n)+' | '+' | '.join(cells)+' |')
 (out/'README.md').write_text('\n'.join(lines)+'\n')
def private(label,result):
 rows=[dict(threads=r['threads'],arm=r['arm'],ops_s=r['measurement']['whole_ops_s'],completed=r['measurement']['completed'],peak_status=r['measurement']['peak_status'],passed=r['passed'],drained=r['drained'],repeat=r['repeat']) for r in result['sessions']]
 title='Independent-mm mmap/munmap' if label=='mmap' else 'CPU fault cycles with private backing'
 detail=('Native mmap/munmap without page access; independent address spaces. No backing-lock operation.' if label=='mmap' else 'MADV_DONTNEED plus checked CPU read, including PTE reset. Native, KD and TCLock backing readers execute locally on the original task; this is not shared-mm writer delegation.')
 detail+=' Kernel `6.1.159-kdclobber2`; source `'+result['source_commit']+'`.'
 render(label,title,rows,['native'] if label=='mmap' else ['native','kdlock','tclock'],detail)
