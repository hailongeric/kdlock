#!/usr/bin/env python3
"""Recovery-guest component timings for unchanged old/new hotlock samplers.

This does not measure lock operations or JIT. Sources and modules are copied to
new external evidence directories; production source files are never replaced.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import kernel_identity
import bench_runtime as runtime


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, obj):
    p.write_text(json.dumps(obj, indent=2) + '\n')


def command(args, log, timeout=120):
    args = list(map(str, args))
    with log.open('w') as stream:
        stream.write(json.dumps(args) + '\n'); stream.flush()
        subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)
    return log.read_text().split('\n', 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True,
                        help='Frozen root containing include/kd_hotlock.h and kernel_module/kd_hotlock.c')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, nargs='+', choices=(1, 4, 20), default=[1, 4, 20])
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--iterations', type=int, default=100000)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    if (os.geteuid() or ROOT != Path('/root/host_fs/kdlock') or
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or
            args.repeats < 1 or not 1 <= args.iterations <= 1000000):
        raise RuntimeError('confirmed recovery guest and valid counts required')
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise RuntimeError('new external evidence directory required')
    runtime.idle()
    if Path('/sys/module/hotlock_record_bench').exists():
        raise RuntimeError('component benchmark already loaded')
    out.mkdir(parents=True)
    identity = kernel_identity.capture(args, out, command)
    write(out / 'environment.json', dict(kernel=identity, argv=sys.argv,
          topology=runtime.capture_topology(list(range(max(args.threads)))),
          cmdline=Path('/proc/cmdline').read_text(),
          preempt=Path('/sys/kernel/debug/sched/preempt').read_text(),
          snapshot=os.environ.get('KDLOCK_SNAPSHOT_TAG')))
    harness = ROOT / 'tests/kernel/hotlock_record'
    modules, hashes = {}, {}
    for variant, source in [('before', args.baseline), ('after', ROOT)]:
        build = out / variant; build.mkdir()
        files = {harness/'record_bench.c': 'record_bench.c', harness/'Makefile': 'Makefile',
                 source/'include/kd_hotlock.h': 'kd_hotlock.h',
                 source/'kernel_module/kd_hotlock.c': 'kd_hotlock.c',
                 ROOT/'include/utils.h': 'utils.h'}
        for src, name in files.items():
            shutil.copyfile(src, build/name)
            hashes[str(build/name)] = digest(build/name)
        command(['make', '-C', build, f'KDIR={args.kernel_source}'], out/f'build-{variant}.log')
        modules[variant] = build/'hotlock_record_bench.ko'
        hashes[str(modules[variant])] = digest(modules[variant])
        command(['objdump', '-dr', modules[variant]], out/f'assembly-{variant}.txt')
    shutil.copyfile(__file__, out/'run.py')
    write(out/'input-sha256.json', hashes)
    plans = []
    for phase, threads, repeat in itertools.product(range(3), args.threads, range(args.repeats)):
        for variant in (('before', 'after') if repeat % 2 == 0 else ('after', 'before')):
            plans.append(dict(phase=phase, threads=threads, repeat=repeat, variant=variant))
    write(out/'plan.json', plans)
    rows = []
    try:
        for index, plan in enumerate(plans):
            runtime.idle()
            if any(digest(Path(p)) != h for p, h in hashes.items()):
                raise RuntimeError('frozen input changed')
            session = out/f'{index:03d}-{plan["variant"]}'; session.mkdir()
            command(['dmesg'], session/'dmesg-before.txt')
            command(['dmesg', '-C'], session/'clear.log')
            try:
                command(['insmod', modules[plan['variant']], f'threads={plan["threads"]}',
                         f'phase={plan["phase"]}', f'iterations={args.iterations}'], session/'load.log', 45)
            finally:
                if Path('/sys/module/hotlock_record_bench').exists():
                    command(['rmmod', 'hotlock_record_bench'], session/'unload.log', 20)
                log = command(['dmesg'], session/'dmesg.txt')
            if re.search(r'BUG:|panic|double fault|soft lockup|unable to handle|WARNING:', log):
                raise RuntimeError(f'kernel error: {session}')
            match = re.findall(r'HOTLOCK_RECORD ((?:\w+=\d+ ?)+)', log)
            if len(match) != 1:
                raise RuntimeError(f'missing/duplicate result: {session}')
            parsed = {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)', match[0])}
            if any(parsed[k] != plan[k] for k in ('phase', 'threads')):
                raise RuntimeError(f'result does not match plan: {parsed}')
            row = dict(plan, **{k:v for k,v in parsed.items() if k not in plan})
            if (row['status'] != (0 if plan['phase'] == 1 else 2) or not row['balanced'] or
                    not row['calls'] or not row['wall_ns'] or
                    (plan['phase'] and row['calls'] != plan['threads']*args.iterations)):
                raise RuntimeError(f'invalid result: {row}')
            row['wall_ns_call'] = row['wall_ns']/row['calls']
            row['worker_ns_call'] = row['worker_ns']/row['calls']
            rows.append(row); write(session/'result.json', row)
            print(f'{index+1}/{len(plans)} {plan}: {row["worker_ns_call"]:.2f} worker ns/call', flush=True)
    finally:
        write(out/'records.json', rows)
    summary = []
    for phase, threads, variant in itertools.product(range(3), args.threads, ('before', 'after')):
        group = [r for r in rows if (r['phase'],r['threads'],r['variant']) == (phase,threads,variant)]
        summary.append(dict(phase=phase, threads=threads, variant=variant, runs=len(group),
            **{key:statistics.median(r[key] for r in group)
               for key in ('calls','wall_ns','wall_ns_call','worker_ns_call')}))
    write(out/'summary.json', summary)
    runtime.idle()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
