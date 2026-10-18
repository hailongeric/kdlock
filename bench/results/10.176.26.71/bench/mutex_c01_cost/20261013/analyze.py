#!/usr/bin/env python3
"""Offline audit/tables for the frozen c01 cost study; starts no workloads."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import statistics as st
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import mutex_study as study
from bench_runtime import digest, require, validate_measurement, FAULT
from summarize import valid, write_json


def csv_write(path, rows):
    with path.open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def frozen(folder):
    sources = json.loads((folder/'source-sha256.json').read_text())
    for name, sha in sources.items():
        require(digest(folder/'source'/name) == sha, 'source changed: '+name)
    binaries = json.loads((folder/'binary-sha256.json').read_text())
    for name, sha in binaries.items():
        path = (folder/'variants'/name.split('/variants/', 1)[1]
                if '/variants/' in name else folder/'binaries'/Path(name).name)
        require(digest(path) == sha, 'binary changed: '+name)
    return dict(source_manifest_sha256=digest(folder/'source-sha256.json'),
                binary_manifest_sha256=digest(folder/'binary-sha256.json'),
                environment_sha256=digest(folder/'environment.json'),
                plan_sha256=digest(folder/'plan.json'),
                source_files=len(sources), binaries=len(binaries))


def diagnostics(folder):
    frozen(folder)
    env = json.loads((folder/'environment.json').read_text())
    require(env['kernel_identity']['ok'] and
            env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960',
            'diagnostic kernel identity differs')
    rows = json.loads((folder/'records.json').read_text())
    plan = json.loads((folder/'plan.json').read_text())
    require(len(rows) == len(plan) == 18, 'incomplete diagnostic series')
    for r, spec in zip(rows, plan):
        require(all(r[k] == v for k, v in spec.items()), 'diagnostic differs from plan')
        require(valid(r) and r['diagnostic'] and not r['score_eligible'], 'invalid diagnostic')
        require(r['cpus'] == list(range(r['threads'])) and r['collector_cpu'] == 63 and
                r['cachelines'] == 1 and r['duration_ms'] == 2000 and
                r['warmup_iterations_per_worker'] == 48000, 'diagnostic geometry differs')
        p = folder/r['name']
        raw = json.loads((p/'measure.json').read_text())
        peak = validate_measurement(raw, r, r['iterations'])
        require(dict(raw, peak=peak) == r['measurement'], 'raw diagnostic data differs')
        require(not FAULT.search((p/'kernel.log').read_text()), 'diagnostic kernel error')
        if r['arm'] == 'kdlock':
            require(r['retired'] == dict(state=2, modules=0, frames=0, writers=0) and
                    r['published_before'] == r['published_after'] and
                    r['jit_after'] - r['jit_before'] == r['jit_bodies'], 'diagnostic JIT/drain differs')
            pub = r['published_before']
            images = p/'workspace/daemon'/hex(pub['entry']['entry'])/str(pub['entry']['tgid'])/'asm'
            for name, sha in pub['images'].items():
                require(digest(images/name) == sha, 'diagnostic JIT image changed')
    return rows


def statistics(rows, group):
    by = defaultdict(list)
    for r in rows:
        by[r['threads'], r['arm']].append(r)
    result = []
    for (threads, arm), cohort in sorted(by.items()):
        m = study.metrics(cohort)
        r = dict(group=group, threads=threads, arm=arm,
                 whole_min_mops=min(m['whole_rates'])/1e6,
                 whole_median_mops=m['median_whole']/1e6,
                 whole_max_mops=max(m['whole_rates'])/1e6,
                 whole_spread_pct=m['whole_spread_pct'],
                 peak_min_mops=min(m['peak_rates'])/1e6,
                 peak_median_mops=st.median(m['peak_rates'])/1e6,
                 peak_best_mops=m['best_peak']/1e6,
                 peak_spread_pct=m['peak_spread_pct'],
                 cpu_ns_per_op_median=st.median(m['worker_cpu_ns_per_op']),
                 worker_share_min=m['worker_share_min'], worker_share_max=m['worker_share_max'],
                 largest_worker_share_median=st.median(max(w['completed'] for w in x['measurement']['workers'])/
                                                     x['measurement']['completed'] for x in cohort),
                 jit_bodies_min=min(m['jit_bodies']), jit_share_median=st.median(m['jit_shares']),
                 delegation_share_median=st.median(x.get('delegation_share', 0) for x in cohort),
                 execution_classes=';'.join(m['execution_classes']))
        result.append(r)
    return result


def plot_statistics(rows, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    series = [('baseline', 'native', 'Linux baseline', '#1675a9'),
              ('baseline', 'tclock', 'TCLock baseline', '#b45231'),
              ('baseline', 'kdlock', 'KD baseline', '#43833c'),
              ('full-grid', 'kdlock', 'KD retained', '#773a96')]
    for group, arm, label, color in series:
        cohort = sorted((r for r in rows if r['group'] == group and r['arm'] == arm),
                        key=lambda r: r['threads'])
        if not cohort:
            continue
        x = [r['threads'] for r in cohort]
        for ax, metric in zip(axes, ('whole_median_mops', 'peak_best_mops')):
            ax.plot(x, [r[metric] for r in cohort], '.-', label=label, color=color)
        axes[0].fill_between(x, [r['whole_min_mops'] for r in cohort],
                            [r['whole_max_mops'] for r in cohort], color=color, alpha=.10)
    for ax, title in zip(axes, ('Median whole run; shading = observed round range',
                               'Best valid warmed peak; 300 ms window')):
        ax.set(title=title, xlabel='Workers', ylabel='Mops/s', ylim=(0, 16))
        ax.grid(alpha=.2)
        ax.axvline(32.5, color='gray', linestyle=':', linewidth=1)
        ax.set_xticks([1, 8, 16, 28, 36, 48, 60])
    axes[1].legend(loc='upper right', fontsize=9)
    fig.suptitle('c01: one increment, 64 post-work rounds, 3 rounds; ondemand governor')
    fig.savefig(out/'throughput.svg', metadata={'Date': None})
    svg = out/'throughput.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def validation(raw, out):
    tests = raw.parent.parent/'tests'/raw.name
    retained = json.loads((tests/'retained-checks.json').read_text())
    previous = json.loads((tests/'final-checks.json').read_text())
    measured = json.loads((raw/'full-grid/source-sha256.json').read_text())
    require(retained['passed'] and retained['drained'], 'retained validation incomplete')
    for name, sha in measured.items():
        if name.startswith(('include/', 'kernel_module/')) and (
                Path(name).suffix in ('.c', '.h', '.inc', '.S') or Path(name).name == 'Makefile'):
            require(retained['sources'][name] == sha, 'tested provider differs from measured provider')
    require(digest(tests/'kdlock-retained-normal.ko') == retained['normal_module_sha256'],
            'normal tested module changed')
    require('Unit tests: 6 passed, 0 failed' in (tests/'unit-retained.log').read_text(),
            'retained affected checks failed')
    require('Unit tests: 14 passed, 0 failed' in (tests/'unit-final.log').read_text(),
            'prefetch-only unit checks failed')
    require('Ran 55 tests' in (tests/'runner.log').read_text() and
            (tests/'runner.log').read_text().strip().endswith('OK'), 'runner checks failed')
    probes = {}
    for name in ('wait-retained', 'task-retained'):
        folder = tests/name
        identity = json.loads((folder/'identity.json').read_text())
        require(digest(folder/'kdlock_km.ko') == identity['module_sha256'], 'probe module changed')
        require(json.loads((folder/'baseline.json').read_text())['ok'], 'probe kernel mismatch')
        for source, sha in json.loads((folder/'sources.json').read_text()).items():
            require(digest(folder/'source'/source) == sha and retained['sources'][source] == sha,
                    'probe source differs from retained source')
        for log in folder.rglob('kernel.log'):
            require(not FAULT.search(log.read_text()), 'retained probe kernel error')
        result = json.loads((folder/'result.json').read_text())
        require(result['passed'] and result['drained'], 'retained probe failed')
        probes[name] = dict(identity=identity, result=result, source_manifest_sha256=digest(folder/'sources.json'))
    host = json.loads((raw/'final-host-state.json').read_text())
    require(host['verified'], 'final host state not verified')
    postflight = json.loads((raw/'postflight.json').read_text())
    require(postflight['idle'] and postflight['possible_cpus'] == postflight['online_cpus'] == '0-63',
            'postflight guest state differs')
    logs = ['unit-retained.log', 'build-retained.log', 'retained-runtime.dis',
            'unit-final.log', 'runner.log', 'unit-resource-retry.log', 'unit-capacity-retry.log']
    write_json(out/'validation.json', dict(
        execution_host='recovery VM on 10.176.26.71', snapshot='mutex-c01-cost-20261013',
        starting_commit='33fde04', retained_provider_matches_measured_full_grid=True,
        retained_normal_module_sha256=retained['normal_module_sha256'],
        retained_source_manifest_sha256=digest(tests/'retained-checks.json'),
        retained_units=dict(basic=2, affected=retained['python_groups'], passed=6),
        prefetch_only_units=dict(basic=2, affected=previous['python_groups'], passed=14,
                                scope='separate rejected variant; includes unchanged admission/ABI/frame checks'),
        runner_tests=55, live_probes=probes,
        build_policy='normal and SELFTEST W=1 UBSAN_SANITIZE=n; existing objtool warnings retained',
        final_host_state_sha256=digest(raw/'final-host-state.json'),
        final_guest_state=postflight, source_retirement_drained=True,
        logs={name: digest(tests/name) for name in logs},
        failures_retained=[
            'Initial static per-CPU counter allocation exceeded the module reserved area; load failed before init. Dynamic allocation replaced it.',
            'Initial resource fixture signedness warning failed compilation; corrected and rerun.',
            'Execution-capacity fixture lacked the opaque wait_queue_head_t type; corrected and rerun.',
            'First perf sample export lacked a recorded CPU field; cleanup succeeded. Separate retry added --sample-cpu.',
            'Duplicate inline annotation removed. inline-code.json compares unlike build configurations and is not optimization evidence.'
        ],
        limits=['97% primary Native parity not reached; no parity confirmation blocks',
                'No full suite, other payload acceptance, or 64-worker topology test',
                'Profiling rates excluded; generic misses do not isolate coherence; frequency not fixed']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--runs', nargs='+', default=['baseline', 'waiter-screen', 'successor-screen',
                                               'prefetch-screen', 'full-grid', 'prefetch-only-grid'])
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    runs, receipts, stats, batches = {}, {}, [], []
    for name in args.runs:
        folder = args.raw/name
        rows = runs[name] = study.load_run(folder)
        receipts[name] = dict(**frozen(folder), sessions=len(rows), scored=True,
                             correct=True, every_worker_progress=True, drained=True)
        stats += statistics(rows, name)
        for r in rows:
            require(not FAULT.search((folder/r['name']/'kernel.log').read_text()),
                    'kernel error in scored session')
            if r['arm'] == 'native':
                continue
            row = dict(group=name, sample=r['name'], threads=r['threads'], arm=r['arm'],
                       completed=r['measurement']['completed'], returned_bodies=r['delegated_bodies'],
                       share=r['delegation_share'], batches=None, bodies_per_batch=None,
                       batch_scope='measurement', result_schedule_calls=None, gate_wait_calls=None)
            if r['arm'] == 'tclock':
                row['batches'] = r['tclock_after']['batches'] - r['tclock_before']['batches']
                row['bodies_per_batch'] = r['delegated_bodies']/row['batches'] if row['batches'] else None
                row['result_schedule_calls'] = r['tclock_after']['parks'] - r['tclock_before']['parks']
            else:
                log = (folder/r['name']/'kernel.log').read_text()
                require(not FAULT.search(log), 'kernel error in scored session')
                line, = [s for s in log.splitlines() if 'kd_mutex stats:' in s]
                counts = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
                require(counts['active_waiters'] == counts['reserved_nodes'] == counts['frame_failure'] == 0,
                        'KD balances/frame failed')
                require(counts['origin_acquires'] == counts['origin_releases'], 'physical owner imbalance')
                row.update(batches=counts['combiner'], batch_scope='lifetime_including_warmup',
                           bodies_per_batch=counts['jit_success']/counts['combiner'] if counts['combiner'] else None,
                           result_schedule_calls=r['mutex_wait_delta']['result_schedule_calls'],
                           gate_wait_calls=r['mutex_wait_delta']['gate_wait_calls'])
            batches.append(row)
    csv_write(args.out/'statistics.csv', stats)
    csv_write(args.out/'batches-and-waits.csv', batches)
    plot_statistics(stats, args.out)
    audits = {name: study.evaluate(runs['baseline'], rows) for name, rows in runs.items() if name != 'baseline'}
    write_json(args.out/'acceptance.json', dict(target_reached=False, retained_threshold=256,
        retained_implementation='full-grid: waiter counters + deferred selection + staged prefetch',
        retained_scope='bounded higher-thread improvement; not primary Native parity',
        confirmation_blocks=[], trials=audits))
    pmu, profiles = [], []
    for group in ('cpu-samples-retry', 'pmu'):
        folder = args.raw/group
        rows = diagnostics(folder)
        receipts[group] = dict(**frozen(folder), sessions=len(rows), scored=False,
                               correct=True, every_worker_progress=True, drained=True)
        for r in rows:
            path = folder/r['name']
            if group == 'pmu':
                events = {}
                for line in (path/'pmu.csv').read_text().splitlines():
                    fields = line.split(';')
                    if len(fields) > 4:
                        require(float(fields[4]) == 100, 'PMU multiplexed/unsupported')
                        events[fields[2]] = float(fields[0])
                require(len(events) == 6, 'missing PMU events')
                n = r['measurement']['completed']
                pmu.append(dict(threads=r['threads'], arm=r['arm'],
                    whole_mops=n*1e3/r['measurement']['wall_ns'],
                    delegation_share=r['delegation_share'],
                    cycles_per_op=events['cycles']/n, instructions_per_op=events['instructions']/n,
                    cache_misses_per_op=events['cache-misses']/n,
                    cpu_ns_per_op=r['measurement']['worker_cpu_ns']/n,
                    context_switches=events['context-switches'], migrations=events['cpu-migrations'],
                    effective_ghz=events['cycles']/events['task-clock']/1e6, running_pct=100))
            else:
                report = (path/'perf-report.txt').read_text()
                require('# Total Lost Samples: 0' in report, 'lost CPU samples')
                require('PERF_RECORD_LOST' not in (path/'perf-samples.txt').read_text(), 'lost raw samples')
                for line in report.splitlines():
                    m = re.match(r'\s*(\d+\.\d+)%\s+(\S+)\s+(\S+)\s+\[k\]\s+(\S+)', line)
                    if m:
                        profiles.append(dict(threads=r['threads'], arm=r['arm'], percent=float(m[1]),
                                             command=m[2], dso=m[3], symbol=m[4], lost_samples=0))
    csv_write(args.out/'pmu.csv', pmu)
    csv_write(args.out/'cpu-profiles.csv', profiles)
    write_json(args.out/'coverage.json', dict(runs=receipts,
        complete_sessions=sum(r['sessions'] for r in receipts.values()),
        diagnostic_sessions=36, performance_sessions=sum(len(r) for r in runs.values()),
        excluded_partial='cpu-samples: first sample export failed; 17 later samples unrun; normal cleanup',
        source_identity_note='Manifest hashes identify exact working bytes; variants and failed candidates remain archived.'))
    artifacts = sorted(p for p in args.raw.iterdir() if p.is_file() and
                       (p.name.endswith(('.tar.gz', '.patch')) or
                        p.name in ('preflight-snapshot.log', 'final-host-state.json', 'postflight.json')))
    index = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in artifacts}
    test_archive = args.raw.parent.parent/'tests'/(args.raw.name+'.tar.gz')
    if test_archive.exists():
        index['../../tests/'+test_archive.name] = dict(bytes=test_archive.stat().st_size,
                                                     sha256=digest(test_archive))
        validation(args.raw, args.out)
    write_json(args.out/'artifacts.json', index)
    print(json.dumps({k: (v['verdict'], [(c['threads'], c['passed']) for c in v['checks']])
                      for k, v in audits.items()}))


if __name__ == '__main__':
    main()
