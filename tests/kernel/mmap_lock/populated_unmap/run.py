#!/usr/bin/env python3
"""Guest-only resident anonymous-page removal, physical ownership and TLB correctness."""
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
    rt.require(row['errors'] == 0 and row['checks'] > 40 and row['idle'] == 1 and
               row['mm'] and row['gate'] and row['reader_peak'] == 2 and
               row['cleanup_calls'] == row['groups'] * 3,
               'mapping/reader/retirement oracle differs')
    for phase in [*row['phases'], row['after_cleanup']]:
        rt.require(phase['calls'] == phase['removed'] + phase['native'] + phase['cancelled'] + phase['failed'] and
                   phase['handbacks'] == phase['acks'] and phase['failed'] == 0,
                   'request, body failure or ACK balance differs')
    before, after = row['phases'][-1], row['after_cleanup']
    for key in ('removed', 'delegated', 'handbacks', 'acks', 'cancelled', 'populated', 'populated_remote'):
        rt.require(after[key] == before[key], 'cleanup claimed another body or altered retirement: ' + key)
    for key in ('calls', 'native'):
        rt.require(after[key] - before[key] == row['cleanup_calls'], 'cleanup call accounting differs')
    rt.require(after['native_only'] == after['refused'] == 1 and
               after['post_ban'] - before['post_ban'] == row['cleanup_calls'] - (row['mode'] in ('cancel','free')),
               'cleanup escaped sticky local continuation')

    pages=row['pages'];width=row['width']
    expected_pins=(32*width+16 if row['groups']==48 else row['groups']*width+(row['mode']=='too-wide'))
    rt.require(1<=width<=4 and row['pin_total']==expected_pins and len(pages)==expected_pins and len({p['pfn'] for p in pages})==len(pages) and
               len({p['address'] for p in pages})==len(pages) and row['pins_owned']==0 and
               row['pins_released']==expected_pins, 'original page references were not retired')
    for i,page in enumerate(pages):
        group,page_index=page['group'],page['page']
        rt.require(0<=group<row['groups'], 'unknown original page group')
        expected_indices=({1} if row['groups']==48 and 16<=group<32 else
                          set(range(5 if row['mode']=='too-wide' and group==1 else width)))
        rt.require(page_index in expected_indices and
                   {p['page'] for p in pages if p['group']==group}==expected_indices, 'incomplete original page group')
        value=1+group*3+page_index
        expected=1469598103934665603
        for _ in range(4096): expected=((expected^value)*1099511628211)&((1<<64)-1)
        rt.require(page['pfn']==page['initial_pfn'] and page['pfn']>0 and page['hash']==expected and
                   page['mapcount']==(row['mode']=='free') and page['refs_before_drop']==1+(row['mode']=='free') and page['charged_same']==1 and page['locked']==0,
                   'original physical data, page accounting or final mapping reference differs')
    rt.require(all(o['fault_code']==1 and o['invalidated']==(o['end']-o['start'])//4096 for phase in row['phases'] for o in phase['origins']),
               'an origin retained a usable cached translation after munmap')


def identities(row, messages, kind, phase, expected):
    suffix = r' result=0' if kind == 'done' else ''
    records = re.findall(r'KD_MM_UNMAP ' + kind + r' mm=([0-9a-f]+) id=(\d+) '
        r'origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+)' + suffix, messages)
    rt.require(len(records) == len(set(records)) == len({r[1] for r in records}) == expected,
               'missing or duplicate ' + kind + ' identity')
    origins = {item['tid']: item for item in phase['origins']}
    rt.require(len(origins) == len(phase['origins']) and all(origins), 'origin identities differ')
    for mm, ident, origin, executor, start, end in records:
        source = origins.get(int(origin), {})
        rt.require(int(mm, 16) == row['mm'] and 0 < int(ident) <= phase['calls'] and
                   int(origin) != int(executor) and int(executor) in origins and
                   source.get('start') == int(start, 16) and source.get('end') == int(end, 16),
                   'receipt is not bound to the requested mapping, mm and different executor')
    return records


def ack_records(row, messages, phase, expected):
    sent = identities(row, messages, 'handback', phase, expected)
    got = identities(row, messages, 'ack', phase, expected)
    rt.require(sorted(sent) == sorted(got), 'exact handback/ACK identity mismatch')
    return len(got)


def expect(phase, **values):
    rt.require(all(phase[k] == v for k, v in values.items()), 'phase accounting differs: ' + str(values))


def physical_records(row, messages, done):
    pages={p['address']:p for p in row['pages']}
    if row['width']==1:
        physical=re.findall(r'KD_MM_POPULATED done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) '
            r'start=([0-9a-f]+) end=([0-9a-f]+) pfn=([0-9a-f]+) pte_none=1 mapcount=0 tables_retained=1',messages)
        physical=[(*p[:6],'0','1',p[6]) for p in physical]
    else:
        physical=re.findall(r'KD_MM_POPULATED_RANGE done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) '
            r'start=([0-9a-f]+) end=([0-9a-f]+) index=(\d+) pages=(\d+) pfn=([0-9a-f]+) '
            r'pte_none=1 mapcount=0 tables_retained=1',messages)
    rt.require(len(physical)==len(set(physical))==len(done)*row['width'], 'missing/duplicate physical completion')
    for receipt in done:
        matches=[p for p in physical if p[:6]==receipt]
        rt.require(len(matches)==row['width'] and {int(p[6]) for p in matches}==set(range(row['width'])),
                   'body lacks a complete set of original page receipts')
        for p in matches:
            start,end=int(p[4],16),int(p[5],16)
            original=pages.get(start+int(p[6])*4096,{})
            rt.require(end-start==row['width']*4096 and int(p[7])==row['width'] and
                       original.get('initial_pfn')==int(p[8],16), 'body removed a different original page')
    return len(physical)


def validate(row, messages):
    check_common(row)
    a, b, c = row['phases']
    rt.require(row['mode'] == 'body' and row['groups'] == row['completed'] == 48 and
               row['checks'] > 16 * 4 * 4096 and row['pending_peak'] == 16 and
               row['late_fault_blocked'] == 1 and row['late_fault_tid'] > 0 and row['late_fault_code'] == 0 and row['late_value'] == 0 and
               'kd_mmap_down_read' in row['late_fault_stack'] and 'do_user_addr_fault' in row['late_fault_stack'],
               'real mapping/content or blocked hardware-fault proof absent')
    rt.require(all(len(p['origins']) == 16 for p in (a, b, c)), 'cohort differs')
    expect(a, calls=16, removed=16, delegated=15, native=0, post_ban=0,
           handbacks=0, cancelled=0, refused=0, native_only=0)
    expect(b, calls=32, removed=16, delegated=15, native=16, post_ban=0,
           handbacks=15, cancelled=0, refused=1, native_only=1)
    expect(c, calls=48, removed=16, delegated=15, native=32, post_ban=16,
           handbacks=15, cancelled=0, refused=1, native_only=1)
    expect(a,populated=16,populated_remote=15)
    expect(b,populated=16,populated_remote=15)
    expect(c,populated=16,populated_remote=15)
    done = identities(row, messages, 'done', a, 15)
    physical_count = physical_records(row, messages, done)
    matched = ack_records(row, messages, b, 15)
    return dict(actual_remote_vma_removals=len(done), mapping_bound_receipts=len(done),
                matched_handbacks=matched, post_ban_local_calls=16,
                real_neighbor_fault_waited_then_resolved=True, origin_tlb_invalidations=32*row['width']+16, physical_page_receipts=physical_count, concurrent_local_readers=2,
                partial_unmap_preserved_contents=True, cleanup_calls=144,
                execution='REAL_POPULATED_DO_MAS_ALIGN_MUNMAP', jit_bodies=0)


def validate_cancellation(row, messages):
    check_common(row)
    p, = row['phases']
    rt.require(row['mode'] == 'cancel' and row['groups'] == 2 and row['pending_peak'] == 2 and
               row['cancel_mapped'] == [0, 1] and row['cancel_result'] == [0, -4] and
               len(set(row['cancel_tid'])) == 2 and all(row['cancel_tid']) and
               'KD_MM_UNMAP done' not in messages, 'cancelled munmap had effects or failed retirement')
    expect(p, calls=2, removed=1, delegated=0, native=0, post_ban=0, handbacks=0,
           cancelled=1, refused=0, native_only=0)
    expect(p,populated=1,populated_remote=0)
    ack_records(row, messages, p, 0)
    return dict(cancelled_before_removal=1, victim_mapping_retained=True,
                queue_retired=True, cleanup_calls=6, jit_bodies=0)


def validate_no_neighbor(row, messages):
    check_common(row)
    a, b = row['phases']
    rt.require(row['mode'] in ('no-neighbor','busy-last','too-wide') and row['groups'] == row['completed'] == 3 and
               row['pending_peak'] == 2 and row['no_neighbor_code'] == 1 and
               'KD_MM_UNMAP done' not in messages, 'table-free case was delegated or stale translation survived')
    expect(a, calls=2, removed=1, delegated=0, native=1, post_ban=0, handbacks=1,
           cancelled=0, refused=1, native_only=1)
    expect(b, calls=3, removed=1, delegated=0, native=2, post_ban=1, handbacks=1,
           cancelled=0, refused=1, native_only=1)
    expect(a,populated=1,populated_remote=0)
    expect(b,populated=1,populated_remote=0)
    ack_records(row, messages, a, 1)
    if row['mode']=='busy-last':
        rollback=re.findall(r'KD_MM_POPULATED_RANGE rollback mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) '
            r'start=([0-9a-f]+) end=([0-9a-f]+) held=(\d+) released=(\d+) effects=0',messages)
        ack=identities(row,messages,'ack',a,1)
        rt.require(row['width']==4 and row['rollback_checked']==1 and len(rollback)==1 and
                   rollback[0][:6]==ack[0] and rollback[0][6:]==('3','3'),
                   'late-page refusal did not prove exact prefix rollback')
    return dict(refusal=row['mode'],required_table_free_handback=int(row['mode']=='no-neighbor'), matched_acks=1, cached_translation_invalidated=True,
                post_ban_local_calls=1, cleanup_calls=9, jit_bodies=0)


def validate_free(row,messages):
    check_common(row)
    p,=row['phases']
    rt.require(row['mode']=='free' and row['groups']==row['completed']==2 and row['pending_peak']==2,
               'unreferenced body cohort differs')
    expect(p,calls=2,removed=2,delegated=1,native=0,post_ban=0,handbacks=0,cancelled=0,
           refused=0,native_only=0,populated=2,populated_remote=1)
    done=identities(row,messages,'done',p,1)
    physical_count=physical_records(row,messages,done)
    ack_records(row,messages,p,0)
    return dict(actual_remote_vma_removals=1,test_references_released_before_body=row['pin_total'],physical_page_receipts=physical_count,
                origin_tlb_invalidations=2*row['width'],cleanup_calls=6,jit_bodies=0,
                post_free_page_dereference=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--cancellation', action='store_true')
    mode.add_argument('--no-neighbor', action='store_true')
    mode.add_argument('--free', action='store_true')
    mode.add_argument('--busy-last', action='store_true')
    mode.add_argument('--too-wide', action='store_true')
    p.add_argument('--pages',type=int,choices=(1,2,3,4),default=1)
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
        module = source / 'payload/kd_mm_populated_test.ko'
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
        row = json.loads(command([client, *(['--cancel'] if a.cancellation else ['--no-neighbor'] if a.no_neighbor else ['--free'] if a.free else ['--busy-last'] if a.busy_last else ['--too-wide'] if a.too_wide else []), '--pages',str(a.pages)], out / 'client.json', 180))
        logs()
        result['evidence'] = (validate_cancellation if a.cancellation else validate_no_neighbor if (a.no_neighbor or a.busy_last or a.too_wide) else validate_free if a.free else validate)(row, messages)
        result['client'] = row
        for rel, digest in hashes.items():
            rt.require(rt.digest(source / rel) == rt.digest(Path(__file__).parent / rel) == digest,
                       'frozen source changed: ' + rel)
        for rel, digest in result['binaries'].items():
            rt.require(rt.digest(source / rel) == digest, 'binary changed: ' + rel)
        command(['rmmod', 'kd_mm_populated_test'], out / 'unload.log')
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
