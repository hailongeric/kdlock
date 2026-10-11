"""Render the audited mutex-only matrix and retain historical comparison."""
import argparse, collections, csv, json, shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--no-plots',action='store_true');a=p.parse_args()
out=a.input;stats=json.loads((out/'final-statistics.json').read_text());allstats=json.loads((out/'statistics.json').read_text());comparisons=json.loads((out/'comparison.json').read_text());verification=json.loads((out/'verification.json').read_text())
previous=json.loads(a.previous.read_text())
labels={'native':'Native','tclock':'TCLock','kdlock':'KD'}
idx={(r['group'].split('/')[-1],r['threads'],r['arm']):r for r in stats}
oldidx={(r['group'],r['threads'],r['arm']):r for r in previous}
rate=lambda v:f'{v/1e6:.3f}' if v is not None else '—'
pct=lambda v:f'{100*(v-1):+.1f}%'
rows=[]
for (g,t,arm),r in idx.items():
 if arm!='kdlock':continue
 old=oldidx[(g,t,arm)]
 row=dict(group=g,threads=t,old_peak_median=old['peak_median_ops_s'],new_peak_median=r['peak_median_ops_s'],old_whole_median=old['whole_median_ops_s'],new_whole_median=r['whole_median_ops_s'])
 row['whole_ratio']=row['new_whole_median']/row['old_whole_median'] if r['complete'] else None
 row['peak_ratio']=row['new_peak_median']/row['old_peak_median'] if r['complete'] else None
 rows.append(row)
with (out/'before-after.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'before-after.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
shutil.copyfile(a.previous,out/'previous-full-statistics.json')

if not a.no_plots:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
 colors={'native':'#626973','tclock':'#0072B2','kdlock':'#D55E00'}
 for group,title in [('mutex-cacheline-c01','Mutex c01'),('mutex-rcuht','Mutex hash')]:
  fig,axes=plt.subplots(1,2,figsize=(13,4.7))
  for ax,field,metric,heading in zip(axes,['whole_median_ops_s','best_peak_ops_s'],['whole','peak'],['Median whole-run throughput','Highest valid warmed peak']):
   ax.axvspan(32.5,66,color='#F2F4F7',zorder=0);ax.axvline(32.5,color='#88919D',ls=':',lw=1)
   for arm in ('native','tclock','kdlock'):
    data=sorted((r for r in stats if r['group'].endswith(group) and r['arm']==arm),key=lambda r:r['threads'])
    x=[r['threads'] for r in data]; y=[r[field]/1e6 if r['complete'] else float('nan') for r in data]
    low=[r[metric+'_min_ops_s']/1e6 if r['complete'] else float('nan') for r in data]; high=[r[metric+'_max_ops_s']/1e6 if r['complete'] else float('nan') for r in data]
    ax.plot(x,y,color=colors[arm],marker='o',ms=3,label=labels[arm],lw=1.7)
    ax.fill_between(x,low,high,color=colors[arm],alpha=.11)
    if arm=='kdlock':
     for r,xx,yy in zip(data,x,y):
      if r['execution_type'] in ('NO_JIT','MIXED'):ax.plot(xx,yy,marker='o',mfc='white',mec=colors[arm],ms=5)
   old=sorted((r for r in previous if r['group']==group and r['arm']=='kdlock'),key=lambda r:r['threads'])
   ax.plot([r['threads'] for r in old],[r[field]/1e6 for r in old],color='#A5683F',ls='--',lw=1,label='KD before')
   ax.set(title=heading,xlabel='Workers',ylabel='Mops/s',xlim=(0,66),ylim=(0,None));ax.set_xticks([1,8,16,24,32,40,48,56,64]);ax.grid(axis='y',alpha=.25)
  fig.suptitle(title+' · 10.176.26.71',fontsize=17,x=.065,ha='left')
  handles,names=axes[0].get_legend_handles_labels();fig.legend(handles,names,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.04))
  fig.text(.065,.018,'3 rounds; shading = min–max. 32 worker cores/node; worker 64 shares a physical core with collection. Open KD marker = NO_JIT/mixed.',fontsize=8)
  fig.tight_layout(rect=(0,.12,1,.95))
  for ext in ('png','svg','pdf'):fig.savefig(out/(group+'.'+ext),dpi=160)
  plt.close(fig)

multi=[r for r in comparisons if r['threads']>1]
lines=['# KD mutex c01 optimization on 10.176.26.71','',
 'The selected changes reduce coordination overhead and cross-NUMA owner movement. **KD still does not match both Native and TCLock at every multithreaded point.** The tables below state the remaining gaps; neither JIT execution nor an improved historical score establishes parity.','',
 f"The final comparison contains **{verification['final_sessions']} drained timed sessions**, **{verification['final_accepted']} accepted**: c01 and hash, Native/TCLock/KD, three rounds at all 22 worker counts from 1–64. Strict comparison uses both highest valid warmed peak and median whole-run throughput. Multithreaded point statuses: `{verification['final_multithread_statuses']}`. These are descriptive three-round comparisons, not confidence intervals.",'',
 '![c01 scaling](mutex-cacheline-c01.png)','',
 '## Causes and selected changes','',
 '1. **Per-acquisition task-record churn.** The opening code allocates a candidate and takes a bucket writer lock for each admitted acquisition, then removes the record on the final put. The selected cache reuses task identities through RCU and atomic exact reference counts. Zero references disable routing immediately. Up to eight identities per bucket remain cached; live acquisitions may temporarily exceed that bound. Eviction uses a zero-to-minus-one CAS, with actual task release after an RCU grace period. This removes repeated allocation/callback work without extending acquisition ownership.','',
 '2. **Polling coherence and cross-NUMA handoff.** Polling formerly shared a line with ABI/result metadata. Completion bytes now use the existing node tail at offsets 304/305/306; minimal packet and metadata writes use different lines. The node remains 320 bytes. FIFO execution also moved packet/body working state between sockets. Bounded local selection defers only fully linked nodes: 64-node scan budget, 128-body local cohort boundary, default 1024-body total cap. Deferred requests receive priority at the boundary. A remote cohort smaller than eight is serviced by the current owner; larger cohorts receive physical handoff. For the 32+4-worker case, avoiding an owner move for four requests was material.','',
 '3. **A widened retirement load.** Disassembly and the separate event profile found a compiler-generated 64-bit ABI/packet comparison overlapping the wrapper’s 32-bit packet-state store. Separate field-width `READ_ONCE` loads preserve the complete retirement predicate. The physical-owner predicate is also inlined without changing its Linux owner/flag mask.','',
 'The protected c01 body is very small, so queue publication, packet/frame preparation, validation, wakeup and pinned polling can cost more than Native’s local optimistic handoff. The selected changes reduce those costs; the remaining within-NUMA gap is consistent with this extra work. That is an architectural interpretation of the measured execution paths, not a precise per-instruction latency attribution. No kernel, governor, payload, admission predicate, owner proof, source lease, final ACK or wrapper ABI was weakened.','',
 '## Current comparison','',
 'Rates are Mops/s. Each table cell is **best warmed peak / median whole-run**. A complete point has three valid rounds for each backend. Full min/median/max/spread, execution types and worker/node progress are in the CSV files. Blank scores indicate incomplete acceptance rather than an estimated result.','']
for group,title in [('mutex-cacheline-c01','c01'),('mutex-rcuht','Hash')]:
 lines += ['### '+title,'','| Workers | Native | TCLock | KD | KD / Native whole | Strict target |','| --- | --- | --- | --- | --- | --- |']
 for t in sorted({r['threads'] for r in stats}):
  arms={arm:idx[(group,t,arm)] for arm in labels}; comp=next(r for r in comparisons if r['group'].endswith(group) and r['threads']==t)
  scores=[f"{rate(arms[arm]['best_peak_ops_s'])} / {rate(arms[arm]['whole_median_ops_s'])}" if arms[arm]['complete'] else 'incomplete' for arm in labels]
  ratio=f"{arms['kdlock']['whole_median_ops_s']/arms['native']['whole_median_ops_s']:.3f}×" if arms['kdlock']['complete'] and arms['native']['complete'] else '—'
  lines.append('| '+str(t)+' | '+' | '.join(scores)+' | '+ratio+' | '+comp['status']+' |')
 lines += ['']
 if title=='Hash':lines+=['![hash scaling](mutex-rcuht.png)','']
# Keep session-lifetime batching distinct from the measured JIT-share delta.
final_samples=json.loads((out/'final-samples.json').read_text())
lines += ['## Remaining c01 bottleneck and worker progress','',
 'At four workers, the measured JIT share is 47–75%, with 4.395 Mops/s median whole-run throughput. Session-lifetime observations (including warmup) show only 4.8–16.2 successful bodies per combiner, versus 892–972 at sixteen workers. Short batches repeatedly pay physical acquisition and queue/frame setup. The selected runtime still has that mixed native/delegation bottleneck; relative to the earlier full matrix, c01 whole-run throughput fell 44.4% at three workers and 6.3% at four workers. Hash at 40 workers fell 4.7%. The earlier three-worker c01 peak spread was 51.2%, so a historical median difference alone cannot isolate source effects from run variability. These measured regressions remain unresolved and are not evidence of universal improvement.','',
 '| c01 workers | Lowest node-1 share of a valid peak | Lowest worker whole-run operations |','| --- | --- | --- |']
for t in (36,40,44,48,52,56,60,64):
 rr=[r for r in final_samples if r['group'].endswith('mutex-cacheline-c01') and r['arm']=='kdlock' and r['threads']==t and r['accepted']]
 lines.append(f"| {t} | {100*min(r['peak_node_share']['1'] for r in rr):.2f}% | {min(r['min_worker_whole_ops'] for r in rr):,} |")
lines += ['', 'All workers made progress in each accepted peak window and over the complete run. Positive counts and bounded within-batch bypass do not prove starvation freedom. Node shares are observed work distribution, not scheduling guarantees.','']
lines += ['## Before and after','',
 'The dashed plot uses the earlier `full-matrix-20261011T025525Z` KD results on the same temporary 66-vCPU geometry and payload settings. These historical samples are not pooled with the new matrix. Host frequency policy stayed `ondemand`; time-dependent frequency/load differences remain possible, which is why the final run includes fresh Native and TCLock controls. Normal 64-vCPU screening stages are separate from both full matrices.','',
 '| Payload | Workers | Previous KD whole | Current KD whole | Change |','| --- | --- | --- | --- | --- |']
for r in rows:
 if r['threads'] in (2,3,4,8,16,32,36,40,60,64):lines.append(f"| {r['group']} | {r['threads']} | {rate(r['old_whole_median'])} | {rate(r['new_whole_median'])} | {pct(r['whole_ratio']) if r['whole_ratio'] else 'incomplete'} |")
lines += ['','## Candidate screening and diagnostics','',
 'All screening used the regular 64-vCPU VM, collector 63, and only c01/hash. Each timed configuration used three rounds. Group identities remain separate in `statistics.csv`; earlier partial candidates and rejected variants are retained with their exact source/ELF/JIT hashes. The frozen group source is authoritative when a saved patch contains only one component of a candidate.','',
 '| Candidate groups | Decision and reason |','| --- | --- |',
 '| `membership-c01` | Reject sharded waiter-count traffic change: no repeatable gain. |',
 '| `layout-c01` | Keep completion/metadata separation as part of the selected layout. |',
 '| `state-words-c01` | Reject packed/wider state comparisons: c01 slowed. |',
 '| `numa128-c01`, `numa128-inline-c01` | Keep bounded NUMA selection; reject executor inlining. Later refine small-remote-cohort service. |',
 '| `task-cache-c01` | Keep bounded RCU task-identity reuse with exact active references. |',
 '| `lookahead4-c01` | Reject four-successor lookahead; cross-NUMA c01 slowed. Keep unchanged-owner predicate inline. |',
 '| `packet-prefetch-c01/hash`, `stack-prefetch-hash` | Packet-only prefetch helped some c01 points but hurt hash. Restore successor SP/SP-8 hints. |',
 '| `field-width-c01/hash` | Keep separate ABI/packet retirement loads. |',
 '| `cohort-floor-c01/hash` | Keep current-owner service for fewer than eight deferred remote requests. |',
 '| `frame-reuse-c01/hash` | Reject frame-header reuse flag: c01 regressed substantially. Restore full initialization. |',
 '| `batch16-c01/hash` | Reject cap 16: cross-NUMA throughput fell. Default remains 1024; built mutex-cap metadata is now verified. |',
 '| `cohort4-c01/hash`, `cohort2-c01/hash` | Reject capped queue admission/native fallback: some c01 gains, but hash and high-worker c01 regressed. |',
 '| `result-layout-c01/hash` | Reject moving packet-state into the polling tail. |',
 '| `late-retry-c01/hash` | Reject extra native retry after heat admission: unstable low-worker routing and poor four-worker c01. |','',
 'PMU runs are diagnostics, excluded from all throughput comparisons. Counters ran without multiplexing (100% enabled/running time). Aggregate events include polling workers and client overhead; dividing by completed operations is not serial critical-section latency.','',
 '| Diagnostic | KD store-forwarding blocks/op | KD store-buffer stall events/op |','| --- | --- | --- |']
for d in json.loads((out/'diagnostics.json').read_text()):
 if d['group'] in ('packet-prefetch-pmu','final-pmu') and 'kdlock' in d['name']:
  c=d['per_completed_op'];lines.append(f"| {d['group']} | {c['ld_blocks.store_forward']:.4f} | {c['resource_stalls.sb']:.2f} |")
lines += ['','The forwarding event fell sharply; total store-buffer stalls did not. The earlier store-buffer event profile had zero lost samples and concentrated at the post-comparison instruction, but skid and other changed components prevent an exact causal partition. Its hardware event used fixed period 100003 and a sample format the profile parser rejected. The original failed session remains unchanged; `parser-recovery-2` separately validates client results, stable publication, returned JIT bodies, source retirement and clean unload. It is a recovered diagnostic, never a performance score.','',
 '## Validation','',
 '- Selected source: two basic programs plus mutex resource, task-cache, terminal, outer-progress and execution-capacity drivers: **7 passed, 0 failed**. Production-code fixtures cover delayed links, refusal rejoin, immediate native reuse, early release, scan/cohort bounds and exact retirement checks; existing mutation checks remain enabled.',
 '- Live cross-NUMA task/ACK probe on CPUs 0,32,33: **two unlock orders, four ACKs, two actual RCU deferred frees**; three-worker × 4096-iteration cache stress checks three reused identities and their actual final frees. This probe executes no JIT bodies.',
 '- Four directly affected benchmark interface/provider/mandatory-JIT/UBSAN-metadata tests passed. Additional ABI/clobber and packet checks from the component trials remain in the raw logs.',
 f"- Final matrix: **{verification['final_sessions']} drained**, **{verification['final_accepted']} accepted**; KD acceptance includes **{verification['final_kd_jit']} ACTUAL_JIT** and **{verification['final_kd_no_jit']} NO_JIT** sessions. NO_JIT controls do not prove delegation gain. Full status-separated aggregates are retained.",
 '- No full test-suite rerun. The maintained benchmark supplies plain mutex JIT; nested/early mutex transitions are covered by production-code fixtures and the real owner/ACK probe, not a new live nested JIT workload. These checks do not prove starvation freedom or every concurrent schedule.','',
 '## Reproduction and evidence','',
 'Host: `10.176.26.71`; captured guest `6.1.159-kdclobber2`, `nopvspin`, `nokaslr`, voluntary preemption, original mitigations. Final workers: guest 0–31,33–64 → physical cores 0–63; collector 65 → physical 63. **At 64 workers, the collector and QEMU services share the last worker’s physical core.** The normal boot has 64 vCPUs; screening used workers from 0–61 and collector 63. No cross-topology pooling.','',
 'Each session uses 48,000 warmup operations per worker, 2,000 ms measurement, a 300 ms peak window after 300 ms settling, and the existing 64 post-work arithmetic rounds. All cacheline payloads use c01. c02/c08/c16 were never run. Mutex JIT stays enabled and existing returned-body acceptance remains enforced.','',
 'The benchmark/test archives retain the original generated report. The separately hashed final-report archive adds the restoration receipt, offline replay result and explicit regression discussion; its scored audit CSV files are unchanged.\n\nThe final source starts at `33b65ce` with the selected runtime/test changes and the same nine pre-existing working-tree edits captured at task start. `control/final-source-approved.json`, `final-source-working-tree.patch` and each group’s frozen source/binary manifests identify measured bytes. Documentation edits made during the run were not synchronized into the running inputs.','',
 '- [Every timed session](samples.csv) and [all screening statistics](statistics.csv)',
 '- [Final comparison samples](final-samples.csv), [final statistics](final-statistics.csv), [execution-status statistics](statistics-by-execution.csv), [strict comparison ratios](comparison.csv)',
 '- [Before/after data](before-after.csv), [PMU/profile diagnostics](diagnostics.json), [independent verification](verification.json), [captured environment](environment.json)',
 '- [Raw archive receipts](archives.json), [offline archive replay](archive-validation.json), [normal VM restoration](vm-restoration.json)',
 '- Portable audit: `python3 audit.py --root EXTRACTED/bench/mutex-opt-20261011T045425Z --output REPLAY`; it hashes frozen inputs and retained ELF/JIT files, independently recomputes warmed peaks, checks raw client totals/placement/progress and source retirement, and keeps the failed diagnostic distinct.',
 '- Plots are available as PNG, SVG and PDF beside this report. `publish.py` consumes audited JSON and `previous-full-statistics.json`; report rendering ran in the guest.','']
(out/'README.md').write_text('\n'.join(lines))
shutil.copyfile(__file__,out/'publish.py')
print(json.dumps(dict(published=str(out),comparisons=len(comparisons),multithread_statuses=verification['final_multithread_statuses'])))
