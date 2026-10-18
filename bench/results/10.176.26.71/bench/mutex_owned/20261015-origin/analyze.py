#!/usr/bin/env python3
"""Audit archived origin/NUMA c01 blocks and export their separate gates.

No benchmark execution. Recheck raw business results, frozen inputs, placement,
returned-body and drain receipts, then recompute the observed warmed windows.
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get('KDLOCK_AUDIT_SOURCE', Path(__file__).resolve().parents[6]))
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import run
from bench_runtime import FAULT, digest, require, validate_measurement
from summarize import valid

THREADS = [*range(1, 9), *range(12, 65, 4)]
ARMS = ['native', 'tclock', 'current-kd', 'numa']
BASELINE = 'b994aefaaf4da8be7b18353fd130818df9b2aba2'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


# Reuse only unchanged backend/owner/ACK checks and serialization, never the
# historical 66-vCPU scope, ordering, scoring or snapshot checks.
previous = module('owned_origin_backend_checks', ROOT /
                  'bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/analyze.py')
read, write_json, write_csv = previous.read, previous.write_json, previous.write_csv


def independent_peak(record):
    m = record['measurement']
    start = max(w['active_started_ns'] for w in m['workers']) + m['peak_settle_ns']
    end = min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in m['workers']))
    points = [s for s in m['samples'] if s['started_ns'] >= start and s['finished_ns'] <= end]
    best = None
    for i, first in enumerate(points):
        for last in points[i + 1:]:
            elapsed = last['finished_ns'] - first['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            progress = [b - a for a, b in zip(first['completed'], last['completed'])]
            if min(progress) > 0:
                total = sum(progress)
                if best is None or total * best[1] > best[0] * elapsed:
                    best = total, elapsed
            break
    require(best is not None and math.isclose(best[0] * 1e9 / best[1],
            m['peak']['throughput_ops_s'], rel_tol=1e-12), 'independent warmed peak differs')


def audit(folder, baseline):
    require(not (folder / 'failure.json').exists(), 'failed or partial block: ' + str(folder))
    archived_plan = read(folder / 'plan.json')
    # Preserve archived experiments; report only the supported candidate and
    # its controls, retaining their original relative execution order.
    plan = [r for r in archived_plan if r['comparison_arm'] in ARMS]
    expected = [(t, repeat, arm) for t in THREADS for repeat in range(3)
                for arm in (ARMS[::-1] if repeat % 2 else ARMS)]
    require([(r['threads'], r['repeat'], r['comparison_arm']) for r in plan] == expected,
            'incomplete or reordered 22-count/three-round grid')
    env = read(folder / 'environment.json')
    require(env['kernel_identity']['ok'] and
            env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
            and env['topology']['online_cpus'] == list(range(64))
            and env['collector_topology']['role_cpus'] == [63]
            and {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split())
            and '(voluntary)' in env['preemption']
            and env['snapshot_tag'] == 'owned-origin-regular64-final-20261015',
            'kernel/boot/topology/recovery identity differs')
    sources = read(folder / 'source-sha256.json')
    require(run.source_post_work_rounds(folder / 'source') == 64, 'post-work changed')
    for name, sha in sources.items():
        require(digest(folder / 'source' / name) == sha, 'source changed: ' + name)
    for name, sha in read(folder / 'baseline-source-sha256.json').items():
        require(digest(baseline / name) == sha, 'baseline source changed: ' + name)
    binaries = read(folder / 'binary-sha256.json')
    for original, sha in binaries.items():
        path = (folder / 'variants' / original.split('/variants/', 1)[1]
                if '/variants/' in original else folder / 'binaries' / Path(original).name)
        require(digest(path) == sha, 'binary changed: ' + original)
    aggregate = {r['name']: r for r in read(folder / 'records.json')}
    require(len(aggregate) == len(archived_plan), 'aggregate coverage differs')
    records, hashes, geometry = [], {}, set()
    for spec in plan:
        path = folder / spec['name']
        r = read(path / 'session.json')
        require(all(r.get(k) == v for k, v in spec.items()) and valid(r) and
                aggregate[r['name']]['score_eligible'] and
                all(aggregate[r['name']].get(k) == v for k, v in r.items()),
                'session/aggregate/acceptance differs: ' + r['name'])
        require(r['lock_kind'] == 'mutex' and r['cachelines'] == 1 and
                r['workload'] == 'cacheline' and r['scenario'] == 'plain' and
                r['post_work_rounds'] == 64 and r['cpus'] == list(range(r['threads'])) and
                r['cpu_nodes'] == [int(cpu >= 32) for cpu in r['cpus']] and
                r['collector_cpu'] == 63 and r['collector_shared'] == (r['threads'] == 64) and
                r['duration_ms'] == 2000 and r['sample_ms'] == 10 and
                r['peak_window_ms'] == r['peak_settle_ms'] == 300 and
                r['warmup_iterations_per_worker'] == 48000 and
                not any(r.get(k, False) for k in ('diagnostic', 'functional', 'pmu', 'profile_lock', 'perf_record')),
                'sample outside the requested scored contract')
        raw = read(path / 'measure.json')
        require(dict(raw, peak=validate_measurement(raw, r, r['iterations'])) == r['measurement'],
                'raw accounting/window differs')
        validate_measurement(read(path / 'warmup.json'), dict(r, duration_ms=0), 48000)
        independent_peak(r)
        log = (path / 'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault in score')
        previous.audit_backend(folder, r, log)
        arm = r['comparison_arm']
        if arm == 'current-kd':
            require(r['baseline_commit'] == BASELINE and 'owned_mutex_origin_spin' not in r
                    and 'owned_mutex_numa' not in r, 'baseline policy differs')
            for original, sha in r['baseline_binary_sha256'].items():
                relative = original.split('/baseline/', 1)[1]
                require(digest(baseline / relative) == sha, 'baseline binary changed')
        elif arm == 'numa':
            require(r['owned_mutex_origin_spin'] is True and r['owned_mutex_numa'] is True,
                    'candidate policy differs')
            delta = dict(zip(('claims', 'claim_failures', 'preparations', 'bypasses', 'bodies'),
                             [b-a for a,b in zip(r['origin_before'], r['origin_after'])]))
            require(len(r['origin_before']) == len(r['origin_after']) == 5 and
                    r['origin_delta'] == delta and min(delta.values()) >= 0 and
                    delta['claims'] == delta['claim_failures'] == delta['preparations'] == 0,
                    'origin accounting differs for GS-independent c01')
        if r['arm'] != 'tclock':
            layout = r['layout']
            require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64, 'public layout changed')
            geometry.add((layout['lock_addr']-layout['data_addr'], layout['slots'],
                          tuple(a-layout['data_addr'] for a in layout['slot_addr'])))
        hashes[r['name']] = {name: digest(path / name) for name in
                            ('session.json', 'measure.json', 'warmup.json', 'kernel.log', 'drain.counts.json')}
        records.append(r)
    require(len(geometry) == 1, 'Native/KD payload geometry differs')
    require(all(a['measurement']['finished_ns'] < b['measurement']['started_ns']
                for a,b in zip(records, records[1:])), 'actual execution order differs')
    return records, dict(passed=True, sessions=len(records), source_files=len(sources),
        binaries=len(binaries), raw_sha256=hashes, candidate='numa',
        archived_sessions=len(archived_plan), omitted_sessions=len(archived_plan)-len(plan),
        manifests={name: digest(folder/name) for name in ('environment.json', 'plan.json',
                   'source-sha256.json', 'baseline-source-sha256.json', 'binary-sha256.json')})


def export(block, records, out):
    samples, workers, groups, comparisons = [], [], {}, []
    for r in records:
        m = r['measurement']
        row = dict(block=block, name=r['name'], arm=r['comparison_arm'], threads=r['threads'], repeat=r['repeat'],
                   collector_shared=r['collector_shared'], whole=m['completed']*1e9/m['wall_ns'],
                   peak=m['peak']['throughput_ops_s'], cpu_ns_per_op=m['worker_cpu_ns']/m['completed'],
                   completed=m['completed'], jit_bodies=r['jit_bodies'], jit_share=r.get('jit_share', 0),
                   delegated_bodies=r['delegated_bodies'], delegated_share=r['delegated_bodies']/m['completed'],
                   parks=None if r['arm']=='native' else r.get('mutex_wait_delta', {}).get('result_schedule_calls',
                       r.get('tclock_after', {}).get('parks',0)-r.get('tclock_before', {}).get('parks',0)),
                   **{k:r.get('origin_delta', {}).get(k) for k in ('claims','claim_failures','preparations','bypasses')})
        samples.append(row)
        groups.setdefault((row['threads'], row['arm']), []).append(row)
        workers.extend(dict(block=block, name=r['name'], arm=row['arm'], threads=row['threads'],
            repeat=row['repeat'], cpu=w['cpu'], completed=w['completed'], cpu_ns=w['cpu_ns'],
            share=w['completed']/m['completed']) for w in m['workers'])
    scores = {}
    for key, rows in groups.items():
        best = max(rows, key=lambda r:r['peak'])
        score = dict(threads=key[0], arm=key[1], median_whole=statistics.median(r['whole'] for r in rows),
                     best_peak=best['peak'], peak_session_whole=best['whole'], best_session=best['name'])
        for metric in ('whole','peak','cpu_ns_per_op','jit_share','delegated_share'):
            values = [r[metric] for r in rows]
            score[metric+'_range'] = [min(values),statistics.median(values),max(values)]
            score[metric+'_spread_pct'] = ((max(values)-min(values))/statistics.median(values)*100
                                           if statistics.median(values) else None)
        for metric in ('completed','jit_bodies','delegated_bodies','parks','claims','claim_failures','preparations','bypasses'):
            values = [r[metric] for r in rows]
            score[metric+'_total'] = None if any(v is None for v in values) else sum(values)
        cohort = [w for w in workers if (w['threads'], w['arm']) == key]
        score.update(worker_progress_min=min(w['completed'] for w in cohort),
                     worker_share_range=[min(w['share'] for w in cohort),max(w['share'] for w in cohort)])
        scores[key] = score
    for (count, arm), candidate in scores.items():
        if arm != 'numa':
            continue
        ratios = {metric:candidate[metric]/scores[count,'current-kd'][metric]
                  for metric in ('median_whole','best_peak','peak_session_whole')}
        native = {metric:candidate[metric]/scores[count,'native'][metric]
                  for metric in ('median_whole','best_peak','peak_session_whole')}
        comparisons.append(dict(threads=count, arm=arm, collector_shared=count==64,
            over_current_kd=ratios, regression_pass=min(ratios.values())>=.97,
            over_native=native, native_applicable=count<=8, native_pass=min(native.values())>=.97))
    target = out/block
    target.mkdir(exist_ok=True)
    for name, rows in (('samples',samples),('workers',workers),('statistics',list(scores.values()))):
        write_csv(target/(name+'.csv'),rows)
    write_json(target/'comparisons.json',comparisons)
    return comparisons


def plot(comparisons, out):
    """Separate block ratios, each using its own freshly measured KD control."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none', 'svg.hashsalt':'owned-origin-20261015', 'font.size':10})
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), sharey=True)
    colors = ['#0072B2','#D55E00','#009E73']
    series = [(block, arm, sorted((r for r in rows if r['arm']==arm), key=lambda r:r['threads']))
              for block, rows in comparisons.items() for arm in sorted({r['arm'] for r in rows})]
    for ax, metric, title in zip(axes, ('median_whole','best_peak'),
                                ('Median whole-run throughput','Best valid warmed peak')):
        ax.axhline(100, color='#999999', linewidth=.7)
        ax.axhline(97, color='#a33333', linestyle='--', linewidth=1, label='97% gate')
        ax.axvspan(20.6, 21.4, color='#eeeeee')
        for color, (block, arm, rows) in zip(colors, series):
            ax.plot(range(len(rows)), [100*r['over_current_kd'][metric] for r in rows],
                    color=color, marker='o', markersize=3, linewidth=1.3, label=f'{block} / {arm}')
        ax.set(title=title, xlabel='Workers (sampled counts)', xticks=range(len(THREADS)),
               xticklabels=[*map(str,THREADS[:-1]),'64*'], xlim=(-.4,21.4))
        ax.tick_params(axis='x',labelsize=8)
        ax.grid(axis='y',alpha=.2)
        ax.spines[['top','right']].set_visible(False)
    axes[0].set_ylabel('Percent of the same block\'s current-KD control')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=4,frameon=False,fontsize=9)
    fig.suptitle('c01 / post64 · independent three-round blocks · *64 workers share collector CPU 63')
    fig.tight_layout(rect=(0,.07,1,.94))
    fig.savefig(out/'regression.svg',metadata={'Date':None})
    svg = out/'regression.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    fig.savefig(out/'regression.png',dpi=120)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).parent)
    p.add_argument('--blocks', nargs='+', default=['screen64','confirm64-a','confirm64-b-clean'])
    p.add_argument('--plot', action='store_true', help='also export the separate-block regression figure')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipts, comparisons, identities = {}, {}, []
    for block in args.blocks:
        records, receipts[block] = audit(args.raw/block, args.raw/'baseline')
        comparisons[block] = export(block, records, args.output)
        identities.append(read(args.raw/block/'source-sha256.json'))
    require(all(identity == identities[0] for identity in identities), 'frozen inputs differ across blocks')
    write_json(args.output/'verification.json', dict(passed=True, blocks=receipts,
        auditor_sha256=digest(Path(__file__)), regression_metrics=['median_whole','best_peak','peak_session_whole'],
        note='Whole-run median and matching peak-session whole are both checked; blocks/topologies are never pooled.'))
    if args.plot:
        plot(comparisons, args.output)
    for block, rows in comparisons.items():
        for arm in sorted({r['arm'] for r in rows}):
            selected = [r for r in rows if r['arm']==arm]
            print(block,arm,'regression failures', [r['threads'] for r in selected if not r['regression_pass']],
                  'Native 1-8 failures',[r['threads'] for r in selected if r['native_applicable'] and not r['native_pass']])


if __name__ == '__main__':
    main()
