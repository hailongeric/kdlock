#!/usr/bin/env python3
"""Small shared-record nano profiles; live work runs only in the recovery VM."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PROFILES = {'mutex': ('mutex', 100), 'rwsem-read': ('rwsem', 1),
            'rwsem-mixed': ('rwsem', 20), 'mutex-locality': ('mutex', 100),
            'mutex-throughput': ('mutex', 100)}
THREADS = [*range(1, 9), *range(12, 61, 4)]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--profiles', nargs='+', choices=PROFILES,
                   default=['mutex-throughput', 'mutex-locality', 'rwsem-read', 'rwsem-mixed'])
    p.add_argument('--threads', nargs='+', type=int, default=THREADS)
    p.add_argument('--backends', nargs='+', choices=('native', 'tclock', 'kdlock'),
                   default=['native', 'tclock', 'kdlock'])
    p.add_argument('--repeats', type=int, choices=(1, 3), default=1)
    p.add_argument('--post-work-rounds', type=int,
                   help='override all profiles; defaults: mutex-throughput/locality=256, other profiles=4')
    p.add_argument('--delegate', choices=('on', 'off'), default='on')
    p.add_argument('--mutex-batch-limit', type=int, default=1024,
                   help='KD mutex total service cap; default 1024')
    p.add_argument('--mutex-numa-boundary', type=int, default=768,
                   help='KD mutex NUMA cohort boundary; default 768')
    p.add_argument('--functional', action='store_true')
    p.add_argument('--plan-only', action='store_true')
    return p


def commands(args):
    cap, boundary = args.mutex_batch_limit, args.mutex_numa_boundary
    if not (type(cap) is int and type(boundary) is int and 1 <= cap <= 32767 and 1 <= boundary <= 32767):
        raise ValueError('mutex policy requires total cap and NUMA boundary in 1..32767')
    if (cap, boundary) != (1024, 768) and not (
            all(PROFILES[name][0] == 'mutex' for name in args.profiles) and
            'kdlock' in args.backends and args.delegate == 'on'):
        raise ValueError('nondefault mutex policy requires only public KD mutex profiles')
    for values in (args.profiles, args.threads, args.backends):
        if not values or len(values) != len(set(values)):
            raise ValueError('empty or duplicate selection')
    if not all(1 <= n <= 60 for n in args.threads) or (
            args.post_work_rounds is not None and not 1 <= args.post_work_rounds <= 256):
        raise ValueError('workers must be 1..60; post-work rounds must be 1..256')
    if args.functional and args.repeats != 1:
        raise ValueError('functional checks require one round')
    for profile in args.profiles:
        family, percent = PROFILES[profile]
        name = profile + ('-local' if args.delegate == 'off' else '')
        counters = profile in ('mutex-throughput', 'mutex-locality')
        lines = 1 if profile == 'mutex-throughput' else 16 if counters else 2
        post_work = args.post_work_rounds if args.post_work_rounds is not None else (256 if counters else 4)
        yield name, [sys.executable, str(ROOT/'bench/rwlock_compare/run.py'),
            '--workloads', 'cacheline' if counters else 'nano',
            '--cachelines', str(lines),
            '--lock-kind', family, '--write-percent', str(percent),
            '--threads', *map(str, args.threads), '--cpus', *map(str, range(max(args.threads))),
            '--collector-cpu', '63', '--backends', *args.backends,
            '--repeats', str(args.repeats), '--duration-ms', '2000',
            '--post-work-rounds', str(post_work), '--delegate', args.delegate,
            '--mutex-batch-limit', str(cap), '--mutex-numa-boundary', str(boundary),
            *(['--functional'] if args.functional else []),
            '--kernel-source', '/root/linux-6.1.159-kdclobber2',
            '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919',
            '--output', str(args.output.resolve()/name)]


def main():
    args = parser().parse_args()
    plan = list(commands(args))
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    if (ROOT != Path('/root/host_fs/kdlock') or os.geteuid() != 0 or
            os.uname().release != '6.1.159-kdclobber2' or
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') != '1' or
            os.environ.get('KDLOCK_SNAPSHOT_TAG') != 'before-mutex-kdonly-20261017T140354Z'):
        raise RuntimeError('confirmed recovery VM required; verify the actual snapshot first')
    out = args.output.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('retain new evidence outside the checkout')
    with open('/run/lock/kdlock-nano.lock', 'w') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out.mkdir(parents=True, exist_ok=False)
        sys.path.insert(0, str(ROOT/'bench/rwlock_compare'))
        from run import sources
        frozen = sources()
        (out/'source-sha256.json').write_text(json.dumps(frozen, indent=2)+'\n')
        (out/'commands.json').write_text(json.dumps(plan, indent=2)+'\n')
        receipt = dict(pid=os.getpid(), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                       source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       provider_mutex_policy=dict(total_cap=args.mutex_batch_limit,
                           numa_boundary=args.mutex_numa_boundary, deferred_handoff=8, scan_budget=64),
                       blocks=[])
        for name, command in plan:
            if sources() != frozen:
                raise RuntimeError('campaign sources changed between profiles')
            if (out/'STOP').exists() or shutil.disk_usage(out).free < 512*1024**2:
                raise RuntimeError('stop requested or storage reserve exhausted')
            row = dict(profile=name, argv=command, started=time.time(), completion_unconfirmed=True)
            receipt['blocks'].append(row)
            with (out/(name+'.log')).open('x') as log:
                child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                row['pid'] = child.pid
                (out/'owner.json').write_text(json.dumps(receipt, indent=2)+'\n')
                print('START', name, flush=True)
                try:
                    code = child.wait(timeout=3600)
                except subprocess.TimeoutExpired:
                    row['error'] = 'deadline expired; child untouched; drain unproven'
                    (out/'owner.json').write_text(json.dumps(receipt, indent=2)+'\n')
                    return 3
            row.update(returncode=code, completion_unconfirmed=False, finished=time.time())
            (out/'owner.json').write_text(json.dumps(receipt, indent=2)+'\n')
            print('FINISH', name, code, flush=True)
            if code:
                return code
            if sources() != frozen:
                raise RuntimeError('campaign sources changed during profile')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
