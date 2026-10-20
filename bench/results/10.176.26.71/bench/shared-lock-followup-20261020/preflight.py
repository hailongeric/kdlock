#!/usr/bin/env python3
"""Check the original current environment and exact shared-lock plan in the VM."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path('/root/host_fs/kdlock')
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--phase', choices=('rwsem', 'rwlock'), required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert Path.cwd() == ROOT and os.geteuid() == 0
    assert os.uname().release == '6.1.159-kdclobber2'
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    manifest, plan, host = map(read, (args.source_manifest, args.plan, args.host_state))
    assert manifest['commit'] == plan['source_commit']
    assert sys.executable == plan['python'] == shutil.which('python3')
    for path, expected in manifest['files'].items():
        assert not Path(path).is_absolute() and '..' not in Path(path).parts
        assert sha(ROOT/path) == expected, path
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archiver = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    out = args.output.resolve()
    assert not out.exists() and not out.is_relative_to(ROOT)
    archiver['idle'](out, rt.idle)
    out.mkdir(parents=True)
    for path, name in ((args.source_manifest, 'committed-source.json'),
                       (args.plan, 'task-plan.json'), (args.host_state, 'host-state.json'),
                       (Path(__file__), 'preflight.py')):
        shutil.copyfile(path, out/name)
    result = dict(passed=False, phase=args.phase, source_commit=manifest['commit'],
                  measured_sessions=0, script_sha256=sha(Path(__file__)))
    try:
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(host['captured_utc'])).total_seconds()
        assert 0 <= age <= 300 and host['pins_verified'] and host['snapshot_listed']
        assert host['recovery_snapshot'] == os.environ['KDLOCK_SNAPSHOT_TAG']
        spec = importlib.util.spec_from_file_location('exact_environment',
                                                      ROOT/'bench/mutex_api_compare/run.py')
        scheduler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scheduler)
        for name, expected in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
            assert sha(ORIGINAL/name) == expected, name
        topology = rt.capture_topology(list(range(60)))
        affinity = os.sched_getaffinity(0)
        try:
            os.sched_setaffinity(0, {63})
            collector = rt.capture_topology([63])
        finally:
            os.sched_setaffinity(0, affinity)
        environment = dict(
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            cmdline=Path('/proc/cmdline').read_text().strip(),
            preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
            packages={n: importlib.metadata.version(n)
                      for n in ('miasm', 'future', 'pyparsing', 'pyelftools')},
            python=sys.executable, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],
            collector_topology=collector)
        rt.write_json(out/'environment.json', environment)
        rt.write_json(out/'topology.json', topology)
        comparison = scheduler.same_environment(
            read(ORIGINAL/'host-state.json'), host, read(ORIGINAL/'environment.json'),
            environment, read(ORIGINAL/'topology.json'), topology)
        rt.write_json(out/'environment-comparison.json', comparison)
        tasks = plan['phases'][args.phase]
        assert len(tasks) == 1
        task = tasks[0]
        assert task['runner'] == 'bench/rwlock_compare/run.py'
        text = rt.command([sys.executable, ROOT/task['runner'], *task['arguments'], '--dry-run'],
                          out/'planned-sessions.json', timeout=60)
        rows = json.loads(text)
        assert len(rows) == task['expected_sessions'] == (756 if args.phase == 'rwsem' else 270)
        assert len({r['name'] for r in rows}) == len(rows)
        arms = {'native', 'kdlock'} if args.phase == 'rwsem' else {'native', 'tclock', 'kdlock'}
        threads = set(range(1, 9)) | set(range(12, 61, 4)) if args.phase == 'rwsem' else {1, 8, 32, 36, 60}
        assert {r['arm'] for r in rows} == arms and {r['threads'] for r in rows} == threads
        assert {(r['workload'], r['cachelines']) for r in rows} == {
            ('cacheline', 1), ('cacheline', 8), ('rcuht', 0)}
        assert {r['write_percent'] for r in rows} == {1, 20}
        assert {r['repeat'] for r in rows} == {0, 1, 2}
        for row in rows:
            assert row['lock_kind'] == args.phase and row['cpus'] == list(range(row['threads']))
            assert (row['collector_cpu'], row['duration_ms'], row['peak_window_ms'],
                    row['peak_settle_ms'], row['sample_ms'], row['post_work_rounds'],
                    row['warmup_iterations_per_worker']) == (63, 2000, 300, 300, 10, 4, 48000)
            assert not row['functional'] and row['provider_ubsan'] == 'off'
            if row['arm'] == 'kdlock':
                assert row['delegate'] and row['spin_entry_ratio_limit'] == 2
                assert row['delegation_batch_limit'] == 1024 and row['numa_policy'] == 'on'
        for path, expected in manifest['files'].items():
            assert sha(ROOT/path) == expected, path
        archiver['idle'](out, rt.idle)
        result.update(passed=True, idle=True, boot_id=environment['boot_id'],
                      planned_sessions=len(rows), source_unchanged=True,
                      source_files=len(manifest['files']))
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out/'result.json', result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
