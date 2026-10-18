#!/usr/bin/env python3
"""Audit and plot the frozen 198-session owned c01 study; no live execution."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import run
import mutex_study as study
from bench_runtime import FAULT, digest, require, validate_measurement
from session import tc_quiescent
from summarize import valid

THREADS = [*range(1, 9), *range(12, 65, 4)]
CPUS = [*range(32), *range(33, 65)]
ARMS = ('native', 'tclock', 'kdlock')
LABELS = dict(native='Linux Native', tclock='TCLock', kdlock='KD ABI4 / reuse 32')


def read(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()} for row in rows)


def log_counts(log, prefix):
    matches = re.findall(re.escape(prefix) + r' ([^\n]+)', log)
    require(len(matches) == 1, 'missing/duplicate drain receipt: ' + prefix)
    pairs = re.findall(r'(\w+)=(\d+)', matches[0])
    require(len(dict(pairs)) == len(pairs), 'duplicate drain counter')
    return {key: int(value) for key, value in pairs}


def audit_backend(folder, record, log):
    path = folder / record['name']
    completed = record['measurement']['completed']
    require(read(path / 'drain.counts.json')['active'] == 0, 'active workers after drain')
    if record['arm'] == 'native':
        require(record['jit_bodies'] == record['delegated_bodies'] == 0 and
                record['execution_class'] == 'NATIVE', 'Native classification differs')
        return
    if record['arm'] == 'tclock':
        for key in ('tclock_before', 'tclock_after', 'tclock_drained'):
            tc_quiescent(record[key], 'mutex')
            require(record[key]['target_lock'] == record['layout']['lock_addr'] and
                    record[key]['komb_batch_size'] == 1024, 'TCLock policy differs')
        before, after = record['tclock_before'], record['tclock_after']
        require(after == record['tclock_drained'] and
                all(after[key] >= before[key] for key in ('delegated', 'batches', 'parks')) and
                after['delegated'] - before['delegated'] == record['delegated_bodies'] and
                0 <= record['delegated_bodies'] <= completed and record['jit_bodies'] == 0 and
                record['delegation_share'] == record['delegated_bodies'] / completed,
                'TCLock delegation/drain differs')
        return
    require(record['mutex_implementation'] == 'owned-v1' and record['owned_mutex_cabi'] is True and
            record['owned_mutex_reuse_spins'] == 32 and record['mutex_routing'] == 'adaptive' and
            record['mutex_acceptance'] == 'adaptive-performance' and
            record['owned_queue_policy'] == 'finite_fifo' and not record['owned_mutex_refill'] and
            record['mutex_spin_limit'] == 4096 and record['numa_policy'] == 'on' and
            record['delegation_batch_limit'] == 1024 and record['kd_provider_ubsan'] == 'off',
            'KD acquisition/build/wait policy differs')
    study.require_owned_evidence(record, path)
    require(record['published_before'] == record['published_after'] and
            record['retired'] == dict(state=2, modules=0, frames=0, writers=0),
            'JIT publication changed or source did not retire')
    publication = record['published_before']
    entry = publication['entry']
    images = path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
    for name, expected in publication['images'].items():
        require(digest(images / name) == expected, 'JIT image changed: ' + name)
    require(record['jit_after'] - record['jit_before'] == record['jit_bodies'] and
            0 <= record['jit_bodies'] <= completed and
            record['jit_share'] == record['jit_bodies'] / completed and
            record['delegated_bodies'] == record['jit_bodies'], 'returned JIT body count differs')
    for key in ('result_schedule_calls', 'result_wakes', 'gate_wait_calls'):
        require(record['mutex_wait_after'][key] - record['mutex_wait_before'][key] ==
                record['mutex_wait_delta'][key] >= 0, 'wait counter difference differs')
    require(record['mutex_wait_delta']['gate_wait_calls'] == 0, 'owned request used legacy gate')
    stats = log_counts(log, 'kd_mutex stats:')
    tasks = log_counts(log, 'kd_mutex tasks:')
    acks = log_counts(log, 'kd_native stats:')
    require(stats['active_waiters'] == stats['reserved_nodes'] == stats['frame_failure'] == 0 and
            stats['origin_acquires'] == stats['origin_releases'] and tasks['active_tasks'] == 0 and
            acks['started'] == acks['completed'], 'owner/queue/task/frame/ACK did not drain')


def audit(folder):
    require(not (folder / 'failure.json').exists(), 'runner retained a failure')
    require((folder.parent / 'exit-status.txt').read_text().strip() == '0', 'runner did not exit successfully')
    control = folder.parent / 'control'
    expected_pins = {str(i): [i if i < 32 else 31 if i == 32 else i - 1 if i < 65 else 63]
                     for i in range(66)}
    for name in ('host-environment.json', 'host-final-state.json'):
        host = read(control / name)
        require({i: item['cpus'] for i, item in host['pins'].items()} == expected_pins and
                set(host['governors'].values()) == {'ondemand'} and
                host['workers'] == CPUS and host['collector'] == 65,
                'physical CPU pin/governor evidence differs')
    require('mutex-owned-c01-full66-20261014' in (control / 'snapshot-list.txt').read_text(),
            'recovery snapshot not present in monitor evidence')
    env = read(folder / 'environment.json')
    require(env['kernel_identity']['ok'] and
            env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus'] == list(range(66)) and
            env['collector_topology']['role_cpus'] == [65] and
            {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'] and
            env['snapshot_tag'] == 'mutex-owned-c01-full66-20261014', 'kernel/boot/topology differs')
    sources = read(folder / 'source-sha256.json')
    require(run.POST_WORK_SOURCE in sources and run.source_post_work_rounds(folder / 'source') == 64,
            'frozen workload is not post64')
    for name, expected in sources.items():
        require(digest(folder / 'source' / name) == expected, 'source changed: ' + name)
    final = read(folder.parent / 'final-state.json')
    require(final['idle'] and final['source_unchanged'] and final['binaries_unchanged'] and
            final['source_files'] == len(sources) and final['online_cpus'] == '0-65',
            'final guest idle/frozen-input check differs')
    binaries = read(folder / 'binary-sha256.json')
    for original, expected in binaries.items():
        path = (folder / 'variants' / original.split('/variants/', 1)[1]
                if '/variants/' in original else folder / 'binaries' / Path(original).name)
        require(digest(path) == expected, 'binary changed: ' + original)
    plan, aggregate = read(folder / 'plan.json'), read(folder / 'records.json')
    expected = [(t, r, arm) for t in THREADS for r in range(3)
                for arm in (ARMS[::-1] if r % 2 else ARMS)]
    require([(r['threads'], r['repeat'], r['arm']) for r in plan] == expected and
            len(aggregate) == len(expected) and len({r['name'] for r in plan}) == len(expected) and
            {r['name'] for r in aggregate} == {r['name'] for r in plan},
            '198-session grid/order differs')
    aggregate = {r['name']: r for r in aggregate}
    spec = importlib.util.spec_from_file_location('independent_full_export', ROOT / 'bench/full_compare/export.py')
    independent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(independent)
    records, hashes, geometry = [], {}, set()
    for item in plan:
        path = folder / item['name']
        record = read(path / 'session.json')
        require(all(record.get(k) == v for k, v in item.items()) and
                all(aggregate[item['name']].get(k) == v for k, v in record.items()) and
                aggregate[item['name']]['score_eligible'] is True and valid(record),
                'session/aggregate/acceptance differs: ' + item['name'])
        require(record['lock_kind'] == 'mutex' and record['cachelines'] == 1 and
                record['workload'] == 'cacheline' and record['scenario'] == 'plain' and
                record['post_work_rounds'] == 64 and record['cpus'] == CPUS[:record['threads']] and
                record['cpu_nodes'] == [int(cpu >= 33) for cpu in record['cpus']] and
                record['collector_cpu'] == 65 and record['duration_ms'] == 2000 and
                record['warmup_iterations_per_worker'] == 48000 and record['sample_ms'] == 10 and
                record['peak_window_ms'] == record['peak_settle_ms'] == 300 and
                not any(record.get(key, False) for key in
                        ('diagnostic', 'functional', 'pmu', 'profile_lock', 'perf_record')),
                'sample outside requested uninstrumented contract')
        raw = read(path / 'measure.json')
        peak = validate_measurement(raw, record, record['iterations'])
        require(dict(raw, peak=peak) == record['measurement'], 'raw measurement/peak differs')
        independent.independently_check_peak(record)
        log = (path / 'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault: ' + item['name'])
        audit_backend(folder, record, log)
        layout = record['layout']
        if record['arm'] != 'tclock':
            require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                    layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0,
                    'Native/KD object layout differs')
            geometry.add((layout['lock_addr'] - layout['data_addr'], layout['slots'],
                          tuple(address - layout['data_addr'] for address in layout['slot_addr'])))
        hashes[item['name']] = {name: digest(path / name) for name in
                               ('session.json', 'measure.json', 'kernel.log', 'drain.counts.json')}
        records.append(record)
    require(len(geometry) == 1, 'Native/KD lock/payload placement differs')
    require(all(a['measurement']['finished_ns'] < b['measurement']['started_ns']
                for a, b in zip(records, records[1:])), 'measurement order differs')
    receipt = dict(passed=True, samples=len(records), source_files=len(sources), binaries=len(binaries),
                   raw_sha256=hashes, manifest_sha256={name: digest(folder / name) for name in
                   ('environment.json', 'plan.json', 'source-sha256.json', 'binary-sha256.json')},
                   control_sha256={p.name: digest(p) for p in sorted(control.iterdir()) if p.is_file()},
                   final_state_sha256=digest(folder.parent / 'final-state.json'),
                   auditor_sha256=digest(Path(__file__)), validator_sha256={str(p.relative_to(ROOT)): digest(p)
                   for p in (ROOT / 'bench/full_compare/export.py', ROOT / 'bench/tclock_compare/mutex_study.py',
                             ROOT / 'bench/tclock_compare/session.py', ROOT / 'bench/spin_cacheline/bench_runtime.py')})
    return records, receipt


def export(records, output):
    samples, workers, stats, comparisons = [], [], [], []
    for record in records:
        m = record['measurement']
        row = dict(name=record['name'], arm=record['arm'], threads=record['threads'], repeat=record['repeat'],
                   whole_ops_s=m['completed'] * 1e9 / m['wall_ns'], peak_ops_s=m['peak']['throughput_ops_s'],
                   worker_cpu_ns_per_op=m['worker_cpu_ns'] / m['completed'],
                   worker_cpu_equivalents=m['worker_cpu_ns'] / m['wall_ns'],
                   jit_bodies=record['jit_bodies'], jit_share=record.get('jit_share', 0),
                   delegated_bodies=record['delegated_bodies'],
                   delegated_share=record['delegated_bodies'] / m['completed'],
                   execution_class=record.get('execution_class', record.get('delegation_status')),
                   completed=m['completed'], post_work_rounds=64, collector_cpu=65,
                   physical_collector_shared=record['threads'] == 64,
                   cpus=record['cpus'], cpu_nodes=record['cpu_nodes'])
        samples.append(row)
        workers.extend(dict(name=record['name'], arm=record['arm'], threads=record['threads'],
                            repeat=record['repeat'], cpu=w['cpu'], completed=w['completed'],
                            share=w['completed'] / m['completed']) for w in m['workers'])
    for count in THREADS:
        for arm in ARMS:
            selected = [r for r in samples if r['threads'] == count and r['arm'] == arm]
            row = dict(threads=count, arm=arm, samples=len(selected), post_work_rounds=64,
                       physical_collector_shared=count == 64)
            for key in ('whole_ops_s', 'peak_ops_s', 'worker_cpu_ns_per_op', 'jit_share', 'delegated_share'):
                values = [r[key] for r in selected]
                for label, fn in (('min', min), ('median', statistics.median), ('max', max)):
                    row[key + '_' + label] = fn(values)
                row[key + '_spread_pct'] = ((max(values) - min(values)) / statistics.median(values) * 100
                                           if statistics.median(values) else None)
            shares = [w['share'] for w in workers if w['threads'] == count and w['arm'] == arm]
            row.update(worker_share_min=min(shares), worker_share_max=max(shares),
                       execution_classes=[r['execution_class'] for r in selected],
                       jit_bodies_total=sum(r['jit_bodies'] for r in selected))
            stats.append(row)
        cohort = {r['arm']: r for r in stats if r['threads'] == count}
        comparison = dict(threads=count, physical_collector_shared=count == 64)
        for arm in ARMS:
            comparison[arm + '_whole_mops_s'] = cohort[arm]['whole_ops_s_median'] / 1e6
            comparison[arm + '_peak_mops_s'] = cohort[arm]['peak_ops_s_max'] / 1e6
        comparison.update(kd_native_whole_ratio=cohort['kdlock']['whole_ops_s_median'] / cohort['native']['whole_ops_s_median'],
                          kd_native_peak_ratio=cohort['kdlock']['peak_ops_s_max'] / cohort['native']['peak_ops_s_max'])
        comparison['meets_97_in_this_block'] = min(comparison['kd_native_whole_ratio'], comparison['kd_native_peak_ratio']) >= .97
        comparisons.append(comparison)
    for name, rows in (('samples', samples), ('workers', workers), ('statistics', stats), ('comparison', comparisons)):
        write_csv(output / (name + '.csv'), rows)
    return stats, comparisons


def plot(stats, output, originals):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import xml.etree.ElementTree as ET
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none', 'svg.hashsalt': 'kd-owned-c01-full-20261014'})
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    colors = dict(native='#626973', tclock='#0072B2', kdlock='#D55E00')
    x = list(range(len(THREADS)))
    for ax, metric, title in zip(axes, ('whole', 'peak'), ('Median whole-run throughput', 'Best valid warmed peak')):
        ax.axvspan(13.5, 21.5, color='#f2f4f7', zorder=0)
        ax.axvline(21, color='#b85b5b', linestyle=':', linewidth=1)
        for arm in ARMS:
            rows = sorted((r for r in stats if r['arm'] == arm), key=lambda r: r['threads'])
            field = metric + '_ops_s_' + ('median' if metric == 'whole' else 'max')
            ax.plot(x, [r[field] / 1e6 for r in rows], marker='o', markersize=3.5,
                    color=colors[arm], label=LABELS[arm], linewidth=1.6)
            ax.fill_between(x, [r[metric + '_ops_s_min'] / 1e6 for r in rows],
                            [r[metric + '_ops_s_max'] / 1e6 for r in rows], color=colors[arm], alpha=.12)
        ax.set(title=title, xlabel='Workers (sampled counts)', xticks=x, xticklabels=THREADS,
               xlim=(-.5, 21.5), ylim=(0, None))
        ax.tick_params(axis='x', labelsize=8)
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Throughput (Mops/s)')
    fig.suptitle('One shared cacheline · post-work 64 · 3 rounds per backend', y=.99)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=3, frameon=False, bbox_to_anchor=(.5, .05))
    fig.text(.5, .02, 'Bands: observed min–max. Gray: workers span NUMA nodes. At 64 workers, collector shares a physical core.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .14, 1, .95))
    fig.savefig(output / 'throughput.png', dpi=170)
    fig.savefig(output / 'throughput.svg', metadata={'Date': None})
    svg = output / 'throughput.svg'
    original = svg.read_text()
    normalized = '\n'.join(line.rstrip() for line in original.splitlines()) + '\n'
    def elements(text):
        return [(element.tag, sorted((key, ' '.join(value.split())) for key, value in element.attrib.items()),
                 (element.text or '').strip(), (element.tail or '').strip())
                for element in ET.fromstring(text).iter()]
    require(elements(original) == elements(normalized), 'SVG normalization changed elements/path tokens')
    originals.mkdir(parents=True, exist_ok=True)
    original_path = originals / 'throughput.original.svg'
    original_path.write_text(original)
    svg.write_text(normalized)
    write_json(output / 'plot-receipt.json', dict(matplotlib=matplotlib.__version__,
        original_svg_sha256=digest(original_path), normalized_svg_sha256=digest(svg),
        png_sha256=digest(output / 'throughput.png'), elements_and_path_tokens_unchanged=True,
        original_archive_path='plot-artifacts/throughput.original.svg'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True, help='frozen runner output directory')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--plots', action='store_true')
    args = p.parse_args()
    records, receipt = audit(args.raw.resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    stats, comparisons = export(records, args.out)
    receipt.update(threads=THREADS, collector_cpu=65, worker_cpus=CPUS,
                   kd_jit_sessions=sum(r['arm'] == 'kdlock' and r['jit_bodies'] > 0 for r in records),
                   comparison_blocks=1, full_scope_acceptance=False,
                   counts_meeting_97_in_this_block=[r['threads'] for r in comparisons if r['meets_97_in_this_block']],
                   limitations=['One descriptive three-round block, not two fresh confirmation blocks.',
                                '66-vCPU topology remains separate from prior 64-vCPU studies.',
                                'At 64 workers the collector shares physical core 63 with the last worker.',
                                'No hardware-counter diagnostics or ownership-streak measurements in this run.'])
    write_json(args.out / 'verification.json', receipt)
    if args.plots:
        plot(stats, args.out, args.raw.resolve().parent / 'plot-artifacts')
    print(json.dumps({key: receipt[key] for key in ('passed', 'samples', 'kd_jit_sessions', 'counts_meeting_97_in_this_block')}))


if __name__ == '__main__':
    main()
