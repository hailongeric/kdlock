#!/usr/bin/env python3
"""Compare Linux native, complete TCLock and kdlock using identical callers.

Freeze both caller ABIs and all three backends; alternate all arms in each
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
    for n, t, repeat in itertools.product(args.cachelines, args.threads, range(args.repeats)):
        arms = list(itertools.product(args.backends, args.abis))
        if repeat % 2:
            arms.reverse()
        for backend, abi in arms:
            result.append(dict(name=f'c{n:02d}-t{t:02d}-r{repeat:02d}-{abi}-{backend}',
                cachelines=n, threads=t, repeat=repeat, arm=backend, caller_abi=abi,
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
        groups.setdefault((r['cachelines'], r['threads'], r['caller_abi'], r['arm']), []).append(r)
    write_json(out/'records.json', records)
    summary = []
    for (n, t, abi, arm), rows in groups.items():
        good = [r for r in rows if valid(r)]
        row = dict(cachelines=n, threads=t, caller_abi=abi, arm=arm,
                   sessions=len(rows), valid=len(good),
                   zero_delegation=sum(r.get('delegated_bodies') == 0 for r in good))
        for metric in ('throughput_ops_s', 'amortized_ns_op', 'delegation_share'):
            values = [r[metric] for r in good if r.get(metric) is not None]
            row['median_'+metric] = statistics.median(values) if values else None
        summary.append(row)
    write_json(out/'summary.json', summary)
    csv_file(out/'summary.csv', list(summary[0]), summary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cachelines', type=int, nargs='+', choices=(1,16), default=[1,16])
    p.add_argument('--threads', type=int, nargs='+', choices=(1,4,20), default=[1,4,20])
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--iterations', type=int, default=100000)
    p.add_argument('--backends', nargs='+', choices=('native','tclock','kdlock'), default=['native','tclock','kdlock'])
    p.add_argument('--abis', nargs='+', choices=('legacy','clobber'), default=['legacy','clobber'])
    p.add_argument('--dry-run', action='store_true')
    kernel_identity.arguments(p)
    args = p.parse_args()
    plan = make_plan(args)
    if args.dry_run:
        print(json.dumps(plan, indent=2)); return 0
    require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'confirmed recovery guest required')
    require(os.uname().release == '6.1.159-kdclobber1', 'same kdclobber1 kernel required')
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
            builds += [('tclock',['make','-C',ROOT/'tclock_backend'])]
            binaries += [TC_MODULE]
        for name, build in builds:
            command([*build,f'KDIR={args.kernel_source}'],out/f'build-{name}.log',timeout=180)
        variants = {}
        for abi in args.abis:
            folder = out/'variants'/abi; folder.mkdir(parents=True)
            for src in WORKLOAD.iterdir():
                if src.suffix in ('.c','.h','.inc') or src.name == 'Makefile':
                    shutil.copyfile(src, folder/src.name)
            # Same batch-boundary IRQ/preempt oracle for all six arms; the
            # measured payload and its per-operation loop remain unchanged.
            command(['patch','--batch','--forward','--fuzz=0','-p1','-i',
                     ROOT/'bench/tclock_compare/workload-observation.patch'],
                    out/f'patch-{abi}.log',cwd=folder)
            flags = '-DKD_SPIN_LEGACY_CALLER' if abi == 'legacy' else ''
            command(['make','-C',folder,f'KDIR={args.kernel_source}',f'KCFLAGS={flags}'],out/f'build-{abi}.log',timeout=120)
            variants[abi] = folder/'spin_cacheline.ko'
            command(['objdump','-dr',variants[abi]],out/f'caller-{abi}.txt')
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
            session = BackendSession(out,spec,workload_module=variants[spec['caller_abi']])
            session.execute()
            print(f'  {session.record["delegation_status"]} share={session.record["delegation_share"]:.4%} drained=True',flush=True)
        idle(); report(out); return 0
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        report(out); print(f'STOP: {error}',file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
