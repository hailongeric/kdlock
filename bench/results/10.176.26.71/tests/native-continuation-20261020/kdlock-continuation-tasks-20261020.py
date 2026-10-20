#!/usr/bin/env python3
"""Run a reviewed, serialized VM task plan without inferring drain on failure."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time


ROOT = Path('/root/host_fs/kdlock')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase')
    args = parser.parse_args()
    if (os.geteuid() != 0 or os.uname().release != '6.1.159-kdclobber2'
            or Path.cwd() != ROOT or os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1'):
        raise RuntimeError('run only in the confirmed recovery VM checkout')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    plan = json.loads(args.plan.read_text())
    manifest = json.loads(args.source_manifest.read_text())
    host = json.loads(args.host_state.read_text())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(host['captured_utc'])).total_seconds()
    if (not host['pins_verified'] or not host['snapshot_listed'] or not 0 <= age <= 300
            or host['recovery_snapshot'] != os.environ.get('KDLOCK_SNAPSHOT_TAG')):
        raise RuntimeError('a fresh verified host placement/snapshot receipt is required')
    if plan['source_commit'] != manifest['commit'] or str(ROOT) != plan['cwd']:
        raise RuntimeError('source identities differ')
    if Path(sys.executable) != Path(plan['python']):
        raise RuntimeError('use the pinned plan interpreter')
    tasks = plan['phases'][args.phase] if args.phase else plan['tasks']
    if not tasks:
        raise RuntimeError('empty task plan')
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise RuntimeError('use a new external evidence directory')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def verify():
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot:
            raise RuntimeError('guest boot changed')
        for relative, expected in manifest['files'].items():
            path = Path(relative)
            if path.is_absolute() or '..' in path.parts or digest(ROOT / path) != expected:
                raise RuntimeError('source changed: ' + relative)
        # Child runners discover source recursively. Reject stale source
        # candidates before their snapshots/builds, even if tracked hashes match.
        extra = []
        for directory in manifest['directories']:
            for path in (ROOT / directory).rglob('*'):
                relative = path.relative_to(ROOT)
                if (not path.is_file() or any(part.startswith('.') or part == '__pycache__'
                                              for part in relative.parts)
                        or path.name.endswith('.mod.c')):
                    continue
                candidate = (path.suffix in ('.c', '.h', '.inc', '.S', '.def', '.py',
                                             '.json', '.patch', '.md')
                             or path.name in ('Makefile', 'requirements.txt', 'guest.config'))
                if candidate and str(relative) not in manifest['files']:
                    extra.append(str(relative))
        if extra:
            raise RuntimeError('uncommitted source candidates require review: ' + repr(sorted(extra)))

    verify()
    if 'bench/archive_run.py' not in manifest['files']:
        raise RuntimeError('archive idle checks must be bound to the committed manifest')
    sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT / 'bench/archive_run.py'))

    def idle():
        archive['idle'](out, rt.idle)
        for comm in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
            try:
                name = comm.read_text().strip()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if name in ('ke_worker', 'kg_worker', 'ks_worker'):
                raise RuntimeError('probe caller remains: ' + str(comm))

    idle()
    out.mkdir(parents=True)
    for path, name in ((args.plan, 'task-plan.json'), (args.source_manifest, 'committed-source.json'),
                       (args.host_state, 'host-before.json'), (Path(__file__), 'run-tasks.py')):
        shutil.copyfile(path, out / name)
    records = []
    result = dict(state='RUNNING', passed=False, final_idle=False, boot_id=boot,
                  source_commit=manifest['commit'], phase=args.phase,
                  script_sha256=digest(Path(__file__)), tasks=records)

    def save():
        archive['save'](out / 'tasks.json', result)

    save()
    try:
        for task in tasks:
            verify()
            idle()
            name = task['name']
            if Path(name).name != name or name in ('.', '..'):
                raise RuntimeError('invalid task name')
            runner = Path(task['runner'])
            if str(runner) not in manifest['files']:
                raise RuntimeError('task runner is not bound to the committed manifest')
            target = out / name
            command = [sys.executable, str(ROOT / runner), *task['arguments'], '--output', str(target)]
            record = dict(name=name, argv=command, state='STARTING', started_unix=time.time(),
                          timeout_seconds=task['timeout_seconds'], output=str(target))
            records.append(record)
            save()
            print('START ' + name, flush=True)
            with (out / (name + '.console.log')).open('x') as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                record.update(pid=process.pid, state='RUNNING')
                save()
                try:
                    status = process.wait(timeout=task['timeout_seconds'])
                except BaseException as error:
                    record.update(state='UNCERTAIN', error=repr(error), finished_unix=time.time())
                    # Do not kill callers, unload modules, or start another task.
                    # Retain the exact PID and its open evidence for inspection.
                    raise
            record.update(state='FINISHED', exit_code=status, finished_unix=time.time())
            save()
            print('FINISH ' + name + ' ' + str(status), flush=True)
            if status:
                result.update(state='FAILED', failed_task=name)
                save()
                return 1
            idle()
            verify()
            frozen = json.loads((target / 'source-sha256.json').read_text())
            if not frozen or any(manifest['files'].get(path) != expected
                                 for path, expected in frozen.items()):
                raise RuntimeError('child snapshot differs from committed source: ' + name)
            record['committed_source_files'] = len(frozen)
            if 'expected_sessions' in task:
                child_plan = json.loads((target / 'plan.json').read_text())
                if len(child_plan) != task['expected_sessions']:
                    raise RuntimeError('child session count differs: ' + name)
                for spec in child_plan:
                    if Path(spec['name']).name != spec['name']:
                        raise RuntimeError('invalid child session name')
                    session = json.loads((target / spec['name'] / 'session.json').read_text())
                    if (session['execution_status'] != 'OK' or not session['drained']
                            or session.get('cleanup_error')):
                        raise RuntimeError('child session did not complete and drain: ' + spec['name'])
                record['completed_sessions'] = len(child_plan)
            save()
        result.update(state='COMPLETE', passed=True, final_idle=True)
        save()
        return 0
    except BaseException as error:
        result.update(state='STOPPED', error=repr(error))
        save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
