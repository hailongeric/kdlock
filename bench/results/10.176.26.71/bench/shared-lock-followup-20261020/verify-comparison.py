#!/usr/bin/env python3
"""Verify a completed shared-lock family in the idle original recovery VM."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix')
RETIRED = dict(state=2, modules=0, writers=0, frames=0)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True, help='completed supervisor output')
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--host-after', type=Path, required=True)
    parser.add_argument('--phase', choices=('rwsem', 'rwlock'), required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path.cwd() == ROOT and not base.is_relative_to(ROOT)
    assert not (base/'health.json').exists() and not (base/'preflight').exists()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archiver = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archiver['idle'](base, rt.idle)
    tasks, manifest, task_plan = (read(base/name) for name in
                                 ('tasks.json', 'committed-source.json', 'task-plan.json'))
    assert len(manifest['files']) == task_plan['source_files'] == 497
    expected = 756 if args.phase == 'rwsem' else 270
    group = 'rwsem-grid' if args.phase == 'rwsem' else 'rwlock-reference'
    assert tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle']
    assert tasks['phase'] == args.phase and len(tasks['tasks']) == 1
    task = tasks['tasks'][0]
    assert task['name'] == group and task['state'] == 'FINISHED' and task['exit_code'] == 0
    assert task['completed_sessions'] == expected
    assert Path(task['output']) == base/group
    assert tasks['source_commit'] == task_plan['source_commit'] == manifest['commit']
    assert sha(base/'run-tasks.py') == tasks['script_sha256'] == task_plan['supervisor_sha256']
    assert sha(base/'committed-source.json') == task_plan['source_manifest_sha256']
    source_checks = 0
    for path, digest in manifest['files'].items():
        assert not Path(path).is_absolute() and '..' not in Path(path).parts
        assert sha(ROOT/path) == digest, path
        source_checks += 1
    preflight = read(args.preflight/'result.json')
    assert preflight['passed'] and preflight['idle'] and preflight['source_unchanged']
    assert preflight['phase'] == args.phase and preflight['planned_sessions'] == expected
    assert preflight['source_commit'] == manifest['commit']
    assert read(args.preflight/'committed-source.json') == manifest
    assert read(args.preflight/'task-plan.json') == task_plan
    assert read(args.preflight/'host-state.json') == read(base/'host-before.json')
    assert sha(args.preflight/'preflight.py') == preflight['script_sha256']
    matrix = base/group
    source = read(matrix/'source-sha256.json')
    assert len(source) == task['committed_source_files']
    for path, digest in source.items():
        assert manifest['files'][path] == digest == sha(matrix/'source'/path), path
        source_checks += 1
    provider = matrix/'build/provider'
    preparation = read(provider/'manifest.json')
    assert preparation['complete']
    for path, digest in preparation['prepared'].items():
        assert sha(provider/path) == digest, path
        source_checks += 1
    for path, digest in preparation['production'].items():
        assert source[path] == digest, path
    for path, digest in preparation['observation'].items():
        assert source['bench/spin_cacheline/provider/'+path] == digest, path
    binaries = read(matrix/'binary-sha256.json')
    for path, digest in binaries.items():
        binary = Path(path)
        assert binary.is_absolute() and binary.is_relative_to(matrix)
        assert sha(binary) == digest, path
    plan, records = read(matrix/'plan.json'), read(matrix/'records.json')
    dry_plan = read(args.preflight/'planned-sessions.json')
    assert len(plan) == len(records) == len(dry_plan) == expected
    assert len({p['name'] for p in plan}) == expected
    environment = read(matrix/'environment.json')
    assert environment['kernel_identity']['ok']
    assert environment['kernel_identity']['running_build_id'] == \
        '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert tasks['boot_id'] == preflight['boot_id'] == environment['boot_policy']['boot_id'] == boot
    oracle = load_module('shared_lock_oracle', ROOT/'bench/rwlock_compare/oracle.py')
    fault_lines, retirements, classes = [], [], Counter()
    totals = Counter()
    for planned, dry, row in zip(plan, dry_plan, records):
        name = planned['name']
        assert Path(name).name == name
        assert all(planned[k] == v for k, v in dry.items())
        assert all(row[k] == v for k, v in planned.items())
        saved = read(matrix/name/'session.json')
        assert all(row[k] == v for k, v in saved.items())
        assert set(row)-set(saved) <= {'whole_ops_s', 'read_ops_s', 'write_ops_s', 'peak_ops_s'}
        assert row['execution_status'] == 'OK' and row['drained']
        assert not row.get('cleanup_error') and not row.get('diagnostic')
        assert not row['functional'] and row['lock_kind'] == args.phase
        m = row['measurement']
        assert m['complete'] and m['data_ok']
        assert oracle.validate(m, row) == m['peak'], name
        evidence = oracle.jit_evidence(
            row['jit_before'], row['jit_after'], m['writes'],
            backend=row['arm'], delegate=row['delegate'],
            completed=row['jit_complete_after']-row['jit_complete_before'])
        assert all(row[k] == v for k, v in evidence.items()), name
        classes[row['arm']+':'+row['jit_status']] += 1
        totals['operations'] += m['completed']
        totals['reads'] += m['reads']
        totals['writes'] += m['writes']
        totals['jit_entries'] += row['jit_bodies']
        totals['jit_completions'] += row['jit_completions']
        if row['arm'] == 'kdlock':
            assert row['retired'] == RETIRED, name
            assert row['published_before'] == row['published_after']
            publication = row['published_before']
            assert publication['source']['writers'] == publication['source']['frames'] == 0
            retirements.append(dict(name=name, retired=row['retired']))
        if row['arm'] == 'tclock':
            assert row['tclock_delegation_status'] == 'UNMEASURED'
        for line in (matrix/name/'kernel.log').read_text().splitlines():
            if rt.FAULT.search(line):
                fault_lines.append(dict(name=name, line=line))
    assert len(retirements) == (378 if args.phase == 'rwsem' else 90)
    assert not fault_lines, fault_lines
    scheduler = load_module('exact_environment', ROOT/'bench/mutex_api_compare/run.py')
    for name, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        assert sha(ORIGINAL/name) == digest, name
    topology_after = rt.capture_topology(list(range(60)))
    affinity = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {63})
        collector = rt.capture_topology([63])
    finally:
        os.sched_setaffinity(0, affinity)
    environment_after = dict(
        boot_id=boot, cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages={n: importlib.metadata.version(n)
                  for n in ('miasm', 'future', 'pyparsing', 'pyelftools')},
        python=sys.executable, snapshot_tag=environment['snapshot_tag'],
        collector_topology=collector)
    endpoints = {}
    for endpoint, host, guest, topology in [
            ('before', read(base/'host-before.json'), read(args.preflight/'environment.json'),
             read(args.preflight/'topology.json')),
            ('after', read(args.host_after), environment_after, topology_after)]:
        try:
            comparison = scheduler.same_environment(
                read(ORIGINAL/'host-state.json'), host, read(ORIGINAL/'environment.json'),
                guest, read(ORIGINAL/'topology.json'), topology)
            endpoints[endpoint] = dict(passed=True, comparison=comparison)
        except ValueError as error:
            endpoints[endpoint] = dict(passed=False, error=str(error))
    assert endpoints['before']['passed']
    # A later mismatch is retained as an open acceptance gap, never waived.
    shutil.copytree(args.preflight, base/'preflight')
    shutil.copyfile(args.host_after, base/'host-after.json')
    reference = base/'reference-environment'
    reference.mkdir()
    for name, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        shutil.copyfile(ORIGINAL/name, reference/name)
        assert sha(reference/name) == digest, name
    rt.write_json(base/'environment-after.json', environment_after)
    rt.write_json(base/'topology-after.json', topology_after)
    shutil.copyfile(Path(__file__), base/'verify-comparison.py')
    archiver['idle'](base, rt.idle)
    health = dict(idle=True, boot_id=boot, source_commit=manifest['commit'],
                  checked_unix=time.time(), sessions=expected, functionally_valid=expected,
                  drained=expected, source_hashes_checked=source_checks,
                  binary_hashes_checked=len(binaries), exact_retirements=retirements,
                  per_session_kernel_faults=fault_lines, execution_classes=dict(classes),
                  totals=dict(totals), host_endpoints=endpoints,
                  runner_parity=read(matrix/'parity.json')['status'],
                  p95_latency='UNMEASURED', within_run_host_interference='UNMEASURED',
                  overall_acceptance='OPEN', verifier_sha256=sha(Path(__file__)),
                  reference_environment_sha256=scheduler.REPLAY_ENVIRONMENT_SHA256,
                  scope='Completed family correctness, exact retirement and input preservation. '
                        'Performance ratios, variance and archive integrity require separate review; '
                        'a failed host endpoint remains failed.')
    with (base/'health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in health.items() if k != 'exact_retirements'}, sort_keys=True))


if __name__ == '__main__':
    main()
