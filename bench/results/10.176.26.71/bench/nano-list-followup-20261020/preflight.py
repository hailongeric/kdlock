#!/usr/bin/env python3
"""Check the retained 264-session list plan and original environment while idle."""
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
    for name in ('source-manifest', 'plan', 'host-state', 'output', 'planned-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    assert Path.cwd() == ROOT and os.geteuid() == 0
    assert os.uname().release == '6.1.159-kdclobber2'
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    manifest, plan, host = map(read, (args.source_manifest, args.plan, args.host_state))
    assert manifest['commit'] == plan['source_commit']
    assert sha(args.source_manifest) == plan['source_manifest_sha256']
    assert sys.executable == plan['python'] == shutil.which('python3')
    for path, expected in manifest['files'].items():
        assert not Path(path).is_absolute() and '..' not in Path(path).parts
        assert sha(ROOT/path) == expected, path
    historical = ROOT/plan['historical_plan']
    assert sha(historical) == plan['historical_plan_sha256']
    assert plan['phases']['timing'] == read(historical)['phases']['timing']
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    out, target = args.output.resolve(), args.planned_output.resolve()
    assert not out.exists() and not target.exists()
    assert not out.is_relative_to(ROOT) and not target.is_relative_to(ROOT)
    assert not out.is_relative_to(target) and not target.is_relative_to(out)
    archive['idle'](target, rt.idle)
    out.mkdir(parents=True)
    for path, name in ((args.source_manifest, 'committed-source.json'),
                       (args.plan, 'task-plan.json'), (args.host_state, 'host-state.json'),
                       (historical, 'historical-plan.json'), (Path(__file__), 'preflight.py')):
        shutil.copyfile(path, out/name)
    result = dict(passed=False, source_commit=manifest['commit'], measured_sessions=0,
                  script_sha256=sha(Path(__file__)), planned_output=str(target))
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
        tasks = plan['phases']['timing']
        assert len(tasks) == 10 and sum(t['expected_sessions'] for t in tasks) == 264
        observed = {}
        for task in tasks:
            text = rt.command([sys.executable, ROOT/task['runner'], *task['arguments'],
                               '--output', target/task['name'], '--dry-run'],
                              out/(task['name']+'.plan.json'), timeout=60)
            rows = json.loads(text)
            assert len(rows) == task['expected_sessions']
            assert len({r['name'] for r in rows}) == len(rows)
            family = {r['lock_kind'] for r in rows}
            assert len(family) == 1
            family = family.pop()
            arms = {'native', 'kdlock'} if family == 'rwsem' else {'native', 'tclock', 'kdlock'}
            assert {r['arm'] for r in rows} == arms
            assert {r['threads'] for r in rows} == {8, 60}
            assert {r['repeat'] for r in rows} == {0, 1, 2}
            for row in rows:
                assert row['workload'] in ('list', 'list-prefetch') and row['list_nodes'] in (16, 128)
                assert row['cpus'] == list(range(row['threads']))
                assert (row['collector_cpu'], row['duration_ms'], row['peak_window_ms'],
                        row['peak_settle_ms'], row['sample_ms'],
                        row['warmup_iterations_per_worker']) == (63, 2000, 300, 300, 10, 48000)
                assert not any(row.get(k) for k in
                               ('functional', 'pmu', 'perf_record', 'diagnostic', 'collector_shared'))
                if family in ('rwlock', 'rwsem'):
                    assert row['write_percent'] == 20 and row['post_work_rounds'] == 4
                    if row['arm'] == 'kdlock':
                        assert row['delegate'] and row['require_jit'] and row['provider_ubsan'] == 'off'
                if row['arm'] == 'kdlock':
                    assert row['spin_entry_ratio_limit'] == 2 and row['numa_policy'] == 'on'
                    assert row['delegation_batch_limit'] == 1024
                    if family in ('spin', 'mutex'):
                        assert row['spin_prefetch'] == 2 and row['kd_provider_ubsan'] == 'off'
                    if family == 'mutex':
                        assert row['caller_shell'] == 'mutex_public_direct'
                        assert row['cookie_storage'] == 'provider_acquisition_ledger'
            observed[task['name']] = dict(family=family, sessions=len(rows))
        for path, expected in manifest['files'].items():
            assert sha(ROOT/path) == expected, path
        archive['idle'](target, rt.idle)
        assert not target.exists()
        result.update(passed=True, idle=True, boot_id=environment['boot_id'],
                      planned_sessions=264, source_unchanged=True,
                      source_files=len(manifest['files']), tasks=observed)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out/'result.json', result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
