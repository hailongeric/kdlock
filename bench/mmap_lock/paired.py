#!/usr/bin/env python3
"""One prepared shared-mm case: admit, run, then qualify separately from drain.

No action boots a kernel. Host endpoint evidence is supplied by controller.py
immediately after run returns. Missing evidence cannot turn business success
into qualified timing, and does not itself prevent proven normal module drain.
"""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
import plain
import window
import eligibility
rt, common, writer, mapping = plain.rt, plain.common, plain.writer, plain.mapping
PROFILE = common.load(Path(__file__).with_name('kdmm31.json'))
SITES = ROOT / 'tests/kernel/mmap_lock/writer_sites_kdmm31.json'
MODULE = 'kd_mmap_writer_native'
LEGACY_PLAN = 'paired-v1'
THROUGHPUT_PLAN = 'plain-v1'
SCALING_PLAN = 'plain-scaling-v1'
SCALING_WORKERS = tuple(range(1, 9)) + tuple(range(12, 61, 4))
PLAIN_PLANS = (THROUGHPUT_PLAN, SCALING_PLAN)
CASES = [(n, observation) for n in (1, 16) for observation in ('plain', 'sampled')]
PLANS = {LEGACY_PLAN: CASES, THROUGHPUT_PLAN: [(1, 'plain'), (16, 'plain')],
         SCALING_PLAN: [(n, 'plain') for n in SCALING_WORKERS]}
FIXED_THREADS, FIXED_ITERATIONS = 16, 5000
PROOF_MUTATIONS = ['different_lock', 'wrong_caller_return', 'wrong_wait_return',
                   'wrong_adapter_return', 'running_task', 'other_wait_channel', 'rescheduled_task',
                   'missing_chain', 'missing_writer_proof']
# Planning assumptions, not measured costs, runtime limits or live permission.
# Storage budgets one retained campaign copy; copies/headroom are applied below.
# Payload/readiness budgets exclude the separately counted dmesg captures.
PLANNING_ASSUMPTIONS = dict(boot_ms=120000, boot_readiness_ms=10000,
    recovery_check_ms=10000, fixed_check_ms=30000, timed_case_overhead_ms=5000,
    host_capture_ms=2000, report_case_ms=1000, payload_cycle_bytes=2*1024**2,
    host_capture_bytes=1024**2, dmesg_dump_bytes=256*1024,
    boot_readiness_bytes=2*1024**2, recovery_bytes=2*1024**2, shared_bytes=16*1024**2,
    retained_copies=2, headroom_percent=25)
# Five candidate boots, plus the final recovery boot. Adjacent same-mode
# repetitions share a boot; the report must not call them independent boots.
BLOCKS = [('native', []), ('kd', [0]), ('native', [0, 1]), ('kd', [1, 2]), ('native', [2])]
ORDER = [(repeat, mode, case) for mode, repeats in BLOCKS
         for repeat in repeats for case in range(4)]
BIND_DIRS = ('bench/mmap_lock', 'bench/mmap_writer', 'bench/mmap_fault',
             'bench/spin_cacheline', 'tests/kernel/mmap_lock', 'tests/kernel/mmap_writer',
             'tests/kernel/mmap_fault', 'tests/protocols', 'disassem', 'kernel_baseline')


def cases_for(plan):
    rt.require(isinstance(plan, str) and plan in PLANS, 'unknown mmap campaign plan')
    return PLANS[plan]


def row_plan(row):
    # Missing always means the original 24-case schema, never an inferred grid.
    plan = row.get('plan', LEGACY_PLAN)
    cases_for(plan)
    return plan


def plan_fields(plan):
    cases_for(plan)
    return {} if plan == LEGACY_PLAN else dict(plan=plan)


def order_for(plan):
    return [(repeat, mode, case) for mode, repeats in BLOCKS
            for repeat in repeats for case in range(len(cases_for(plan)))]


def bounds(plan):
    measured = len(order_for(plan))
    validation = 2 * (1 + len(cases_for(plan)))
    return dict(measured_sessions=measured, unscored_checks=validation,
                payload_cycles=measured + validation, boots=len(BLOCKS) + 1,
                host_captures=1 + len(BLOCKS) + 2 * measured + 1)


def describe_plan(plan, assumptions=None):
    """Pure planning arithmetic; no guest check, capture, output file or workload.

    Each backend validates one fixed proof and every timed case before K0.
    There is no warmup loop. The timed client has a 100 ms scheduled start delay;
    its two-second target comes from the same specifications used by run().
    Neither the start delay nor the target bounds scheduling or drain time.
    """
    rt.require(plan in PLAIN_PLANS, 'estimates require an explicit plain plan')
    a = dict(PLANNING_ASSUMPTIONS if assumptions is None else assumptions)
    rt.require(set(a) == set(PLANNING_ASSUMPTIONS) and
               all(type(v) is int and v >= 0 for v in a.values()) and a['retained_copies'] > 0,
               'complete nonnegative integer planning assumptions required')
    cases, order, limits = cases_for(plan), order_for(plan), bounds(plan)
    fixed_checks = 2
    timed_controls = 2 * len(cases)
    timed_sessions = len(order) + timed_controls
    # ready: one; fixed: two; timed validation: three; measurement: four.
    dmesg_dumps = len(BLOCKS) + 2*fixed_checks + 3*timed_controls + 4*len(order)
    measured_ms = sum(specification(case, repeat, mode, plan)['duration_ms']
                      for repeat, mode, case in order)
    validation_ms = sum(specification(case, 0, mode, plan)['duration_ms']
                        for mode in ('native', 'kd') for case in range(len(cases)))
    time_parts = dict(measured_intervals_ms=measured_ms, validation_intervals_ms=validation_ms,
        client_start_delays_ms=100*timed_sessions, fixed_checks_ms=fixed_checks*a['fixed_check_ms'],
        timed_overhead_ms=timed_sessions*a['timed_case_overhead_ms'],
        host_captures_ms=limits['host_captures']*a['host_capture_ms'],
        boots_ms=limits['boots']*a['boot_ms'], readiness_ms=len(BLOCKS)*a['boot_readiness_ms'],
        recovery_check_ms=a['recovery_check_ms'], report_ms=len(order)*a['report_case_ms'])
    storage_parts = dict(payload_cycles=limits['payload_cycles']*a['payload_cycle_bytes'],
        host_captures=limits['host_captures']*a['host_capture_bytes'],
        boot_readiness=len(BLOCKS)*a['boot_readiness_bytes'], recovery=a['recovery_bytes'],
        dmesg=dmesg_dumps*a['dmesg_dump_bytes'], shared=a['shared_bytes'])
    one_copy = sum(storage_parts.values())
    reserve = (one_copy*a['retained_copies']*(100+a['headroom_percent']) + 99)//100
    return dict(plan=plan, worker_counts=[n for n, _ in cases], observations=['plain'],
        order_fields=['repeat', 'mode', 'case'], order=order, limits=limits,
        checks=dict(fixed=fixed_checks, timed_validation=timed_controls, warmups=0,
                    fixed_worker_cycles=fixed_checks*FIXED_THREADS*FIXED_ITERATIONS,
                    negative_receipt_mutations=fixed_checks*len(PROOF_MUTATIONS),
                    dmesg_dumps=dmesg_dumps,
                    runtime_saved_timed_replays=len(order)*timed_controls,
                    runtime_saved_fixed_replays=len(order)*fixed_checks,
                    report_saved_timed_replays=len(order)*timed_controls,
                    report_saved_fixed_replays=len(order)*fixed_checks),
        placement=dict(worker_cpus='0..N-1', collector_cpu=63, collector_shared=False,
                       guest_node_cpus={'0': list(range(32)), '1': list(range(32, 64))}),
        assumptions=a, time=dict(components_ms=time_parts, estimated_ms=sum(time_parts.values())),
        storage=dict(components_bytes=storage_parts, one_copy_bytes=one_copy,
                     reserve_bytes=reserve, rounded_gib_bytes=((reserve+1024**3-1)//1024**3)*1024**3),
        limitations='Planning estimates, not measured duration, hard completion bounds or approval. '
                    'Storage copies mean raw plus archive on each retention filesystem; no compression credit. '
                    'Recheck actual space, logs and scope before execution. No build/install space included.')


def bind(path):
    return dict(path=str(path.resolve()), sha256=rt.digest(path))


def file_bound(row):
    path = Path(row['path'])
    rt.require(rt.digest(path) == row['sha256'], 'bound receipt changed: ' + str(path))
    return path


def load_bound(row):
    return common.load(file_bound(row))


def specification(case, repeat, mode, plan=LEGACY_PLAN):
    cases = cases_for(plan)
    rt.require(isinstance(case, int) and 0 <= case < len(cases), 'case outside campaign plan')
    n, observation = cases[case]
    value = writer.spec(n, observation, repeat)
    value['arm'] = mode
    return value


def expected_block(repeat, mode):
    return next(i for i, (arm, repeats) in enumerate(BLOCKS) if arm == mode and repeat in repeats)


def control_files():
    files = {}
    for name in BIND_DIRS:
        for path in (ROOT / name).rglob('*'):
            rel = path.relative_to(ROOT)
            if (path.is_file() and not any(p.startswith('.') or p == '__pycache__' for p in rel.parts)
                    and path.suffix in ('.py', '.json', '.inc', '.h', '.c')):
                files[str(path)] = rt.digest(path)
    for name in ('bench/archive_run.py', 'bench/mutex_api_compare/run.py',
                 'bench/mutex_api_compare/rcuht_boundary.py'):
        files[str(ROOT / name)] = rt.digest(ROOT / name)
    return files


def check_kernel(mode, boot, loaded=False):
    rt.require(os.geteuid() == 0 and str(ROOT) == '/root/host_fs/kdlock' and
               sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
               os.uname().release == PROFILE['release'], 'exact candidate VM and pinned Python required')
    rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot, 'boot changed')
    rt.require(Path('/proc/cmdline').read_text().split() ==
               PROFILE['cmdline_common'] + ['kd_mmap=' + PROFILE['modes'][mode]], 'boot policy differs')
    mods = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    rt.require(mods == sorted(PROFILE['modules'] + ([MODULE] if loaded else [])),
               'exact candidate module set differs')
    rt.require(int(Path('/proc/sys/kernel/tainted').read_text()) in (4096, 12288), 'unexpected taint')
    rt.require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG') == common.SNAPSHOT, 'confirmed recovery required')
    if not loaded:
        writer.check.idle(Path('/root'))


def projection(host):
    return sorted(({k: t[k] for k in ('tid', 'comm', 'affinity')}
                   for t in host['qemu'][0]['tasks']), key=lambda t: t['tid'])


def host_check(host, *, fresh, measurement_policy=window.LEGACY, role_manifest=None):
    expected = PROFILE['host']
    rt.require(host['passed'] and host['capture']['complete'] and host['pins_verified'] and
               host['snapshot_listed'] and host['recovery_snapshot'] == expected['snapshot'] and
               host['boot_id'] == expected['boot_id'] and len(host['qemu']) == 1 and
               host['final_identity'] == dict(pid=expected['pid'], start_ticks=expected['start_ticks'],
                   command_sha256=expected['command_sha256']), 'host identity/snapshot capture differs')
    if fresh:
        age = (datetime.datetime.now(datetime.timezone.utc) -
               datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
        rt.require(0 <= age <= 300, 'fresh host admission required')
    for name, h in common.scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        rt.require(rt.digest(common.ORIGINAL / name) == h, 'original environment changed')
    old = common.load(common.ORIGINAL / 'host-state.json')
    if measurement_policy == window.POLICY:
        core = window.core_inventory(old, host)
        if role_manifest is not None:
            admission = window.role_manifest(role_manifest)
            expected_identity = {k: expected[k] for k in ('pid', 'start_ticks', 'command_sha256')}
            if admission == window.WORKER_ADMISSION:
                rt.require(host['capture']['identity_before'] == host['capture']['identity_after'] ==
                           expected_identity, 'host capture membership identity differs')
            window.resolve_roles(host['qemu'][0]['tasks'], core, role_manifest['roles'],
                                 admission=admission, qemu_identity=expected_identity)
    else:
        rt.require(measurement_policy == window.LEGACY and
                   len(projection(host)) == expected['task_count'] == 67 and
                   projection(host) == projection(old), 'strict original QEMU thread set differs')
    return old


def ready_roles(row):
    if window.admission_policy(row) == window.FIXED_ADMISSION:
        return None
    roles = load_bound(row['window_roles'])
    rt.require(window.role_manifest(roles) == window.admission_policy(row), 'bound admission policy differs')
    return roles


def environment():
    import importlib.metadata
    previous = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, {63})
        collector = rt.capture_topology([63])
    finally:
        os.sched_setaffinity(0, previous)
    env = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        cmdline=Path('/proc/cmdline').read_text().strip(), python=sys.executable,
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        packages={p: importlib.metadata.version(p) for p in ('miasm', 'future', 'pyparsing', 'pyelftools')},
        snapshot_tag=common.SNAPSHOT, collector_topology=collector)
    topo = rt.capture_topology(list(range(60)))
    rt.require(topo['online_cpus'] == list(range(64)) and topo['role_nodes'] == [0]*32 + [1]*28 and
               '(voluntary)' in env['preemption'], 'guest CPU/NUMA/preemption differs')
    return env, topo


def host_environment(host, env, topo, measurement_policy=window.LEGACY, role_manifest=None):
    old = host_check(host, fresh=False, measurement_policy=measurement_policy, role_manifest=role_manifest)
    original = common.load(common.ORIGINAL / 'environment.json')
    original.update(boot_id=env['boot_id'], cmdline=env['cmdline'])
    compare = window.same_environment if measurement_policy == window.POLICY else common.scheduler.same_environment
    return compare(old, host, original, env,
        common.load(common.ORIGINAL / 'topology.json'), topo)


def fault_check(out, label):
    messages = rt.command(['dmesg'], out / (label + '.log'))
    rt.require(not rt.FAULT.search(messages), 'kernel fault; retain payload')


def health(destroyed):
    value = Path('/sys/module', MODULE, 'parameters/health').read_text().strip()
    rt.require(value == f'files=0 mm_refs=0 destroyed={destroyed} release_errors=0',
               'exact file/mm/VMA lifetime did not drain')
    return value


def prepared(path):
    data = common.load(path)
    rt.require(data['passed'] and data['built_only'] and not data['modules_loaded'] and
               data['profile'] == PROFILE, 'matching build-only inputs required')
    common.verify_maps(data['files'])
    return data


def ready(a):
    plan = a.plan or LEGACY_PLAN
    cases_for(plan)
    check_kernel(a.mode, a.boot_id)
    out = a.output
    out.mkdir(parents=True)
    result = dict(passed=False, accepted=False, mode=a.mode, boot_id=a.boot_id, block=a.block,
                  **plan_fields(plan))
    policy = getattr(a, 'measurement_policy', None) or window.LEGACY
    eligible = getattr(a, 'eligibility_policy', None) or eligibility.STRICT
    result.update(eligibility.fields(eligible))
    if eligible == eligibility.FUNCTIONAL:
        rt.require(plan == SCALING_PLAN and policy == window.POLICY,
                   'functional eligibility requires explicit scaling/window policy')
    if policy == window.POLICY:
        rt.require(plan in PLAIN_PLANS, 'prepared window is plain only')
        result.update(window.binding())
    roles = None
    if getattr(a, 'window_roles', None) is not None:
        rt.require(policy == window.POLICY, 'role manifest requires prepared-window measurement')
        roles = common.load(a.window_roles)
        window.role_manifest(roles)
        result.update(window.admission_fields(roles), window_roles=bind(a.window_roles))
    try:
        rt.require(BLOCKS[a.block][0] == a.mode, 'ordered candidate boot mode differs')
        inputs = prepared(a.prepared)
        if eligible == eligibility.FUNCTIONAL:
            rt.require(inputs.get('fixed_eligibility_policy') == eligible,
                       'functional fixed-client build required')
        result['prior_api'] = []
        for mode, path in [('native', a.native_api), ('kd', a.kd_api)]:
            expected = PROFILE['prior_api'][mode]
            rt.require(rt.digest(path) == expected['sha256'], 'preserved actual mmap API receipt differs')
            api = common.load(path)
            rt.require(api['passed'] and api['drained'] and api['mode'] == mode and
                       api['probe']['checks'] == expected['checks'] and not api['probe']['errors'] and
                       api['probe']['use_kd'] == int(mode == 'kd') and
                       api['kernel_identity']['running_build_id'] == PROFILE['build_id'],
                       'corrected image API prerequisite differs')
            result['prior_api'].append(bind(path))
        rt.require(rt.digest(Path(PROFILE['bundle']) / 'manifest.json') ==
                   PROFILE['baseline_manifest_sha256'], 'captured kernel manifest differs')
        identity = common.kernel_identity.capture(argparse.Namespace(
            kernel_source=Path('/root/kdlock-kernel-work/mmap-irq-20261025/candidate-1/runtime-identity'),
            kernel_baseline=Path(PROFILE['bundle'])), out, rt.command)
        rt.require(identity['running_build_id'] == PROFILE['build_id'], 'live kernel Build ID differs')
        host = common.load(a.host_state)
        host_check(host, fresh=True, measurement_policy=policy, role_manifest=roles)
        env, topo = environment()
        comparison = host_environment(host, env, topo, policy, roles)
        fault_check(out, 'ready-dmesg')
        result.update(passed=True, prepared=bind(a.prepared), files=control_files(),
            environment=env, topology=topo, host_comparison=comparison, kernel_identity=identity)
    finally:
        rt.write_json(out / 'result.json', result)


def readiness(path):
    row = common.load(path)
    row_plan(row)
    policy = window.policy(row)
    eligibility.policy(row)
    ready_roles(row)
    if policy == window.POLICY:
        rt.require(all(row.get(k) == v for k, v in window.binding().items()), 'readiness control source differs')
    rt.require(row['passed'], 'same-boot readiness required')
    common.verify_maps(row['files'])
    check_kernel(row['mode'], row['boot_id'])
    inputs = prepared(Path(row['prepared']['path']))
    load_bound(row['prepared'])
    if eligibility.policy(row) == eligibility.FUNCTIONAL:
        rt.require(row_plan(row) == SCALING_PLAN and policy == window.POLICY and
                   inputs.get('fixed_eligibility_policy') == eligibility.FUNCTIONAL,
                   'functional readiness scope/build differs')
    for binding in row['prior_api']:
        load_bound(binding)
    return row, inputs


def measurement(rows, spec, mode, plan=LEGACY_PLAN):
    cases_for(plan)
    result = writer.validate(rows, spec)
    if plan in PLAIN_PLANS:
        rt.require(spec['observation'] == 'plain' and result['latency_samples'] == 0,
                   'plain campaign cannot include workload latency sampling')
        result.update(execution='KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK',
                      latency_percentiles_ns={}, latency_sample_policy='disabled')
        return result
    values = sorted(v for w in rows[1]['workers'] for v in w['latency_ns'])
    result.update(execution='KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK',
                  latency_percentiles_ns={str(p): values[math.ceil(p/100*len(values))-1]
                    for p in (50, 95, 99)} if values else {},
                  latency_sample_policy='every 64th whole mmap/munmap cycle; per-worker stagger')
    return result


def fixed(inputs, out, mode, eligibility_policy=eligibility.STRICT):
    mapping.SITES = common.load(SITES)
    sites = mapping.SITES
    chain = sites['chains'][mode]
    proof = [str(sites['sites'][name]['return_offset']) for name in ('vm_mmap_pgoff', '__vm_munmap')]
    proof += [chain['waiter'], *map(str, chain['wait_returns']), str(chain['adapter_return']), sites['adapter']]
    options = ['--eligibility-policy', eligibility_policy] if eligibility_policy == eligibility.FUNCTIONAL else []
    eligibility.fields(eligibility_policy)
    rt.command(['insmod', inputs['binaries']['payload'], 'observe=1'], out / 'load-fixed.log')
    fault_check(out, 'after-fixed-load-dmesg')
    health(0)
    data = rt.command([inputs['binaries']['fixed'], 'cycle', str(FIXED_THREADS), str(FIXED_ITERATIONS), *proof, *options],
                      out / 'fixed.jsonl', timeout=120)
    rows = [json.loads(line) for line in data.splitlines()]
    result = mapping.validate(rows, 'cycle', FIXED_THREADS, FIXED_ITERATIONS, mode, eligibility_policy)
    result['rejected_mutations'] = (mapping.reject_mutations(rows, mode, eligibility_policy)
        if eligibility.observation(result) == 'observed' else [])
    result['health'] = health(1)
    fault_check(out, 'fixed-dmesg')
    rt.command(['rmmod', MODULE], out / 'unload-fixed.log')
    return result


def timed(inputs, out, spec, nonce=None, admission=window.FIXED_ADMISSION):
    rt.command(['insmod', inputs['binaries']['payload'], 'observe=0'], out / 'load.log')
    fault_check(out, 'after-load-dmesg')
    health(0)
    argv = [inputs['binaries']['timed'], str(spec['threads']), spec['observation']]
    settling = window.post_setup_wait() if admission == window.WORKER_ADMISSION else None
    if nonce is None:
        rt.command(argv, out / 'client.jsonl', timeout=120)
    else:
        record, stdout, stderr = window.bridge(argv, nonce, sys.stdin.buffer, sys.stdout.buffer)
        if settling is not None:
            record.update(admission_policy=admission, post_setup_settling=settling)
        # A failed exchange is preserved as failed evidence. It does not make an
        # early publication, uncertain client exit or module teardown acceptable.
        (out / 'client.jsonl').write_bytes(stdout)
        (out / 'client.stderr').write_bytes(stderr)
        record.update(stdout_sha256=rt.digest(out / 'client.jsonl'), stderr_sha256=rt.digest(out / 'client.stderr'))
        rt.write_json(out / 'window-control.json', record)
        window.control_replay(record)


def business_finish(out, spec, mode, plan=LEGACY_PLAN):
    # Evidence qualification is separate. Only normal client completion, exact
    # lifetime accounting and a fault-free guest authorize ordinary unload.
    fault_check(out, 'before-unload-dmesg')
    rows = [json.loads(line) for line in (out / 'client.jsonl').read_text().splitlines()]
    result = measurement(rows, spec, mode, plan)
    value = health(1)
    rt.command(['rmmod', MODULE], out / 'unload.log')
    fault_check(out, 'after-unload-dmesg')
    writer.check.idle(Path('/root'))
    return result, value


def validate(a):
    ready, inputs = readiness(a.ready)
    plan = row_plan(ready)
    out = a.output
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, accepted=False, mode=ready['mode'],
                  prepared=ready['prepared'], ready=bind(a.ready), cases=[], **plan_fields(plan))
    if window.policy(ready) == window.POLICY:
        result.update(window.binding())
    result.update(window.admission_fields(ready))
    result.update(eligibility.fields(eligibility.policy(ready)))
    try:
        options = [] if eligibility.policy(ready) == eligibility.STRICT else [eligibility.policy(ready)]
        result['fixed'] = fixed(inputs, out, ready['mode'], *options)
        if options:
            result['writer_observation'] = eligibility.observation(result['fixed'])
        result['fixed_raw'] = bind(out / 'fixed.jsonl')
        for index, (n, observation) in enumerate(cases_for(plan)):
            case = out / f'{n}-{observation}'
            case.mkdir()
            spec = specification(index, 0, ready['mode'], plan)
            timed(inputs, case, spec, admission=window.admission_policy(ready))
            row, value = business_finish(case, spec, ready['mode'], plan)
            result['cases'].append(dict(spec=spec, measurement=row, health=value,
                                       raw=bind(case / 'client.jsonl')))
        common.verify_maps(inputs['files'])
        writer.check.idle(Path('/root'))
        result.update(passed=True, drained=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'result.json', result)


def validation_shape(v, mode, prepared_ref, plan=LEGACY_PLAN):
    count = len(cases_for(plan))
    window.policy(v)
    rt.require(row_plan(v) == plan, 'validation campaign plan differs')
    rt.require(v['passed'] and v['drained'] and not v['accepted'] and v['mode'] == mode and
               v['prepared'] == prepared_ref and len(v['cases']) == count and
               [c['spec'] for c in v['cases']] == [specification(i, 0, mode, plan) for i in range(count)],
               'validation case set/specification differs')
    f = v['fixed']
    eligible = eligibility.policy(v)
    rt.require(eligibility.policy(f) == eligible, 'fixed/validation eligibility differs')
    observed = eligibility.observation(f)
    if eligible == eligibility.FUNCTIONAL:
        rt.require(eligibility.observation(v) == observed, 'validation observation differs')
    rt.require(f['passed'] and f['mode'] == 'cycle' and f['threads'] == FIXED_THREADS and f['iterations'] == FIXED_ITERATIONS and
               f['protocol'] == ('KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK') and
               f['health'] == 'files=0 mm_refs=0 destroyed=1 release_errors=0' and
               f['rejected_mutations'] == (PROOF_MUTATIONS if observed == 'observed' else []),
               'required fixed-work validation differs')


def validation_receipt(path, mode, prepared_ref, plan=LEGACY_PLAN):
    """Replay saved positive evidence without executing a workload or test."""
    v = common.load(path)
    if 'compatibility' in v:
        import reuse
        return reuse.replay(path, mode, prepared_ref, plan)
    validation_shape(v, mode, prepared_ref, plan)
    ready = load_bound(v['ready'])
    rt.require(eligibility.policy(v) == eligibility.policy(ready), 'validation/readiness eligibility differs')
    rt.require(window.admission_policy(v) == window.admission_policy(ready), 'validation admission policy differs')
    rt.require(ready['passed'] and ready['mode'] == mode and ready['prepared'] == prepared_ref and
               window.policy(ready) == window.policy(v) and
               ready['block'] == (0 if mode == 'native' else 1) and row_plan(ready) == plan,
               'validation readiness differs')
    mapping.SITES = common.load(SITES)
    raw = [json.loads(line) for line in file_bound(v['fixed_raw']).read_text().splitlines()]
    proof = mapping.validate(raw, 'cycle', FIXED_THREADS, FIXED_ITERATIONS, mode, eligibility.policy(v))
    rt.require(all(v['fixed'][key] == value for key, value in proof.items()), 'saved writer proof differs')
    for case in v['cases']:
        raw = [json.loads(line) for line in file_bound(case['raw']).read_text().splitlines()]
        rt.require(measurement(raw, case['spec'], mode, plan) == case['measurement'] and
                   case['health'] == 'files=0 mm_refs=0 destroyed=1 release_errors=0',
                   'saved timed-client validation differs')
    return v


def run(a):
    ready, inputs = readiness(a.ready)
    plan = row_plan(ready)
    order = order_for(plan)
    rt.require(a.repeat in BLOCKS[ready['block']][1] and 0 <= a.case < len(cases_for(plan)), 'case/block differs')
    out = a.output
    out.mkdir(parents=True)
    spec = specification(a.case, a.repeat, ready['mode'], plan)
    result = dict(passed=False, accepted=False, drained=False, client_exited=False,
        ready=bind(a.ready), mode=ready['mode'], boot_id=ready['boot_id'], spec=spec,
        repeat=a.repeat, case=a.case, block=ready['block'], prepared=ready['prepared'], **plan_fields(plan))
    policy = window.policy(ready)
    if policy == window.POLICY:
        result.update(window.binding())
    result.update(window.admission_fields(ready))
    eligible = eligibility.policy(ready)
    result.update(eligibility.fields(eligible))
    if eligible == eligibility.FUNCTIONAL:
        result['writer_observations'] = {}
    try:
        index = order.index((a.repeat, ready['mode'], a.case))
        rt.require((index == 0) == (a.previous is None), 'ordered predecessor required')
        if a.previous is not None:
            prior = common.load(a.previous)
            rt.require(prior['passed'] and prior['drained'] and prior['accepted'] and
                (prior['repeat'], prior['mode'], prior['case']) == order[index-1] and
                row_plan(prior) == plan and
                window.policy(prior) == policy and
                window.admission_policy(prior) == window.admission_policy(ready) and
                eligibility.policy(prior) == eligible and
                prior['prepared'] == ready['prepared'] and
                ((prior['block'] == ready['block']) == (prior['boot_id'] == ready['boot_id'])),
                'preceding qualified case or boot transition differs')
            result['previous'] = bind(a.previous)
        result['validated'] = []
        for mode, path in [('native', a.native_validation), ('kd', a.kd_validation)]:
            validation = validation_receipt(path, mode, ready['prepared'], plan)
            rt.require(eligibility.policy(validation) == eligible, 'validation eligibility differs')
            if eligible == eligibility.FUNCTIONAL:
                result['writer_observations'][mode] = eligibility.observation(validation)
                rt.require(window.admission_policy(validation) == window.admission_policy(ready),
                           'validation admission policy differs')
                import reuse
                reuse.match_ready(validation, ready)
            if policy == window.POLICY:
                rt.require(window.policy(validation) == policy, 'validation measurement policy differs')
            result['validated'].append(bind(path))
        host = common.load(a.host_state)
        host_check(host, fresh=True, **({'measurement_policy': policy, 'role_manifest': ready_roles(ready)} if policy == window.POLICY else {}))
        if a.previous is not None:
            rt.require(host['captured_utc'] > prior['endpoint_captured_utc'],
                       'fresh admission must follow the preceding endpoint')
        env, topo = environment()
        result['host_comparison'] = host_environment(host, env, topo, *([policy, ready_roles(ready)] if policy == window.POLICY else []))
        result['admission'] = bind(a.host_state)
        shutil.copyfile(a.host_state, out / 'host-before.json')
        fault_check(out, 'before-load-dmesg')
        timed(inputs, out, spec, *([os.environ['KDLOCK_WINDOW_NONCE']] if policy == window.POLICY else []),
              **({'admission': window.admission_policy(ready)} if window.admission_policy(ready) != window.FIXED_ADMISSION else {}))
        result['client_exited'] = True
        if policy == window.POLICY:
            result['window_control'] = bind(out / 'window-control.json')
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'client-result.json', result)


def screen(a):
    """One fixed proof and one controlled 16-worker case; never a grid receipt."""
    ready, inputs = readiness(a.ready)
    rt.require(eligibility.policy(ready) == eligibility.STRICT, 'screen retains strict writer proof')
    rt.require(window.policy(ready) == window.POLICY and row_plan(ready) == SCALING_PLAN,
               'screen needs explicit window/scaling readiness')
    out = a.output
    out.mkdir(parents=True)
    spec = specification(9, 0, ready['mode'], SCALING_PLAN)
    result = dict(**window.binding(), plan=SCALING_PLAN, screen=True,
        **window.admission_fields(ready),
        passed=False, accepted=False, drained=False, client_exited=False,
        ready=bind(a.ready), prepared=ready['prepared'], mode=ready['mode'], boot_id=ready['boot_id'],
        block=ready['block'], repeat=0, case=9, spec=spec)
    try:
        rt.require(ready['block'] == (0 if ready['mode'] == 'native' else 1), 'screen boot block differs')
        host = common.load(a.host_state)
        host_check(host, fresh=True, measurement_policy=window.POLICY, role_manifest=ready_roles(ready))
        env, topo = environment()
        result['host_comparison'] = host_environment(host, env, topo, window.POLICY, ready_roles(ready))
        result['admission'] = bind(a.host_state)
        result['fixed'] = fixed(inputs, out, ready['mode'])
        result['fixed_raw'] = bind(out / 'fixed.jsonl')
        timed(inputs, out, spec, os.environ['KDLOCK_WINDOW_NONCE'], admission=window.admission_policy(ready))
        result.update(client_exited=True, window_control=bind(out / 'window-control.json'))
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'client-result.json', result)


def qualify(out, client, directory):
    controller = common.load(directory / 'controller.json')
    policy = window.policy(client)
    rt.require(window.policy(controller) == policy, 'controller/client measurement policy differs')
    host_path = directory / 'host-endpoint.json'
    host = common.load(host_path)
    rt.require(controller['passed'] and controller['guest_returncode'] == controller['host_returncode'] ==
        controller['result_fetch_returncode'] == 0 and controller['guest_result_path'] == str(out / 'client-result.json') and
        controller['guest_result_sha256'] == rt.digest(out / 'client-result.json') and
        controller['host_sha256'] == rt.digest(host_path) and controller['admission_sha256'] == client['admission']['sha256'],
        'endpoint/controller/result/admission binding differs')
    rt.require(0 <= controller['host_capture_started_monotonic_ns'] - controller['guest_exit_observed_monotonic_ns'] < 1_000_000_000 and
               controller['host_capture_finished_monotonic_ns'] >= controller['host_capture_started_monotonic_ns'],
               'endpoint not requested immediately after guest SSH completion')
    rt.require(controller['driver_sha256'] == rt.digest(ROOT / 'bench/mmap_lock/controller.py') and
               controller['helper_sha256'] == rt.digest(ROOT / 'bench/mmap_lock/host_state.py') and
               controller['observer_sha256'] == rt.digest(ROOT / 'bench/mmap_lock/host_capture_control.py'),
               'reviewed endpoint tooling differs')
    before = load_bound(client['admission'])
    ready = load_bound(client['ready'])
    rt.require(eligibility.policy(client) == eligibility.policy(ready), 'client/readiness eligibility differs')
    eligibility.observations(client)
    roles = ready_roles(ready)
    rt.require(window.admission_policy(controller) == window.admission_policy(client) ==
               window.admission_policy(ready), 'mixed admission policies')
    host_check(host, fresh=False, measurement_policy=policy, role_manifest=roles)
    ids = lambda h: sorted((t['tid'], t['start_ticks']) for t in h['capture']['tasks'])
    if policy == window.LEGACY:
        rt.require(ids(before) == ids(host), 'QEMU task lifetime changed across measurement')
    rt.require(row_plan(client) == row_plan(ready) and window.policy(ready) == policy,
               'measurement/readiness campaign or policy differs')
    host_environment(host, ready['environment'], ready['topology'], policy, roles)
    result = dict(captured_utc=host['captured_utc'], controller=bind(directory / 'controller.json'),
                  endpoint=bind(host_path), admission=client['admission'])
    if policy == window.POLICY:
        from window_replay import qualify_window
        result['window'] = qualify_window(out, client, directory, before, host, ready)
    return result


def finish(a):
    out = a.output
    client = common.load(out / 'client-result.json')
    rt.require(client['client_exited'] and not (out / 'result.json').exists(), 'normal client completion and new finalization required')
    result = dict(client, passed=False, accepted=False, drained=False, endpoint_checked=False)
    try:
        check_kernel(client['mode'], client['boot_id'], loaded=True)
        ready = load_bound(client['ready'])
        common.verify_maps(ready['files'])
        prepared(Path(client['prepared']['path']))
        load_bound(client['prepared'])
        # A missing/malformed endpoint still permits these independent, exact
        # business/drain checks. No new workload starts during finalization.
        result['measurement'], result['health'] = business_finish(out, client['spec'], client['mode'], row_plan(ready))
        result.update(passed=True, drained=True)
        try:
            evidence = qualify(out, client, a.controller)
            result.update(endpoint_checked=True, accepted=True, qualification=evidence,
                          endpoint_captured_utc=evidence['captured_utc'])
        except (OSError, ValueError, KeyError, TypeError, rt.Failure) as error:
            result['qualification_error'] = repr(error)
    except BaseException as error:
        result.update(passed=False, accepted=False, error=repr(error))
        raise
    finally:
        rt.write_json(out / 'result.json', result)
    rt.require(result['accepted'], 'measurement rejected; normal cleanup completed; do not continue campaign')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('describe', 'ready', 'validate', 'run', 'screen', 'finish'))
    p.add_argument('--output', type=Path)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--native-api', type=Path)
    p.add_argument('--kd-api', type=Path)
    p.add_argument('--mode', choices=('native', 'kd'))
    p.add_argument('--block', type=int, choices=range(5))
    p.add_argument('--boot-id')
    p.add_argument('--ready', type=Path)
    p.add_argument('--host-state', type=Path)
    p.add_argument('--repeat', type=int, choices=range(3))
    p.add_argument('--case', type=int, choices=range(max(map(len, PLANS.values()))))
    p.add_argument('--native-validation', type=Path)
    p.add_argument('--kd-validation', type=Path)
    p.add_argument('--controller', type=Path)
    p.add_argument('--previous', type=Path)
    p.add_argument('--plan', choices=tuple(PLANS), help='select at describe/ready; later actions inherit bound readiness')
    p.add_argument('--measurement-policy', choices=(window.LEGACY, window.POLICY))
    p.add_argument('--window-roles', type=Path, help='versioned role manifest selected at ready')
    p.add_argument('--eligibility-policy', choices=(eligibility.STRICT, eligibility.FUNCTIONAL))
    a = p.parse_args()
    if a.action == 'describe':
        if a.plan not in PLAIN_PLANS or a.output is not None:
            p.error('describe requires an explicit plain --plan and writes only to stdout')
        print(json.dumps(describe_plan(a.plan), indent=2, sort_keys=True))
        return
    if a.plan is not None and a.action != 'ready':
        p.error('--plan is selected at ready and inherited by later actions')
    if a.measurement_policy is not None and a.action != 'ready':
        p.error('--measurement-policy is selected at ready and inherited')
    if a.window_roles is not None and a.action != 'ready':
        p.error('--window-roles is selected at ready and inherited')
    if a.eligibility_policy is not None and a.action != 'ready':
        p.error('--eligibility-policy is selected at ready and inherited')
    if a.output is None:
        p.error('--output is required for live actions')
    a.output = a.output.resolve()
    rt.require(not a.output.is_relative_to(ROOT) and (a.action == 'finish' or not a.output.exists()),
               'unique evidence directory outside source required')
    globals()[a.action](a)


if __name__ == '__main__':
    main()
