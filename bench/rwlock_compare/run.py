#!/usr/bin/env python3
"""Compare native, TCLock and KD rwlocks in the verified recovery guest."""
import argparse
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
from bench_runtime import Failure, command, digest, idle as common_idle, require, capture_topology
from summarize import write_json
import kernel_identity
from provider.prepare import prepare as prepare_provider
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
from context_audit import audit
# Import our session explicitly from this directory, not the spin/mutex runner.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from session import RWSession
from parity import assess
import boot_policy

FULL_THREADS = [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mutex-spin-limit', type=int, default=4096)
    p.add_argument('--output', type=Path)
    p.add_argument('--backends', nargs='+', choices=('native', 'tclock', 'kdlock'),
                   default=['native', 'tclock', 'kdlock'])
    p.add_argument('--workloads', nargs='+', choices=('cacheline', 'rcuht'), default=['rcuht'])
    p.add_argument('--cachelines', nargs='+', type=int, choices=(1, 2, 4, 8, 16), default=[1])
    p.add_argument('--write-percent', nargs='+', type=int, default=[1, 20])
    p.add_argument('--threads', nargs='+', type=int, default=FULL_THREADS)
    p.add_argument('--full-matrix', action='store_true', help='select the existing 15-point thread set')
    p.add_argument('--cpus', nargs='+', type=int, help='ordered worker CPU list; cohorts take prefixes')
    p.add_argument('--collector-cpu', type=int, default=38)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--duration-ms', type=int, default=2000)
    p.add_argument('--peak-window-ms', type=int, default=300)
    p.add_argument('--peak-settle-ms', type=int, default=300)
    p.add_argument('--sample-ms', type=int, default=10)
    p.add_argument('--iterations', type=int, default=50000, help='per worker for fixed/functional runs')
    p.add_argument('--post-work-rounds', type=int, default=4)
    p.add_argument('--spin-entry-ratio-limit', type=int, default=2)
    p.add_argument('--delegate', choices=('on', 'off'), default='on', help='KD native control when off')
    p.add_argument('--require-jit', action='store_true', help='require JIT for every multithread KD writer case')
    p.add_argument('--require-parity', action='store_true',
                   help='fail after the full comparison if KD is slower on peak or median whole-run throughput')
    p.add_argument('--functional', action='store_true', help='one fixed-iteration round, no performance scores')
    p.add_argument('--dry-run', action='store_true', help='print plan without builds, modules or timing')
    kernel_identity.arguments(p)
    return p


def make_plan(args):
    require(0 <= getattr(args, 'mutex_spin_limit', 4096) <= 1048576, 'mutex spin limit must be 0..1048576')
    threads = FULL_THREADS if args.full_matrix else args.threads
    for values, name in ((threads, 'threads'), (args.backends, 'backends'), (args.workloads, 'workloads'),
                         (args.cachelines, 'cachelines'), (args.write_percent, 'write percentages')):
        require(values and len(values) == len(set(values)), 'empty/duplicate ' + name)
    require(all(1 <= n <= 64 for n in threads), 'threads must be 1..64')
    require(all(0 <= p <= 100 for p in args.write_percent), 'write percentages must be 0..100')
    require(1 <= args.post_work_rounds <= 256 and 0 < args.iterations <= 100000000,
            'invalid post-work or iterations')
    require(args.repeats == (1 if args.functional else 3), 'use one functional round or three performance rounds')
    require(not args.require_parity or (not args.functional and
            set(args.backends) == {'native', 'tclock', 'kdlock'}),
            '--require-parity needs all three backends and a timed comparison')
    require(args.spin_entry_ratio_limit in (0, *(1 << n for n in range(1, 32))), 'invalid entry ratio limit')
    require(not args.require_jit or (args.delegate == 'on' and 'kdlock' in args.backends and
            max(threads) > 1 and max(args.write_percent) > 0), '--require-jit needs contended KD writers')
    cpus = args.cpus if args.cpus is not None else list(range(max(threads)))
    require(len(cpus) >= max(threads) and len(set(cpus)) == len(cpus) and all(c >= 0 for c in cpus),
            'need distinct nonnegative worker CPUs')
    require(args.collector_cpu >= 0 and args.collector_cpu not in cpus[:max(threads)],
            'collector must have a separate CPU')
    duration = 0 if args.functional else args.duration_ms
    require(args.functional or 0 < duration <= 10000, 'performance runs require a timed interval')
    require(0 < args.sample_ms <= args.peak_window_ms and args.peak_settle_ms >= 0 and
            (not duration or args.peak_settle_ms + args.peak_window_ms < duration), 'invalid peak intervals')
    cases = [(workload, lines) for workload in args.workloads
             for lines in (args.cachelines if workload == 'cacheline' else [0])]
    plan = []
    for (workload, lines), percent, n, repeat in itertools.product(cases, args.write_percent, threads, range(args.repeats)):
        for arm in (args.backends if repeat % 2 == 0 else list(reversed(args.backends))):
            variant = f'{workload}-c{lines:02d}-{arm}'
            plan.append(dict(name=f'{variant}-w{percent:03d}-t{n:02d}-r{repeat:02d}', variant=variant,
                arm=arm, workload=workload, cachelines=lines, write_percent=percent, threads=n, repeat=repeat,
                cpus=cpus[:n], collector_cpu=args.collector_cpu, iterations=args.iterations,
                duration_ms=duration, peak_window_ms=args.peak_window_ms, peak_settle_ms=args.peak_settle_ms,
                sample_ms=args.sample_ms, functional=args.functional, post_work_rounds=args.post_work_rounds,
                warmup_iterations_per_worker=48000, mix_policy='evenly_spaced_worker_phase17',
                lock_kind='rwlock', caller_abi='clobber' if arm == 'kdlock' else 'c',
                delegate=args.delegate == 'on' if arm == 'kdlock' else False,
                require_jit=args.require_jit and arm == 'kdlock' and percent > 0 and n > 1,
                spin_entry_ratio_limit=args.spin_entry_ratio_limit if arm == 'kdlock' else None,
                mutex_wait_mode='blocking' if arm == 'kdlock' else 'not_applicable',
                mutex_spin_limit=getattr(args, 'mutex_spin_limit', 4096) if arm == 'kdlock' else None,
                numa_policy='on' if arm != 'native' else 'not_applicable', provider_ubsan='off',
                delegation_batch_limit=1024 if arm != 'native' else None))
    return plan


def valid(row):
    return (row.get('execution_status') == 'OK' and row.get('drained') is True and
            row.get('measurement', {}).get('data_ok') is True and
            row.get('measurement', {}).get('complete') is True)


def report(out):
    records, groups = [], {}
    for spec in json.loads((out / 'plan.json').read_text()):
        path = out / spec['name'] / 'session.json'
        row = json.loads(path.read_text()) if path.exists() else dict(spec, execution_status='NOT_RUN', drained=False)
        records.append(row)
        if not valid(row) or row['functional']:
            continue
        m = row['measurement']
        row['whole_ops_s'] = m['completed'] * 1e9 / m['wall_ns']
        row['read_ops_s'] = m['reads'] * 1e9 / m['wall_ns']
        row['write_ops_s'] = m['writes'] * 1e9 / m['wall_ns']
        row['peak_ops_s'] = m['peak']['throughput_ops_s']
        # No pooling of JIT positives and native-admitted runs, or different
        # placement/mixes/post-work. This report consumes one frozen plan only.
        key = (row['variant'], row['write_percent'], row['threads'], row['jit_status'])
        groups.setdefault(key, []).append(row)
    summary = []
    for key, rows in groups.items():
        peaks = [row['peak_ops_s'] for row in rows]
        whole = [row['whole_ops_s'] for row in rows]
        summary.append(dict(variant=key[0], write_percent=key[1], threads=key[2], jit_status=key[3],
            valid_rounds=len(rows), expected_rounds=3, complete=len(rows) == 3,
            best_peak_ops_s=max(peaks), peak_min_ops_s=min(peaks), peak_median_ops_s=statistics.median(peaks),
            peak_max_ops_s=max(peaks), peak_spread_pct=(max(peaks) - min(peaks)) * 100 / min(peaks),
            whole_min_ops_s=min(whole), whole_median_ops_s=statistics.median(whole), whole_max_ops_s=max(whole),
            samples=[row['name'] for row in rows]))
    write_json(out / 'records.json', records)
    write_json(out / 'summary.json', summary)
    parity = assess(json.loads((out / 'plan.json').read_text()), summary)
    write_json(out / 'parity.json', parity)
    return parity


def idle():
    common_idle()
    for module in ('rwlock_bench', 'rwlock_test', 'tclock_backend_km', 'tclock_mutex_backend_km',
                   'tclock_rwlock_backend_km', 'tc_allocator_guard'):
        require(not Path('/sys/module', module).exists(), 'existing module: ' + module)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            require(path.read_text().strip() != 'rb_worker', 'existing rwlock worker')
        except FileNotFoundError:
            pass


def sources():
    result = {}
    for directory in ('include', 'kernel_module', 'daemon', 'disassem', 'tclock_backend',
                      'workload_modules/rwlock_bench', 'workload_modules/spin_cacheline',
                      'bench/rwlock_compare', 'bench/spin_cacheline', 'bench/tclock_compare',
                      'tests/protocols', 'kernel_baseline'):
        for path in (ROOT / directory).rglob('*'):
            relative = path.relative_to(ROOT)
            if (path.is_file() and not any(part.startswith('.') or part in ('__pycache__', 'results')
                                          for part in relative.parts) and not path.name.endswith('.mod.c') and
                    (path.suffix in ('.c', '.h', '.inc', '.S', '.def', '.py', '.patch', '.json') or
                     path.name in ('Makefile', 'requirements.txt', 'guest.config'))):
                result[str(relative)] = digest(path)
    return result


def build(args, out, plan):
    source = out / 'source'
    builds = out / 'build'
    builds.mkdir()
    binaries = dict(workloads={})
    guard = builds / 'guard'
    shutil.copytree(source / 'bench/tclock_compare/allocator_guard', guard)
    command(['make', '-C', guard, f'KDIR={args.kernel_source}'], out / 'build-guard.log', timeout=180)
    binaries['guard'] = guard / 'tc_allocator_guard.ko'
    if 'kdlock' in args.backends:
        provider = builds / 'provider'
        prepare_provider(provider, source)
        command(['make', '-C', provider / 'kernel_module', f'KDIR={args.kernel_source}', 'W=1',
                 'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024', 'UBSAN_SANITIZE=n'],
                out / 'build-kdlock.log', timeout=180)
        binaries['kdlock'] = provider / 'kernel_module/kdlock_km.ko'
        command(['make', '-C', source / 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'],
                out / 'build-daemon.log', timeout=120)
        binaries['daemon'] = source / 'daemon/daemon'
        for field, expected in (('spin_numa', '1'), ('spin_batch', '1024')):
            require(command(['modinfo', '-F', field, binaries['kdlock']], out / (field + '.txt')).strip() == expected,
                    'KD compiled policy differs')
    if 'tclock' in args.backends:
        tc = builds / 'tclock'
        shutil.copytree(source / 'tclock_backend', tc)
        command(['make', '-C', tc, f'KDIR={args.kernel_source}', 'TCLOCK_RWLOCK=1', 'TCLOCK_NUMA=1'],
                out / 'build-tclock.log', timeout=180)
        binaries['tclock'] = tc / 'tclock_rwlock_backend_km.ko'
        require(command(['modinfo', '-F', 'rwlock_numa', binaries['tclock']], out / 'tc-numa.txt').strip() == '1',
                'TCLock compiled policy differs')
        disasm = command(['objdump', '-dr', '--no-show-raw-insn', binaries['tclock']], out / 'tclock-context.txt')
        write_json(out / 'tclock-context-audit.json', audit(disasm, 'rwlock'))
    for spec in plan:
        variant, backend = spec['variant'], spec['arm']
        if variant in binaries['workloads']:
            continue
        folder = builds / variant
        shutil.copytree(source / 'workload_modules/rwlock_bench', folder)
        extra = [] if backend == 'native' else [f'KBUILD_EXTRA_SYMBOLS={binaries[backend].parent / "Module.symvers"}']
        command(['make', '-C', folder, f'KDIR={args.kernel_source}', f'RB_BACKEND={backend}',
                 f'RB_WORKLOAD={spec["workload"]}', f'RB_LINES={spec["cachelines"]}',
                 f'RB_POST_WORK_ROUNDS={spec["post_work_rounds"]}',
                 f'KDLOCK_INCLUDE={source / "include"}', f'TCLOCK_INCLUDE={source / "tclock_backend/include"}',
                 f'RB_SHARED={source / "workload_modules/spin_cacheline"}', *extra],
                out / ('build-' + variant + '.log'), timeout=180)
        binary = folder / 'rwlock_bench.ko'
        binaries['workloads'][variant] = binary
        imports = command(['nm', '-u', binary], out / ('imports-' + variant + '.txt'))
        expected = {'native': (), 'tclock': ('komb_read_lock', 'komb_read_unlock', 'komb_write_lock', 'komb_write_unlock'),
                    'kdlock': ('kd_spin_prepare', 'kd_rwlock_lock_pinned_clobber_v1', 'kd_spin_unlock_clobber_v1')}[backend]
        require(all(name in imports.split() for name in expected), 'missing direct rwlock API imports')
        require(backend != 'native' or not any(name in imports for name in ('kd_', 'komb_')), 'native imports a delegate')
        command(['objdump', '-dr', binary], out / ('caller-' + variant + '.txt'))
    all_binaries = [value for key, value in binaries.items() if key != 'workloads'] + list(binaries['workloads'].values())
    for binary in all_binaries:
        if binary.suffix == '.ko':
            imports = command(['nm', '-u', binary], out / (binary.parent.name + '-ubsan.txt'))
            require('__ubsan_' not in imports, 'benchmark module imports UBSAN handlers')
    hashes = {str(path): digest(path) for path in all_binaries}
    write_json(out / 'binary-sha256.json', hashes)
    return binaries, hashes


def main(argv=None):
    args = parser().parse_args(argv)
    plan = make_plan(args)
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    require(args.output is not None, '--output is required')
    require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'confirmed recovery guest and recorded snapshot tag required')
    out = args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT), 'use a new output directory outside source')
    idle()
    out.mkdir(parents=True)
    write_json(out / 'plan.json', plan)
    try:
        identity = kernel_identity.capture(args, out, command)
        require(command(['findmnt', '-T', ROOT, '-n', '-o', 'FSTYPE'], out / 'mount.txt').strip() == 'ext4', 'ext4 required')
        require('nokaslr' in Path('/proc/cmdline').read_text().split() and
                '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text(), 'runtime policy differs')
        policy = boot_policy.capture(args.kernel_source, out, command)
        packages = {p: importlib.metadata.version(p) for p in ('miasm', 'future', 'pyparsing', 'pyelftools')}
        require(packages == dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27'), 'dependencies differ')
        cpus = max((spec['cpus'] for spec in plan), key=len)
        topology = capture_topology(cpus + [args.collector_cpu])
        for spec in plan:
            spec['cpu_nodes'] = topology['role_nodes'][:spec['threads']]
        write_json(out / 'plan.json', plan)
        write_json(out / 'environment.json', dict(kernel_identity=identity, boot_policy=policy,
            topology=topology, packages=packages, argv=sys.argv, python=sys.executable,
            snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], cmdline=Path('/proc/cmdline').read_text(),
            preemption=Path('/sys/kernel/debug/sched/preempt').read_text(), uname=list(os.uname())))
        frozen = sources()
        for relative in frozen:
            target = out / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        require(frozen == {relative: digest(out / 'source' / relative) for relative in frozen}, 'source copy changed')
        write_json(out / 'source-sha256.json', frozen)
        binaries, hashes = build(args, out, plan)
        for index, spec in enumerate(plan):
            require(not (out / 'STOP').exists(), 'STOP requested at drained case boundary', 'STOPPED')
            require(sources() == frozen and
                    all(digest(out / 'source' / path) == value for path, value in frozen.items()) and
                    all(digest(Path(path)) == value for path, value in hashes.items()),
                    'frozen inputs changed')
            idle()
            print(f'[{index + 1}/{len(plan)}] {spec["name"]}', flush=True)
            session = RWSession(out, spec, binaries)
            session.execute()
            print(f'  reads={session.record["measurement"]["reads"]} writes={session.record["measurement"]["writes"]} '
                  f'JIT={session.record["jit_bodies"]} drained=True', flush=True)
        idle()
        parity = report(out)
        require(not args.require_parity or parity['status'] == 'PASS',
                'KD throughput parity target not met; see parity.json', 'PERFORMANCE_REGRESSION')
        return 0
    except (Failure, OSError, ValueError, KeyError, AssertionError) as error:
        write_json(out / 'failure.json', dict(error=str(error), status=getattr(error, 'status', 'FAILED')))
        report(out)
        print(f'STOP: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
