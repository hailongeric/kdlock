#!/usr/bin/env python3
"""Capture exact Native writer call returns from a verified Linux 7 ELF.

This is a read-only candidate capture, not a contention or performance pass.
The live correctness check must still observe the exact same-mm sleeping task,
first stack frame, wait channel and scheduler bracket for these return sites.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'bench/mmap_fault'))
import timing as common
rt = common.rt
CALLERS = ('vm_mmap_pgoff', '__vm_munmap')
ACQUIRE = 'down_write_killable'
SUPPORT = (ACQUIRE, 'rwsem_down_write_slowpath', 'in_sched_functions',
           'stack_trace_consume_entry_nosched', 'stack_trace_save_tsk')


def call_returns(text, caller, target=ACQUIRE):
    """Decode only exact E8 calls and their next instruction boundaries."""
    headers = list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:$', text, re.M))
    selected = [index for index, match in enumerate(headers) if match[2] == caller]
    rt.require(len(selected) == 1, 'missing/ambiguous writer function: '+caller)
    index = selected[0]
    start = int(headers[index][1], 16)
    body = text[headers[index].end():headers[index+1].start() if index+1 < len(headers) else len(text)]
    rows = []
    for line in body.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(\S.*)?$', line)
        if match and match[3]:
            rows.append((int(match[1], 16), bytes.fromhex(match[2]), match[3].strip(), line.strip()))
    calls = [(i, row) for i, row in enumerate(rows)
             if re.fullmatch(r'callq?\s+([0-9a-f]+) <'+re.escape(target)+r'>', row[2])]
    rt.require(calls, 'missing direct writer acquisition: '+caller)
    result = []
    for i, row in calls:
        target_address = int(re.fullmatch(r'callq?\s+([0-9a-f]+) <'+re.escape(target)+r'>', row[2])[1], 16)
        rt.require(len(row[1]) == 5 and row[1][0] == 0xe8 and i+1 < len(rows) and
                   rows[i+1][0] == row[0]+5 and
                   row[0]+5+int.from_bytes(row[1][1:], 'little', signed=True) == target_address,
                   'writer call bytes/target/return boundary differ: '+caller)
        result.append(dict(return_offset=row[0]+5-start, return_address=hex(row[0]+5),
                    function_address=hex(start), call_address=hex(row[0]),
                    target_address=hex(target_address), call_bytes=row[1].hex(),
                    call_line=row[3], next_line=rows[i+1][3], acquire=target))
    return result


def call_return(text, caller, target=ACQUIRE):
    result = call_returns(text, caller, target)
    rt.require(len(result) == 1, 'ambiguous direct writer acquisition: '+caller)
    return result[0]


def derive(vmlinux, out, command):
    outputs = {}
    sites = {}
    for name in (*CALLERS, *SUPPORT):
        path = out/(name+'.asm')
        text = command(['objdump', '-d', '--disassemble='+name, vmlinux], path, timeout=120)
        rt.require(re.search(r'^[0-9a-f]+ <'+re.escape(name)+r'>:$', text, re.M),
                   'required writer/support symbol missing: '+name)
        outputs[path.name] = rt.digest(path)
        if name in CALLERS:
            sites[name] = call_return(text, name)
    rt.require(len({value['target_address'] for value in sites.values()}) == 1,
               'writer callers target different acquisition symbols')
    return dict(sites=sites, outputs=outputs)


def derive_shared(vmlinux, out, command):
    """Require the existing bounded acquisition chain, derived from this ELF.

    An unexpected outlined frame, tail call or additional schedule site refuses
    capture; it needs its own exact client/ELF review before any live test.
    """
    adapter = 'kd_mmap_write_lock_killable'
    waiter = 'kd_mmap_down_write_killable'
    outputs, assembly = {}, {}
    for name in (*CALLERS, *SUPPORT, adapter, waiter):
        path = out/(name+'.asm')
        assembly[name] = command(['objdump','-d','--disassemble='+name,vmlinux],path,timeout=120)
        rt.require(re.search(r'^[0-9a-f]+ <'+re.escape(name)+r'>:$',assembly[name],re.M),
                   'required shared writer symbol missing: '+name)
        outputs[path.name] = rt.digest(path)
    sites = {name:call_return(assembly[name],name,adapter) for name in CALLERS}
    native = call_return(assembly[adapter],adapter,ACQUIRE)
    kd = call_return(assembly[adapter],adapter,waiter)
    waits = call_returns(assembly[waiter],waiter,'schedule')
    rt.require(len(waits) == 1, 'shared writer wait shape needs independent ELF review')
    rt.require(len({site['target_address'] for site in sites.values()}) == 1 and
               sites[CALLERS[0]]['target_address'] == native['function_address'] == kd['function_address'] and
               kd['target_address'] == waits[0]['function_address'],
               'shared writer chain symbol addresses differ')
    return dict(adapter=adapter, sites=sites, outputs=outputs, chains={
        'native':dict(waiter=adapter,wait_returns=[native['return_offset']]*2,
                      adapter_return=native['return_offset'],instructions=[native]),
        'kd':dict(waiter=waiter,wait_returns=[waits[0]['return_offset']]*2,
                  adapter_return=kd['return_offset'],instructions=[*waits,kd])})


def validate_witness(row, sites):
    rt.require(row['proof'] == 'FILTERED_SCHED_RETURN_SITE' and row['acquire'] == ACQUIRE and
               row['caller'] in CALLERS, 'exact Native writer wait witness missing')
    frames = [(name, int(offset, 16)) for name, offset in
              re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/', row['raw_stack'])]
    offset = sites['sites'][row['caller']]['return_offset']
    rt.require(frames and frames[0] == (row['caller'], offset) and row['return_offset'] == offset and
               row['state_before'] == row['state_after'] == 'D' and
               row['wchan_before'] == row['wchan_after'] == row['caller'] and
               row['schedstat_before'] == row['schedstat_after'] and
               len(row['schedstat_before'].split()) == 3 and
               all(value.isdigit() for value in row['schedstat_before'].split()),
               'Native writer stack/return/site/sleep bracket differs')


def checked_receipt(path, expected_sha256, binding, vmlinux, out, command):
    rt.require(bool(re.fullmatch('[0-9a-f]{64}', expected_sha256 or '')) and
               rt.digest(path) == expected_sha256, 'reviewed writer-site receipt hash differs')
    receipt = common.load(path)
    rt.require(receipt.get('schema') == 1 and receipt.get('kernel_binding') == binding and
               receipt.get('vmlinux_sha256') == rt.digest(vmlinux),
               'writer-site receipt belongs to another kernel ELF')
    shared = binding.get('variant') in ('kdmm1-native','kdmm1-kd','kdscope1-native','kdscope1-kd',
                                        'kdscope2-native','kdscope2-kd')
    current = (derive_shared if shared else derive)(vmlinux, out, command)
    rt.require(current == {key: receipt[key] for key in current},
               'writer-site disassembly differs from reviewed receipt')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--mode',choices=('native','kd'),
                        help='explicit enabled-MM variant; omitted for the ordinary Native kernel')
    common.kernel_identity.arguments(parser)
    args = parser.parse_args()
    if args.mode:
        shared = common.module('writer_shared_platform',Path(__file__).with_name('shared_platform.py'))
        shared.guest(args)
    else:
        common.guest(args.boot_id)
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence output required')
    out.mkdir(parents=True)
    identity = common.kernel_identity.capture(args, out, rt.command)
    binding = (shared.binding(identity,args.kernel_source,args.kernel_baseline,args.mode,
                              variant=args.kernel_variant) if args.mode else
               common.mm_platform.kernel_binding(identity,args.kernel_source,args.kernel_baseline,
                                                  private_backing_locks=False))
    vmlinux = args.kernel_source/'vmlinux'
    before = rt.digest(vmlinux)
    evidence = (derive_shared if args.mode else derive)(vmlinux, out, rt.command)
    rt.require(rt.digest(vmlinux) == before and
               Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
               'writer capture input or boot changed')
    receipt = dict(schema=1, captured=True, kernel_binding=binding, vmlinux_sha256=before,
                   script_sha256=rt.digest(Path(__file__)), **evidence,
                   scope='Exact writer-call return PCs only; no live contention/teardown pass.')
    rt.write_json(out/'writer-sites.json', receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
