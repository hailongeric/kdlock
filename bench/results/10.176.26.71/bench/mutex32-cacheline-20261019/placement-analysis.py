#!/usr/bin/env python3
"""VM-only arithmetic and lifetime checks for the separate placement diagnostic."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import median


FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'unable to handle|general protection fault|Oops:|\[ERROR\]|'
                   r'invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production(manifest):
    return {name: value for name, value in manifest.items()
            if name.startswith(('include/', 'kernel_module/')) and not name.endswith('.mod.c')
            and (Path(name).suffix in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
                 or Path(name).name == 'Makefile')}


def stats(values):
    return dict(n=len(values), min=min(values), median=median(values), max=max(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    args = parser.parse_args()
    require(os.uname().release == '6.1.159-kdclobber2', 'run in the recovery VM')
    base = args.base.resolve(strict=True)
    folder = base / 'placement'
    result, commands = read(folder / 'result.json'), read(folder / 'commands.json')
    baseline_path = base / 'packed32/pipe/source-sha256.json'
    baseline = read(baseline_path)
    original = read(folder / 'input-source-hashes.json')
    require(result.get('passed') is True and result.get('final_idle') is True
            and result.get('source_unchanged') is True and result.get('source_revision') == '09ebd8f'
            and result.get('baseline_revision') == '0987358'
            and result.get('provider_matches_baseline') is True
            and result.get('diagnostic') is True and result.get('score_eligible') is False
            and result.get('offsets') == [32, 40] and result.get('expected_sessions') == 12
            and result.get('returned_jit_sessions') == 12 and result.get('profiles') == 0,
            'placement result is incomplete or has unexpected scope/source')
    require(result.get('baseline_manifest_sha256') == digest(baseline_path)
            and result.get('input_source_hashes_sha256') == digest(folder / 'input-source-hashes.json')
            and result.get('script_sha256') == digest(base / 'run-placement.py')
            and production(original) == production(baseline), 'source or runner binding differs')
    require(commands == result.get('commands') and len(commands) == 4
            and [row.get('name') for row in commands] == ['runner-plan', 'runner-report', 'offset32', 'offset40']
            and all(row.get('exit_code') == 0 and row.get('finished_unix', 0) >= row.get('started_unix', 1)
                    for row in commands), 'placement command receipts differ')
    inputs = {str(path.relative_to(base)): digest(path) for path in
              (folder / 'result.json', folder / 'commands.json', folder / 'input-source-hashes.json',
               baseline_path, base / 'run-placement.py')}
    sessions, cohorts, manifests = [], defaultdict(list), []
    for offset in (32, 40):
        collection = folder / ('offset' + str(offset))
        records_path, source_path = collection / 'records.json', collection / 'source-sha256.json'
        rows, source = read(records_path), read(source_path)
        saved = {name: value for name, value in source.items()
                 if not name.startswith('bench/spin_cacheline/.build/provider/')}
        require(saved == original and production(source) == production(baseline),
                'placement source/provider differs at offset ' + str(offset))
        identity = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        command = commands[2 + int(offset == 40)]
        require(command.get('sessions') == command.get('returned_jit_sessions') == 6
                and command.get('records_sha256') == digest(records_path)
                and command.get('source_manifest_sha256') == digest(source_path), 'collection receipt differs')
        require(len(rows) == 6 and {(row['threads'], row['repeat']) for row in rows} ==
                {(workers, repeat) for workers in (8, 60) for repeat in range(3)}, 'placement inventory differs')
        for path in (records_path, source_path):
            inputs[str(path.relative_to(base))] = digest(path)
        manifests.append(dict(offset=offset, source_identity=identity, source_manifest_sha256=digest(source_path),
                              records_sha256=digest(records_path), provider_matches_baseline=True))
        for row in rows:
            name = row['name']
            require(Path(name).name == name and name not in ('.', '..'), 'unsafe session name')
            path = collection / name
            require(read(path / 'session.json') == row, 'aggregate/session differs')
            m, workers = row['measurement'], row['threads']
            count, wall, returned, bodies = m['completed'], m['wall_ns'], row['jit_completions'], row['jit_bodies']
            require(all(type(value) is int and value > 0 for value in (count, wall, returned, bodies))
                    and bodies == returned <= count, 'invalid measured count/body interval')
            rate = count * 1000 / wall
            require(math.isclose(row['whole_throughput_ops_s'], rate * 1e6, rel_tol=1e-12), 'rate differs')
            require(row.get('execution_status') == 'OK' and row.get('drained') is True
                    and not row.get('error') and not row.get('cleanup_error')
                    and row.get('retired') == dict(state=2, modules=0, frames=0, writers=0)
                    and row.get('diagnostic') is True and not row.get('perf_record') and not row.get('pmu')
                    and row.get('mutex_lock_offset') == offset and row.get('source_identity') == identity,
                    'execution/retirement/diagnostic/source differs')
            require(row.get('cpus') == list(range(workers)) and row.get('collector_cpu') == 63
                    and row.get('duration_ms') == 2000 and row.get('warmup') == 48000
                    and row.get('warmup_ms') == 1000 and row.get('kind') == 'pipebytes'
                    and row.get('query') == 'query' and row.get('entries') == 16
                    and row.get('value_size') == 64 and row.get('caller_abi') == 'clobber'
                    and row.get('entry_abi') == 2 and row.get('learning_waves') == [], 'workload policy differs')
            require(m.get('ok') is True and m.get('phase') == 'measure'
                    and m.get('collector_error') == 0 and m.get('collector_observed_cpu') == 63
                    and m.get('duration_ns') == 2000000000
                    and wall == m['finished_ns'] - m['started_ns']
                    and row.get('redirected_calls') == row.get('jit_eligible_operations') == count,
                    'measurement oracle or interval differs')
            progress = m.get('workers', [])
            require(len(progress) == workers and [w['cpu'] for w in progress] == list(range(workers))
                    and all(w['completed'] > 0 and w['error'] == 0 and w['observed_cpu'] == w['cpu'] for w in progress)
                    and sum(w['completed'] for w in progress) == count, 'worker progress differs')
            address = row.get('lock_addr')
            require(type(address) is int and address % 64 == offset
                    and row.get('mutex_lock_placement') == dict(offset=offset, cache_line_bytes=64, storage_bytes=128),
                    'actual object placement differs')
            field_lines = {field: dict(address=address + displacement,
                                      line=(address + displacement) // 64,
                                      offset=(address + displacement) % 64)
                           for field, displacement in (('owner', 0), ('gate', 24), ('tail', 28))}
            text = (path / 'kernel.log').read_text(errors='replace')
            require(not FAULT.search(text), 'kernel fault in placement diagnostic')
            counters = {}
            for key, marker in (('physical', 'kd_mutex stats:'), ('tasks', 'kd_mutex tasks:')):
                lines = [line for line in text.splitlines() if marker in line]
                require(len(lines) == 1, 'missing/ambiguous final counter row')
                counters[key] = {key: int(value) for key, value in re.findall(r'(\w+)=(-?\d+)', lines[0])}
            p, task = counters['physical'], counters['tasks']
            require(p.get('origin_acquires') == p.get('origin_releases') and p.get('origin_acquires', -1) >= 0
                    and all(p.get(key) == 0 for key in ('active_waiters', 'reserved_nodes', 'frame_failure'))
                    and task.get('active_tasks') == 0, 'exact final owner/node/task drain differs')
            for endpoint in ('check-before', 'check-after'):
                require(read(path / (endpoint + '.json')).get('check') is True, 'business oracle failed')
            summary = dict(offset=offset, threads=workers, repeat=row['repeat'], session_path=str(path.relative_to(base)),
                           diagnostic=True, score_eligible=False, valid=True, completed=count, wall_ns=wall,
                           whole_mops=rate, jit_bodies=bodies, jit_completions=returned,
                           measured_returned_jit_share=returned / count, lock_addr=address, field_lines=field_lines,
                           session_sha256=digest(path / 'session.json'), kernel_log_sha256=digest(path / 'kernel.log'))
            sessions.append(summary)
            cohorts[(offset, workers)].append(summary)
    groups = []
    for (offset, workers), rows in sorted(cohorts.items()):
        groups.append(dict(offset=offset, threads=workers, repeats=[row['repeat'] for row in rows],
                           whole_mops=stats([row['whole_mops'] for row in rows]),
                           measured_returned_jit_share=sum(row['jit_completions'] for row in rows) /
                               sum(row['completed'] for row in rows)))
    by_key = {(row['offset'], row['threads']): row for row in groups}
    effects = []
    for workers in (8, 60):
        left, right = (by_key[(offset, workers)]['whole_mops']['median'] for offset in (32, 40))
        effects.append(dict(threads=workers, offset32_mops=left, offset40_mops=right,
                            split_over_shared=right / left, change_percent=100 * (right / left - 1)))
    output = dict(schema=1, complete=True, issues=[], source_revision='09ebd8f', baseline_revision='0987358',
                  diagnostic=True, score_eligible=False, provider_matches_baseline=True,
                  input_sha256=inputs, script_sha256=digest(Path(__file__)),
                  collections=manifests, sessions=sessions, groups=groups, effects=effects,
                  kernel_logs=[row['session_path'] + '/kernel.log' for row in sessions],
                  limits=['Separate placement-only diagnostics; do not pool with main timings or profiles.',
                          'Three sequential repeats per cohort, not a confidence interval.',
                          'Both placements use dedicated padding, unlike the ordinary private object.',
                          'A placement effect is not a direct cache-transfer or HITM measurement.'])
    (base / 'placement-analysis.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    lines = ['| Workers | Offset 32 Mops/s | Offset 40 Mops/s | Split / shared |',
             '| ---: | ---: | ---: | ---: |']
    for effect in effects:
        lines.append('| {threads} | {offset32_mops:.3f} | {offset40_mops:.3f} | {split_over_shared:.3f} |'.format(**effect))
    (base / 'placement-table.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(complete=True, sessions=len(sessions), effects=effects)))


if __name__ == '__main__':
    main()
