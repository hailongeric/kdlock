#!/usr/bin/env python3
"""Offline raw-evidence audit for the c01 optimistic-spin experiment."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import statistics as st
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT/'bench/tclock_compare'))
import mutex_study as study
from bench_runtime import digest, require, FAULT
from summarize import write_json


def csv_write(path, rows):
    with path.open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def audit(folder):
    rows = study.load_run(folder)
    for row in rows:
        log = (folder/row['name']/'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault in '+str(folder))
        if row['arm'] == 'kdlock':
            line, = [s for s in log.splitlines() if 'kd_mutex stats:' in s]
            counts = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
            require(counts['active_waiters'] == counts['reserved_nodes'] == counts['frame_failure'] == 0,
                    'incomplete KD drain or frame failure')
            require(counts['origin_acquires'] == counts['origin_releases'], 'owner imbalance')
    return rows


def elf_sections(path):
    data = path.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'expected little-endian ELF64')
    offset = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 58)
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset+i*stride) for i in range(count)]
    header = headers[names_index]
    names = data[header[4]:header[4]+header[5]]
    return {names[h[0]:].split(b'\0', 1)[0].decode():
            (h[2], data[h[4]:h[4]+h[5]]) for h in headers if h[1] != 8}


def validation(raw, out):
    tests = raw.parent.parent/'tests'/raw.name
    archive = tests.with_suffix('.tar.gz')
    require('Unit tests: 10 passed, 1 failed' in (tests/'unit-initial.log').read_text(),
            'initial development receipt differs')
    require('Unit tests: 1 passed, 0 failed' in (tests/'unit-resource-retry.log').read_text(),
            'resource fixture retry failed')
    require('Unit tests: 2 passed, 0 failed' in (tests/'unit-osq.log').read_text() and
            '11 optimistic retry/OSQ decision mutations rejected' in (tests/'unit-osq.log').read_text(),
            'OSQ decision fixture failed')
    require('Unit tests: 3 passed, 0 failed' in (tests/'unit-retained.log').read_text(),
            'retained drain fixture failed')
    for name in ('runner.log', 'runner-osq.log'):
        log = (tests/name).read_text()
        require('Ran 62 tests' in log and log.strip().endswith('OK'), 'runner checks failed')
    for name, folder in (('unit-sources.json', 'unit-source'),
                         ('retained-sources.json', 'retained-source')):
        for source, sha in json.loads((tests/name).read_text()).items():
            require(digest(tests/folder/source) == sha, 'test source changed')
    candidate = json.loads((raw/'osq-64/source-sha256.json').read_text())
    baseline = json.loads((raw/'baseline/source-sha256.json').read_text())
    retained = json.loads((raw/'retained-check/source-sha256.json').read_text())
    provider = {name: sha for name, sha in baseline.items()
                if name.startswith(('include/', 'kernel_module/')) and
                (Path(name).suffix in ('.c', '.h', '.inc', '.S') or Path(name).name == 'Makefile')}
    for name, sha in provider.items():
        require(retained[name] == sha, 'accepted provider differs from baseline')
    for name, sha in json.loads((tests/'retained-sources.json').read_text()).items():
        if name in retained:
            require(retained[name] == sha, 'retained code differs from its tested bytes')
    checks = audit(raw/'retained-check')
    require(len(checks) == 3 and {r['arm'] for r in checks} == {'native', 'tclock', 'kdlock'},
            'retained three-backend check incomplete')
    require(all(r['threads'] == 16 and r['repeat'] == 0 for r in checks), 'retained check geometry differs')
    kd, = [r for r in checks if r['arm'] == 'kdlock']
    require(kd['jit_bodies'] > 0 and 'mutex_optimistic_spin_limit' not in kd['parameters'] and
            'mutex_optimistic_osq' not in kd['parameters'], 'rejected provider still active')
    probes = {}
    for name in ('wait-candidate', 'task-candidate'):
        folder = tests/name
        identity = json.loads((folder/'identity.json').read_text())
        result = json.loads((folder/'result.json').read_text())
        require(digest(folder/'kdlock_km.ko') == identity['module_sha256'], 'probe binary changed')
        require(result['passed'] and result['drained'], 'live protocol probe failed')
        require(json.loads((folder/'baseline.json').read_text())['ok'], 'probe kernel mismatch')
        for source, sha in json.loads((folder/'sources.json').read_text()).items():
            require(digest(folder/'source'/source) == sha, 'probe source changed')
            if source in provider or source == 'kernel_module/lock/mutex_optimistic.inc':
                require(candidate[source] == sha, 'probe source differs from screened candidate')
        for log in folder.rglob('kernel.log'):
            require(not FAULT.search(log.read_text()), 'probe kernel error')
        probes[name] = dict(identity=identity, result=result,
                           source_manifest_sha256=digest(folder/'sources.json'))
    postflight = json.loads((tests/'postflight.json').read_text())
    require(postflight['idle'] and postflight['online_cpus'] == postflight['possible_cpus'] == '0-63',
            'final guest not idle or topology changed')
    require(json.loads((raw/'host-postflight.json').read_text())['verified'], 'host placement changed')
    restored_sections = json.loads((raw/'restored-provider-sections.json').read_text())
    before = elf_sections(raw/'baseline/binaries/kdlock_km.ko')
    after = elf_sections(raw/'retained-check/binaries/kdlock_km.ko')
    differing = [n for n in sorted(before.keys() | after.keys()) if before.get(n) != after.get(n)]
    require(differing == restored_sections['different_sections'] == ['.BTF'] and
            not ((before['.BTF'][0] | after['.BTF'][0]) & 2), 'restored executable differs')
    require(restored_sections['all_allocatable_section_bytes_equal'] and
            restored_sections['different_sections'] == ['.BTF'], 'restored executable sections differ')
    write_json(out/'validation.json', dict(starting_provider='9b7671984cc9adadc5cd94e698ac9b80c3b3b6d6',
        rejected_candidate='260d330f7e0f58e2d894e5e7ba4bfed0a3244850',
        rejected_tag='archive/perf/mutex-optimistic-c01-20261013',
        execution_host='recovery VM on 10.176.26.71', snapshot='mutex-optimistic-c01-20261013',
        performance_sessions=369, candidate_primary_acceptance=False, confirmation_blocks=[],
        candidate_units=dict(basic=2, affected=9, passed_after_fixture_correction=True,
                             osq_mutations=11, runner_and_auditor_tests=62),
        retained_units=dict(basic=2, affected=1, configurations=['OSQ enabled', 'OSQ disabled']),
        retained_provider_matches_baseline=True, compared_provider_files=len(provider),
        restored_provider_sections=restored_sections,
        retained_live_checks=dict(sessions=3, counts=[16], repeats=1, scored=False,
            returned_kd_jit=kd['jit_bodies'], correct=True, every_worker_progress=True, drained=True,
            source_manifest_sha256=digest(raw/'retained-check/source-sha256.json'),
            binary_manifest_sha256=digest(raw/'retained-check/binary-sha256.json')),
        probes=probes, probe_retry_setting='default disabled; constructed protocol checks, no JIT',
        final_guest=postflight, final_host_sha256=digest(raw/'host-postflight.json'),
        tests_archive=dict(path=str(archive.resolve().relative_to(ROOT)), sha256=digest(archive), bytes=archive.stat().st_size),
        test_logs={p.name:digest(p) for p in sorted(tests.glob('*.log'))},
        unit_source_manifest_sha256=digest(tests/'unit-sources.json'),
        retained_source_manifest_sha256=digest(tests/'retained-sources.json'),
        development_failure='Resource fixture expected three native-return sites; new retry adds a fourth. Corrected and rerun; initial failure retained.',
        build_policy='candidate normal and SELFTEST W=1 UBSAN_SANITIZE=n; existing objtool warnings retained',
        limits=['All six primary screens fail; candidate counts 1,3,5,6,7,8,12,20,24,36,48 not screened',
                'No full suite, other-payload acceptance or 64-worker topology',
                'Frequency not fixed; low-thread variation prevents stable-gain claims',
                'No new PMU/ownership profile of the optimistic candidates']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--preview', type=Path, help='optional PNG rendering of the report figure')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    runs, coverage, statistics, samples, decisions = {}, {}, [], [], {}
    for name in ('baseline', 'spin-16', 'spin-64', 'spin-256', 'spin-1024', 'osq-64', 'osq-1024'):
        folder = args.raw/name
        rows = runs[name] = audit(folder)
        require(len(rows) == (153 if name == 'baseline' else 36), 'incomplete series')
        sources = json.loads((folder/'source-sha256.json').read_text())
        expected_limit = 0 if name == 'baseline' else int(name.split('-')[1])
        for r in rows:
            if r['arm'] == 'kdlock':
                require(r.get('mutex_optimistic_spin_limit', 0) == expected_limit and
                        r.get('mutex_optimistic_osq', False) == name.startswith('osq-'),
                        'retry policy differs from named series')
                require(int(r['parameters'].get('mutex_optimistic_spin_limit', '0')) == expected_limit and
                        r['parameters'].get('mutex_optimistic_osq', 'N') ==
                        ('Y' if name.startswith('osq-') else 'N'), 'loaded retry policy differs')
            measurement = r['measurement']
            shares = [w['completed']/measurement['completed'] for w in measurement['workers']]
            samples.append(dict(series=name, sample=r['name'], threads=r['threads'], arm=r['arm'],
                repeat=r['repeat'], retry_limit=r.get('mutex_optimistic_spin_limit', 0),
                osq=r.get('mutex_optimistic_osq', False),
                classification=r.get('execution_class', 'NATIVE' if r['arm'] == 'native' else 'TCLOCK'),
                whole_mops=measurement['completed']*1000/measurement['wall_ns'],
                peak_mops=measurement['peak']['throughput_ops_s']/1e6,
                cpu_ns_per_op=measurement['worker_cpu_ns']/measurement['completed'],
                min_worker_share=min(shares), max_worker_share=max(shares),
                returned_jit=r.get('jit_bodies', 0), delegation_share=r.get('delegation_share', 0),
                result_schedule_calls=r.get('mutex_wait_delta', {}).get('result_schedule_calls'),
                gate_wait_calls=r.get('mutex_wait_delta', {}).get('gate_wait_calls'),
                drained=r['drained']))
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['threads'], row['arm']].append(row)
        for (threads, arm), cohort in sorted(grouped.items()):
            m = study.metrics(cohort)
            statistics.append(dict(series=name, threads=threads, arm=arm,
                whole_min_mops=min(m['whole_rates'])/1e6,
                whole_median_mops=m['median_whole']/1e6,
                whole_max_mops=max(m['whole_rates'])/1e6,
                whole_spread_pct=m['whole_spread_pct'],
                peak_min_mops=min(m['peak_rates'])/1e6,
                peak_median_mops=st.median(m['peak_rates'])/1e6,
                peak_best_mops=m['best_peak']/1e6, peak_spread_pct=m['peak_spread_pct'],
                cpu_ns_per_op_median=st.median(m['worker_cpu_ns_per_op']),
                min_worker_share=m['worker_share_min'], max_worker_share=m['worker_share_max'],
                largest_worker_share_median=st.median(max(w['completed'] for w in r['measurement']['workers'])/
                    r['measurement']['completed'] for r in cohort),
                returned_jit_min=min(m['jit_bodies']), jit_share_median=st.median(m['jit_shares']),
                delegation_share_median=st.median(r.get('delegation_share', 0) for r in cohort),
                classifications=';'.join(sorted(set(m['execution_classes'])))))
        coverage[name] = dict(sessions=len(rows), correct=True, every_worker_progress=True,
            drained=True, source_files=len(sources), source_manifest_sha256=digest(folder/'source-sha256.json'),
            binary_manifest_sha256=digest(folder/'binary-sha256.json'),
            plan_sha256=digest(folder/'plan.json'), environment_sha256=digest(folder/'environment.json'),
            retry_limit=expected_limit, osq=name.startswith('osq-'))
        if name != 'baseline':
            decisions[name] = study.evaluate(runs['baseline'], rows)
    csv_write(args.out/'statistics.csv', statistics)
    csv_write(args.out/'samples.csv', samples)
    write_json(args.out/'coverage.json', coverage)
    require(all(d['verdict'] == 'REJECTED' for d in decisions.values()), 'review any passing candidate')
    require(len(samples) == 369, 'performance coverage differs')
    write_json(args.out/'acceptance.json', dict(target_reached=False, retained_ratio_limit=256,
        confirmation_blocks=[], candidates=decisions))
    artifacts = {str(p.relative_to(args.raw)): dict(bytes=p.stat().st_size, sha256=digest(p))
                 for p in sorted(args.raw.iterdir()) if p.is_file()}
    write_json(args.out/'artifacts.json', artifacts)
    validation(args.raw, args.out)
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.hashsalt'] = 'kdlock-optimistic-c01-20261013'
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    series = [('baseline', 'native', 'Linux baseline'), ('baseline', 'tclock', 'TCLock baseline'),
              ('baseline', 'kdlock', 'Current KD baseline'), ('spin-1024', 'kdlock', 'KD retries 1024'),
              ('osq-1024', 'kdlock', 'KD OSQ + retries 1024')]
    for name, arm, label in series:
        cohort = [r for r in statistics if (r['series'], r['arm']) == (name, arm)]
        if not cohort:
            continue
        for ax, metric in zip(axes, ('whole_median_mops', 'peak_best_mops')):
            ax.plot([r['threads'] for r in cohort], [r[metric] for r in cohort], '.-', label=label)
    for ax, title in zip(axes, ('Median whole run', 'Best valid warmed peak')):
        ax.set(title=title, xlabel='Workers', ylabel='Mops/s', ylim=(0, 15))
        ax.set_xticks([1, 4, 16, 28, 32, 36, 48, 60])
        ax.axvline(32.5, color='gray', linestyle=':', linewidth=1)
        ax.grid(alpha=.2)
    axes[1].legend(fontsize=8)
    fig.suptitle('c01 optimistic-spin screens: 3 rounds, 64 post-work rounds, ondemand')
    fig.savefig(args.out/'throughput.svg', metadata={'Date': None})
    if args.preview:
        fig.savefig(args.preview, dpi=140)
    path = args.out/'throughput.svg'
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
    print(json.dumps(dict(sessions=len(samples), decisions={k:v['verdict'] for k,v in decisions.items()})))


if __name__ == '__main__':
    main()
