#!/usr/bin/env python3
"""Verify resident-list evidence in the idle original VM, preserving failures."""
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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'preflight', 'host-after'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--stopped-rwlock', action='store_true',
                   help='Audit the exact timing-1 failure; never accept it as a completed run.')
    args = p.parse_args()
    base = args.base.resolve()
    assert Path.cwd() == ROOT and os.geteuid() == 0
    assert os.uname().release == '6.1.159-kdclobber2' and not base.is_relative_to(ROOT)
    assert not (base/'health.json').exists() and not (base/'preflight').exists()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](base, rt.idle)
    tasks, manifest, plan = (read(base/n) for n in
                             ('tasks.json', 'committed-source.json', 'task-plan.json'))
    stopped = args.stopped_rwlock
    if stopped:
        assert base.name == 'timing-1'
        assert tasks['state'] == 'FAILED' and tasks['passed'] is False and tasks['final_idle'] is False
        assert tasks['failed_task'] == 'rwlock-w20' and len(tasks['tasks']) == 9
    else:
        assert tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle']
        assert len(tasks['tasks']) == 10
    assert tasks['phase'] == 'timing' and len(plan['phases']['timing']) == 10
    assert tasks['source_commit'] == manifest['commit'] == plan['source_commit']
    assert sha(base/'committed-source.json') == plan['source_manifest_sha256']
    assert sha(base/'run-tasks.py') == tasks['script_sha256'] == plan['supervisor_sha256']
    assert len(manifest['files']) == plan['source_files'] == 497
    source_hashes, binary_hashes, compiled_audits = 0, 0, 0
    for path, digest in manifest['files'].items():
        assert sha(ROOT/path) == digest, path
        source_hashes += 1
    pf = read(args.preflight/'result.json')
    assert pf['passed'] and pf['idle'] and pf['source_unchanged'] and pf['planned_sessions'] == 264
    assert pf['planned_output'] == str(base) and pf['source_commit'] == manifest['commit']
    assert read(args.preflight/'committed-source.json') == manifest
    assert read(args.preflight/'task-plan.json') == plan
    assert read(args.preflight/'host-state.json') == read(base/'host-before.json')
    assert sha(args.preflight/'preflight.py') == pf['script_sha256']
    rw_oracle = load('list_rw_oracle', ROOT/'bench/rwlock_compare/oracle.py')
    faults, retired, images, results, failures, not_run = [], [], [], [], [], []
    totals, classes = Counter(), Counter()
    for task, planned_task in zip(tasks['tasks'], plan['phases']['timing']):
        name = task['name']
        assert name == planned_task['name'] and Path(task['output']) == base/name
        failed_child = stopped and name == 'rwlock-w20'
        assert task['state'] == 'FINISHED' and task['exit_code'] == int(failed_child)
        if failed_child:
            assert 'completed_sessions' not in task and 'committed_source_files' not in task
        else:
            assert task['completed_sessions'] == planned_task['expected_sessions']
        child = base/name
        source = read(child/'source-sha256.json')
        for path, digest in source.items():
            assert sha(child/'source'/path) == digest, path
            if path in manifest['files']:
                assert manifest['files'][path] == digest, path
            source_hashes += 1
        overlay = 'bench/spin_cacheline/.build/provider/'
        extra = {p: h for p, h in source.items() if p not in manifest['files']}
        provider = child/'source'/overlay if extra else child/'build/provider'
        prepared = read(provider/'manifest.json')
        assert prepared['complete']
        if extra:
            expected = {overlay+p: h for p, h in prepared['prepared'].items()}
            expected[overlay+'manifest.json'] = sha(provider/'manifest.json')
            assert extra == expected and len(extra) == task['reconstructed_provider_files']
        assert len(source)-len(extra) == (248 if failed_child else task['committed_source_files'])
        if failed_child:
            assert not extra and len(prepared['prepared']) == 93
        for path, digest in prepared['prepared'].items():
            assert sha(provider/path) == digest, path
            source_hashes += 1
        for category, prefix in [('production', ''), ('observation', 'bench/spin_cacheline/provider/')]:
            for path, digest in prepared[category].items():
                assert source[prefix+path] == digest, path
        binaries = read(child/'binary-sha256.json')
        for path, digest in binaries.items():
            binary = Path(path)
            if not binary.is_relative_to(child):
                assert binary.is_relative_to(ROOT)
                binary = child/'binaries'/binary.name
            assert sha(binary) == digest, path
            binary_hashes += 1
        cold = list(child.glob('list-audit-*/audit.json'))
        assert len(cold) == (8 if name == 'rwsem-w20' else 12 if name == 'rwlock-w20' else 3)
        for path in cold:
            audit = read(path)
            assert audit['sha256'] in binaries.values()
            assert audit['functions']
            for function in audit['functions'].values():
                assert bool(function['hints']) == audit['prefetch']
                assert all(h['mnemonic'] in ('prefetchnta', 'prefetcht0', 'prefetcht1', 'prefetcht2')
                           for h in function['hints'])
            compiled_audits += 1
        specs, records = read(child/'plan.json'), read(child/'records.json')
        dry = read(args.preflight/(name+'.plan.json'))
        assert len(specs) == len(records) == len(dry) == planned_task['expected_sessions']
        completed = 0
        env = read(child/'environment.json')
        assert env['kernel_identity']['ok'] and env['kernel_identity']['running_build_id'] == \
            '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
        for spec, saved_plan, row in zip(specs, dry, records):
            tag = name+'/'+spec['name']
            assert all(spec[k] == v for k, v in saved_plan.items())
            assert all(row[k] == v for k, v in spec.items())
            if failed_child and row['execution_status'] == 'NOT_RUN':
                assert completed == 3 and not (child/spec['name']).exists()
                not_run.append(name+'/'+spec['name'])
                continue
            completed += 1
            failed_session = failed_child and completed == 3
            saved = read(child/spec['name']/'session.json')
            assert all(row[k] == v for k, v in saved.items())
            assert row['execution_status'] == ('NO_JIT' if failed_session else 'OK')
            assert row['drained'] and not row.get('cleanup_error')
            if failed_session:
                assert spec['name'] == 'list-n16-kdlock-w020-t08-r00'
                assert row['error'] == 'required complete KD body did not execute'
                assert row['require_jit'] is True and row['helper_waves'] == 0
                failures.append(dict(path=tag, status=row['execution_status'], error=row['error']))
                assert read(child/'failure.json') == dict(status='NO_JIT', error=row['error'])
            assert not any(row.get(k) for k in ('functional', 'diagnostic', 'pmu', 'perf_record'))
            assert row['workload'] in ('list', 'list-prefetch') and row['list_nodes'] in (16, 128)
            m = row['measurement']
            shared = row['lock_kind'] in ('rwlock', 'rwsem')
            variant = row['variant'] if shared else row['arm']
            compiled = read(child/('list-audit-'+variant)/'audit.json')
            assert compiled['prefetch'] == (row['workload'] == 'list-prefetch')
            assert m['schema'] == (1 if shared else 2)
            assert m['complete'] is True and m['data_ok'] is True
            raw = read(child/spec['name']/'measure.json')
            assert {k: v for k, v in m.items() if k != 'peak'} == \
                {k: v for k, v in raw.items() if k != 'peak'}
            peak = rw_oracle.validate(m, row) if shared else rt.validate_timed_measurement(m, row)
            assert peak == m['peak'], tag
            operations = m['writes'] if shared else m['completed']
            entries = row['jit_bodies']
            if row['arm'] == 'tclock' and not shared:
                # This backend does not load KD or expose a KD completion
                # counter. Never use this exception for a KD observation.
                assert 'jit_completions' not in row and row['jit_status'] == 'NOT_APPLICABLE'
                completions = 0
                assert all(row[k]['quiescent'] == 1 for k in
                           ('tclock_before', 'tclock_after', 'tclock_drained'))
                if row['lock_kind'] == 'mutex':
                    delegated = row['tclock_after']['delegated']-row['tclock_before']['delegated']
                    assert 0 < delegated <= m['completed'] and row['delegated_bodies'] == delegated
                    assert row['delegation_status'] == 'PASS'
                else:
                    assert row['delegated_bodies'] is None and row['delegation_status'] == 'UNMEASURED'
            else:
                completions = row['jit_completions']
                if row['arm'] == 'tclock':
                    assert shared and row['tclock_delegation_status'] == 'UNMEASURED'
                    assert all(row[k]['quiescent'] == 1 for k in
                               ('tclock_before', 'tclock_after', 'tclock_drained'))
            assert 0 <= completions <= entries <= operations
            kind = 'NATIVE'
            if row['arm'] == 'kdlock':
                assert entries == row['jit_after']-row['jit_before']
                key = 'jit_complete' if shared else 'jit_completions'
                assert completions == row[key+'_after']-row[key+'_before']
                kind = 'RETURNED_JIT' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT'
                assert kind != 'PARTIAL_JIT'
                required = shared or row['lock_kind'] == 'mutex' or row['threads'] >= 20
                if failed_session:
                    assert required and entries == completions == 0 and kind == 'NO_JIT'
                else:
                    assert not required or completions > 0
                assert row['retired'] == RETIRED
                retired.append(dict(task=name, name=row['name'], retired=row['retired']))
                publication = row['published_before']
                assert publication == row['published_after']
                assert publication['source']['state'] == publication['source']['writers'] == \
                    publication['source']['frames'] == 0
                image = row['list_image_audit']
                prefix = child/row['name']
                assert image == read(prefix/'list-image/audit.json')
                assert image['byte_for_byte_match'] and image['prefetch'] == \
                    (row['workload'] == 'list-prefetch')
                assert bool(image['hints']) == image['prefetch']
                entry = publication['entry']
                workspace = prefix/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
                assert sha(prefix/'list-image/loaded.bin') == image['loaded_sha256'] == \
                    image['uploaded_sha256'] == sha(workspace/'jit.bin')
                assert sha(workspace/'jit.o') == image['jit_object_sha256']
                for filename, digest in publication['images'].items():
                    assert sha(workspace/filename) == digest
                images.append(dict(task=name, name=row['name'], loaded_sha256=image['loaded_sha256']))
            else:
                assert entries == completions == 0
            totals['operations'] += m['completed']
            totals['writes'] += operations
            totals['reads'] += m['reads'] if shared else 0
            totals['jit_entries'] += entries
            totals['jit_completions'] += completions
            classes[row['lock_kind']+':'+row['arm']+':'+kind] += 1
            for line in (child/row['name']/'kernel.log').read_text().splitlines():
                if rt.FAULT.search(line):
                    faults.append(dict(session=tag, line=line))
        assert completed == (3 if failed_child else planned_task['expected_sessions'])
        results.append(dict(task=name, sessions=completed, source_files=len(source),
                            binary_files=len(binaries), compiled_list_audits=len(cold)))
    if stopped:
        remaining = plan['phases']['timing'][-1]
        assert remaining['name'] == 'rwsem-w20' and not (base/'rwsem-w20').exists()
        not_run += ['rwsem-w20/'+s['name'] for s in read(args.preflight/'rwsem-w20.plan.json')]
    count = 147 if stopped else 264
    assert len(retired) == len(images) == (49 if stopped else 96)
    assert sum(r['sessions'] for r in results) == count
    assert compiled_audits == (36 if stopped else 44) and not faults
    assert len(failures) == int(stopped) and len(not_run) == (117 if stopped else 0)
    assert len(set(not_run)) == len(not_run)
    scheduler = load('list_environment', ROOT/'bench/mutex_api_compare/run.py')
    for name, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        assert sha(ORIGINAL/name) == digest
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == tasks['boot_id'] == pf['boot_id']
    topology = rt.capture_topology(list(range(60)))
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {63})
        collector = rt.capture_topology([63])
    finally:
        os.sched_setaffinity(0, previous)
    environment = dict(boot_id=boot, cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages={p: importlib.metadata.version(p) for p in ('miasm', 'future', 'pyparsing', 'pyelftools')},
        python=sys.executable, snapshot_tag=env['snapshot_tag'], collector_topology=collector)
    endpoints = {}
    for label, host, guest, topo in (
        ('before', read(base/'host-before.json'), read(args.preflight/'environment.json'),
         read(args.preflight/'topology.json')),
        ('after', read(args.host_after), environment, topology)):
        try:
            result = scheduler.same_environment(read(ORIGINAL/'host-state.json'), host,
                read(ORIGINAL/'environment.json'), guest, read(ORIGINAL/'topology.json'), topo)
            endpoints[label] = dict(passed=True, comparison=result)
        except ValueError as error:
            endpoints[label] = dict(passed=False, error=str(error))
    assert endpoints['before']['passed']
    shutil.copytree(args.preflight, base/'preflight')
    shutil.copyfile(args.host_after, base/'host-after.json')
    shutil.copyfile(Path(__file__), base/'verify.py')
    reference = base/'reference-environment'
    reference.mkdir()
    for name in scheduler.REPLAY_ENVIRONMENT_SHA256:
        shutil.copyfile(ORIGINAL/name, reference/name)
    rt.write_json(base/'environment-after.json', environment)
    rt.write_json(base/'topology-after.json', topology)
    archive['idle'](base, rt.idle)
    health = dict(idle=True, boot_id=boot, source_commit=manifest['commit'],
        checked_unix=time.time(), sessions=count, functionally_valid=count-int(stopped), drained=count,
        planned_sessions=264, business_oracles_valid=count, strict_failures=failures, not_run=not_run,
        supervisor_state=tasks['state'], stopped_rwlock=stopped,
        tasks=results, source_hashes_checked=source_hashes, binary_hashes_checked=binary_hashes,
        compiled_list_audits=compiled_audits, loaded_images=images, exact_retirements=retired,
        per_session_kernel_faults=faults, totals=dict(totals), execution_classes=dict(classes),
        host_endpoints=endpoints, reference_environment_sha256=scheduler.REPLAY_ENVIRONMENT_SHA256,
        verifier_sha256=sha(Path(__file__)), overall_acceptance='OPEN',
        control_completion_scope='TCLock exclusive has no KD completion counter; its native mutex delegation is checked separately.',
        p95_latency='UNMEASURED', within_run_host_interference='UNMEASURED')
    rt.write_json(base/'health.json', health)
    print(json.dumps({k: v for k, v in health.items()
                      if k not in ('loaded_images', 'exact_retirements')}, sort_keys=True))


if __name__ == '__main__':
    main()
