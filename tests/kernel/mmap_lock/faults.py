#!/usr/bin/env python3
"""Separate page-fault, VMA retry, fork/exit and remote-mm correctness task."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
sys.path.insert(0, str(ROOT / 'tests/protocols'))
from cpu_placement import capture_topology


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('native', 'kd'), required=True)
    p.add_argument('--output', type=Path, required=True)
    kernel_identity.arguments(p)
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release.startswith('6.1.159-kdmm'), 'experimental guest required')
    rt.idle()
    for m in Path('/sys/module').iterdir():
        rt.require(not m.name.startswith(('kd_', 'tc_', 'tclock_', 'jit_')), 'project module remains')
    boot_args = Path('/proc/cmdline').read_text().split()
    rt.require([s for s in boot_args if s.startswith('kd_mmap=')] ==
               ['kd_mmap=' + ('on' if a.mode == 'kd' else 'off')] and
               all(s in boot_args for s in ('nokaslr', 'nopvspin')), 'boot mode or policy differs')
    topology = capture_topology(list(range(64)))
    rt.require(topology['online_cpus'] == list(range(64)) and
               topology['role_nodes'] == [0] * 32 + [1] * 32, 'guest topology differs')
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence output required')
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, drained=False, accepted=False, timing=False,
                  workload='PAGE_FAULT_RETRY_FORK_REMOTE', mode=a.mode, delegated=False,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  boot_args=boot_args, topology=topology,
                  limits='Does not cover VM_FAULT_COMPLETED or every filesystem/device fault callback')
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
        rt.require(not rt.FAULT.search(messages), 'kernel fault', 'KERNEL_FAULT')

    try:
        result['kernel_identity'] = kernel_identity.capture(a, out, rt.command)
        hashes = {}
        for source in (Path(__file__), Path(__file__).with_name('fault_cases.c')):
            hashes[source.name] = rt.digest(source)
            shutil.copyfile(source, out / source.name)
        rt.write_json(out / 'source-sha256.json', hashes)
        client = out / 'fault_cases'
        rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
                    out / 'fault_cases.c', '-o', client], out / 'build.log', timeout=60)
        result['binary_sha256'] = rt.digest(client)
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        result['state'] = 'RUNNING'
        rt.write_json(out / 'result.json', result)
        data = rt.command([client], out / 'cases.jsonl', timeout=120)
        logs()
        rows = [json.loads(line) for line in data.splitlines()]
        rt.require(len(rows) == 18 and all(r['passed'] is True for r in rows), 'case count/results differ')
        rt.require(rows[0] == dict(case='fork_cow_remote_exit', children=16, remote_reads=16,
                                  remote_writes=16, joined=16, passed=True), 'remote-mm or child joins differ')
        for i, row in enumerate(rows[1:-1]):
            address = row['address']
            rt.require(row['case'] == 'userfault_retry_vma_split' and row['round'] == i and
                       row['tid'] > 0 and row['joined'] == 1 and row['value'] == 0xa0 + i and
                       row['before_start'] == address - 4096 and row['before_end'] == address + 8192 and
                       row['after_start'] == address and row['after_end'] == address + 4096,
                       'fault retry/range revalidation or exact worker differs')
        rt.require(rows[-1]['case'] == 'complete' and rows[-1]['checks'] > 0 and
                   rows[-1]['timing'] is False, 'completion missing')
        for name, h in hashes.items():
            rt.require(rt.digest(Path(__file__).parent / name) == rt.digest(out / name) == h,
                       'frozen input changed: ' + name)
        rt.require(rt.digest(client) == result['binary_sha256'], 'binary changed')
        rt.idle()
        result.update(state='COMPLETE', passed=True, drained=True, cases=rows,
                      children_joined=16, fault_threads_joined=16, source_unchanged=True)
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
