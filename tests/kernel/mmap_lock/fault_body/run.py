#!/usr/bin/env python3
"""Guest-only actual write-fault installation, handback, retry and cancellation."""
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


def check_common(row):
    rt.require(row['errors'] == 0 and row['checks'] > 20 and row['idle'] == 1 and
               row['unmapped_pages'] == 512 and row['mm'] and row['gate'] and
               row['reader_peak'] == 2, 'memory/reader/retirement oracle differs')
    for phase in row['phases']:
        rt.require(phase['calls'] == phase['supported'] + phase['native'] + phase['cancelled'] and
                   phase['handbacks'] == phase['acks'], 'request or ACK balance differs')


def ack_records(row, messages, expected):
    records = {}
    for kind in ('handback', 'ack'):
        records[kind] = re.findall(r'KD_MM_FAULT ' + kind + r' mm=([0-9a-f]+) id=(\d+) '
            r'origin=(\d+) executor=(\d+) address=([0-9a-f]+)', messages)
    rt.require(len(records['handback']) == len(set(records['handback'])) == expected and
               sorted(records['handback']) == sorted(records['ack']), 'exact handback/ACK identity mismatch')
    for mm, ident, origin, executor, address in records['ack']:
        rt.require(int(mm, 16) == row['mm'] and int(ident) > 0 and
                   int(origin) != int(executor) and int(address, 16) % 4096 == 0,
                   'refusal does not name the original mm and distinct tasks')
    return len(records['ack'])


def validate(row, messages):
    check_common(row)
    a, b, c = row['phases']
    rt.require(row['mode'] == 'body' and row['completed'] == 400 and
               row['checks'] > 400 * 8190 and row['delegated_with_readers'] > 0,
               'actual contents or concurrent-reader proof absent')
    for phase in (a, b, c):
        rt.require(len(set(phase['tids'])) == 16 and all(phase['tids']) and phase['cancelled'] == 0,
                   'fault origins or cancellation differ')
    rt.require(a['calls'] == a['supported'] == 256 and a['delegated'] > 0 and
               a['native'] == a['native_only'] == a['handbacks'] == a['refused'] == 0,
               'supported real body did not complete')
    rt.require(b['calls'] == 272 and b['supported'] == 256 and b['delegated'] == a['delegated'] and
               b['native'] == 16 and b['handbacks'] == 15 and b['native_only'] == b['refused'] == 1,
               'unsupported handback and sticky refusal differ')
    rt.require(c['calls'] == 400 and c['supported'] == 256 and c['delegated'] == a['delegated'] and
               c['native'] == 144 and c['handbacks'] == 15 and c['native_only'] == c['refused'] == 1 and
               c['post_ban'] - b['post_ban'] == 128, 'sticky calls escaped native continuation')
    records = re.findall(r'KD_MM_FAULT done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) '
                         r'address=([0-9a-f]+) pfn=([0-9a-f]+)', messages)
    rt.require(len(records) == min(a['delegated'], 16) and
               len({r[1] for r in records}) == len(records), 'missing or duplicate remote completion receipts')
    pages = {p['address']:p for p in row['pages']}
    rt.require(len(pages) == 256 and len({p['pfn'] for p in pages.values()}) == 256,
               'installed private physical pages are not distinct')
    for mm, ident, origin, executor, address, pfn in records:
        page = pages.get(int(address, 16), {})
        rt.require(int(mm, 16) == row['mm'] and 0 < int(ident) <= 256 and
                   int(origin) != int(executor) and int(origin) in a['tids'] and int(executor) in a['tids'] and
                   page.get('origin') == int(origin) and page.get('pfn') == int(pfn, 16) and int(pfn, 16),
                   'receipt does not bind the actual installed PTE to its origin and another executor')
    acks = ack_records(row, messages, 15)
    return dict(actual_remote_page_installations=a['delegated'], pte_bound_receipts=len(records),
                matched_handbacks=acks, post_ban_local_calls=128, reader_delegation=False,
                execution='REAL_DO_ANONYMOUS_PAGE_INSTALL', jit_bodies=0)


def validate_cancellation(row, messages):
    check_common(row)
    p = row['phases'][0]
    expected = dict(calls=2, supported=1, delegated=0, native=0, post_ban=0,
                    handbacks=0, acks=0, cancelled=1, refused=0, native_only=0)
    rt.require(row['mode'] == 'cancel' and all(p[k] == v for k, v in expected.items()) and
               row['cancel_present'] == [1, 0] and row['cancel_result'] == [0, -14] and
               len(set(row['cancel_tid'])) == 2 and all(row['cancel_tid']) and
               'KD_MM_FAULT done' not in messages, 'cancelled fault had effects or was not retired')
    ack_records(row, messages, 0)
    return dict(cancelled_before_installation=1, victim_pte_absent=True,
                original_read_lock_released=True, queue_retired=True, jit_bodies=0)


def validate_retry(row, messages):
    check_common(row)
    a, b = row['phases']
    rt.require(row['mode'] == 'retry' and row['completed'] == 3 and row['retry_writer_completed'] == 1 and
               a['calls'] == 2 and a['supported'] == 1 and a['native'] == 1 and a['delegated'] == 0 and
               a['handbacks'] == 1 and a['native_only'] == a['refused'] == 1 and a['cancelled'] == 0 and
               b['calls'] == 3 and b['native'] == 2 and b['post_ban'] - a['post_ban'] == 1 and
               b['supported'] == 1 and b['delegated'] == 0 and b['handbacks'] == 1 and b['cancelled'] == 0,
               'userfaultfd refusal/retry/writer or sticky continuation differs')
    ack_records(row, messages, 1)
    rt.require('KD_MM_FAULT done' not in messages, 'unsupported fault counted as a remote body')
    return dict(real_userfaultfd_handback=1, matched_acks=1, writer_during_unresolved_fault=True,
                resolved_page_contents=True, post_ban_local_calls=1, jit_bodies=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--cancellation', action='store_true')
    mode.add_argument('--retry', action='store_true')
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
        module = source / 'payload/kd_mm_fault_test.ko'
        client = source / 'client'
        command(['make', '-C', module.parent, 'KDIR=' + str(a.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                out / 'build-module.log')
        command(['cc', '-pthread', '-O2', '-Wall', '-Wextra', '-Werror', '-o', client, source / 'client.c'],
                out / 'build-client.log')
        result['binaries'] = {str(path.relative_to(source)): rt.digest(path) for path in (module, client)}
        api.idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        command(['insmod', module], out / 'load.log')
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        row = json.loads(command([client, *(['--cancel'] if a.cancellation else ['--retry'] if a.retry else [])], out / 'client.json', 180))
        logs()
        result['evidence'] = (validate_cancellation if a.cancellation else validate_retry if a.retry else validate)(row, messages)
        result['client'] = row
        for rel, digest in hashes.items():
            rt.require(rt.digest(source / rel) == rt.digest(Path(__file__).parent / rel) == digest,
                       'frozen source changed: ' + rel)
        for rel, digest in result['binaries'].items():
            rt.require(rt.digest(source / rel) == digest, 'binary changed: ' + rel)
        command(['rmmod', 'kd_mm_fault_test'], out / 'unload.log')
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
