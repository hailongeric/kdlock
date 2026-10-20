#!/usr/bin/env python3
"""Validate fresh three-backend evidence in the idle VM before grouped archiving."""
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
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020')
COLLECTIONS = ('c01', 'c08', 'rcuht', 'seek-set', 'seek-end', 'pipebytes', 'pipecap')
RUNNER_TESTS = ('bench/tclock_compare/test_direct.py', 'bench/spin_cacheline/test_peak.py',
                'bench/real_api/test_plan.py', 'bench/real_api/test_report.py')


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, data):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def relative_file(base, name):
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe relative path: ' + name)
    path = base / relative
    require(path.is_file() and path.resolve().is_relative_to(base.resolve()), 'missing/outside file: ' + str(path))
    return path


def production(manifest):
    suffixes = ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
    return {k: v for k, v in manifest.items() if k.startswith(('include/', 'kernel_module/'))
            and not k.endswith('.mod.c') and (Path(k).suffix in suffixes or Path(k).name == 'Makefile')}


def topology(base):
    before, after = (read(base / name) for name in ('host-before.json', 'host-after.json'))
    require(before.get('snapshot_listed') and after.get('snapshot_listed')
            and before['recovery_snapshot'] == after['recovery_snapshot'], 'real recovery snapshot missing/changed')
    require(before['cpufreq'] == after['cpufreq'] and before['numa'] == after['numa'], 'host frequency/NUMA topology changed')
    require(len(before['qemu']) == len(after['qemu']) == 1, 'ambiguous QEMU identity')
    left, right = before['qemu'][0], after['qemu'][0]
    require(left['pid'] == right['pid'] and left['args'] == right['args'], 'QEMU identity changed')
    bt, at = ({t['tid']: t for t in q['tasks']} for q in (left, right))
    require({k: v for k, v in bt.items() if v['comm'].startswith('CPU ')} ==
            {k: v for k, v in at.items() if v['comm'].startswith('CPU ')}, 'vCPU pins changed')
    require(all(bt[k] == at[k] for k in bt.keys() & at.keys()), 'retained host task pins changed')
    require(all(t['affinity'] == [63] for t in [*bt.values(), *at.values()] if not t['comm'].startswith('CPU ')),
            'service thread outside collector CPU')
    return dict(snapshot=after['recovery_snapshot'], unchanged=True,
        before_sha256=digest(base / 'host-before.json'), after_sha256=digest(base / 'host-after.json'),
        added_service_threads=[at[k] for k in sorted(at.keys() - bt.keys())],
        removed_service_threads=[bt[k] for k in sorted(bt.keys() - at.keys())])


def validate_checks(base, prod, commit, snapshot):
    folder = base / 'checks'
    result, commands = read(folder / 'result.json'), read(folder / 'commands.json')
    require(result.get('passed') is True and result.get('final_idle') is True and result.get('source_unchanged') is True
        and result.get('full_suite') is False and result.get('unit_basic') == 2 and result.get('unit_drivers') == []
        and result.get('runner_tests') == list(RUNNER_TESTS) and result.get('source_revision') == commit
        and result.get('snapshot_tag') == snapshot and result.get('script_sha256') == digest(base / 'run-checks.py'),
        'basic/affected check scope/source/result differs')
    require(commands == result.get('commands'), 'check command receipts differ')
    python = commands[0].get('argv', [''])[0]
    require(Path(python).name.startswith('python'), 'missing Python command')
    expected = [
        ('dependencies', [python, '-m', 'pip', 'check'], ROOT, 60),
        ('provider', ['make', '-C', 'kernel_module', 'KDIR=/root/linux-6.1.159-kdclobber2', 'W=1', 'UBSAN_SANITIZE=n'], folder / 'source', 240),
        ('daemon', ['make', '-C', 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'], folder / 'source', 60),
        ('unit', ['make', '-C', 'tests/unit', 'run', 'PY_TESTS='], folder / 'source', 300)]
    expected += [(Path(path).stem, [python, path], folder / 'source', 180) for path in RUNNER_TESTS]
    require(len(commands) == len(expected), 'check command count differs')
    logs = {}
    for row, (name, argv, cwd, timeout) in zip(commands, expected):
        require(row.get('name') == name and row.get('argv') == argv and row.get('cwd') == str(cwd)
            and row.get('timeout_seconds') == timeout and row.get('exit_code') == 0
            and row.get('finished_unix', 0) >= row.get('started_unix', 1), 'unexpected/failed check: ' + name)
        logs[name] = digest(folder / (name + '.log'))
    unit = (folder / 'unit.log').read_text()
    require(re.findall(r'Unit tests: (\d+) passed, (\d+) failed', unit) == [('2', '0')]
        and '[PASS] test_control_call' in unit and '[PASS] test_daemon_policy' in unit, 'basic pass evidence missing')
    tests = {}
    for path in RUNNER_TESTS:
        name = Path(path).stem
        text = (folder / (name + '.log')).read_text()
        module = ast.parse((folder / 'source' / path).read_text())
        count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(module))
        require(count > 0 and re.findall(r'(?m)^Ran (\d+) tests? in ', text) == [str(count)]
                and re.search(r'(?m)^OK$', text) and 'skipped=' not in text, 'runner count/pass/no-skip differs: ' + name)
        tests[name] = dict(path=path, tests=count, passed=True, log_sha256=logs[name])
    manifest = read(folder / 'source-sha256.json')
    require(production(manifest) == prod, 'checked and measured production differ')
    for name, sha in manifest.items():
        require(digest(relative_file(folder / 'source', name)) == sha, 'checked frozen source changed: ' + name)
    provider = (folder / 'provider.log').read_text(errors='replace')
    return dict(passed=True, source_commit=commit, unit_basic=2, unit_passed=2, unit_failed=0,
        unit_affected_drivers=[], runner_tests=tests, full_suite=False, live_probes_rerun=False,
        source_manifest_sha256=digest(folder / 'source-sha256.json'), frozen_source_files=len(manifest),
        source_unchanged=True, result_sha256=digest(folder / 'result.json'), commands_sha256=digest(folder / 'commands.json'),
        logs_sha256=logs, provider_warning_lines=sum(bool(re.search(r'\bwarning:', line, re.I)) for line in provider.splitlines()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    require(Path.cwd() == ROOT and os.uname().release == '6.1.159-kdclobber2' and os.geteuid() == 0,
            'run from the idle recovery VM checkout')
    base = args.base.resolve(strict=True)
    require(base.is_dir() and not base.is_relative_to(ROOT), 'use an external evidence root')
    sys.dont_write_bytecode = True
    local = runpy.run_path(str(ROOT / 'tests/kernel/mutex/local/run.py'))
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))
    archive['idle'](base, local['idle'])
    host = topology(base)
    comparison = read(base / 'comparison.json')
    require(comparison.get('complete') is True and not comparison.get('issues') and
        comparison.get('analysis_helper') == dict(file='summarize.py', sha256=digest(base / 'summarize.py')),
        'summary incomplete/helper binding differs')
    rows = comparison['sessions']
    require(len(rows) == 567 and all(r.get('valid') is True for r in rows)
        and Counter((r['collection'], r['backend']) for r in rows) ==
        Counter({(c, b): 27 for c in COLLECTIONS for b in ('native', 'tclock', 'kdlock')}), 'session validity/inventory differs')
    require(all(r['score_eligible'] is (not r['retained_no_jit_rejection']) for r in rows), 'NO_JIT rejection scored or valid timing excluded')
    matrix = read(base / 'current/matrix.json')
    commit = matrix.get('source_commit', '')
    require(re.fullmatch(r'[0-9a-f]{7,40}', commit) and comparison.get('source_commit') == commit,
            'concrete source revision missing/different')
    require(matrix.get('version') == 'current' and matrix.get('passed') is True and matrix.get('final_idle') is True
        and matrix.get('plain_sessions') == 567 and matrix.get('profile_sessions') == 0 and matrix.get('full_suite') is False
        and matrix.get('snapshot_tag') == host['snapshot'] and matrix.get('script_sha256') == digest(base / 'run-matrix.py'),
        'matrix scope/snapshot/result/helper binding differs')
    collector = runpy.run_path(str(base / 'run-matrix.py'))
    receipts = matrix['commands']
    require(len(receipts) == 7, 'collection receipt count differs')
    prod = None
    manifests = {}
    for index, name in enumerate(COLLECTIONS):
        receipt = read(base / 'current' / (name + '-command.json'))
        argv = receipt.get('argv', [])
        require(argv and Path(argv[0]).name.startswith('python'), 'collection Python missing')
        expected_name, expected_argv = collector['commands'](argv[0])[index]
        expected_argv += ['--output', str(base / 'current' / name)]
        require(expected_name == name and receipt == receipts[index] and argv == expected_argv
            and receipt.get('collection') == name and receipt.get('source_commit') == commit and receipt.get('cwd') == str(ROOT)
            and receipt.get('expected_sessions') == 81 and receipt.get('timeout_seconds') == 1800
            and receipt.get('finished_unix', 0) >= receipt.get('started_unix', 1) and receipt.get('idle_after') is True,
            name + ': exact command receipt differs')
        validated = collector['validate_records'](base / 'current' / name, name, receipt['exit_code'])
        require(all(receipt.get(k) == v for k, v in validated.items()), name + ': complete drain/verdict receipt differs')
        folder = base / 'current' / name
        manifest = read(folder / 'source-sha256.json')
        current_prod = production(manifest)
        require(current_prod and any(n.endswith('.inc') for n in current_prod), name + ': missing private production inputs')
        if prod is None:
            prod = current_prod
        require(current_prod == prod, name + ': production source changed')
        manifests[name] = dict(source_manifest_sha256=digest(folder / 'source-sha256.json'),
            records_sha256=digest(folder / 'records.json'), command_sha256=digest(base / 'current' / (name + '-command.json')))
    checks = validate_checks(base, prod, commit, host['snapshot'])
    require(all(digest(relative_file(ROOT, name)) == sha for name, sha in prod.items()), 'current production differs from checked frozen source')
    expected_logs = {str(Path(r['session_path']) / 'kernel.log') for r in rows}
    require(len(expected_logs) == 567, 'duplicate session paths')
    fault = re.compile(local['rt'].FAULT.pattern + r'|runtime error:|KASAN:|UBSAN:', re.I)
    logs, faults = {}, []
    for path in sorted(base.rglob('kernel.log')):
        name = str(path.relative_to(base))
        matches = [line for line in path.read_text(errors='replace').splitlines() if fault.search(line)]
        logs[name] = digest(path)
        if matches:
            faults.append(dict(path=name, matches=matches))
    require(expected_logs <= logs.keys() and not faults, 'missing kernel logs or runtime fault')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    guest_receipts = {}
    for name in ('guest-during.log', 'guest-after.log'):
        text = (base / name).read_text()
        require(re.findall(r'(?m)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', text) == [boot]
            and '6.1.159-kdclobber2' in text and 'nokaslr' in text and 'nopvspin' in text
            and '(voluntary)' in text and re.search(r'(?m)^0-63$', text),
            'guest during/after boot or runtime policy differs: ' + name)
        guest_receipts[name] = digest(base / name)
    validation = dict(schema=1, passed=True, full_suite=False, source_revision=commit, checks=checks,
        matrix_sha256=digest(base / 'current/matrix.json'), collection_manifests=manifests,
        execution_status_counts=comparison['execution_status_counts'], execution_class_counts=comparison['execution_class_counts'],
        score_eligible_sessions=comparison['score_eligible_sessions'], retained_no_jit_rejections=comparison['retained_no_jit_rejections'],
        comparison_sha256=digest(base / 'comparison.json'), helper_file=Path(__file__).name, helper_sha256=digest(Path(__file__)),
        note='Two fresh basic programs and four benchmark test programs; no protocol-driver/live-probe rerun. '
             'Complete safely drained inventory preserves synthetic NO_JIT rejection verdicts; these are excluded from scores.')
    save(base / 'validation.json', validation)
    archive['idle'](base, local['idle'])
    health = dict(schema=1, idle=True, boot_id=boot, kernel_release=os.uname().release, captured_unix=time.time(),
        snapshot=host['snapshot'], topology=host, source_revision=commit, per_session_kernel_faults=faults,
        kernel_logs=logs, expected_kernel_logs=sorted(expected_logs), additional_retained_kernel_logs=sorted(logs.keys() - expected_logs),
        collected_sessions=567, valid_timing_sessions=comparison['score_eligible_sessions'], valid_profiles=0,
        retained_no_jit_rejections=comparison['retained_no_jit_rejections'], validation_sha256=digest(base / 'validation.json'),
        comparison_sha256=validation['comparison_sha256'], guest_receipts_sha256=guest_receipts,
        guest_preflight_note='Initial preflight was observed in tool output; persisted runtime receipts begin during collection and after completion.')
    save(base / 'health.json', health)
    print(json.dumps(dict(passed=True, idle=True, sessions=567, score_eligible=comparison['score_eligible_sessions'],
        rejected_no_jit=comparison['retained_no_jit_rejections'], kernel_logs=len(logs), faults=0)))


if __name__ == '__main__':
    main()
