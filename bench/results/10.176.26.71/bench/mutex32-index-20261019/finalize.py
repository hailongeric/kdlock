#!/usr/bin/env python3
"""Finalize completed VM evidence from recorded checks; never run a workload."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-index-20261019')
ARMS = ('compact-rcu', 'precompact-256', 'compact-index', 'compact-transfer')
CHECKS = {'compact-index': 'checks', 'compact-transfer': 'checks-transfer'}
PLAIN, PROFILE = 24 * len(ARMS), 2 * len(ARMS)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (BASE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def validate_checks(arm, directory, comparison):
    folder = BASE / directory
    checks = read(folder / 'result.json')
    require(checks['passed'] is True and checks['final_idle'] is True
            and checks['source_unchanged'] is True and checks['full_suite'] is False,
            directory + ': basic/affected check receipt incomplete')
    commit = read(BASE / arm / 'matrix.json')['source_commit']
    require(re.fullmatch(r'[0-9a-f]{7,40}', commit) is not None, 'missing candidate revision')
    require(checks['unit_basic'] == 2 and len(set(checks['unit_drivers'])) == 12,
            directory + ': unexpected basic/affected scope')
    commands = read(folder / 'commands.json')
    require(commands == checks['commands'] and
            [c['name'] for c in commands] == ['dependencies', 'provider', 'daemon', 'unit',
                                           'local', 'rwsem', 'instruction-exit'] and
            all(c.get('exit_code') == 0 for c in commands), directory + ': failed/missing check command')
    unit_log = (folder / 'unit.log').read_text()
    totals = re.findall(r'Unit tests: (\d+) passed, (\d+) failed', unit_log)
    require(totals == [('14', '0')], directory + ': unit result totals missing or different')
    controls = ('missing-post-pin-key-validation', 'missing-observation-sequence-validation',
                'free-before-retirement')
    if arm == 'compact-transfer':
        controls += ('borrow-ignores-current-owner', 'borrow-ignores-key',
                     'borrow-ignores-sequence-validation', 'fast-owner-restores-reference-pair',
                     'fast-owner-drops-transferred-reference', 'unlock-restores-temporary-reference',
                     'unlock-error-drops-owner-reference', 'unlock-drops-owner-before-gate')
    require(all('mutation detected: ' + control in unit_log for control in controls),
            directory + ': auxiliary negative control evidence missing')
    live = {name: read(folder / name / 'result.json')
            for name in ('local', 'rwsem', 'instruction-exit')}
    require(all(r['passed'] is True and r['drained'] is True for r in live.values()),
            directory + ': live probe failed or undrained')
    require(live['local']['final_idle'] is True, directory + ': ordinary probe final idle missing')
    manifests = read(folder / 'source-sha256.json')
    matched = [p for p in comparison['provenance'] if p['arm'] == arm]
    require(len(matched) == 4, arm + ': missing collection provenance')
    production = {n for n in manifests if n.startswith(('include/', 'kernel_module/'))}
    for p in matched:
        require(p['source_commit'] == commit, arm + ': benchmark revision differs')
        require(production and all(p['source_manifest'].get(n) == manifests[n] for n in production),
                arm + ': benchmark and checked production bytes differ')
    provider_log = (folder / 'provider.log').read_text(errors='replace')
    return dict(passed=True, arm=arm, directory=directory, source_revision=commit,
        checked_source_label=checks['source_revision'], source_unchanged=checks['source_unchanged'],
        candidate_production_matches_checked_source=True, unit_basic=checks['unit_basic'],
        unit_affected_drivers=checks['unit_drivers'], unit_final_passed=int(totals[0][0]),
        unit_final_failed=int(totals[0][1]), negative_controls=list(controls), full_suite=False,
        commands=commands, checks_result_sha256=digest(folder / 'result.json'),
        provider=dict(passed=True, flags='W=1 UBSAN_SANITIZE=n', log=directory + '/provider.log',
                      warning_lines=[l for l in provider_log.splitlines() if re.search(r'\bwarning:', l, re.I)]),
        daemon=dict(passed=True, flags='-O2 -Wall -Wextra -Werror', log=directory + '/daemon.log'),
        dependencies=dict(passed=True, log=directory + '/dependencies.log'), live=live)


def main():
    require(Path.cwd() == ROOT and os.uname().release == '6.1.159-kdclobber2'
            and os.geteuid() == 0, 'run from the maintained recovery-VM checkout')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](BASE, local['idle'])
    comparison, profiles = (read(BASE / name) for name in ('comparison.json', 'profile-analysis.json'))
    require(comparison['complete'] is True and comparison['valid_sessions'] == PLAIN + PROFILE
            and comparison['scored_plain_sessions'] == PLAIN
            and set(comparison['arms']) == set(ARMS), 'incomplete comparison')
    require(profiles['complete'] is True and len(profiles['profiles']) == PROFILE,
            'incomplete profiles')
    require(all(p['complete'] and p['report_lost_samples'] == [0] for p in profiles['profiles']),
            'incomplete/lost profile evidence')
    for arm in ARMS:
        matrix = read(BASE / arm / 'matrix.json')
        require(matrix['passed'] is True and matrix['final_idle'] is True
                and matrix['plain_sessions'] == 24 and matrix['profile_sessions'] == 2,
                arm + ': incomplete matrix receipt')
        require(len(matrix['commands']) == 4 and all(c.get('exit_code') == 0 for c in matrix['commands']),
                arm + ': incomplete command receipts')
        provenance = [p for p in comparison['provenance'] if p['arm'] == arm]
        require(len(provenance) == 4 and all(p['source_commit'] == matrix['source_commit']
                                           for p in provenance), arm + ': matrix source label differs')

    before, after = (read(BASE / name) for name in ('host-before.json', 'host-after.json'))
    require(before['snapshot_listed'] and after['snapshot_listed']
            and before['recovery_snapshot'] == after['recovery_snapshot'], 'snapshot differs or missing')
    require(before['cpufreq'] == after['cpufreq'] and before['numa'] == after['numa'],
            'host frequency policy or NUMA topology changed')
    require(len(before['qemu']) == len(after['qemu']) == 1, 'ambiguous QEMU identity')
    bq, aq = before['qemu'][0], after['qemu'][0]
    require(bq['pid'] == aq['pid'] and bq['args'] == aq['args'], 'QEMU identity changed')
    bt, at = ({t['tid']: t for t in q['tasks']} for q in (bq, aq))
    require({k: v for k, v in bt.items() if v['comm'].startswith('CPU ')} ==
            {k: v for k, v in at.items() if v['comm'].startswith('CPU ')}, 'vCPU pins changed')
    require(all(bt[k] == at[k] for k in bt.keys() & at.keys()), 'retained host task pins changed')
    require(all(t['affinity'] == [63] for t in [*bt.values(), *at.values()]
                if not t['comm'].startswith('CPU ')), 'service threads not pinned to collector')

    check_results = {arm: validate_checks(arm, directory, comparison)
                     for arm, directory in CHECKS.items()}
    commit = check_results['compact-transfer']['source_revision']
    preparation = read(BASE / 'preparation-failure.json')
    retained = preparation['retained_guest_directory']
    require(preparation.get('workloads_started') is False and preparation.get('exit_code') != 0
            and Path(retained).name == retained and (BASE / retained).is_dir(),
            'preparation failure receipt/directory missing')
    faults, logs = [], {}
    fault_pattern = re.compile(local['rt'].FAULT.pattern + r'|runtime error:|KASAN:|UBSAN:', re.I)
    for path in BASE.rglob('kernel.log'):
        matches = [line for line in path.read_text(errors='replace').splitlines()
                   if fault_pattern.search(line)]
        if matches:
            faults.append(dict(path=str(path.relative_to(BASE)), matches=matches))
        logs[str(path.relative_to(BASE))] = digest(path)
    expected_logs = {r['session_path'] + '/kernel.log' for r in comparison['sessions']}
    require(len(expected_logs) == PLAIN + PROFILE, 'duplicate or missing session log paths')
    for directory in CHECKS.values():
        expected_logs.update(directory + '/' + suffix for suffix in (
            'local/kernel.log', 'rwsem/local/kernel.log', 'instruction-exit/session/kernel.log'))
    require(not faults and expected_logs <= logs.keys(), 'kernel fault or missing session/probe logs')
    validation = dict(passed=True, source_revision=commit, full_suite=False,
        checks_by_arm=check_results,
        preparation_failure=dict(receipt=preparation, sha256=digest(BASE / 'preparation-failure.json')),
        note='Synthetic JIT counts witness entry; API and instruction-exit completion probes establish returns. No full-suite claim.')
    save('validation.json', validation)

    plot = read(BASE / 'plot-input.json')
    require(plot['comparison_sha256'] == digest(BASE / 'comparison.json')
            and plot['eligible_plain_sessions'] == plot['planned_plain_sessions'] == PLAIN
            and plot['excluded_profile_sessions'] == PROFILE and plot['all_plotted_groups_complete'],
            'plot input does not match complete comparison')
    postprocess = {}
    for name, script, outputs in (
            ('summary', 'summarize.py', ('comparison.json', 'comparison.csv', 'sessions.csv')),
            ('profiles', 'profile-analysis.py', ('profile-analysis.json',)),
            ('plot', 'plot.py', ('plot-input.json', 'comparison.svg', 'comparison.png'))):
        postprocess[name] = dict(script_sha256=digest(BASE / script),
                                outputs={n: digest(BASE / n) for n in outputs},
                                validation='recorded complete outputs checked; command exit not inferred')
    save('postprocess.json', postprocess)
    local['idle']()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    before_boot = re.findall(r'(?m)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$',
                             (BASE / 'guest-before.log').read_text())
    require(before_boot == [boot], 'guest boot changed or preflight boot identity missing')
    health = dict(idle=True, boot_id=boot, kernel_release=os.uname().release, captured_unix=time.time(),
        per_session_kernel_faults=faults, kernel_logs=logs, expected_kernel_logs=sorted(expected_logs),
        valid_timing_sessions=PLAIN, valid_profiles=PROFILE,
        source_unchanged_checks={arm: row['source_unchanged'] for arm, row in check_results.items()},
        host_pins_frequency_policy_snapshot_unchanged=True,
        added_host_service_threads=[at[k] for k in at.keys()-bt.keys()],
        removed_host_service_threads=[bt[k] for k in bt.keys()-at.keys()],
        snapshot=after['recovery_snapshot'], source_revision=commit,
        comparison_sha256=digest(BASE / 'comparison.json'), validation_sha256=digest(BASE / 'validation.json'),
        profile_analysis_sha256=digest(BASE / 'profile-analysis.json'),
        profile_samples=sum(p['parsed_sample_lines'] for p in profiles['profiles']))
    save('health.json', health)
    print(json.dumps(dict(idle=True, kernel_logs=len(logs), faults=0, timing=PLAIN,
                          profiles=PROFILE, checks=list(check_results), source_revision=commit)))


if __name__ == '__main__':
    main()
