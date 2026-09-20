#!/usr/bin/env python3
"""Compare Linux native, the TCLock port and kdlock through direct lock APIs.

Freeze one workload per backend; alternate all arms in each
repeat. Preparation is excluded, correctness and actual delegation are required.
Build/run exclusively in the recovery guest, retaining failures without retry.
"""
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
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import kernel_identity
import bench_runtime as runtime
from bench_runtime import HERE, WORKLOAD, PROVIDER, require, command, digest, Failure
from summarize import write_json, csv_file, valid
from session import BackendSession, TC_MODULE, GUARD_MODULE
from context_audit import audit as audit_context


def idle():
    runtime.idle()
    require(not Path('/sys/module/tclock_backend_km').exists(), 'existing TCLock module')
    require(not Path('/sys/module/tc_allocator_guard').exists(), 'existing allocator guard')


def source_state():
    result = runtime.source_state()
    for folder in ('tclock_backend', 'bench/tclock_compare'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and not any(x.startswith('.') or x == '__pycache__'
                                      for x in p.relative_to(ROOT).parts) and (
                    p.suffix in ('.c', '.h', '.S', '.py', '.patch', '.json', '.md') or
                    p.name == 'Makefile') and not p.name.endswith('.mod.c'):
                result[str(p.relative_to(ROOT))] = digest(p)
    unit = 'tests/unit/spin/test_tclock_context.py'
    result[unit] = digest(ROOT/unit)
    return result


def make_plan(args):
    require(args.repeats > 0 and 0 < args.iterations <= 100000000,
            'invalid repeats/iterations')
    result = []
    workload = getattr(args, 'workload', 'cacheline')
    sizes = [0] if workload == 'rcuht' else (args.cachelines or [1, 16])
    for n, t, repeat in itertools.product(sizes, args.threads, range(args.repeats)):
        arms = list(args.backends)
        if repeat % 2:
            arms.reverse()
        for backend in arms:
            prefix = 'hash1024' if workload == 'rcuht' else f'c{n:02d}'
            result.append(dict(name=f'{prefix}-t{t:02d}-r{repeat:02d}-direct-{backend}',
                cachelines=n, threads=t, repeat=repeat, arm=backend, caller_abi='clobber' if backend == 'kdlock' else 'c',
                api_mode='direct', workload=workload, hotlock_mode=getattr(args, 'hotlock_mode', 'observe'),
                scenario=getattr(args, 'scenario', 'plain'),
                iterations=args.iterations, cpus=list(range(t))))
    return result


def report(out):
    records, groups = [], {}
    for spec in json.loads((out/'plan.json').read_text()):
        p = out/spec['name']/'session.json'
        r = json.loads(p.read_text()) if p.exists() else dict(spec, execution_status='NOT_RUN', drained=False)
        m = r.get('measurement', {})
        r['throughput_ops_s'] = m['completed']*1e9/m['wall_ns'] if valid(r) else None
        r['amortized_ns_op'] = m['wall_ns']/m['completed'] if valid(r) else None
        records.append(r)
        groups.setdefault((r['cachelines'], r['threads'], r['arm']), []).append(r)
    write_json(out/'records.json', records)
    summary = []
    for (n, t, arm), rows in groups.items():
        good = [r for r in rows if valid(r)]
        row = dict(cachelines=n, threads=t, api_mode='direct', arm=arm,
                   workload=rows[0].get('workload', 'cacheline'),
                   sessions=len(rows), valid=len(good),
                   hotlock_mode=rows[0].get('hotlock_mode', 'unrecorded'),
                   actual_jit_sessions=sum(r.get('jit_bodies', 0) > 0 for r in good))
        for metric in ('throughput_ops_s', 'amortized_ns_op'):
            values = [r[metric] for r in good if r.get(metric) is not None]
            row['median_'+metric] = statistics.median(values) if values else None
        summary.append(row)
    natives = {(r['cachelines'], r['threads']): r['median_throughput_ops_s']
               for r in summary if r['arm'] == 'native'}
    for row in summary:
        native = natives.get((row['cachelines'], row['threads']))
        row['throughput_over_linux'] = row['median_throughput_ops_s']/native if native and row['valid'] else None
    write_json(out/'summary.json', summary)
    if summary:
        csv_file(out/'summary.csv', list(summary[0]), summary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workload', choices=('cacheline', 'rcuht'), default='cacheline')
    p.add_argument('--cachelines', type=int, nargs='+', choices=(1,16))
    # The direct comparison uses all five agreed contention levels.
    p.add_argument('--threads', type=int, nargs='+', choices=(1,4,8,16,20), default=[1,4,8,16,20])
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--iterations', type=int, default=100000)
    p.add_argument('--backends', nargs='+', choices=('native','tclock','kdlock'), default=['native','tclock','kdlock'])
    p.add_argument('--dry-run', action='store_true')
    kernel_identity.arguments(p)
    p.add_argument("--hotlock-mode", choices=("observe", "adaptive"), default="observe")
    p.add_argument("--scenario", choices=("plain", "nested", "early"), default="plain")
    args = p.parse_args()
    require(args.scenario == "plain" or (args.backends == ["kdlock"] and args.workload == "cacheline"),
            "nested protocol regression requires KD cacheline workload")
    require(args.workload != 'rcuht' or args.cachelines is None,
            'RCUHT uses a fixed hash table, not --cachelines')
    plan = make_plan(args)
    if args.dry_run:
        print(json.dumps(plan, indent=2)); return 0
    require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'confirmed recovery guest required')
    require(os.uname().release == '6.1.159-kdclobber2', 'verified kdclobber2 kernel required')
    out = args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    idle(); out.mkdir(parents=True); write_json(out/'plan.json', plan)
    try:
        identity = kernel_identity.capture(args, out, command)
        require(command(['findmnt','-T',ROOT,'-n','-o','FSTYPE'],out/'mount.txt').strip() == 'ext4','ext4 required')
        require('nokaslr' in Path('/proc/cmdline').read_text().split() and
                '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text(), 'runtime differs')
        packages = {p:importlib.metadata.version(p) for p in ('miasm','future','pyparsing','pyelftools')}
        require(packages == dict(miasm='0.1.5',future='1.0.0',pyparsing='2.4.7',pyelftools='0.27'), 'dependencies differ')
        topology = runtime.capture_topology(list(range(max(args.threads))))
        for spec in plan:
            spec['cpu_nodes'] = topology['role_nodes'][:spec['threads']]
        write_json(out/'plan.json', plan)
        write_json(out/'environment.json', dict(kernel_identity=identity,topology=topology,packages=packages,
            argv=sys.argv,python=sys.executable,snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            cmdline=Path('/proc/cmdline').read_text(),preemption=Path('/sys/kernel/debug/sched/preempt').read_text(),
            watchdog=Path('/proc/sys/kernel/watchdog').read_text(),uname=list(os.uname())))
        builds = [('client',['make','-C',HERE,'client']),
                  ('allocator-guard',['make','-C',GUARD_MODULE.parent])]
        binaries = [HERE/'client', GUARD_MODULE]
        if 'kdlock' in args.backends:
            builds += [('provider',['make','-C',HERE,'provider']),
                       ('daemon',['make','-C',ROOT/'daemon','CFLAGS=-O2 -Wall -Wextra -Werror'])]
            binaries += [PROVIDER,ROOT/'daemon/daemon']
        if 'tclock' in args.backends:
            # Keep backend and workload build logs distinct: the latter uses
            # build-tclock.log below and must not overwrite backend evidence.
            builds += [('tclock-backend',['make','-C',ROOT/'tclock_backend'])]
            binaries += [TC_MODULE]
        for name, build in builds:
            command([*build,f'KDIR={args.kernel_source}'],out/f'build-{name}.log',timeout=180)
        if 'tclock' in args.backends:
            # Check the actual ELF: changing a Kbuild variable must not leave a
            # stale instrumented backend in a run labelled as unsanitized.
            imported = command(['nm', '-u', TC_MODULE], out/'imports-tclock-backend.txt')
            require('__ubsan_' not in imported, 'TCLock backend still imports UBSAN handlers')
            symbols = command(['nm', '-a', TC_MODULE], out/'symbols-tclock-backend.txt')
            require(not any(name in symbols for name in
                            ('tc_delegated', 'tc_completed', 'tc_batches')),
                    'TCLock still contains added execution counters')
            disassembly = command(['objdump', '-dr', '--no-show-raw-insn', TC_MODULE],
                                  out/'tclock-backend.txt')
            write_json(out/'tclock-context-audit.json', audit_context(disassembly))
        variants = {}
        for backend in args.backends:
            folder = out/'variants'/backend; folder.mkdir(parents=True)
            for src in WORKLOAD.iterdir():
                if src.suffix in ('.c','.h','.inc') or src.name == 'Makefile':
                    shutil.copyfile(src, folder/src.name)
            extra = []
            if backend != 'native':
                module = PROVIDER if backend == 'kdlock' else TC_MODULE
                extra = [f'KBUILD_EXTRA_SYMBOLS={module.parent / "Module.symvers"}']
            command(['make','-C',folder,f'KDIR={args.kernel_source}',
                     f'SC_BACKEND={backend}', f'SC_WORKLOAD={args.workload}',
                     f'SC_SCENARIO={dict(plain=0, nested=1, early=2)[args.scenario]}',
                     f'KDLOCK_INCLUDE={ROOT / "include"}', *extra],
                    out/f'build-{backend}.log',timeout=120)
            variants[backend] = folder/'spin_cacheline.ko'
            command(['objdump','-dr',variants[backend]],out/f'caller-{backend}.txt')
            imported = command(['nm', '-u', variants[backend]], out/f'imports-{backend}.txt')
            require('__ubsan_' not in imported, 'direct workload still imports UBSAN handlers')
            require('kd_raw_spin_' not in imported and 'kd_spin_dispatch_' not in imported,
                    'workload still imports a unified spin hook')
            expected = {'kdlock': ('kd_spin_lock_clobber_v1', 'kd_spin_unlock_clobber_v1', 'kd_spin_prepare'),
                        'tclock': ('komb_spin_lock', 'komb_spin_unlock'), 'native': ()}[backend]
            require(all(symbol in imported.split() for symbol in expected), 'missing direct API import')
        (out/'binaries').mkdir()
        for binary in binaries:
            shutil.copyfile(binary,out/'binaries'/binary.name)
        binaries += list(variants.values())
        frozen = source_state(); write_json(out/'source-sha256.json',frozen)
        for relative in frozen:
            target = out/'source'/relative; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,target)
        hashes = {str(p):digest(p) for p in binaries}; write_json(out/'binary-sha256.json',hashes)
        for index,spec in enumerate(plan):
            require(not (out/'STOP').exists(),'STOP requested at drained boundary','STOPPED')
            require(source_state()==frozen and all(digest(Path(p))==h for p,h in hashes.items()),'frozen inputs changed')
            idle(); print(f'[{index+1}/{len(plan)}] {spec["name"]}',flush=True)
            session = BackendSession(out,spec,workload_module=variants[spec['arm']])
            session.execute()
            m = session.record['measurement']
            print(f'  {m["completed"]*1e3/m["wall_ns"]:.3f} Mops/s; '
                  f'{m["wall_ns"]/m["completed"]:.2f} ns/op; drained=True',flush=True)
        idle(); report(out); return 0
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        report(out); print(f'STOP: {error}',file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
