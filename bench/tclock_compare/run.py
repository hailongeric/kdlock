#!/usr/bin/env python3
"""Compare Linux native, the TCLock port and kdlock through direct lock APIs.

Freeze each backend build; KD always uses adaptive CPU and lock admission.
Three rounds alternate arm order. Preparation is excluded; acceptance checks remain.
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

DEFAULT_SPIN_CONTENTION_PCT = 100
TIMING_FIELDS = ('duration_ms', 'peak_window_ms', 'peak_settle_ms',
                 'sample_ms', 'collector_cpu')


def timing_settings(args):
    settings = {name: getattr(args, name, default) for name, default in
                zip(TIMING_FIELDS, (0, 300, 300, 10, 30))}
    duration = settings['duration_ms']
    require(0 <= duration <= 10000, 'duration must be 0..10000 ms')
    if duration:
        require(0 < settings['sample_ms'] <= settings['peak_window_ms'] and
                settings['peak_settle_ms'] >= 0 and
                settings['peak_settle_ms'] + settings['peak_window_ms'] < duration,
                'invalid peak timing intervals')
        require(settings['collector_cpu'] >= 0 and all(
                settings['collector_cpu'] not in range(t) for t in args.threads),
                'collector CPU must be outside every worker cohort')
        require(getattr(args, 'scenario', 'plain') == 'plain' and
                getattr(args, 'workload', 'cacheline') == 'cacheline' and
                not getattr(args, 'functional', False),
                'timed peaks require the plain cacheline performance workload')
    return settings


def collector_topology(cpu):
    # Preparation keeps the runner's original NUMA placement. Only the live
    # progress collector deliberately expands affinity to its reserved CPU.
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {cpu})
        return runtime.capture_topology([cpu])
    finally:
        os.sched_setaffinity(0, previous)


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
    contention_pct = getattr(args, 'spin_contention_pct', DEFAULT_SPIN_CONTENTION_PCT)
    require(0 <= contention_pct <= 100, 'invalid spin contention percentage')
    result = []
    timing = timing_settings(args)
    workload = getattr(args, 'workload', 'cacheline')
    sizes = [0] if workload == 'rcuht' else (args.cachelines or [1, 16])
    # Admission is adaptive only. Retain the fixed metadata label so reports
    # keep current results separate from historically frozen admission modes.
    variants = [(backend, 'adaptive' if backend == 'kdlock' else 'not_applicable')
                for backend in args.backends]
    for n, t, repeat in itertools.product(sizes, args.threads, range(args.repeats)):
        arms = list(variants)
        if repeat % 2:
            arms.reverse()
        for backend, mode in arms:
            prefix = 'hash1024' if workload == 'rcuht' else f'c{n:02d}'
            suffix = f'-{mode}' if backend == 'kdlock' else ''
            result.append(dict(name=f'{prefix}-t{t:02d}-r{repeat:02d}-direct-{backend}{suffix}',
                cachelines=n, threads=t, repeat=repeat, arm=backend, caller_abi='clobber' if backend == 'kdlock' else 'c',
                api_mode='direct', workload=workload, hotlock_mode=mode,
                caller_shell='cold_clobber' if backend == 'kdlock' else 'c',
                cookie_storage='percpu_rate_hot' if backend == 'kdlock' else 'not_applicable',
                cpu_heat_policy='mcs_entry_ratio512_simple' if backend == 'kdlock' else 'not_applicable',
                spin_contention_pct=contention_pct if backend == 'kdlock' else None,
                pmu=getattr(args, 'pmu', False),
                scenario=getattr(args, 'scenario', 'plain'),
                spin_delegate=getattr(args, 'spin_delegate', 'on'),
                warmup_policy='all_workers', warmup_iterations_per_worker=48000,
                warmup_pause_seconds=0,
                measurement_mode='timed_peak' if timing['duration_ms'] else 'fixed_iterations',
                **timing,
                iterations=args.iterations, cpus=list(range(t))))
    return result


def report(out):
    plan = json.loads((out/'plan.json').read_text())
    if plan and plan[0].get('functional'):
        # Functional acceptance retains raw evidence but publishes no timing
        # or cross-backend score. It uses the same body/context/drain oracle.
        rows = []
        for spec in plan:
            path = out/spec['name']/'session.json'
            row = json.loads(path.read_text()) if path.exists() else {}
            rows.append(dict(name=spec['name'], scenario=spec['scenario'],
                hotlock_mode=spec.get('hotlock_mode', 'unrecorded'),
                cpu_heat_policy=spec.get('cpu_heat_policy', 'unrecorded'),
                spin_contention_pct=spec.get('spin_contention_pct', 'unrecorded'),
                caller_shell=spec.get('caller_shell', 'unrecorded'),
                cookie_storage=spec.get('cookie_storage', 'unrecorded'),
                status=row.get('execution_status', 'NOT_RUN'),
                drained=row.get('drained', False),
                completed=row.get('measurement', {}).get('completed', 0),
                jit_bodies=row.get('jit_bodies', 0),
                jit_acceptance=row.get('jit_acceptance', 'NOT_RUN')))
        write_json(out/'functional.json', rows)
        return

    records, groups = [], {}
    for spec in json.loads((out/'plan.json').read_text()):
        p = out/spec['name']/'session.json'
        r = json.loads(p.read_text()) if p.exists() else dict(spec, execution_status='NOT_RUN', drained=False)
        m = r.get('measurement', {})
        good = valid(r)
        timed = bool(r.get('duration_ms', 0))
        r['whole_throughput_ops_s'] = m['completed']*1e9/m['wall_ns'] if good else None
        r['whole_amortized_ns_op'] = m['wall_ns']/m['completed'] if good else None
        peak = m.get('peak', {})
        # A timed score requires a validated full-cohort window. The full run
        # remains visible; neither its JIT share nor its mean describes peak.
        require(not good or not timed or peak.get('throughput_ops_s', 0) > 0,
                'valid timed session has no peak window')
        r['throughput_ops_s'] = (peak['throughput_ops_s'] if timed else
                                 r['whole_throughput_ops_s']) if good else None
        r['amortized_ns_op'] = (peak['amortized_ns_op'] if timed else
                                r['whole_amortized_ns_op']) if good else None
        records.append(r)
        # Mode and contention threshold are frozen policy inputs, including
        # threshold zero's diagnostic bypass. Never pool tuning candidates.
        mode = r.get('hotlock_mode', 'unrecorded')
        groups.setdefault((r['cachelines'], r['threads'], r['arm'], mode,
                           r.get('caller_shell', 'unrecorded'),
                           r.get('cookie_storage', 'unrecorded'),
                           r.get('cpu_heat_policy', 'unrecorded'),
                           r.get('spin_contention_pct', 'unrecorded'),
                           tuple(r.get(key) for key in TIMING_FIELDS),
                           r.get('spin_delegate', 'on')), []).append(r)
    write_json(out/'records.json', records)
    summary = []
    for (n, t, arm, mode, shell, cookie, heat_policy, contention_pct, timing, delegate), rows in groups.items():
        good = [r for r in rows if valid(r)]
        row = dict(cachelines=n, threads=t, api_mode='direct', arm=arm,
                   workload=rows[0].get('workload', 'cacheline'),
                   sessions=len(rows), valid=len(good),
                   hotlock_mode=mode, caller_shell=shell,
                   cookie_storage=cookie,
                   cpu_heat_policy=heat_policy,
                   spin_contention_pct=contention_pct,
                   spin_delegate=delegate,
                   **dict(zip(TIMING_FIELDS, timing)),
                   actual_jit_sessions=sum(r.get('jit_bodies', 0) > 0 for r in good))
        # Select one valid session per backend. Keep its matching ns/op and
        # identity so the maximum throughput is auditable in records.json.
        best = max(good, key=lambda r: r['throughput_ops_s']) if good else None
        row['comparison_policy'] = ('best_valid_warmed_peak' if rows[0].get('duration_ms', 0)
                                    else 'best_valid_throughput')
        row['best_session'] = best['name'] if best else None
        for metric in ('throughput_ops_s', 'amortized_ns_op',
                       'whole_throughput_ops_s', 'whole_amortized_ns_op'):
            row['best_'+metric] = best[metric] if best else None
        row['best_peak'] = best.get('measurement', {}).get('peak') if best else None
        # Keep variation visible without mixing the winning throughput and
        # latency pair. Failed or undrained sessions never enter the range.
        rates = [r['throughput_ops_s'] for r in good]
        row['min_throughput_ops_s'] = min(rates) if rates else None
        row['median_throughput_ops_s'] = statistics.median(rates) if rates else None
        row['max_throughput_ops_s'] = max(rates) if rates else None
        row['throughput_spread_pct'] = (
            100 * (max(rates) - min(rates)) / row['median_throughput_ops_s']
            if len(rates) > 1 else None)
        summary.append(row)
    natives = {(r['cachelines'], r['threads'], tuple(r[k] for k in TIMING_FIELDS)):
               r['best_throughput_ops_s']
               for r in summary if r['arm'] == 'native'}
    for row in summary:
        native = natives.get((row['cachelines'], row['threads'],
                              tuple(row[k] for k in TIMING_FIELDS)))
        row['throughput_over_linux'] = row['best_throughput_ops_s']/native if native and row['valid'] else None
    write_json(out/'summary.json', summary)
    if summary:
        csv_file(out/'summary.csv', list(summary[0]), summary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workload', choices=('cacheline', 'rcuht'), default='cacheline')
    p.add_argument('--cachelines', type=int, nargs='+', choices=(1,16))
    p.add_argument('--threads', type=int, nargs='+', choices=(1,2,3,4,5,6,7,8,16,20), default=[1,4,8,16,20])
    p.add_argument('--repeats', type=int, default=3,
                   help='measurement rounds per configuration (default: 3; functional mode requires 1)')
    p.add_argument('--iterations', type=int, default=100000)
    p.add_argument('--duration-ms', type=int, default=0,
                   help='continuous measured duration; 0 keeps fixed iterations')
    p.add_argument('--peak-window-ms', type=int, default=300)
    p.add_argument('--peak-settle-ms', type=int, default=300,
                   help='exclude initial measured settling from peak selection')
    p.add_argument('--sample-ms', type=int, default=10)
    p.add_argument('--collector-cpu', type=int, default=30,
                   help='dedicated progress collector CPU, outside the worker set')
    p.add_argument('--backends', nargs='+', choices=('native','tclock','kdlock'), default=['native','tclock','kdlock'])
    p.add_argument('--pmu', action='store_true',
                   help='separate long-batch diagnostic: perf stat around measured client only')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--functional', action='store_true',
                   help='KD functional acceptance only; requires --backends kdlock --repeats 1; no throughput report')
    kernel_identity.arguments(p)
    p.add_argument("--scenario", choices=("plain", "nested", "early"), default="plain")
    p.add_argument("--spin-delegate", choices=("on", "off"), default="on",
                   help="off: explicit KD self-execution control, no JIT acceptance")
    p.add_argument('--spin-contention-pct', type=int, choices=range(101),
                   metavar='0..100', default=DEFAULT_SPIN_CONTENTION_PCT,
                   help='adaptive minimum MCS/entry percentage over 512 MCS publications '
                        f'(default: {DEFAULT_SPIN_CONTENTION_PCT}; 0 bypasses only ratio)')
    args = p.parse_args()
    require(args.scenario == "plain" or (args.backends == ["kdlock"] and args.workload == "cacheline"),
            "nested protocol regression requires KD cacheline workload")
    require(args.workload != 'rcuht' or args.cachelines is None,
            'RCUHT uses a fixed hash table, not --cachelines')
    if args.functional:
        require(args.backends == ['kdlock'] and args.repeats == 1,
                'functional mode requires --backends kdlock --repeats 1')
    plan = make_plan(args)
    if args.functional:
        for spec in plan:
            spec['functional'] = True
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
        collector = (collector_topology(args.collector_cpu)
                     if args.duration_ms else None)
        for spec in plan:
            spec['cpu_nodes'] = topology['role_nodes'][:spec['threads']]
        write_json(out/'plan.json', plan)
        write_json(out/'environment.json', dict(kernel_identity=identity,topology=topology,
            collector_topology=collector,packages=packages,
            argv=sys.argv,python=sys.executable,snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            runner_affinity=sorted(os.sched_getaffinity(0)),
            cmdline=Path('/proc/cmdline').read_text(),preemption=Path('/sys/kernel/debug/sched/preempt').read_text(),
            watchdog=Path('/proc/sys/kernel/watchdog').read_text(),uname=list(os.uname())))
        builds = [('client',['make','-C',HERE,'client']),
                  ('allocator-guard',['make','-C',GUARD_MODULE.parent])]
        binaries = [HERE/'client', GUARD_MODULE]
        if args.pmu:
            perf = shutil.which('perf')
            require(perf is not None, 'PMU diagnostic requires perf in PATH')
            perf = Path(perf).resolve()
            write_json(out/'pmu-tool.json', dict(path=str(perf), sha256=digest(perf),
                version=command([perf, 'version'], out/'perf-version.txt').strip(),
                scope='measure client and inherited workers; setup/warmup excluded'))
            binaries.append(perf)
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
        # Observe/adaptive share the same heat-routed caller, built once.
        for backend in dict.fromkeys(s['arm'] for s in plan):
            build_name = backend
            folder = out/'variants'/build_name; folder.mkdir(parents=True)
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
                    out/f'build-{build_name}.log',timeout=120)
            variants[backend] = binary = folder/'spin_cacheline.ko'
            command(['objdump','-dr',binary],out/f'caller-{build_name}.txt')
            imported = command(['nm', '-u', binary], out/f'imports-{build_name}.txt')
            require('__ubsan_' not in imported, 'direct workload still imports UBSAN handlers')
            require('kd_raw_spin_' not in imported and 'kd_spin_dispatch_' not in imported,
                    'workload still imports a unified spin hook')
            expected = {'kdlock': ('kd_spin_direct_native_contended', 'kd_spin_fast_cpu',
                                   'kd_hotlock_spin_entries', 'kd_spin_lock_pinned_clobber_v1',
                                   'kd_spin_unlock_clobber_v1', 'kd_spin_prepare'),
                        'tclock': ('komb_spin_lock', 'komb_spin_unlock'), 'native': ()}[backend]
            if backend == 'kdlock':
                require('kd_spin_direct_native_lock' not in imported.split(),
                        'cold caller still imports the out-of-line CAS entry')
                require('kd_spin_direct_native_unlock' not in imported.split(),
                        'paired caller still bypasses the generic clobber unlock')
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
            if args.functional:
                print(f'  completed={m["completed"]}; '
                      f'jit_bodies={session.record.get("jit_bodies", 0)}; drained=True', flush=True)
            else:
                peak = m.get('peak')
                prefix = (f'  peak {peak["throughput_ops_s"]/1e6:.3f} Mops/s; whole '
                          if peak else '  ')
                print(f'{prefix}{m["completed"]*1e3/m["wall_ns"]:.3f} Mops/s; '
                      f'{m["wall_ns"]/m["completed"]:.2f} ns/op; drained=True',flush=True)
        idle(); report(out); return 0
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        report(out); print(f'STOP: {error}',file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
