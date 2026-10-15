#!/usr/bin/env python3
"""Verify a completed, extracted rwlock run and export its measurements offline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
THREADS = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
RUN = 'rwlock-c01-grid-20261015'
GUEST = '/root/kdlock-evidence/10.176.26.71/bench/' + RUN


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path, help='extracted run directory')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    raw, out = args.raw.resolve(), args.output.resolve()
    sys.path.insert(0, str(raw / 'source/bench/rwlock_compare'))
    from oracle import validate, jit_evidence
    from parity import assess
    from bench_runtime import FAULT

    assert (raw.parent / (RUN + '.exit')).read_text().strip() == '0'
    assert not (raw / 'failure.json').exists()
    plan, records = read(raw / 'plan.json'), read(raw / 'records.json')
    expected = [(p, t, r, a) for p in (1, 20) for t in THREADS for r in range(3)
                for a in (ARMS[::-1] if r % 2 else ARMS)]
    assert [(s['write_percent'], s['threads'], s['repeat'], s['arm']) for s in plan] == expected
    assert len(records) == len(plan) == 378
    env = read(raw / 'environment.json')
    assert env['kernel_identity']['ok']
    assert env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
    assert env['topology']['online_cpus'] == list(range(64))
    assert {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split())
    assert '(voluntary)' in env['preemption'] and env['snapshot_tag'] == RUN
    sources, binaries = read(raw / 'source-sha256.json'), read(raw / 'binary-sha256.json')
    for name, sha in sources.items():
        assert digest(raw / 'source' / name) == sha, name
    for name, sha in binaries.items():
        assert name.startswith(GUEST + '/'), name
        assert digest(raw / name[len(GUEST) + 1:]) == sha, name

    samples, workers, groups, image_count = [], [], {}, 0
    for spec, aggregate in zip(plan, records):
        path = raw / spec['name']
        row = read(path / 'session.json')
        assert all(row[k] == v for k, v in spec.items())
        assert row['execution_status'] == 'OK' and row['drained'] is True
        assert row['lock_kind'] == 'rwlock' and row['cachelines'] == 1
        assert row['cpus'] == list(range(row['threads'])) and row['collector_cpu'] == 63
        assert row['post_work_rounds'] == 4 and row['duration_ms'] == 2000
        assert not FAULT.search((path / 'kernel.log').read_text())
        assert (path / 'unload-source.log').exists()
        warm = read(path / 'warmup.json')
        assert warm['data_ok'] is True
        assert validate(warm, dict(spec, iterations=48000, duration_ms=0)) is None
        m = row['measurement']
        assert m['data_ok'] is True and m['collector_observed_cpu'] == 63
        assert not m['collector_error']
        assert validate(m, spec) == m['peak']
        evidence = jit_evidence(row['jit_before'], row['jit_after'], m['writes'],
            backend=row['arm'], delegate=row['delegate'], operation='writer',
            completed=row['jit_complete_after'] - row['jit_complete_before'])
        assert all(row[k] == v for k, v in evidence.items())
        if row['arm'] == 'kdlock':
            assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
            assert (path / 'unload-kdlock.log').exists()
            assert row['publication']['entry']['entry_abi'] == 3
            for pub in row['publications']:
                for name, sha in pub['images'].items():
                    assert digest(path / pub['path'] / name) == sha
                    image_count += 1
        elif row['arm'] == 'tclock':
            assert all(row[k]['quiescent'] == 1 for k in ('tclock_before', 'tclock_after', 'tclock_drained'))
            assert (path / 'unload-tclock.log').exists()
            assert row['tclock_delegation_status'] == 'UNMEASURED'
        row.update(whole_ops_s=m['completed'] * 1e9 / m['wall_ns'],
                   read_ops_s=m['reads'] * 1e9 / m['wall_ns'],
                   write_ops_s=m['writes'] * 1e9 / m['wall_ns'],
                   peak_ops_s=m['peak']['throughput_ops_s'])
        assert row == aggregate
        samples.append({k: row[k] for k in ('name', 'arm', 'write_percent', 'threads', 'repeat',
            'jit_status', 'whole_ops_s', 'peak_ops_s', 'jit_bodies', 'jit_completions', 'jit_complete_share')})
        samples[-1].update(reads=m['reads'], writes=m['writes'], completed=m['completed'],
                           cpu_ns_per_op=sum(w['cpu_ns'] for w in m['workers']) / m['completed'])
        for index, worker in enumerate(m['workers']):
            workers.append(dict(name=row['name'], arm=row['arm'], write_percent=row['write_percent'],
                threads=row['threads'], repeat=row['repeat'], worker=index, **worker,
                operation_share=worker['completed'] / m['completed']))
        key = (row['variant'], row['write_percent'], row['threads'], row['jit_status'])
        groups.setdefault(key, []).append(row)

    summary = []
    for (variant, percent, threads, status), rows in groups.items():
        peaks, whole = ([r[k] for r in rows] for k in ('peak_ops_s', 'whole_ops_s'))
        summary.append(dict(variant=variant, write_percent=percent, threads=threads, jit_status=status,
            valid_rounds=len(rows), expected_rounds=3, complete=len(rows) == 3,
            best_peak_ops_s=max(peaks), peak_min_ops_s=min(peaks), peak_median_ops_s=statistics.median(peaks),
            peak_max_ops_s=max(peaks), peak_spread_pct=(max(peaks) - min(peaks)) * 100 / min(peaks),
            whole_min_ops_s=min(whole), whole_median_ops_s=statistics.median(whole), whole_max_ops_s=max(whole),
            whole_spread_pct=(max(whole) - min(whole)) * 100 / min(whole),
            samples=[r['name'] for r in rows]))
    assert summary == read(raw / 'summary.json')
    parity = assess(plan, summary)
    assert parity == read(raw / 'parity.json')
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'samples.csv', samples)
    write_csv(out / 'workers.csv', workers)
    statistics_rows = []
    for group in summary:
        members = groups[(group['variant'], group['write_percent'], group['threads'], group['jit_status'])]
        shares = [r['jit_complete_share'] for r in members]
        statistics_rows.append(dict({k: v for k, v in group.items() if k != 'samples'},
            jit_complete_share_min=min(shares), jit_complete_share_median=statistics.median(shares),
            jit_complete_share_max=max(shares),
            jit_completions=sum(r['jit_completions'] for r in members)))
    write_csv(out / 'statistics.csv', statistics_rows)
    write_json(out / 'summary.json', summary)
    write_json(out / 'parity.json', parity)
    write_json(out / 'environment.json', env)
    write_json(out / 'source-sha256.json', sources)
    write_json(out / 'binary-sha256.json', binaries)
    verification = dict(sessions=len(samples), workers=len(workers), source_files=len(sources),
        binaries=len(binaries), published_image_files=image_count, all_valid=True, all_drained=True,
        whole_and_peak_recomputed=True, warmup_and_measurement_revalidated=True,
        jit_status_counts={status: sum(r['jit_status'] == status for r in samples)
                           for status in sorted({r['jit_status'] for r in samples})},
        delegated_writers=sum(r['jit_completions'] for r in samples),
        parity_counts={status: sum(r['status'] == status for r in parity['points'])
                       for status in sorted({r['status'] for r in parity['points']})},
        input_hashes={name: digest(raw / name) for name in
                      ('plan.json', 'records.json', 'summary.json', 'parity.json', 'environment.json')})
    write_json(out / 'verification.json', verification)
    print(json.dumps(verification, indent=2))


if __name__ == '__main__':
    main()
