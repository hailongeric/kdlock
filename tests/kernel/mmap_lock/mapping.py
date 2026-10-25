#!/usr/bin/env python3
"""Untouched actual-mm mmap/munmap checks, separate from page-fault work."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
sys.path.insert(0, str(ROOT / 'tests/protocols'))
from cpu_placement import capture_topology

spec = importlib.util.spec_from_file_location('mmap_writer_checks', ROOT / 'tests/kernel/mmap_writer/run.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
SITES = json.loads(Path(__file__).with_name('writer_sites.json').read_text())


def chain_proof(row, mode):
    chain = SITES['chains'][mode]
    rt.require(row['proof'] == 'EXACT_MMAP_WRITER_CHAIN' and row['acquire'] == SITES['adapter'] and
               row['caller'] in SITES['sites'], 'missing exact writer chain')
    frames = [(name, int(offset, 16)) for name, offset in
              re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/', row['raw_stack'])]
    expected = [(chain['waiter'], row['wait_return_offset'])]
    if chain['waiter'] != SITES['adapter']:
        expected.append((SITES['adapter'], chain['adapter_return']))
    expected.append((row['caller'], SITES['sites'][row['caller']]['return_offset']))
    rt.require(row['waiter'] == chain['waiter'] and row['wait_return_offset'] in chain['wait_returns'] and
               row['adapter_return_offset'] == chain['adapter_return'] and
               row['return_offset'] == expected[-1][1] and frames[:len(expected)] == expected,
               'raw writer chain differs from this kernel ELF')
    rt.require(row['state_before'] == row['state_after'] == 'D' and
               row['wchan_before'] == row['wchan_after'] == chain['waiter'] and
               row['schedstat_before'] == row['schedstat_after'] and
               len(row['schedstat_before'].split()) == 3 and
               all(v.isdigit() for v in row['schedstat_before'].split()),
               'writer sleep bracket or scheduler identity changed')


def validate(rows, mode, count, iterations, backend, eligibility_policy=checks.eligibility.STRICT):
    row = checks.validate(rows, mode, count, iterations, lambda r: chain_proof(r, backend), eligibility_policy)
    row['protocol'] = 'KD_LOCAL_MMAP_LOCK' if backend == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK'
    return row


def reject_mutations(rows, backend, eligibility_policy=checks.eligibility.STRICT):
    # Keep the positive exact-object/ELF proof, then ensure a corrupt identity,
    # missing frame or rescheduled observation still fails the same verifier.
    rejected = []
    mutations = {
        'different_lock': lambda r: r.__setitem__('mmap_lock', 1),
        'wrong_caller_return': lambda r: r.__setitem__('return_offset', 1),
        'wrong_wait_return': lambda r: r.__setitem__('wait_return_offset', 1),
        'wrong_adapter_return': lambda r: r.__setitem__('adapter_return_offset', 1),
        'running_task': lambda r: r.__setitem__('state_after', 'R'),
        'other_wait_channel': lambda r: r.__setitem__('wchan_before', 'futex_wait'),
        'rescheduled_task': lambda r: r.__setitem__('schedstat_after', '1 2 3\n'),
        'missing_chain': lambda r: r.__setitem__('raw_stack', '[<0>] vm_mmap_pgoff+0x1/0x170\n'),
    }
    for name, mutate in mutations.items():
        bad = copy.deepcopy(rows)
        mutate(next(r for r in bad if r['event'] == 'writer_stack'))
        try:
            validate(bad, 'cycle', 16, 5000, backend, eligibility_policy)
        except rt.Failure:
            rejected.append(name)
        else:
            raise RuntimeError('corrupt writer proof accepted: ' + name)
    bad = [r for r in rows if r['event'] != 'writer_stack']
    try:
        validate(bad, 'cycle', 16, 5000, backend, eligibility_policy)
    except rt.Failure:
        rejected.append('missing_writer_proof')
    else:
        raise RuntimeError('missing writer proof accepted')
    return rejected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('native', 'kd'), required=True)
    p.add_argument('--api-result', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--writer-sites', type=Path, default=Path(__file__).with_name('writer_sites.json'),
                   help='reviewed call-site manifest bound to the exact candidate ELF')
    kernel_identity.arguments(p)
    a = p.parse_args()
    global SITES
    SITES = json.loads(a.writer_sites.read_text())
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release.startswith('6.1.159-kdmm') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed experimental guest required')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    api = json.loads(a.api_result.read_text())
    rt.require(api['passed'] and api['drained'] and api['boot_id'] == boot and api['mode'] == a.mode and
               api['probe']['use_kd'] == int(a.mode == 'kd'), 'matching actual-mm API pass required')
    boot_args = Path('/proc/cmdline').read_text().split()
    rt.require([s for s in boot_args if s.startswith('kd_mmap=')] ==
               ['kd_mmap=' + ('on' if a.mode == 'kd' else 'off')], 'boot backend differs')
    topology = capture_topology(list(range(64)))
    rt.require(topology['online_cpus'] == list(range(64)) and
               topology['role_nodes'] == [0] * 32 + [1] * 32, 'guest topology differs')
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new output required')
    checks.idle(out.parent)
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, drained=False, accepted=False, timing=False,
                  workload='UNTOUCHED_MMAP_MUNMAP', mode=a.mode, delegated=False, jit_bodies=0,
                  boot_id=boot, topology=topology, cases=[], api_result_sha256=rt.digest(a.api_result))
    rt.write_json(out / 'result.json', result)
    fd, messages = None, ''

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
        rt.require(result['kernel_identity']['running_build_id'] == SITES['kernel_build_id'] and
                   rt.digest(a.kernel_source / 'vmlinux') == SITES['vmlinux_sha256'], 'writer proof ELF differs')
        shutil.copyfile(a.writer_sites, out / 'writer-sites.json')
        result['writer_sites_sha256'] = rt.digest(out / 'writer-sites.json')
        source, hashes = out / 'source', {}
        for directory in ('workload_modules/mmap_writer', 'bench/mmap_writer', 'tests/kernel/mmap_writer',
                          'tests/kernel/mmap_lock'):
            for path in (ROOT / directory).rglob('*'):
                rel = path.relative_to(ROOT)
                if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in rel.parts) or
                        path.name.endswith('.mod.c') or
                        (path.suffix not in ('.c', '.h', '.inc', '.py', '.json') and path.name != 'Makefile')):
                    continue
                hashes[str(rel)] = rt.digest(path)
                target = source / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        rt.write_json(out / 'source-sha256.json', hashes)

        def verify():
            rt.require(rt.digest(a.writer_sites) == rt.digest(out / 'writer-sites.json') ==
                       result['writer_sites_sha256'], 'reviewed writer proof changed')
            for name, h in hashes.items():
                rt.require(rt.digest(ROOT / name) == rt.digest(source / name) == h, 'frozen source changed: ' + name)

        payload = source / 'workload_modules/mmap_writer/kd_mmap_writer_native.ko'
        rt.command(['make', '-C', payload.parent, 'KDIR=' + str(a.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                   out / 'build-payload.log', timeout=180)
        imports = rt.command(['nm', '-u', payload], out / 'imports.txt')
        rt.require('kd_mmap_is_contended' in imports and not re.search(r'\bkd_(?!mmap_)', imports),
                   'payload did not use the builtin actual-mm interface')
        client = out / 'client'
        rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-I' + str(payload.parent),
                    source / 'bench/mmap_writer/client.c', '-o', client], out / 'build-client.log', timeout=60)
        binaries = {str(p.relative_to(out)): rt.digest(p) for p in (client, payload)}
        rt.write_json(out / 'binary-sha256.json', binaries)
        verify()
        checks.idle(out.parent)
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', payload, 'observe=1'], out / 'load.log')
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        chain = SITES['chains'][a.mode]
        proof_args = [str(SITES['sites'][name]['return_offset']) for name in ('vm_mmap_pgoff', '__vm_munmap')]
        proof_args += [chain['waiter'], *map(str, chain['wait_returns']), str(chain['adapter_return']), SITES['adapter']]
        plan = [('scope', 1, 1), ('cycle', 1, 1000), ('cycle', 16, 5000),
                ('lifetime', 1, 1), ('lifetime', 16, 1), ('exit', 1, 1)]
        for i, (mode, count, iterations) in enumerate(plan):
            name = f'{i:02d}-{mode}-{count}'
            data = rt.command([client, mode, str(count), str(iterations), *proof_args],
                              out / (name + '.jsonl'), timeout=120)
            logs()
            rows = [json.loads(line) for line in data.splitlines()]
            case = validate(rows, mode, count, iterations, a.mode)
            health = Path('/sys/module/kd_mmap_writer_native/parameters/health').read_text().strip()
            rt.require(health == f'files=0 mm_refs=0 destroyed={i+1} release_errors=0', 'file/VMA/mm teardown differs')
            case.update(name=name, health=health)
            if mode == 'cycle' and count == 16:
                case['rejected_mutations'] = reject_mutations(rows, a.mode)
            result['cases'].append(case)
            rt.write_json(out / 'result.json', result)
            print(name, 'PASS', flush=True)
        rt.command(['rmmod', 'kd_mmap_writer_native'], out / 'unload.log')
        logs()
        verify()
        checks.idle(out.parent)
        rt.require(all(rt.digest(out / name) == h for name, h in binaries.items()), 'binary changed')
        result.update(state='COMPLETE', passed=True, drained=True, binaries=binaries, source_unchanged=True)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        try:
            logs()
        finally:
            rt.write_json(out / 'result.json', result)
            if fd is not None:
                os.close(fd)
    print(json.dumps({k: result[k] for k in ('state', 'passed', 'drained', 'mode')}))


if __name__ == '__main__':
    main()
