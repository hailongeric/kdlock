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
import re
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
from session import BackendSession, TC_MODULE, TC_MUTEX_MODULE, GUARD_MODULE
from context_audit import audit as audit_context

DEFAULT_SPIN_ENTRY_RATIO_LIMIT = 2
DEFAULT_KD_PROVIDER_UBSAN = 'off'
SPIN_ENTRY_RATIO_LIMITS = (0, *(1 << shift for shift in range(1, 32)))
TIMING_FIELDS = ('duration_ms', 'peak_window_ms', 'peak_settle_ms',
                 'sample_ms', 'collector_cpu', 'collector_shared')


def worker_cpus(args):
    """Use an ordered, explicit CPU list; each cohort takes its prefix."""
    cpus = getattr(args, 'cpus', None)
    cpus = list(range(max(args.threads))) if cpus is None else cpus
    require(len(cpus) >= max(args.threads) and len(set(cpus)) == len(cpus)
            and all(type(cpu) is int and cpu >= 0 for cpu in cpus),
            'worker placement needs enough distinct nonnegative CPUs')
    return cpus[:max(args.threads)]


def timing_settings(args):
    settings = {name: getattr(args, name, default) for name, default in
                zip(TIMING_FIELDS[:-1], (0, 300, 300, 10, 63))}
    duration = settings['duration_ms']
    shared = getattr(args, 'share_collector', False)
    require(type(shared) is bool, 'collector sharing must be explicitly boolean')
    require(not shared or (duration and max(args.threads) == 64 and
                           worker_cpus(args) == list(range(64)) and
                           settings['collector_cpu'] == 63),
            'shared collector requires timed workers 0-63 and collector 63')
    require(0 <= duration <= 10000, 'duration must be 0..10000 ms')
    if duration:
        require(0 < settings['sample_ms'] <= settings['peak_window_ms'] and
                settings['peak_settle_ms'] >= 0 and
                settings['peak_settle_ms'] + settings['peak_window_ms'] < duration,
                'invalid peak timing intervals')
        require(settings['collector_cpu'] >= 0 and (shared or
                settings['collector_cpu'] not in worker_cpus(args)),
                'collector CPU must be outside every worker cohort')
        require(getattr(args, 'scenario', 'plain') == 'plain' and
                getattr(args, 'workload', 'cacheline') in ('cacheline', 'rcuht') and
                not getattr(args, 'functional', False),
                'timed peaks require a plain performance workload')
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


def provider_build(args):
    # This target recreates the benchmark's private provider copy. Command-line
    # Kbuild variables propagate through recursive make; ordinary builds keep
    # the kernel's sanitizer policy and all explicit protocol checks.
    build = ['make', '-C', HERE, 'provider',
             f'KDLOCK_NUMA={int(args.numa == "on")}',
             f'KDLOCK_SPIN_BATCH={args.kd_batch_size}']
    if getattr(args, 'kd_provider_ubsan', DEFAULT_KD_PROVIDER_UBSAN) == 'off':
        build.append('UBSAN_SANITIZE=n')
    return build


def audit_provider_ubsan(out, policy):
    imported = command(['nm', '-u', PROVIDER], out/'imports-kdlock-provider.txt')
    handlers = sorted(symbol for symbol in imported.split() if symbol.startswith('__ubsan_'))
    write_json(out/'kdlock-provider-ubsan.json', dict(policy=policy, imports=handlers))
    require(policy != 'off' or not handlers,
            'KD provider still imports UBSAN handlers with --kd-provider-ubsan off')


def idle():
    runtime.idle()
    require(not Path('/sys/module/tclock_backend_km').exists(), 'existing TCLock module')
    require(not Path('/sys/module/tclock_mutex_backend_km').exists(), 'existing TCLock mutex module')
    require(not Path('/sys/module/tc_allocator_guard').exists(), 'existing allocator guard')


def source_state():
    result = runtime.source_state()
    for folder in ('tclock_backend', 'bench/tclock_compare'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and not any(x.startswith('.') or x == '__pycache__'
                                      for x in p.relative_to(ROOT).parts) and (
                    p.suffix in ('.c', '.h', '.inc', '.S', '.py', '.patch', '.json', '.md') or
                    p.name == 'Makefile') and not p.name.endswith('.mod.c'):
                result[str(p.relative_to(ROOT))] = digest(p)
    for unit in ('tests/unit/spin/test_tclock_context.py',
                 'tests/unit/mutex/test_tclock_mutex_context.py',
                 'tests/unit/infrastructure/source_text.py'):
        result[unit] = digest(ROOT/unit)
    return result


def make_plan(args):
    require(args.repeats > 0 and 0 < args.iterations <= 100000000,
            'invalid repeats/iterations')
    require(not (getattr(args, 'pmu', False) and getattr(args, 'perf_record', False)),
            'PMU counters and CPU sampling require separate diagnostic runs')
    ratio_limit = getattr(args, 'spin_entry_ratio_limit', DEFAULT_SPIN_ENTRY_RATIO_LIMIT)
    require(ratio_limit in SPIN_ENTRY_RATIO_LIMITS, 'invalid spin entry ratio limit')
    batch = getattr(args, 'kd_batch_size', 1024)
    require(1 <= batch <= 1024, 'KD batch must be 1..1024')
    numa = getattr(args, 'numa', 'on')
    require(numa in ('on', 'off'), 'invalid NUMA policy')
    prefetch = getattr(args, 'spin_prefetch', 2)
    require(prefetch in (0, 1, 2), 'invalid spin prefetch mode')
    provider_ubsan = getattr(args, 'kd_provider_ubsan', DEFAULT_KD_PROVIDER_UBSAN)
    require(provider_ubsan in ('kernel', 'off'), 'invalid KD provider UBSAN policy')
    result = []
    cpus = worker_cpus(args)
    timing = timing_settings(args)
    workload = getattr(args, 'workload', 'cacheline')
    lock_kind = getattr(args, 'lock_kind', 'spin')
    require(lock_kind != 'mutex' or getattr(args, 'spin_delegate', 'on') == 'on',
            '--spin-delegate off is a spin-only control; mutex JIT is required')
    sizes = [0] if workload == 'rcuht' else (args.cachelines or [1])
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
                api_mode='direct', workload=workload, lock_kind=lock_kind, hotlock_mode=mode,
                caller_shell=('mutex_outer_cookie' if lock_kind == 'mutex' else 'cold_clobber') if backend == 'kdlock' else 'c',
                cookie_storage=('outer_acquisition_local' if lock_kind == 'mutex' else 'percpu_direct_gate') if backend == 'kdlock' else 'not_applicable',
                cpu_heat_policy=('mutex_contention1024_ratio256' if lock_kind == 'mutex' else 'mcs_reset1024_shift10_lock512_head6') if backend == 'kdlock' else 'not_applicable',
                spin_entry_ratio_limit=ratio_limit if backend == 'kdlock' else None,
                spin_prefetch=prefetch if backend == 'kdlock' else None,
                kd_provider_ubsan=provider_ubsan if backend == 'kdlock' else 'not_applicable',
                numa_policy=numa if backend != 'native' else 'not_applicable',
                delegation_batch_limit=batch if backend == 'kdlock' else (1024 if backend == 'tclock' else None),
                pmu=getattr(args, 'pmu', False),
                perf_record=getattr(args, 'perf_record', False),
                diagnostic=bool(getattr(args, 'pmu', False) or getattr(args, 'perf_record', False)),
                scenario=getattr(args, 'scenario', 'plain'),
                spin_delegate=getattr(args, 'spin_delegate', 'on'),
                warmup_policy='all_workers', warmup_iterations_per_worker=48000,
                warmup_pause_seconds=0,
                measurement_mode='timed_peak' if timing['duration_ms'] else 'fixed_iterations',
                **timing,
                collector_shared=bool(getattr(args, 'share_collector', False) and t == 64),
                iterations=args.iterations, cpus=cpus[:t]))
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
                spin_entry_ratio_limit=spec.get('spin_entry_ratio_limit', 'unrecorded'),
                caller_shell=spec.get('caller_shell', 'unrecorded'),
                cookie_storage=spec.get('cookie_storage', 'unrecorded'),
                kd_provider_ubsan=spec.get('kd_provider_ubsan', 'unrecorded'),
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
        r['score_eligible'] = good and not any(r.get(k, False) for k in
                                              ('diagnostic', 'pmu', 'perf_record'))
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
        # Keep old percentage and current shifted-entry limits as separate
        # identities, including zero's bypass. Never pool tuning candidates.
        mode = r.get('hotlock_mode', 'unrecorded')
        groups.setdefault((r.get('lock_kind', 'spin'), r['cachelines'], r['threads'], r['arm'], mode,
                           r.get('caller_shell', 'unrecorded'),
                           r.get('cookie_storage', 'unrecorded'),
                           r.get('cpu_heat_policy', 'unrecorded'),
                           r.get('spin_contention_pct', 'unrecorded'),
                           r.get('spin_entry_ratio_limit', 'unrecorded'),
                           tuple(r.get(key) for key in TIMING_FIELDS),
                           r.get('spin_delegate', 'on'),
                           r.get('numa_policy', 'unrecorded'),
                           r.get('delegation_batch_limit', 'unrecorded'),
                           r.get('spin_prefetch', 'unrecorded'),
                           r.get('kd_provider_ubsan', 'unrecorded'),
                           tuple(r.get('cpus', range(r['threads'])))), []).append(r)
    write_json(out/'records.json', records)
    summary = []
    for (lock_kind, n, t, arm, mode, shell, cookie, heat_policy, contention_pct, ratio_limit, timing, delegate, numa, batch, prefetch, provider_ubsan, cpus), rows in groups.items():
        good = [r for r in rows if r['score_eligible']]
        row = dict(cachelines=n, threads=t, api_mode='direct', arm=arm, lock_kind=lock_kind,
                   workload=rows[0].get('workload', 'cacheline'),
                   sessions=len(rows), valid=len(good),
                   hotlock_mode=mode, caller_shell=shell,
                   cookie_storage=cookie,
                   cpu_heat_policy=heat_policy,
                   spin_contention_pct=contention_pct,
                   spin_entry_ratio_limit=ratio_limit,
                   spin_delegate=delegate,
                   numa_policy=numa, delegation_batch_limit=batch, spin_prefetch=prefetch,
                   kd_provider_ubsan=provider_ubsan,
                   cpus=list(cpus), cpu_nodes=rows[0].get('cpu_nodes'),
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
    natives = {(r['lock_kind'], r['cachelines'], r['threads'], tuple(r[k] for k in TIMING_FIELDS), tuple(r['cpus'])):
               r['best_throughput_ops_s']
               for r in summary if r['arm'] == 'native'}
    for row in summary:
        native = natives.get((row['lock_kind'], row['cachelines'], row['threads'],
                              tuple(row[k] for k in TIMING_FIELDS), tuple(row['cpus'])))
        row['throughput_over_linux'] = row['best_throughput_ops_s']/native if native and row['valid'] else None
    write_json(out/'summary.json', summary)
    if summary:
        csv_file(out/'summary.csv', list(summary[0]), summary)


def execute_session(session, keep_going_no_jit=False):
    """Collect a drained missing-body failure without changing its verdict.

    A native-only adaptive sample can be useful diagnostic evidence, but it
    must never become a contended JIT positive or an accepted timing score.
    All other failures and any uncertain cleanup still stop the matrix.
    """
    try:
        session.execute()
    except Failure as error:
        record = session.record
        measurement = record.get('measurement', {})
        if (keep_going_no_jit and error.status == 'NO_JIT' and not error.unsafe
                and record.get('execution_status') == 'NO_JIT'
                and record.get('jit_acceptance') == 'NO_JIT'
                and record.get('jit_bodies') == 0 and record.get('drained')
                and not record.get('cleanup_error')
                and measurement.get('complete') and measurement.get('data_ok')):
            return False
        raise
    return True


def main(lock_kind='spin'):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--workload', choices=('cacheline', 'rcuht'), default='cacheline')
    p.add_argument('--cachelines', type=int, nargs='+', choices=(1,2,4,8,16))
    p.add_argument('--threads', type=int, nargs='+', choices=range(1, 65), default=[1,4,8,16,20])
    p.add_argument('--cpus', type=runtime.cpu_list,
                   help='ordered worker CPUs, e.g. 0-7,20-27; each cohort uses its prefix')
    p.add_argument('--spin-prefetch', type=int, choices=(0,1,2), default=2,
                   help='existing KD prefetch mode: off, consumer lookup, producer hints')
    p.add_argument('--numa', choices=('on', 'off'), default='on',
                   help='build NUMA queue selection for KD and TCLock')
    p.add_argument('--kd-batch-size', type=int, default=1024,
                   help='maximum KD delegated bodies and NUMA scan budget per batch (1..1024)')
    p.add_argument('--kd-provider-ubsan', choices=('kernel', 'off'),
                   default=DEFAULT_KD_PROVIDER_UBSAN,
                   help='private benchmark provider only: disable UBSAN instrumentation '
                        '(default: off), or use kernel to inherit the kernel policy')
    p.add_argument('--repeats', type=int, default=3,
                   help='measurement rounds per configuration (default: 3; functional mode requires 1)')
    p.add_argument('--keep-going-no-jit', action='store_true',
                   help='collect remaining performance samples after a drained NO_JIT; '
                        'failed samples remain excluded and the final exit stays nonzero')
    p.add_argument('--iterations', type=int, default=100000)
    p.add_argument('--duration-ms', type=int, default=0,
                   help='continuous measured duration; 0 keeps fixed iterations')
    p.add_argument('--peak-window-ms', type=int, default=300)
    p.add_argument('--peak-settle-ms', type=int, default=300,
                   help='exclude initial measured settling from peak selection')
    p.add_argument('--sample-ms', type=int, default=10)
    p.add_argument('--collector-cpu', type=int, default=63,
                   help='dedicated progress collector CPU, outside the worker set')
    p.add_argument('--share-collector', action='store_true',
                   help='explicitly share CPU 63 at the 64-worker point only; '
                        'requires timed workers 0-63 on the 64-vCPU VM')
    p.add_argument('--backends', nargs='+', choices=('native','tclock','kdlock'), default=['native','tclock','kdlock'])
    perf_mode = p.add_mutually_exclusive_group()
    perf_mode.add_argument('--pmu', action='store_true',
                   help='separate long-batch diagnostic: perf stat around measured client only')
    perf_mode.add_argument('--perf-record', action='store_true',
                   help='unscored 199 Hz kernel cycle samples around measured client and workers')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--functional', action='store_true',
                   help='KD functional acceptance only; requires --backends kdlock --repeats 1; no throughput report')
    kernel_identity.arguments(p)
    p.add_argument("--scenario", choices=("plain", "nested", "early"), default="plain")
    p.add_argument("--spin-delegate", choices=("on", "off"), default="on",
                   help="off: spin-only KD self-execution control, no JIT acceptance")
    p.add_argument('--spin-entry-ratio-limit', type=int, choices=SPIN_ENTRY_RATIO_LIMITS,
                   metavar='0|2|4|...|2147483648', default=DEFAULT_SPIN_ENTRY_RATIO_LIMIT,
                   help='adaptive (entries >> 10) upper bound per resettable 1024-MCS window; '
                        f'unsigned power of two >=2 (default: {DEFAULT_SPIN_ENTRY_RATIO_LIMIT}; '
                        '0 bypasses only ratio)')
    args = p.parse_args()
    args.lock_kind = lock_kind
    require(lock_kind in ('spin', 'mutex'), 'unknown lock kind')
    require(lock_kind != 'mutex' or args.scenario == 'plain',
            'mutex benchmark supports ordinary operations only')
    workload_dir = ROOT/'workload_modules/mutex_cacheline' if lock_kind == 'mutex' else WORKLOAD
    tc_module = TC_MUTEX_MODULE if lock_kind == 'mutex' else TC_MODULE
    require(args.scenario == "plain" or (args.backends == ["kdlock"] and args.workload == "cacheline"),
            "nested protocol regression requires KD cacheline workload")
    require(args.workload != 'rcuht' or args.cachelines is None,
            'RCUHT uses a fixed hash table, not --cachelines')
    if args.functional:
        require(args.backends == ['kdlock'] and args.repeats == 1,
                'functional mode requires --backends kdlock --repeats 1')
        require(not args.keep_going_no_jit,
                'keep-going-no-jit is for performance evidence collection only')
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
        topology = runtime.capture_topology(worker_cpus(args))
        collector = (collector_topology(args.collector_cpu)
                     if args.duration_ms else None)
        runtime.annotate_topology(plan, topology)
        write_json(out/'plan.json', plan)
        write_json(out/'environment.json', dict(kernel_identity=identity,topology=topology,
            collector_topology=collector,packages=packages,
            argv=sys.argv,python=sys.executable,snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            kd_provider_ubsan=args.kd_provider_ubsan if 'kdlock' in args.backends else 'not_applicable',
            runner_affinity=sorted(os.sched_getaffinity(0)),
            cmdline=Path('/proc/cmdline').read_text(),preemption=Path('/sys/kernel/debug/sched/preempt').read_text(),
            watchdog=Path('/proc/sys/kernel/watchdog').read_text(),uname=list(os.uname())))
        builds = [('client',['make','-C',HERE,'client']),
                  ('allocator-guard',['make','-C',GUARD_MODULE.parent])]
        binaries = [HERE/'client', GUARD_MODULE]
        if args.pmu or args.perf_record:
            perf = shutil.which('perf')
            require(perf is not None, 'performance diagnostic requires perf in PATH')
            perf = Path(perf).resolve()
            write_json(out/'pmu-tool.json', dict(path=str(perf), sha256=digest(perf),
                version=command([perf, 'version'], out/'perf-version.txt').strip(),
                scope='measure client and inherited workers; setup/warmup excluded'))
            binaries.append(perf)
        if 'kdlock' in args.backends:
            builds += [('provider',provider_build(args)),
                       ('daemon',['make','-C',ROOT/'daemon','CFLAGS=-O2 -Wall -Wextra -Werror'])]
            binaries += [PROVIDER,ROOT/'daemon/daemon']
        if 'tclock' in args.backends:
            # Keep backend and workload build logs distinct: the latter uses
            # build-tclock.log below and must not overwrite backend evidence.
            builds += [('tclock-backend',['make','-C',ROOT/'tclock_backend',
                               f'TCLOCK_NUMA={int(args.numa == "on")}',
                               f'TCLOCK_MUTEX={int(lock_kind == "mutex")}'])]
            binaries += [tc_module]
        for name, build in builds:
            command([*build,f'KDIR={args.kernel_source}'],out/f'build-{name}.log',timeout=180)
        # Verify the compiled configuration, including rebuilds after a flag change.
        for backend, binary in (('kdlock', PROVIDER), ('tclock', tc_module)):
            if backend not in args.backends:
                continue
            numa_field = 'mutex_numa' if backend == 'tclock' and lock_kind == 'mutex' else 'spin_numa'
            numa_value = command(['modinfo', '-F', numa_field, binary],
                                 out/f'{backend}-numa.txt').strip()
            require(numa_value == str(int(args.numa == 'on')), 'NUMA build identity differs')
            if backend == 'kdlock':
                batch_value = command(['modinfo', '-F', 'spin_batch', binary],
                                      out/'kdlock-batch.txt').strip()
                require(batch_value == str(args.kd_batch_size), 'KD batch build identity differs')
                if lock_kind == 'mutex':
                    mutex_batch = command(['modinfo', '-F', 'mutex_batch', binary],
                                          out/'kdlock-mutex-batch.txt').strip()
                    require(mutex_batch == str(args.kd_batch_size),
                            'KD mutex batch build identity differs')
                audit_provider_ubsan(out, args.kd_provider_ubsan)
        if 'tclock' in args.backends:
            # Check the actual ELF: changing a Kbuild variable must not leave a
            # stale instrumented backend in a run labelled as unsanitized.
            imported = command(['nm', '-u', tc_module], out/'imports-tclock-backend.txt')
            require('__ubsan_' not in imported, 'TCLock backend still imports UBSAN handlers')
            symbols = command(['nm', '-a', tc_module], out/'symbols-tclock-backend.txt')
            require(not any(name in symbols for name in
                            ('tc_delegated', 'tc_completed', 'tc_batches')),
                    'TCLock still contains added execution counters')
            disassembly = command(['objdump', '-dr', '--no-show-raw-insn', tc_module],
                                  out/'tclock-backend.txt')
            write_json(out/'tclock-context-audit.json', audit_context(disassembly, lock_kind))
        variants = {}
        # Each backend has one caller variant per frozen build.
        for backend in dict.fromkeys(s['arm'] for s in plan):
            build_name = backend
            folder = out/'variants'/build_name; folder.mkdir(parents=True)
            for src in workload_dir.iterdir():
                if src.suffix in ('.c','.h','.inc') or src.name == 'Makefile':
                    shutil.copyfile(src, folder/src.name)
            extra = []
            if backend != 'native':
                module = PROVIDER if backend == 'kdlock' else tc_module
                extra = [f'KBUILD_EXTRA_SYMBOLS={module.parent / "Module.symvers"}']
            command(['make','-C',folder,f'KDIR={args.kernel_source}',
                     f'SC_BACKEND={backend}', f'SC_WORKLOAD={args.workload}',
                     f'SC_SCENARIO={dict(plain=0, nested=1, early=2)[args.scenario]}',
                     f'KDLOCK_INCLUDE={ROOT / "include"}',
                     f'SC_SHARED={WORKLOAD}',
                     f'TCLOCK_INCLUDE={ROOT / "tclock_backend/include"}', *extra],
                    out/f'build-{build_name}.log',timeout=120)
            variants[backend] = binary = folder/f'{lock_kind}_cacheline.ko'
            command(['objdump','-dr',binary],out/f'caller-{build_name}.txt')
            imported = command(['nm', '-u', binary], out/f'imports-{build_name}.txt')
            require('__ubsan_' not in imported, 'direct workload still imports UBSAN handlers')
            require('kd_raw_spin_' not in imported and 'kd_spin_dispatch_' not in imported,
                    'workload still imports a unified spin hook')
            expected = {'kdlock': ('kd_spin_direct_native_contended', 'kd_spin_fast_cpu',
                                   'kd_hotlock_spin_entries', 'kd_spin_lock_pinned_clobber_v1',
                                   'kd_spin_unlock_clobber_v1', 'kd_spin_prepare'),
                        'tclock': ('komb_spin_lock', 'komb_spin_unlock'), 'native': ()}[backend]
            if lock_kind == 'mutex':
                expected = {'kdlock': ('kd_mutex_outer_contended_clobber_v1',
                                       'kd_hotlock_mutex_entries', 'kd_mutex_local_unlock',
                                       'kd_mutex_direct_unlock_clobber_v1', 'kd_mutex_prepare'),
                            'tclock': ('komb_mutex_lock', 'komb_mutex_unlock',
                                       'tc_mutex_worker_register', 'tc_mutex_workers_drain'),
                            'native': ('mutex_lock', 'mutex_unlock')}[backend]
                if backend == 'kdlock':
                    require(not re.search(r'\bU (?:atomic_dec_and_mutex_lock|mutex\w*|__mutex\w*|kd_mutex_(?:lock|unlock)_clobber_v1|osq_lock|osq_unlock)\b', imported),
                            'KD-only caller imports a Linux mutex API')
                require('kd_mutex_lock_clobber_v1' not in imported.split() and
                        'kd_mutex_unlock_clobber_v1' not in imported.split(),
                        'workload still imports experimental kernel mutex bridge')
            if backend == 'kdlock' and lock_kind == 'spin':
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
        rejected_no_jit = []
        for index,spec in enumerate(plan):
            require(not (out/'STOP').exists(),'STOP requested at drained boundary','STOPPED')
            require(source_state()==frozen and all(digest(Path(p))==h for p,h in hashes.items()),'frozen inputs changed')
            idle(); print(f'[{index+1}/{len(plan)}] {spec["name"]}',flush=True)
            session = BackendSession(out,spec,workload_module=variants[spec['arm']])
            if not execute_session(session, args.keep_going_no_jit):
                rejected_no_jit.append(spec['name'])
                print('  REJECTED: no returned JIT body; drained=True; continuing', flush=True)
                continue
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
        idle(); report(out)
        if rejected_no_jit:
            write_json(out/'failure.json', dict(status='NO_JIT',
                error='drained samples lacked returned JIT bodies', sessions=rejected_no_jit))
            print(f'FAILED: {len(rejected_no_jit)} NO_JIT samples; full matrix retained',
                  file=sys.stderr)
            return 1
        return 0
    except (Failure,OSError,ValueError) as error:
        write_json(out/'failure.json',dict(error=str(error),status=getattr(error,'status','FAILED')))
        report(out); print(f'STOP: {error}',file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
