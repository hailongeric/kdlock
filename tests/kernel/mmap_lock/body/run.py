#!/usr/bin/env python3
"""Guest-only actual mmap-lock body completion, handback and sticky refusal."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


def command(args, log, timeout=180):
    # A deadline stops the controller, never the in-flight operation. Retain
    # its PID, loaded modules and live evidence until real drain is established.
    with log.open('w') as stream:
        child = subprocess.Popen(list(map(str, args)), stdout=stream, stderr=subprocess.STDOUT)
        rt.write_json(log.with_suffix('.command.json'), dict(argv=list(map(str, args)), pid=child.pid))
        try:
            code = child.wait(timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'UNKNOWN_DRAIN: pid {child.pid}; {log}')
    rt.require(code == 0, f'command exited {code}: {log}')
    return log.read_text()


def validate(row, messages):
    rt.require(row['errors'] == 0 and row['checks'] >= 50 and row['completed'] == 2576 and
               row['reader_peak'] == 2 and row['pending_peak'] == 16 and row['idle'] == 1 and
               row['unmapped'] == 16 and row['mm'] and row['lock'], 'body/read/cleanup oracle differs')
    a, b, c = row['phases']
    for p in (a, b, c):
        rt.require(len(p['tids']) == len(set(p['tids'])) == 16 and
                   p['calls'] == p['supported'] + p['native'] + p['cancelled'] and
                   p['cancelled'] == 0 and p['handbacks'] == p['acks'], 'request/ACK balance differs')
    rt.require(a['calls'] == a['supported'] == 2048 and a['delegated'] > 0 and
               a['native'] == a['native_only'] == a['handbacks'] == 0, 'supported body did not complete')
    rt.require(b['calls'] == 2064 and b['supported'] == a['supported'] and
               b['delegated'] == a['delegated'] and b['native'] == 16 and
               b['handbacks'] > 0 and b['native_only'] == 1, 'unsupported handback/sticky refusal differs')
    rt.require(c['calls'] == 2576 and c['native'] == 528 and c['native_only'] == 1 and
               c['delegated'] == b['delegated'] and c['handbacks'] == b['handbacks'] and
               c['supported'] == b['supported'] and c['post_ban'] - b['post_ban'] == 512,
               'post-ban body was delegated or failed native continuation')
    records = re.findall(r'KD_MM_BODY done mm=([0-9a-f]+) origin=(\d+) executor=(\d+) '
                         r'start=([0-9a-f]+) end=([0-9a-f]+) behavior=(\d+) result=(-?\d+)', messages)
    rt.require(records and len(records) == min(a['delegated'], 16), 'missing physical executor receipts')
    for mm, origin, executor, start, end, behavior, result in records:
        rt.require(int(mm, 16) == row['mm'] and int(origin) != int(executor) and
                   int(origin) in a['tids'] and int(executor) in a['tids'] and
                   int(end, 16) - int(start, 16) == 3 * 4096 and int(behavior) in (16, 17) and
                   int(result) == 0, 'body receipt does not identify the actual mm and a different executor')
    return dict(returned_compiled_bodies=a['delegated'], handbacks=b['handbacks'],
                post_ban_local_calls=512, jit_bodies=0, reader_delegation=False,
                execution='FIXED_IN_TREE_MADVISE_BODY', receipts=len(records))


def validate_cancellation(row, messages):
    rt.require(row['errors'] == 0 and row['checks'] == 11 and row['completed'] == 2 and
               row['pending_peak'] == 2 and row['idle'] == 1 and row['unmapped'] == 16 and
               row['mm'] and row['lock'], 'cancellation/effect/retirement oracle differs')
    p = row['phases'][0]
    expected = dict(calls=2, supported=1, delegated=0, handbacks=0, native=0,
                    post_ban=0, cancelled=1, acks=0, native_only=0)
    rt.require(all(p[k] == v for k, v in expected.items()) and
               p['tids'][0] != p['tids'][1] and all(p['tids'][:2]) and
               'KD_MM_BODY done' not in messages, 'cancelled body executed or accounting differs')
    return dict(cancelled_before_admission=1, unchanged_victim_vma=True,
                queue_retired=True, jit_bodies=0, execution='CANCELLED_QUEUED_BODY')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cancellation', action='store_true')
    kernel_identity.arguments(p)
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release.startswith('6.1.159-kdmm') and
               'kd_mmap=on' in Path('/proc/cmdline').read_text().split() and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'verified experimental KD guest required')
    from importlib.machinery import SourceFileLoader
    api = SourceFileLoader('mm_api_probe', str(ROOT / 'tests/kernel/mmap_lock/run.py')).load_module()
    api.idle()
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence directory required')
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, accepted=False, state='PREPARATION',
                  performance='DEFERRED', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    rt.write_json(out / 'result.json', result)
    fd = None
    messages = ''

    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out / 'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages), 'kernel fault; retain module', 'KERNEL_FAULT')

    try:
        result['kernel_identity'] = kernel_identity.capture(a, out, rt.command)
        source = out / 'source'
        hashes = {}
        for path in Path(__file__).parent.rglob('*'):
            if path.is_file() and (path.suffix in ('.py', '.c', '.h', '.md') or path.name == 'Makefile'):
                rel = path.relative_to(Path(__file__).parent)
                target = source / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                hashes[str(rel)] = rt.digest(path)
        rt.write_json(out / 'source-sha256.json', hashes)
        module = source / 'payload/kd_mm_body_test.ko'
        client = source / 'client'
        command(['make', '-C', module.parent, 'KDIR=' + str(a.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                out / 'build-module.log')
        command(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-o', client, source / 'client.c'],
                out / 'build-client.log')
        result['binaries'] = {str(path.relative_to(source)): rt.digest(path) for path in (module, client)}
        api.idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        command(['insmod', module], out / 'load.log')
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        row = json.loads(command([client, *(['--cancel'] if a.cancellation else [])], out / 'client.json', 180))
        logs()
        result['evidence'] = (validate_cancellation if a.cancellation else validate)(row, messages)
        result['client'] = row
        for rel, digest in hashes.items():
            rt.require(rt.digest(source / rel) == rt.digest(Path(__file__).parent / rel) == digest,
                       'frozen source changed: ' + rel)
        for rel, digest in result['binaries'].items():
            rt.require(rt.digest(source / rel) == digest, 'binary changed: ' + rel)
        command(['rmmod', 'kd_mm_body_test'], out / 'unload.log')
        logs()
        api.idle()
        result.update(state='COMPLETE', passed=True, drained=True)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        try:
            logs()
        finally:
            if fd is not None:
                os.close(fd)
            rt.write_json(out / 'result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
