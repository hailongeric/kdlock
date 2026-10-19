#!/usr/bin/env python3
"""Validate a completed traffic comparison in the idle VM before archiving.

This reads retained receipts and frozen bytes; it never builds or runs a test.
Select every comparison arm explicitly and map each newly checked arm with
--check ARM=DIRECTORY. Redirect stdout outside --base: the archive idle guard
rejects every writable descriptor into the evidence tree, including this one.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
import time


ROOT = Path('/root/host_fs/kdlock')
DEFAULT_BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019')
RELEASE = '6.1.159-kdclobber2'
DRIVERS = ['mutex/test_mutex_aux.py', 'mutex/test_mutex_resources.py',
           'mutex/test_mutex_balances.py', 'mutex/test_mutex_terminal.py',
           'mutex/test_mutex_outer_progress.py', 'mutex/test_mutex_outer_api.py',
           'mutex/test_mutex_wait_clobber.py', 'mutex/test_mutex_task_cache.py',
           'execution/test_exec_capacity.py', 'infrastructure/test_provider_lifecycle.py',
           'execution/test_mutex_images.py', 'execution/test_remote_outer.py']
COLLECTIONS = {'profile': ('profile/pipe', 2), 'synthetic': ('synthetic', 12),
               'seek': ('seek', 6), 'pipe': ('pipe', 6)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def child(base, name):
    require(isinstance(name, str) and re.fullmatch(r'[a-z0-9][a-z0-9._-]*', name)
            and name not in ('.', '..'), 'unsafe top-level name: ' + str(name))
    path = base / name
    require(path.is_dir() and not path.is_symlink(), 'missing ordinary directory: ' + str(path))
    return path


def relative_file(base, name):
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts,
            'unsafe relative evidence path: ' + name)
    path = base / relative
    require(path.is_file() and path.resolve().is_relative_to(base.resolve()),
            'missing/outside evidence file: ' + str(path))
    return path


def production(manifest):
    # The check snapshot excludes maintained prose and generated module files.
    # Compare every captured production input, including private .inc files.
    suffixes = ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
    return {name: value for name, value in manifest.items()
            if name.startswith(('include/', 'kernel_module/'))
            and not name.endswith('.mod.c')
            and (Path(name).suffix in suffixes or Path(name).name == 'Makefile')}


def manifest_identity(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def validate_matrix(base, arm, snapshot):
    folder = child(base, arm)
    matrix = read(folder / 'matrix.json')
    commit = matrix.get('source_commit', '')
    require(re.fullmatch(r'[0-9a-f]{7,40}', commit) is not None,
            arm + ': missing committed source identity')
    require(matrix.get('version') == arm and matrix.get('passed') is True and matrix.get('final_idle') is True
            and matrix.get('full_suite') is False and matrix.get('plain_sessions') == 24
            and matrix.get('profile_sessions') == 2 and matrix.get('snapshot_tag') == snapshot,
            arm + ': matrix is incomplete or has different scope/snapshot')
    commands = matrix.get('commands', [])
    require(len(commands) == len(COLLECTIONS), arm + ': matrix command count differs')
    all_production, manifests = None, {}
    for index, (name, (directory, count)) in enumerate(COLLECTIONS.items()):
        receipt_path = folder / (name + '-command.json')
        receipt = read(receipt_path)
        require(commands[index] == receipt and receipt.get('exit_code') == 0
                and receipt.get('source_commit') == commit and receipt.get('version') == arm
                and receipt.get('expected_sessions') == count
                and receipt.get('timeout_seconds') == 900 and receipt.get('cwd') == str(ROOT)
                and receipt.get('finished_unix', 0) >= receipt.get('started_unix', 1)
                and '--output' in receipt.get('argv', [])
                and receipt['argv'][-2:] == ['--output', str(folder / name)],
                arm + '/' + name + ': command receipt differs or failed')
        records_path = folder / directory / 'records.json'
        records = read(records_path)
        require(len(records) == count and all(r.get('execution_status') == 'OK'
                and r.get('drained') is True for r in records),
                arm + '/' + name + ': result count or drain differs')
        path = folder / directory / 'source-sha256.json'
        manifest = read(path)
        prod = production(manifest)
        require(prod and any(n.endswith('.inc') for n in prod),
                arm + '/' + name + ': production manifest/private includes missing')
        if all_production is None:
            all_production = prod
        require(prod == all_production, arm + ': collection production bytes differ')
        manifests[name] = dict(path=str(path.relative_to(base)), sha256=digest(path),
                               records_sha256=digest(records_path), sessions=count,
                               command_sha256=digest(receipt_path))
    profile = read(folder / 'profile/result.json')
    require(profile.get('passed') is True and profile.get('final_idle') is True
            and profile.get('exit_code') == 0 and profile.get('sessions') == 2
            and profile.get('diagnostic') is True and profile.get('score_eligible') is False
            and profile.get('source_commit') == commit,
            arm + ': profile collection did not finish and drain')
    result = dict(source_commit=commit, plain_sessions=24, profile_sessions=2,
                  matrix_sha256=digest(folder / 'matrix.json'), collections=manifests,
                  production_files=len(all_production),
                  production_private_includes=sum(n.endswith('.inc') for n in all_production),
                  production_manifest_sha256=manifest_identity(all_production))
    return result, all_production


def mutation_names(path, optional=False):
    assignments = [node for node in ast.walk(ast.parse(path.read_text()))
                   if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                   and any(isinstance(t, ast.Name) and t.id == 'mutations' for t in node.targets)]
    if optional and not assignments:
        return []
    require(len(assignments) == 1, 'missing mutation dictionary: ' + str(path))
    keys = assignments[0].value.keys
    require(all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in keys),
            'nonliteral mutation identity: ' + str(path))
    return [key.value for key in keys]


def validate_checks(base, arm, directory, prod, revision, snapshot):
    folder = child(base, directory)
    result = read(folder / 'result.json')
    require(result.get('passed') is True and result.get('final_idle') is True
            and result.get('source_unchanged') is True and result.get('full_suite') is False
            and result.get('unit_basic') == 2 and result.get('unit_drivers') == DRIVERS
            and result.get('snapshot_tag') == snapshot,
            directory + ': incomplete checks or unexpected scope')
    commands = read(folder / 'commands.json')
    require(commands == result.get('commands'), directory + ': inconsistent command receipts')
    expected = [
        ('dependencies', ['-m', 'pip', 'check'], ROOT, 60),
        ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2',
                      'W=1', 'UBSAN_SANITIZE=n'], folder / 'source', 240),
        ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'], folder / 'source', 60),
        ('unit', ['make', '-C', 'tests/unit', 'run', 'PY_TESTS=' + ' '.join(DRIVERS)], folder / 'source', 300),
        ('local', ['tests/kernel/mutex/local/run.py', '--output', str(folder / 'local')], ROOT, 300),
        ('rwsem', ['tests/kernel/rwsem/run.py', '--output', str(folder / 'rwsem')], ROOT, 300),
        ('instruction-exit', ['tests/kernel/jit_escape/run.py', '--cpus', '0-7,32-39',
                              '--iterations', '200000', '--warmup-iterations', '200000',
                              '--output', str(folder / 'instruction-exit')], ROOT, 900)]
    require(len(commands) == len(expected), directory + ': check command count differs')
    python = commands[0].get('argv', [''])[0]
    require(Path(python).name.startswith('python'), directory + ': missing Python command')
    logs = {}
    for row, (name, argv, cwd, timeout) in zip(commands, expected):
        if name in ('dependencies', 'local', 'rwsem', 'instruction-exit'):
            argv = [python, *argv]
        require(row.get('name') == name and row.get('argv') == argv
                and row.get('cwd') == str(cwd) and row.get('timeout_seconds') == timeout
                and row.get('exit_code') == 0
                and row.get('finished_unix', 0) >= row.get('started_unix', 1),
                directory + ': unexpected/failed command ' + name)
        logs[name] = digest(folder / (name + '.log'))
    text = (folder / 'unit.log').read_text()
    require(re.findall(r'Unit tests: (\d+) passed, (\d+) failed', text) == [('14', '0')]
            and '[PASS] test_control_call' in text and '[PASS] test_daemon_policy' in text,
            directory + ': exact basic and affected pass evidence missing')
    controls = {}
    for name, prefix, optional in (('mutex/test_mutex_aux.py', 'mutation detected: ', False),
                                   ('mutex/test_mutex_resources.py', 'mutex resource mutation detected: ', False),
                                   ('mutex/test_mutex_outer_api.py', 'outer retry mutation detected: ', True)):
        names = mutation_names(folder / 'source/tests/unit' / name, optional)
        require((names or optional) and all(prefix + control in text for control in names),
                directory + ': missing negative-control outcomes for ' + name)
        if names:
            controls[name] = names
    manifest_path = folder / 'source-sha256.json'
    manifest = read(manifest_path)
    require(production(manifest) == prod, arm + ': checked and measured production bytes differ')
    for name, sha in manifest.items():
        require(digest(relative_file(folder / 'source', name)) == sha,
                directory + ': frozen source changed: ' + name)
    live, expected_logs = {}, set()
    for name, kernel_log in (('local', 'local/kernel.log'), ('rwsem', 'rwsem/local/kernel.log'),
                             ('instruction-exit', 'instruction-exit/session/kernel.log')):
        path = folder / name / 'result.json'
        probe = read(path)
        require(probe.get('passed') is True and probe.get('drained') is True
                and (name != 'local' or probe.get('final_idle') is True),
                directory + '/' + name + ': failed or undrained live probe')
        live[name] = dict(passed=True, drained=True, result_sha256=digest(path))
        expected_logs.add(directory + '/' + kernel_log)
    provider = (folder / 'provider.log').read_text(errors='replace')
    return dict(passed=True, source_commit=revision, checked_source_label=result['source_revision'],
                directory=directory, unit_basic=2, unit_affected_drivers=DRIVERS,
                unit_passed=14, unit_failed=0, full_suite=False,
                production_matches_benchmark=True, frozen_source_files=len(manifest),
                source_manifest_sha256=digest(manifest_path), source_unchanged=True,
                result_sha256=digest(folder / 'result.json'),
                commands_sha256=digest(folder / 'commands.json'), logs_sha256=logs,
                provider_warning_lines=sum(bool(re.search(r'\bwarning:', line, re.I))
                                           for line in provider.splitlines()),
                negative_controls=controls, live=live), expected_logs


def topology(base):
    before, after = (read(base / name) for name in ('host-before.json', 'host-after.json'))
    require(before.get('snapshot_listed') and after.get('snapshot_listed')
            and before['recovery_snapshot'] == after['recovery_snapshot'],
            'real recovery snapshot missing or changed')
    require(before['cpufreq'] == after['cpufreq'] and before['numa'] == after['numa'],
            'host frequency policy or NUMA topology changed')
    require(len(before['qemu']) == len(after['qemu']) == 1, 'ambiguous QEMU identity')
    left, right = before['qemu'][0], after['qemu'][0]
    require(left['pid'] == right['pid'] and left['args'] == right['args'], 'QEMU identity changed')
    bt, at = ({t['tid']: t for t in q['tasks']} for q in (left, right))
    require({k: v for k, v in bt.items() if v['comm'].startswith('CPU ')} ==
            {k: v for k, v in at.items() if v['comm'].startswith('CPU ')}, 'vCPU pins changed')
    require(all(bt[k] == at[k] for k in bt.keys() & at.keys()), 'retained host task pins changed')
    require(all(t['affinity'] == [63] for t in [*bt.values(), *at.values()]
                if not t['comm'].startswith('CPU ')), 'service thread outside collector CPU')
    return dict(snapshot=after['recovery_snapshot'], unchanged=True,
                before_sha256=digest(base / 'host-before.json'), after_sha256=digest(base / 'host-after.json'),
                added_service_threads=[at[k] for k in sorted(at.keys() - bt.keys())],
                removed_service_threads=[bt[k] for k in sorted(bt.keys() - at.keys())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--arms', nargs='+', required=True)
    parser.add_argument('--check', action='append', required=True, metavar='ARM=DIRECTORY')
    parser.add_argument('--current-arm', required=True,
                        help='checked candidate whose production bytes are now in the maintained checkout')
    args = parser.parse_args()
    require(Path.cwd() == ROOT and os.uname().release == RELEASE and os.geteuid() == 0,
            'run from the maintained recovery-VM checkout')
    base = args.base.resolve(strict=True)
    require(base.is_dir() and not base.is_relative_to(ROOT), 'use an external evidence directory')
    require(len(args.arms) == len(set(args.arms)), 'duplicate comparison arms')
    checks = {}
    for item in args.check:
        arm, separator, directory = item.partition('=')
        require(separator and arm in args.arms and arm not in checks
                and directory not in checks.values(), 'invalid/duplicate check mapping: ' + item)
        checks[arm] = directory
    require(args.current_arm in checks, 'current arm needs its own checked-source mapping')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](base, local['idle'])
    host = topology(base)
    comparison, profiles = (read(base / name) for name in ('comparison.json', 'profile-analysis.json'))
    require(comparison.get('complete') is True and not comparison.get('issues')
            and comparison.get('arms') == args.arms, 'comparison incomplete or arm order differs')
    sessions = comparison['sessions']
    require(len(sessions) == 26 * len(args.arms)
            and Counter(row['arm'] for row in sessions) == Counter({arm: 26 for arm in args.arms})
            and all(row.get('valid') is True for row in sessions), 'session count or validity differs')
    require(Counter(row['arm'] for row in sessions if row.get('score_eligible') is True) ==
            Counter({arm: 24 for arm in args.arms}), 'plain/profile score separation differs')
    require(profiles.get('complete') is True and not profiles.get('issues')
            and len(profiles['profiles']) == 2 * len(args.arms), 'profile analysis incomplete')
    require(Counter(row['arm'] for row in profiles['profiles']) ==
            Counter({arm: 2 for arm in args.arms}), 'profile arm count differs')
    matrices, production_by_arm = {}, {}
    for arm in args.arms:
        matrices[arm], production_by_arm[arm] = validate_matrix(base, arm, host['snapshot'])
        commit = matrices[arm]['source_commit']
        require(all(row.get('source_commit') == commit for row in sessions if row['arm'] == arm),
                arm + ': summary source identity differs')
        selected_profiles = [p for p in profiles['profiles'] if p['arm'] == arm]
        require({(p['threads'], p['repeat']) for p in selected_profiles} == {(8, 0), (60, 0)},
                arm + ': profile worker/repeat identity differs')
        for row in selected_profiles:
            require(row.get('complete') is True and not row.get('issues')
                    and row.get('source_commit') == commit and row.get('parsed_sample_lines', 0) > 0
                    and row.get('report_lost_samples') == [0],
                    arm + ': profile source, loss or parsing differs')
            matched = [s for s in sessions if s['session_path'] == row['profile_path']]
            require(len(matched) == 1 and matched[0]['collection'] == 'profile'
                    and matched[0]['arm'] == arm and matched[0]['threads'] == row['threads']
                    and matched[0]['repeat'] == row['repeat']
                    and matched[0]['session_sha256'] == row['input_sha256'].get('session.json'),
                    arm + ': profile analysis is not bound to its validated session')
    expected_logs = {str(Path(row['session_path']) / 'kernel.log') for row in sessions}
    require(len(expected_logs) == len(sessions), 'duplicate session paths')
    check_results = {}
    for arm, directory in checks.items():
        check_results[arm], probe_logs = validate_checks(base, arm, directory, production_by_arm[arm],
                                                        matrices[arm]['source_commit'], host['snapshot'])
        expected_logs.update(probe_logs)
    current = production_by_arm[args.current_arm]
    require(all(digest(relative_file(ROOT, name)) == sha for name, sha in current.items()),
            'maintained checkout production differs from current checked candidate')
    faults, logs = [], {}
    fault = re.compile(local['rt'].FAULT.pattern + r'|runtime error:|KASAN:|UBSAN:', re.I)
    for path in sorted(base.rglob('kernel.log')):
        matches = [line for line in path.read_text(errors='replace').splitlines() if fault.search(line)]
        name = str(path.relative_to(base))
        logs[name] = digest(path)
        if matches:
            faults.append(dict(path=name, matches=matches))
    require(expected_logs <= logs.keys() and not faults, 'missing kernel logs or retained runtime faults')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    preflight = (base / 'guest-before.log').read_text()
    require(re.findall(r'(?m)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', preflight) == [boot],
            'guest boot changed or preflight boot identity missing')
    validation = dict(schema=1, passed=True, full_suite=False, current_arm=args.current_arm,
                      source_revision=matrices[args.current_arm]['source_commit'],
                      checks_by_arm=check_results, matrices=matrices,
                      comparison_sha256=digest(base / 'comparison.json'),
                      profile_analysis_sha256=digest(base / 'profile-analysis.json'),
                      helper_sha256=digest(Path(__file__)),
                      note='Basic plus the twelve listed affected drivers and three live probes only. '
                           'Synthetic entry witnesses are not return proofs; diagnostic profiles are unscored.')
    save(base / 'validation.json', validation)
    # Close every output before the strict final idle check. This receipt is
    # subsequently accepted by the maintained grouped archiver on this boot.
    archive['idle'](base, local['idle'])
    health = dict(schema=1, idle=True, boot_id=boot, kernel_release=os.uname().release,
                  captured_unix=time.time(), snapshot=host['snapshot'], topology=host,
                  current_arm=args.current_arm, source_revision=validation['source_revision'],
                  per_session_kernel_faults=faults, kernel_logs=logs,
                  expected_kernel_logs=sorted(expected_logs),
                  additional_retained_kernel_logs=sorted(logs.keys() - expected_logs),
                  valid_timing_sessions=24 * len(args.arms), valid_profiles=2 * len(args.arms),
                  validation_sha256=digest(base / 'validation.json'),
                  comparison_sha256=validation['comparison_sha256'],
                  profile_analysis_sha256=validation['profile_analysis_sha256'],
                  guest_before_sha256=digest(base / 'guest-before.log'))
    save(base / 'health.json', health)
    print(json.dumps(dict(passed=True, idle=True, timing=health['valid_timing_sessions'],
                          profiles=health['valid_profiles'], kernel_logs=len(logs), faults=0,
                          checks=list(checks), current_arm=args.current_arm), sort_keys=True))


if __name__ == '__main__':
    main()
