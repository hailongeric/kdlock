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
rt, common, writer, mapping = plain.rt, plain.common, plain.writer, plain.mapping
PROFILE = common.load(Path(__file__).with_name('kdmm31.json'))
SITES = ROOT / 'tests/kernel/mmap_lock/writer_sites_kdmm31.json'
MODULE = 'kd_mmap_writer_native'
CASES = [(n, observation) for n in (1, 16) for observation in ('plain', 'sampled')]
# Five candidate boots, plus the final recovery boot. Adjacent same-mode
# repetitions share a boot; the report must not call them independent boots.
BLOCKS = [('native', []), ('kd', [0]), ('native', [0, 1]), ('kd', [1, 2]), ('native', [2])]
ORDER = [(repeat, mode, case) for mode, repeats in BLOCKS
         for repeat in repeats for case in range(4)]
BIND_DIRS = ('bench/mmap_lock', 'bench/mmap_writer', 'bench/mmap_fault',
             'bench/spin_cacheline', 'tests/kernel/mmap_lock', 'tests/kernel/mmap_writer',
             'tests/kernel/mmap_fault', 'tests/protocols', 'disassem', 'kernel_baseline')


def bind(path):
    return dict(path=str(path.resolve()), sha256=rt.digest(path))


def file_bound(row):
    path = Path(row['path'])
    rt.require(rt.digest(path) == row['sha256'], 'bound receipt changed: ' + str(path))
    return path


def load_bound(row):
    return common.load(file_bound(row))


def specification(case, repeat, mode):
    n, observation = CASES[case]
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


def host_check(host, *, fresh):
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
    rt.require(len(projection(host)) == expected['task_count'] == 67 and
               projection(host) == projection(old), 'strict original QEMU thread set differs')
    return old


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


def host_environment(host, env, topo):
    old = host_check(host, fresh=False)
    original = common.load(common.ORIGINAL / 'environment.json')
    original.update(boot_id=env['boot_id'], cmdline=env['cmdline'])
    return common.scheduler.same_environment(old, host, original, env,
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
    check_kernel(a.mode, a.boot_id)
    out = a.output
    out.mkdir(parents=True)
    result = dict(passed=False, accepted=False, mode=a.mode, boot_id=a.boot_id, block=a.block)
    try:
        rt.require(BLOCKS[a.block][0] == a.mode, 'ordered candidate boot mode differs')
        inputs = prepared(a.prepared)
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
        host_check(host, fresh=True)
        env, topo = environment()
        comparison = host_environment(host, env, topo)
        fault_check(out, 'ready-dmesg')
        result.update(passed=True, prepared=bind(a.prepared), files=control_files(),
            environment=env, topology=topo, host_comparison=comparison, kernel_identity=identity)
    finally:
        rt.write_json(out / 'result.json', result)


def readiness(path):
    row = common.load(path)
    rt.require(row['passed'], 'same-boot readiness required')
    common.verify_maps(row['files'])
    check_kernel(row['mode'], row['boot_id'])
    inputs = prepared(Path(row['prepared']['path']))
    load_bound(row['prepared'])
    for binding in row['prior_api']:
        load_bound(binding)
    return row, inputs


def measurement(rows, spec, mode):
    result = writer.validate(rows, spec)
    values = sorted(v for w in rows[1]['workers'] for v in w['latency_ns'])
    result.update(execution='KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK',
                  latency_percentiles_ns={str(p): values[math.ceil(p/100*len(values))-1]
                    for p in (50, 95, 99)} if values else {},
                  latency_sample_policy='every 64th whole mmap/munmap cycle; per-worker stagger')
    return result


def fixed(inputs, out, mode):
    mapping.SITES = common.load(SITES)
    sites = mapping.SITES
    chain = sites['chains'][mode]
    proof = [str(sites['sites'][name]['return_offset']) for name in ('vm_mmap_pgoff', '__vm_munmap')]
    proof += [chain['waiter'], *map(str, chain['wait_returns']), str(chain['adapter_return']), sites['adapter']]
    rt.command(['insmod', inputs['binaries']['payload'], 'observe=1'], out / 'load-fixed.log')
    fault_check(out, 'after-fixed-load-dmesg')
    health(0)
    data = rt.command([inputs['binaries']['fixed'], 'cycle', '16', '5000', *proof],
                      out / 'fixed.jsonl', timeout=120)
    rows = [json.loads(line) for line in data.splitlines()]
    result = mapping.validate(rows, 'cycle', 16, 5000, mode)
    result['rejected_mutations'] = mapping.reject_mutations(rows, mode)
    result['health'] = health(1)
    fault_check(out, 'fixed-dmesg')
    rt.command(['rmmod', MODULE], out / 'unload-fixed.log')
    return result


def timed(inputs, out, spec):
    rt.command(['insmod', inputs['binaries']['payload'], 'observe=0'], out / 'load.log')
    fault_check(out, 'after-load-dmesg')
    health(0)
    rt.command([inputs['binaries']['timed'], str(spec['threads']), spec['observation']],
               out / 'client.jsonl', timeout=120)


def business_finish(out, spec, mode):
    # Evidence qualification is separate. Only normal client completion, exact
    # lifetime accounting and a fault-free guest authorize ordinary unload.
    fault_check(out, 'before-unload-dmesg')
    rows = [json.loads(line) for line in (out / 'client.jsonl').read_text().splitlines()]
    result = measurement(rows, spec, mode)
    value = health(1)
    rt.command(['rmmod', MODULE], out / 'unload.log')
    fault_check(out, 'after-unload-dmesg')
    writer.check.idle(Path('/root'))
    return result, value


def validate(a):
    ready, inputs = readiness(a.ready)
    out = a.output
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, accepted=False, mode=ready['mode'],
                  prepared=ready['prepared'], ready=bind(a.ready), cases=[])
    try:
        result['fixed'] = fixed(inputs, out, ready['mode'])
        result['fixed_raw'] = bind(out / 'fixed.jsonl')
        for index, (n, observation) in enumerate(CASES):
            case = out / f'{n}-{observation}'
            case.mkdir()
            spec = specification(index, 0, ready['mode'])
            timed(inputs, case, spec)
            row, value = business_finish(case, spec, ready['mode'])
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


def validation_shape(v, mode, prepared_ref):
    rt.require(v['passed'] and v['drained'] and not v['accepted'] and v['mode'] == mode and
               v['prepared'] == prepared_ref and len(v['cases']) == 4 and
               [c['spec'] for c in v['cases']] == [specification(i, 0, mode) for i in range(4)],
               'validation case set/specification differs')
    f = v['fixed']
    rt.require(f['passed'] and f['mode'] == 'cycle' and f['threads'] == 16 and f['iterations'] == 5000 and
               f['protocol'] == ('KD_LOCAL_MMAP_LOCK' if mode == 'kd' else 'NATIVE_CONTROL_MMAP_LOCK') and
               f['health'] == 'files=0 mm_refs=0 destroyed=1 release_errors=0' and
               f['rejected_mutations'] == ['different_lock', 'wrong_caller_return', 'wrong_wait_return',
                   'wrong_adapter_return', 'running_task', 'other_wait_channel', 'rescheduled_task',
                   'missing_chain', 'missing_writer_proof'], 'required fixed-work writer proof differs')


def validation_receipt(path, mode, prepared_ref):
    """Replay saved positive evidence without executing a workload or test."""
    v = common.load(path)
    validation_shape(v, mode, prepared_ref)
    ready = load_bound(v['ready'])
    rt.require(ready['passed'] and ready['mode'] == mode and ready['prepared'] == prepared_ref and
               ready['block'] == (0 if mode == 'native' else 1), 'validation readiness differs')
    mapping.SITES = common.load(SITES)
    raw = [json.loads(line) for line in file_bound(v['fixed_raw']).read_text().splitlines()]
    proof = mapping.validate(raw, 'cycle', 16, 5000, mode)
    rt.require(all(v['fixed'][key] == value for key, value in proof.items()), 'saved writer proof differs')
    for case in v['cases']:
        raw = [json.loads(line) for line in file_bound(case['raw']).read_text().splitlines()]
        rt.require(measurement(raw, case['spec'], mode) == case['measurement'] and
                   case['health'] == 'files=0 mm_refs=0 destroyed=1 release_errors=0',
                   'saved timed-client validation differs')
    return v


def run(a):
    ready, inputs = readiness(a.ready)
    rt.require(a.repeat in BLOCKS[ready['block']][1] and 0 <= a.case < len(CASES), 'case/block differs')
    out = a.output
    out.mkdir(parents=True)
    spec = specification(a.case, a.repeat, ready['mode'])
    result = dict(passed=False, accepted=False, drained=False, client_exited=False,
        ready=bind(a.ready), mode=ready['mode'], boot_id=ready['boot_id'], spec=spec,
        repeat=a.repeat, case=a.case, block=ready['block'], prepared=ready['prepared'])
    try:
        index = ORDER.index((a.repeat, ready['mode'], a.case))
        rt.require((index == 0) == (a.previous is None), 'ordered predecessor required')
        if a.previous is not None:
            prior = common.load(a.previous)
            rt.require(prior['passed'] and prior['drained'] and prior['accepted'] and
                (prior['repeat'], prior['mode'], prior['case']) == ORDER[index-1] and
                prior['prepared'] == ready['prepared'] and
                ((prior['block'] == ready['block']) == (prior['boot_id'] == ready['boot_id'])),
                'preceding qualified case or boot transition differs')
            result['previous'] = bind(a.previous)
        result['validated'] = []
        for mode, path in [('native', a.native_validation), ('kd', a.kd_validation)]:
            validation_receipt(path, mode, ready['prepared'])
            result['validated'].append(bind(path))
        host = common.load(a.host_state)
        host_check(host, fresh=True)
        if a.previous is not None:
            rt.require(host['captured_utc'] > prior['endpoint_captured_utc'],
                       'fresh admission must follow the preceding endpoint')
        env, topo = environment()
        result['host_comparison'] = host_environment(host, env, topo)
        result['admission'] = bind(a.host_state)
        shutil.copyfile(a.host_state, out / 'host-before.json')
        fault_check(out, 'before-load-dmesg')
        timed(inputs, out, spec)
        result['client_exited'] = True
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'client-result.json', result)


def qualify(out, client, directory):
    controller = common.load(directory / 'controller.json')
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
    host_check(host, fresh=False)
    ids = lambda h: sorted((t['tid'], t['start_ticks']) for t in h['capture']['tasks'])
    rt.require(ids(before) == ids(host), 'QEMU task lifetime changed across measurement')
    ready = load_bound(client['ready'])
    host_environment(host, ready['environment'], ready['topology'])
    return dict(captured_utc=host['captured_utc'], controller=bind(directory / 'controller.json'),
                endpoint=bind(host_path), admission=client['admission'])


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
        result['measurement'], result['health'] = business_finish(out, client['spec'], client['mode'])
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
    p.add_argument('action', choices=('ready', 'validate', 'run', 'finish'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--native-api', type=Path)
    p.add_argument('--kd-api', type=Path)
    p.add_argument('--mode', choices=('native', 'kd'))
    p.add_argument('--block', type=int, choices=range(5))
    p.add_argument('--boot-id')
    p.add_argument('--ready', type=Path)
    p.add_argument('--host-state', type=Path)
    p.add_argument('--repeat', type=int, choices=range(3))
    p.add_argument('--case', type=int, choices=range(4))
    p.add_argument('--native-validation', type=Path)
    p.add_argument('--kd-validation', type=Path)
    p.add_argument('--controller', type=Path)
    p.add_argument('--previous', type=Path)
    a = p.parse_args()
    a.output = a.output.resolve()
    rt.require(not a.output.is_relative_to(ROOT) and (a.action == 'finish' or not a.output.exists()),
               'unique evidence directory outside source required')
    globals()[a.action](a)


if __name__ == '__main__':
    main()
