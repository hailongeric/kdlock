#!/usr/bin/env python3
"""Audit and export the frozen 189-session c01 rerun; no live execution."""
import argparse
import importlib.util
import os
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(os.environ.get('KDLOCK_AUDIT_SOURCE') or Path(__file__).resolve().parents[6])
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import run
from bench_runtime import FAULT, digest, require, validate_measurement
from summarize import valid

THREADS = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
COMMIT = '5b50a4afb1d0c948227497ac9a15eb0f69f4a83c'
SNAPSHOT = 'mutex-numa-c01-rerun-20261015'
LABELS = dict(native='Linux Native', tclock='TCLock', kdlock='KD NUMA')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


# Reuse backend/drain checks only, without the historical grid or topology.
previous = module('rerun_backend_checks', ROOT /
                  'bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/analyze.py')
independent = module('rerun_peak_check', ROOT / 'bench/full_compare/export.py')
read, write_json, write_csv = previous.read, previous.write_json, previous.write_csv


def audit(container):
    folder, control = container / 'matrix', container / 'control'
    require((container / 'exit-status.txt').read_text().strip() == '0' and
            not (folder / 'failure.json').exists(), 'failed or partial run')
    identity = read(container / 'source-identity.json')
    require(identity['commit'] == COMMIT and
            digest(container / 'source-5b50a4a.tar') == identity['archive_sha256'],
            'committed source archive identity differs')
    for name, sha in identity['manifest'].items():
        require(digest(container / 'source' / name) == sha, 'committed file changed: ' + name)
    before, final = read(control / 'guest-before.json'), read(control / 'guest-final.json')
    boot = read(control / 'boot-policy.json')
    require(before['passed'] and before['idle'] and before['kernel_identity']['ok'] and
            final['passed'] and final['idle'] and final['source_unchanged'] and
            final['binaries_unchanged'] and not final['project_modules'] and
            before['boot_id'] == final['boot_id'] == boot['boot_id'] and
            boot['method'] == 'live_pv_ops_two_function_pointers' and
            final['online_cpus'] == '0-63' and '(voluntary)' in final['preemption'],
            'preflight or final drain differs')
    hosts = [read(control / name) for name in ('host-before.json', 'host-final.json')]
    require(hosts[0]['created'] and hosts[0]['qemu_pid'] == hosts[1]['qemu_pid'],
            'snapshot or VM process identity differs')
    for host in hosts:
        require(host['passed'] and host['snapshot_tag'] == SNAPSHOT and
                SNAPSHOT in host['snapshot_listing'] and
                {i: v['affinity'] for i, v in host['vcpus'].items()} ==
                {str(i): [i] for i in range(64)} and
                all(v['affinity'] == [63] for v in host['service_threads']) and
                set(host['governors'].values()) == {'ondemand'}, 'host placement/policy differs')
    env = read(folder / 'environment.json')
    require(env['kernel_identity']['ok'] and env['kernel_identity']['running_build_id'] ==
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus'] == list(range(64)) and
            env['collector_topology']['role_cpus'] == [63] and
            {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'] and env['snapshot_tag'] == SNAPSHOT,
            'kernel/boot/topology differs')
    sources, binaries = read(folder / 'source-sha256.json'), read(folder / 'binary-sha256.json')
    require(run.source_post_work_rounds(folder / 'source') == 64 and
            final['source_files'] == len(sources), 'frozen post-work/source count differs')
    for name, sha in sources.items():
        require(digest(folder / 'source' / name) == digest(container / 'source' / name) == sha,
                'frozen source changed: ' + name)
    for original, sha in binaries.items():
        path = (folder / 'variants' / original.split('/variants/', 1)[1]
                if '/variants/' in original else folder / 'binaries' / Path(original).name)
        require(digest(path) == sha, 'binary changed: ' + original)
    plan, aggregate = read(folder / 'plan.json'), read(folder / 'records.json')
    expected = [(t, r, arm) for t in THREADS for r in range(3)
                for arm in (ARMS[::-1] if r % 2 else ARMS)]
    # The live runner adds observed NUMA placement after dry-run planning.
    dry_plan = [dict(r, cpu_nodes=[int(cpu >= 32) for cpu in r['cpus']])
                for r in read(control / 'plan.json')]
    require(plan == dry_plan and
            [(r['threads'], r['repeat'], r['arm']) for r in plan] == expected and
            len(aggregate) == len(expected) == len({r['name'] for r in aggregate}) and
            {r['name'] for r in plan} == {r['name'] for r in aggregate},
            '189-session grid/order/coverage differs')
    aggregate = {r['name']: r for r in aggregate}
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
                r['collector_cpu'] == 63 and not r['collector_shared'] and
                r['duration_ms'] == 2000 and r['warmup_iterations_per_worker'] == 48000 and
                r['sample_ms'] == 10 and r['peak_window_ms'] == r['peak_settle_ms'] == 300 and
                not any(r.get(k, False) for k in
                        ('diagnostic', 'functional', 'pmu', 'profile_lock', 'perf_record')),
                'sample outside the requested contract')
        raw = read(path / 'measure.json')
        require(dict(raw, peak=validate_measurement(raw, r, r['iterations'])) == r['measurement'],
                'raw measurement/peak differs')
        validate_measurement(read(path / 'warmup.json'), dict(r, duration_ms=0), 48000)
        independent.independently_check_peak(r)
        log = (path / 'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault: ' + r['name'])
        previous.audit_backend(folder, r, log)
        if r['arm'] == 'kdlock':
            require(r['entry_abi'] == 4 and r['owned_mutex_origin_spin'] is True and
                    r['owned_mutex_numa'] is True, 'KD policy differs')
            delta = dict(zip(('claims', 'claim_failures', 'preparations', 'bypasses', 'bodies'),
                             [b-a for a, b in zip(r['origin_before'], r['origin_after'])]))
            require(len(r['origin_before']) == len(r['origin_after']) == 5 and
                    r['origin_delta'] == delta and min(delta.values()) >= 0 and
                    delta['claims'] == delta['claim_failures'] == delta['preparations'] == 0 and
                    delta['bodies'] == r['jit_bodies'],
                    'GS-independent c01 origin accounting differs')
            require(r['threads'] == 1 or r['jit_bodies'] > 0,
                    'multithreaded KD session lacks returned JIT bodies')
        if r['arm'] != 'tclock':
            layout = r['layout']
            require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                    layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0, 'layout differs')
            geometry.add((layout['lock_addr'] - layout['data_addr'], layout['slots'],
                          tuple(a-layout['data_addr'] for a in layout['slot_addr'])))
        hashes[r['name']] = {name: digest(path / name) for name in
                            ('session.json', 'measure.json', 'warmup.json', 'kernel.log', 'drain.counts.json')}
        records.append(r)
    require(len(geometry) == 1, 'Native/KD payload placement differs')
    require(all(a['measurement']['finished_ns'] < b['measurement']['started_ns']
                for a, b in zip(records, records[1:])), 'actual execution order differs')
    require(not FAULT.search((control / 'kernel-final.log').read_text()), 'final kernel fault')
    return records, dict(passed=True, sessions=len(records), source_commit=COMMIT,
        source_files=len(sources), committed_files=len(identity['manifest']), binaries=len(binaries),
        raw_sha256=hashes, auditor_sha256=digest(Path(__file__)),
        manifests={name: digest(folder / name) for name in
                   ('environment.json', 'plan.json', 'records.json', 'source-sha256.json', 'binary-sha256.json')},
        controls={p.name: digest(p) for p in sorted(control.iterdir()) if p.is_file()},
        validators={str(p.relative_to(ROOT)): digest(p) for p in
                    (Path(previous.__file__), Path(independent.__file__),
                     ROOT / 'bench/tclock_compare/mutex_study.py', ROOT / 'bench/tclock_compare/session.py',
                     ROOT / 'bench/spin_cacheline/bench_runtime.py')})


def export(records, output):
    samples, workers, groups, comparisons = [], [], {}, []
    for r in records:
        m = r['measurement']
        row = dict(name=r['name'], arm=r['arm'], threads=r['threads'], repeat=r['repeat'],
                   whole_ops_s=m['completed'] * 1e9 / m['wall_ns'], peak_ops_s=m['peak']['throughput_ops_s'],
                   worker_cpu_ns_per_op=m['worker_cpu_ns'] / m['completed'],
                   worker_cpu_equivalents=m['worker_cpu_ns'] / m['wall_ns'],
                   completed=m['completed'], jit_bodies=r['jit_bodies'], jit_share=r.get('jit_share', 0),
                   delegated_bodies=r['delegated_bodies'], delegated_share=r['delegated_bodies']/m['completed'],
                   execution_class=r.get('execution_class', r.get('delegation_status')),
                   parks=None if r['arm'] == 'native' else r.get('mutex_wait_delta', {}).get(
                       'result_schedule_calls', r.get('tclock_after', {}).get('parks', 0) -
                       r.get('tclock_before', {}).get('parks', 0)),
                   **{k: r.get('origin_delta', {}).get(k) for k in
                      ('claims', 'claim_failures', 'preparations', 'bypasses', 'bodies')})
        samples.append(row)
        groups.setdefault((r['threads'], r['arm']), []).append(row)
        workers.extend(dict(name=r['name'], arm=r['arm'], threads=r['threads'], repeat=r['repeat'],
            cpu=w['cpu'], node=r['cpu_nodes'][i], completed=w['completed'], cpu_ns=w['cpu_ns'],
            share=w['completed']/m['completed']) for i, w in enumerate(m['workers']))
    scores = {}
    for (count, arm), rows in groups.items():
        best = max(rows, key=lambda r: r['peak_ops_s'])
        score = dict(threads=count, arm=arm, samples=len(rows),
                     median_whole_ops_s=statistics.median(r['whole_ops_s'] for r in rows),
                     best_peak_ops_s=best['peak_ops_s'], peak_session_whole_ops_s=best['whole_ops_s'],
                     best_session=best['name'])
        for metric in ('whole_ops_s', 'peak_ops_s', 'worker_cpu_ns_per_op', 'worker_cpu_equivalents',
                       'jit_share', 'delegated_share'):
            values = [r[metric] for r in rows]
            for label, fn in (('min', min), ('median', statistics.median), ('max', max)):
                score[metric + '_' + label] = fn(values)
            score[metric + '_spread_pct'] = ((max(values)-min(values))/statistics.median(values)*100
                                           if statistics.median(values) else None)
        for metric in ('completed', 'jit_bodies', 'delegated_bodies', 'parks', 'claims',
                       'claim_failures', 'preparations', 'bypasses', 'bodies'):
            values = [r[metric] for r in rows]
            score[metric + '_total'] = None if any(v is None for v in values) else sum(values)
        cohort = [w for w in workers if (w['threads'], w['arm']) == (count, arm)]
        score.update(worker_progress_min=min(w['completed'] for w in cohort),
                     worker_share_min=min(w['share'] for w in cohort),
                     worker_share_max=max(w['share'] for w in cohort))
        scores[count, arm] = score
    for count in THREADS:
        comparison = dict(threads=count)
        for metric in ('median_whole_ops_s', 'best_peak_ops_s', 'peak_session_whole_ops_s'):
            for arm in ARMS:
                comparison[arm + '_' + metric] = scores[count, arm][metric]
            for baseline in ('native', 'tclock'):
                comparison['kd_over_' + baseline + '_' + metric] = (
                    scores[count, 'kdlock'][metric] / scores[count, baseline][metric])
        comparisons.append(comparison)
    for name, rows in (('samples', samples), ('workers', workers),
                       ('statistics', list(scores.values())), ('comparisons', comparisons)):
        write_csv(output / (name + '.csv'), rows)
    write_json(output / 'comparisons.json', comparisons)
    return list(scores.values())


def plot(scores, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype': 'none', 'svg.hashsalt': SNAPSHOT, 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), sharey=True)
    for ax, metric, title in zip(axes, ('median_whole_ops_s', 'best_peak_ops_s'),
                                ('Median whole-run throughput', 'Best valid warmed peak')):
        ax.axvspan(13.5, 20.5, color='#eeeeee', label='Workers span both NUMA nodes')
        for arm, color in zip(ARMS, ('#626973', '#0072B2', '#D55E00')):
            rows = sorted((r for r in scores if r['arm'] == arm), key=lambda r: r['threads'])
            ax.plot(range(len(rows)), [r[metric]/1e6 for r in rows], color=color, marker='o',
                    markersize=3, linewidth=1.5, label=LABELS[arm])
        ax.set(title=title, xlabel='Workers (sampled counts)', xticks=range(len(THREADS)),
               xticklabels=THREADS, xlim=(-.4, 20.4), ylim=(0, None))
        ax.tick_params(axis='x', labelsize=8)
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Million operations / second')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False, fontsize=9)
    fig.suptitle('Mutex c01 / post64 · 3 fresh rounds · KD owned ABI4 / reuse 32 / NUMA · separate collector CPU 63')
    fig.tight_layout(rect=(0, .08, 1, .94))
    fig.savefig(output / 'throughput.svg', metadata={'Date': None})
    path = output / 'throughput.svg'
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
    fig.savefig(output / 'throughput.png', dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records, receipt = audit(args.raw)
    scores = export(records, args.output)
    write_json(args.output / 'verification.json', receipt)
    if args.plot:
        plot(scores, args.output)
    print(f"Verified {len(records)} sessions; {len(scores)} three-round cohorts.")


if __name__ == '__main__':
    main()
