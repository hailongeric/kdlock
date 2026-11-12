#!/usr/bin/env python3
"""VM-only observer for the unchanged bounded mmap API runner.

A stopped observer never signals, closes the runner's endpoints, unloads a
provider or substitutes for owner drain. Live runner sessions remain retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
REPO = BASE/'mm-provider-ioctl-build-0798c1ab-01/input'
RUNNER = REPO/'tests/kernel/mmap_api/runner.py'
RUNNER_SHA = '3f36ab1289a6bc8e1601a745d36615d96d4a4bb9600c13d4ce8d99e321744afa'
PYTHON = Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3')
PYTHON_SHA = '52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41'
SOURCE = '0798c1abf422017cfc93647a2649be0e5a73c75a'
RELEASE = '7.0.0-38-kdrebuild8'
OBSERVER_SECONDS = 600
LOG_BYTES = 32 * 1024 * 1024
RESULT_BYTES = 32 * 1024 * 1024
GATES = {'all_round_effects', 'client_returned_zero', 'original_owner_left',
         'provider_retired', 'native_gate_drained', 'shutdown_archive_settle_end',
         'channel_closed', 'provider_unloaded', 'provider_devices_absent'}


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def bounded(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    need(len(data) <= limit, 'observer input exceeds byte limit: ' + str(path))
    return data


def save(root, name, value):
    path = root/name
    temp = root/('.' + name + '.tmp')
    with temp.open('wb') as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def process(pid):
    row = {'pid': pid}
    try:
        row['stat'] = bounded(Path('/proc')/str(pid)/'stat', 8192).decode()
        row['argv'] = bounded(Path('/proc')/str(pid)/'cmdline', 8192).replace(b'\0', b' ').decode(errors='replace')
        row['session'] = os.getsid(pid)
        row['process_group'] = os.getpgid(pid)
        children = bounded(Path('/proc')/str(pid)/'task'/str(pid)/'children', 8192).decode().split()
        row['direct_children'] = [int(value) for value in children]
    except (FileNotFoundError, ProcessLookupError):
        row['process_absent_at_snapshot'] = True
    return row


def idle(config, fresh):
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    taint = int(Path('/proc/sys/kernel/tainted').read_text())
    need(boot == config['boot_id'] and os.uname().release == config['release'] == RELEASE,
         'actual boot or release differs')
    if fresh:
        need(taint == 0, 'dispatch requires fresh taint0 boot')
    modules = Path('/proc/modules').read_text()
    absent = ('kd_mmap_api_provider', 'kd_rwsem_killable_fixture', 'kd_rwsem_runtime_fixture',
              'kd_runtime_fixture', 'kd_rwsem_api_provider')
    need(all(not (Path('/sys/module')/name).exists() for name in absent), 'a prior provider or fixture remains')
    devices = ('kd_mmap_api', 'kd_mmap_api_events', 'kd_mmap_jit', 'kd_rwsem_killable_fixture',
               'kd_rwsem_runtime_fixture', 'kd_runtime_fixture', 'kd_rwsem_api')
    need(all(not (Path('/dev')/(name+suffix)).exists() for name in devices
             for suffix in ('', '_ctl', '_events')), 'a prior control/event device remains')
    actors = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            comm = (entry/'comm').read_text().strip()
            argv = bounded(entry/'cmdline', 65536).replace(b'\0', b' ').decode(errors='replace')
            if comm.startswith('kd-kill') or comm == 'mmap-userspace' or any(
                    token in argv for token in ('tests/kernel/mmap_api/runner.py',
                                                'tests/kernel/rwsem_killable/runner.py')):
                actors.append({'pid': int(entry.name), 'comm': comm, 'argv': argv})
        except (FileNotFoundError, ProcessLookupError):
            continue
    need(not actors, 'a prior API runner or original client remains: ' + repr(actors))
    return {'boot_id': boot, 'release': RELEASE, 'taint': taint, 'modules': modules, 'actors': actors}


def success(value, child_pid, config_sha):
    need(value.get('controller_pid') == child_pid and value.get('config_sha256') == config_sha,
         'runner result does not belong to this exact child/config')
    need(value.get('status') == 'syscall_and_borrowed_jit_prefix_pass', 'runner prefix status is not a pass')
    for key in ('overall_pass', 'syscall_pass', 'borrowed_generated_entry_observed',
                'borrowed_jit_prefix_observed', 'channel_shutdown_complete', 'channel_closed', 'provider_unloaded'):
        need(value.get(key) is True, 'runner success field is not true: ' + key)
    need(value.get('client_returncode') == 0, 'original client did not return zero')
    gates = value.get('protected_completion_final_gates')
    need(isinstance(gates, dict) and set(gates) == GATES and all(v is True for v in gates.values()),
         'ordinary leave/retirement/channel/endpoint final gates did not all pass')
    return {'status': value['status'], 'syscall_pass': True, 'borrowed_jit_prefix_observed': True,
            'final_gates': gates, 'protected_mm_completion_required': False,
            'protected_mm_completion_observed': value.get('protected_mm_completion_observed'),
            'meaningful_returned_mm_body': value.get('meaningful_returned_mm_body'),
            'root_prefix_attribution': 'Exact mmap and munmap attribution remains separate post-run evidence review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-json', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    need(os.geteuid() == 0, 'VM root is required')
    need(len(args.config_sha256) == 64 and args.config_sha256 == bytes.fromhex(args.config_sha256).hex(),
         'exact lowercase config SHA-256 is required')
    need(args.receipt.is_absolute() and args.receipt.parent == BASE and BASE.resolve(strict=True) == BASE
         and not os.path.lexists(args.receipt), 'fresh exact outer receipt leaf required')
    args.receipt.mkdir(mode=0o700)
    root = args.receipt
    started = time.monotonic()
    child = None
    record = {'status': 'PRE_DISPATCH', 'config': str(args.config_json), 'config_sha256': args.config_sha256,
              'observer_seconds': OBSERVER_SECONDS, 'log_observer_limit_bytes': LOG_BYTES,
              'started_unix': time.time(), 'supervisor_pid': os.getpid(), 'child_pid': None,
              'signals_or_cleanup_on_failure': False, 'full_protected_mm_completion_required': False}
    save(root, 'result.json', record)
    try:
        need(args.config_json.is_absolute() and args.config_json.resolve(strict=True) == args.config_json,
             'exact canonical config file required')
        raw = bounded(args.config_json, 1048576)
        need(hashlib.sha256(raw).hexdigest() == args.config_sha256, 'actual config SHA differs')
        config = json.loads(raw)
        need(config['repo_head'] == SOURCE and Path(config['paths']['repo']) == REPO and REPO.resolve(strict=True) == REPO,
             'unchanged frozen0798 runner input required')
        output = Path(config['paths']['output'])
        need(output.is_absolute() and output.parent == BASE and not os.path.lexists(output) and output != root,
             'fresh separate runner output required')
        need(os.statvfs('/').f_bavail * os.statvfs('/').f_frsize >= 1 << 30 and
             os.statvfs(BASE).f_bavail * os.statvfs(BASE).f_frsize >= 4 << 30, 'root/output floor below1/4GiB')
        need(PYTHON.resolve(strict=True) == Path('/usr/bin/python3.14') and digest(PYTHON) == PYTHON_SHA,
             'pinned venv Python identity differs')
        need(digest(RUNNER) == RUNNER_SHA, 'unchanged mmap API runner differs')
        record['identity_before'] = idle(config, True)
        with (root/'config.json').open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        argv = [str(PYTHON), '-B', str(RUNNER), '--config-json', str(args.config_json)]
        record.update(argv=argv, cwd=str(REPO), log=str(root/'runner.log'), runner_result=str(output/'result.json'),
                      python_sha256=PYTHON_SHA, runner_sha256=RUNNER_SHA)
        save(root, 'result.json', record)
        with (root/'runner.log').open('xb', buffering=0) as log:
            child = subprocess.Popen(argv, cwd=REPO, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'},
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record.update(status='RUNNING', child_pid=child.pid, child_at_dispatch=process(child.pid),
                          dispatched_unix=time.time())
            save(root, 'result.json', record)
            deadline = time.monotonic() + OBSERVER_SECONDS
            value = None
            result_raw = None
            while True:
                record['elapsed_seconds'] = time.monotonic() - started
                record['log_bytes'] = (root/'runner.log').stat().st_size
                if record['log_bytes'] > LOG_BYTES:
                    record['status'] = 'OUTPUT_LIMIT_CHILD_RETAINED'
                    break
                try:
                    result_raw = bounded(output/'result.json', RESULT_BYTES)
                    value = json.loads(result_raw)
                except (FileNotFoundError, json.JSONDecodeError):
                    value = None
                if isinstance(value, dict) and value.get('status') == 'failed_retained':
                    need(value.get('controller_pid') == child.pid and value.get('config_sha256') == args.config_sha256,
                         'retained runner result identity differs')
                    record.update(status='RUNNER_FAILED_RETAINED', runner_status=value['status'],
                                  runner_error=str(value.get('error'))[:4096], client_pid=value.get('client_pid'))
                    break
                returned = child.poll()
                if returned is not None:
                    record['child_returncode'] = returned
                    need(returned == 0, 'actual runner returned nonzero')
                    # Reopen after actual exit, avoiding a partial final write.
                    result_raw = bounded(output/'result.json', RESULT_BYTES)
                    value = json.loads(result_raw)
                    need(isinstance(value, dict), 'runner returned without an exact complete result')
                    record['runner_success'] = success(value, child.pid, args.config_sha256)
                    record['identity_after'] = idle(config, False)
                    record['status'] = 'SYSCALL_AND_BORROWED_PREFIX_COMPLETE'
                    break
                if time.monotonic() >= deadline:
                    record['status'] = 'OBSERVER_TIMEOUT_CHILD_RETAINED'
                    break
                time.sleep(0.1)
            if result_raw is not None and value is not None:
                with (root/'runner-result-snapshot.json').open('xb') as stream:
                    stream.write(result_raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                record['runner_result_sha256'] = hashlib.sha256(result_raw).hexdigest()
            record['child_final_observation'] = process(child.pid)
            record['child_returncode'] = child.poll()
            record['config_unchanged'] = digest(args.config_json) == args.config_sha256
            need(record['config_unchanged'], 'actual runner config changed during observation')
            save(root, 'result.json', record)
    except BaseException as error:
        failed_status = ('OBSERVER_FAILED_CHILD_RETAINED' if child and child.poll() is None else
                         'RUNNER_RETURNED_INCOMPLETE' if child else 'PRE_DISPATCH_FAILED')
        record.update(status=failed_status, error=repr(error))
        if child:
            record.update(child_pid=child.pid, child_returncode=child.poll(), child_final_observation=process(child.pid))
        save(root, 'result.json', record)
    record['elapsed_seconds'] = time.monotonic() - started
    save(root, 'result.json', record)
    print(json.dumps({'status': record['status'], 'receipt': str(root/'result.json'),
                      'child_pid': record['child_pid'], 'child_returncode': record.get('child_returncode')}), flush=True)
    return 0 if record['status'] == 'SYSCALL_AND_BORROWED_PREFIX_COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
