#!/usr/bin/env python3
"""One guest-owned mmap1 point, with retirement in a fresh process.

The configuration binds an immutable source root and optional provider built
from that root. Application bodies and the public lock API are unchanged.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True


def jit_observations(parameters):
    words = (parameters / 'reached_jit_stats').read_text().split()
    values = {name: int(value) for name, value in (word.split('=') for word in words)}
    assert set(values) == {'entries', 'retired', 'interpreted'}
    assert values['entries'] >= values['retired'] >= 0 and values['interpreted'] == 0
    return values


def demand_learning(c, out, owner, daemon, bench, rt, inputs, verify):
    """Renew exact receipts only at quiescent learning boundaries."""
    timeout = c.get('learning_timeout', 900)
    assert type(timeout) is int and 1 <= timeout <= 3600
    deadline = time.monotonic() + timeout
    limit = c.get('learning_rounds', 3)
    assert type(limit) is int and 1 <= limit <= 8
    previous, epochs = None, []
    sites = {row['entry'] for row in owner.audit['records']}
    base_files = dict(owner.files)

    def snapshot():
        nonlocal previous
        verify()
        parameters = bench.execution.PARAMETERS
        active = parameters / 'rwsem_provider_active'
        mode = parameters / 'rwsem_provider_mode'
        assert active.read_text().strip() == 'Y'
        mode.write_text('deactivate\n')
        settled_since = None
        while True:
            assert time.monotonic() < deadline, 'demand learning did not reach a quiescent boundary'
            assert daemon.daemon.poll() is None, 'translation daemon exited during learning'
            source, rows = rt.status(), rt.registry()
            stable = (not rt.children(daemon.daemon.pid) and source['state'] == source['frames'] == 0 and
                      source['writers'] == 1 and all(row['status'] in (0, -3) for row in rows))
            if not stable:
                settled_since = None
                time.sleep(0.05)
                continue
            bench.execution.demand_registry(rows, sites)
            signature = (source, bench.execution.registry(rows))
            now = time.monotonic()
            if settled_since is None or settled_since[1] != signature:
                settled_since = (now, signature)
            if now - settled_since[0] < 1:
                time.sleep(0.05)
                continue
            if previous is not None:
                bench.execution.demand_transition(previous, rows, sites)
            verify()
            epoch = out / 'epochs' / ('epoch-%03d' % len(epochs))
            epoch.mkdir(parents=True)
            owner.model, owner.files = epoch, dict(base_files)
            for row in rows:
                if row['status'] != 0:
                    continue
                source_dir = out / 'workspace/daemon' / hex(row['entry']) / str(row['tgid']) / 'asm'
                destination = epoch / (hex(row['entry']) + '-g' + str(row['generation']))
                destination.mkdir()
                for name in ('jit.bin', 'jit.S', 'bin.txt'):
                    target = destination / name
                    __import__('shutil').copyfile(source_dir / name, target)
                    owner.files[str(target)] = rt.digest(target)
            mode.write_text('activate\n')
            try:
                receipt = owner.session_receipt(daemon, rows)
                receipt.verify()
            except rt.Failure as error:
                if error.status not in ('LEARNING_ADVANCED', 'UNDRAINED'):
                    raise
                epochs.append(dict(path=str(epoch), accepted=False, error=str(error)))
                mode.write_text('deactivate\n')
                settled_since = None
                continue
            previous = rows
            epochs.append(dict(path=str(epoch), accepted=True, registry=rows))
            rt.write_json(out / 'learning-epochs.json', epochs)
            return receipt

    class LearningSession(bench.execution.ExecutionSession):
        def __init__(self):
            self.current = snapshot()
            self.__dict__.update(self.current.__dict__)

        def verify(self, *, allow_identity_probe=False):
            current = snapshot()
            self.current = current
            self.__dict__.update(current.__dict__)
            return current.verify(allow_identity_probe=allow_identity_probe)

    learning = LearningSession()
    observations = []
    for number in range(limit):
        before = bench.execution.registry(learning.expected['registry'])
        application = bench.run_point(out / ('learning-%02d' % number), dict(
            model=c['model'], workers=c['workers'], round=number, nominal_seconds=2),
            inputs, verify, execution_session=learning, learning=True)
        after = bench.execution.registry(learning.expected['registry'])
        observations.append(dict(application=application, registry_before=before, registry_after=after))
        rt.write_json(out / 'learning.json', observations)
        if before == after:
            return learning.current, observations
    raise rt.Failure('LEARNING_ADVANCED', 'bounded application learning has not reached a stable timing epoch')


def image_point(c, config_bytes, root, out, controller, finalize):
    """Use the ordinary immutable-image session without changing its checks."""
    bench, rt = controller.bench, controller.rt
    args = argparse.Namespace(mode=c['mode'], boot_id=c['boot_id'],
        kernel_variant=c['variant'], kernel_source=Path(c['kdir']),
        kernel_baseline=Path(c['bundle']), host_state=Path(c['host_state']),
        host_reference=Path(c['host_state']), host_reference_sha256=c['host_sha256'],
        execution_mode='image', demand=c.get('demand', False),
        sites=Path(c['sites']), sites_sha256=c['sites_sha256'],
        source_commit=c['source_commit'], source_state=root / 'source-state.json',
        source_manifest=root / 'source-sha256.json',
        source_state_sha256=c['state_sha256'], source_manifest_sha256=c['manifest_sha256'])
    result_path = out / ('finalization.json' if finalize else 'result.json')
    result = dict(schema=1, passed=False, drained=False, accepted=False,
        execution_mode='image', config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        source_commit=c['source_commit'], runner_sha256=rt.digest(Path(__file__)),
        mode=c['mode'], model=c['model'], workers=c['workers'], boot_id=c['boot_id'],
        delegation_proved=False, physical_batch_length_measured=False)
    try:
        assert os.geteuid() == 0 and sys.executable == controller.PYTHON
        assert c['mode'] in ('native', 'kd') and c['model'] in bench.MODELS
        assert c['workers'] in bench.WORKERS and c['profile'] is False
        assert type(args.demand) is bool
        controller.source_manifest(args)
        if finalize:
            original = bench.load(out / 'result.json')
            assert original['state'] == 'MEASURED_RETIREMENT_PENDING' and not original['passed']
            assert original['config_sha256'] == result['config_sha256']
            assert original['application']['passed'] and original['application']['drained']
            args.captured_runtime_policy = original['environment']['kernel_identity']['runtime_policy']
            bench.verify_boot(args)
            expected = bench.load(Path(original['execution_session']['path']))
            bench.verified_files(expected['files'])
            assert rt.digest(Path(original['execution_session']['path'])) == original['execution_session']['sha256']
            assert (controller.PARAMETERS / 'rwsem_provider_active').read_text().strip() == 'N'
            deadline = time.monotonic() + 10
            wanted = dict(expected['source'], writers=0, frames=0)
            while True:
                observed = dict(source=rt.status(), bindings=int(
                    (controller.PARAMETERS / 'rwsem_provider_bindings').read_text()))
                result['retirement_observation'] = observed
                if observed == dict(source=wanted, bindings=0):
                    break
                assert time.monotonic() < deadline, 'exact image-session retirement did not drain'
                time.sleep(0.01)
            assert bench.execution.registry(rt.registry()) == bench.execution.registry(expected['registry'])
            assert rt.digest(bench.execution.NOTE) == bench.execution.module_note_sha256(Path(c['provider']))
            result['service_progress'] = (controller.PARAMETERS / 'service_progress').read_text()
            assert result['service_progress'].strip() == 'total=0 shown=0'
            with open('/dev/kd_dev', 'rb', buffering=0) as device:
                fcntl.ioctl(device, rt.RETIRE)
                result['retired'] = rt.info(device.fileno())
            assert result['retired'] == dict(state=2, modules=0, frames=0, writers=0)
            rt.command(['rmmod', 'kdlock_km'], out / 'unload.log', timeout=30)
            bench.idle()
            result.update(state='COMPLETE', passed=True, drained=True, final_idle=True,
                measured_result=dict(path=str(out / 'result.json'), sha256=rt.digest(out / 'result.json')))
            return

        bench.idle()
        assert __import__('shutil').disk_usage('/').free >= 2 * controller.GIB + controller.GIB // 4
        out.mkdir(exist_ok=False)
        result['environment'] = bench.admit(args, out)
        assert rt.digest(Path(c['inputs'])) == c['inputs_sha256']
        inputs = bench.inputs_from(Path(c['inputs']))
        files = dict(inputs['files'])
        files[str(args.sites)] = c['sites_sha256']
        audit = controller.site_audit(args, result['environment']['kernel_binding'])
        def verify():
            bench.verify_boot(args)
            bench.verified_files(files)
        exact = daemon = None
        if c['mode'] == 'kd':
            provider, binary = Path(c['provider']), Path(c['daemon'])
            assert rt.digest(provider) == c['provider_sha256'] and rt.digest(binary) == c['daemon_sha256']
            files.update({str(provider): c['provider_sha256'], str(binary): c['daemon_sha256']})
            load = ['insmod', str(provider), 'bench_quiet=1', 'bench_complete_probe=0',
                'jit_timing=0', 'hotlock_stats=0', 'service_cpus=0-61']
            if args.demand:
                load.append('rwsem_provider_demand=1')
            rt.command(load, out / 'load.log', timeout=30)
            assert (controller.PARAMETERS / 'bench_quiet').read_text().strip() == 'Y'
            assert (controller.PARAMETERS / 'bench_complete_probe').read_text().strip() == 'N'
            assert (controller.PARAMETERS / 'service_trace').read_text().strip() == 'N'
            assert (controller.PARAMETERS / 'rwsem_provider_active').read_text().strip() == 'N'
            assert (controller.PARAMETERS / 'rwsem_provider_bindings').read_text().strip() == '0'
            daemon = controller.Daemon(out, root, binary)
            daemon.start()
            owner = controller.Controller.__new__(controller.Controller)
            owner.args, owner.model, owner.files, owner.audit = args, out, files, audit
            owner.binaries = dict(provider=provider)
            (controller.PARAMETERS / 'rwsem_provider_mode').write_text('prepare\n')
            timeout = c.get('prewarm_timeout', 180)
            assert type(timeout) is int and 1 <= timeout <= 3600
            deadline = time.monotonic() + timeout
            rows = []
            if not args.demand:
                while True:
                    rows = owner.ready(daemon)
                    if rows:
                        break
                    assert time.monotonic() < deadline, 'all-site image preparation did not complete'
                    time.sleep(0.05)
            for row in rows:
                folder = out / 'workspace/daemon' / hex(row['entry']) / str(row['tgid']) / 'asm'
                for name in ('jit.bin', 'jit.S', 'bin.txt'):
                    path = folder / name
                    assert path.is_file() and path.stat().st_size > 0
                    files[str(path)] = rt.digest(path)
            (controller.PARAMETERS / 'rwsem_provider_mode').write_text('activate\n')
            if args.demand:
                exact, result['learning'] = demand_learning(c, out, owner, daemon, bench, rt, inputs, verify)
            else:
                exact = owner.session_receipt(daemon, rows)
            exact.verify()
            result['execution_session'] = exact.identity()
            result['prior_delegation_proof'] = c.get('delegation_proof')
        rt.write_json(result_path, dict(result, state='RUNNING'))
        result['application'] = bench.run_point(out / 'application', dict(
            model=c['model'], workers=c['workers'], round=0, nominal_seconds=2),
            inputs, verify, execution_session=exact)
        result['upstream'] = bench.parse_output((out / 'application/upstream.log').read_text(), c['workers'])
        verify()
        if exact is not None:
            exact.verify()
            (controller.PARAMETERS / 'rwsem_provider_mode').write_text('deactivate\n')
            daemon.stop()
            result.update(state='MEASURED_RETIREMENT_PENDING', factory_active=False,
                retirement='fresh process after controller exit required')
        else:
            bench.idle()
            result.update(state='COMPLETE', passed=True, drained=True, final_idle=True)
        controller.source_manifest(args)
    except BaseException as error:
        result.update(state='LEARNING_ADVANCED' if isinstance(error, rt.Failure) and
                      error.status == 'LEARNING_ADVANCED' else 'FAILED',
                      error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        if out.exists():
            rt.write_json(result_path, result)
        print(json.dumps({key: result.get(key) for key in
            ('state', 'passed', 'drained', 'mode', 'model', 'workers', 'upstream', 'error')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--finalize', action='store_true')
    options = parser.parse_args()
    config_bytes = options.config.read_bytes()
    c = json.loads(config_bytes)
    root, out = Path(c['root']), Path(c['output'])
    sys.path.insert(0, str(root / 'bench/spin_cacheline'))
    spec = importlib.util.spec_from_file_location('mm_point_controller',
        root / 'tests/kernel/mmap1_identity/delegated.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    if c.get('execution_mode') == 'image':
        return image_point(c, config_bytes, root, out, controller, options.finalize)
    bench, rt = controller.bench, controller.rt
    args = argparse.Namespace(mode=c['mode'], boot_id=c['boot_id'],
        kernel_variant=c['variant'], kernel_source=Path(c['kdir']),
        kernel_baseline=Path(c['bundle']), host_state=Path(c['host_state']),
        host_reference=Path(c['host_state']), host_reference_sha256=c['host_sha256'],
        execution_mode='reached', sites=Path(c['sites']), sites_sha256=c['sites_sha256'],
        source_commit=c['source_commit'], source_state=root / 'source-state.json',
        source_manifest=root / 'source-sha256.json',
        source_state_sha256=c['state_sha256'], source_manifest_sha256=c['manifest_sha256'])
    result_path = out / ('finalization.json' if options.finalize else 'result.json')
    result = dict(schema=1, passed=False, drained=False, scored=not c['profile'],
        config_sha256=hashlib.sha256(config_bytes).hexdigest(), source_commit=c['source_commit'],
        runner_sha256=rt.digest(Path(__file__)), mode=c['mode'], boot_id=c['boot_id'],
        model=c['model'], workers=c['workers'], profile=c['profile'])
    profiler = None
    try:
        assert os.geteuid() == 0 and sys.executable == controller.PYTHON
        assert c['mode'] in ('native', 'kd') and c['workers'] in bench.WORKERS
        assert c['model'] in bench.MODELS and type(c['profile']) is bool
        assert rt.digest(args.source_state) == c['state_sha256']
        assert rt.digest(args.source_manifest) == c['manifest_sha256']
        controller.source_manifest(args)
        if options.finalize:
            original = bench.load(out / 'result.json')
            assert original['state'] == 'MEASURED_RETIREMENT_PENDING' and not original['passed']
            assert original['config_sha256'] == result['config_sha256']
            assert original['application']['passed'] and original['application']['drained']
            assert original['application']['returncode'] == 0
            args.captured_runtime_policy = original['environment']['kernel_identity']['runtime_policy']
            bench.verify_boot(args)
            parameters = controller.PARAMETERS
            assert (parameters / 'rwsem_provider_active').read_text().strip() == 'N'
            deadline = time.monotonic() + 5
            observed = []
            while True:
                state = dict(bindings=int((parameters / 'rwsem_provider_bindings').read_text()),
                             source=rt.status())
                if not observed or observed[-1]['state'] != state:
                    observed.append(dict(at_ns=time.monotonic_ns(), state=state))
                    result['retirement_observations'] = observed
                if state == dict(bindings=0, source=dict(state=0, modules=0, frames=0, writers=0)):
                    break
                assert time.monotonic() < deadline, 'exact retirement state did not drain'
                time.sleep(0.01)
            provider = Path(c['provider'])
            assert rt.digest(provider) == c['provider_sha256']
            assert rt.digest(bench.execution.NOTE) == bench.execution.module_note_sha256(provider)
            stats = bench.execution.reached_observations()
            assert stats['active'] == stats['unsupported'] == 0 and stats['roots'] == stats['completions']
            result['final_reached'] = stats
            result['final_jit'] = jit_observations(parameters)
            assert result['final_jit']['retired'] > original['jit_before']['retired']
            with open('/dev/kd_dev', 'rb', buffering=0) as device:
                fcntl.ioctl(device, rt.RETIRE)
                result['retired'] = rt.info(device.fileno())
            assert result['retired'] == dict(state=2, modules=0, frames=0, writers=0)
            r = subprocess.run(['rmmod', 'kdlock_km'], capture_output=True, text=True, timeout=30)
            (out / 'unload.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0, r.stderr
            bench.idle()
            result.update(state='COMPLETE', passed=True, drained=True, final_idle=True,
                          measured_result=dict(path=str(out / 'result.json'), sha256=rt.digest(out / 'result.json')))
            return

        bench.idle()
        assert __import__('shutil').disk_usage('/').free >= 2 * controller.GIB + controller.GIB // 4
        out.mkdir(exist_ok=False)
        result['environment'] = bench.admit(args, out)
        inputs = bench.inputs_from(Path(c['inputs']))
        assert rt.digest(Path(c['inputs'])) == c['inputs_sha256']
        files = dict(inputs['files'])
        files[str(args.sites)] = c['sites_sha256']
        audit = controller.site_audit(args, result['environment']['kernel_binding'])
        exact = None
        if c['profile']:
            profile_log = (out / 'perf-record.log').open('w')
            command = ['taskset', '-c', '62', 'perf', 'record', '-a', '-e', 'cycles:k', '-F', '199',
                '--clockid', 'mono', '-o', str(out / 'perf.data'), '--', controller.PYTHON,
                '-c', "import time;print('PROFILE_READY',flush=True);time.sleep(20)"]
            profiler = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=profile_log,
                                        start_new_session=True)
            result['profiler'] = dict(argv=command, pid=profiler.pid, started_ns=time.monotonic_ns())
            assert select.select([profiler.stdout], [], [], 10)[0], 'profiler workload readiness timed out'
            assert profiler.stdout.readline() == b'PROFILE_READY\n', 'profiler workload readiness differs'
            result['profiler']['ready_ns'] = time.monotonic_ns()
            assert profiler.poll() is None, 'profiler exited before application'
        if c['mode'] == 'kd':
            provider = Path(c['provider'])
            assert rt.digest(provider) == c['provider_sha256']
            files[str(provider)] = c['provider_sha256']
            r = subprocess.run(['insmod', str(provider), 'bench_quiet=1', 'bench_complete_probe=0',
                'jit_timing=0', 'hotlock_stats=0', 'service_reached=1', 'service_cpus=0-61'],
                capture_output=True, text=True, timeout=30)
            (out / 'load.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0, r.stderr
            parameters = controller.PARAMETERS
            if c['profile']:
                sections = Path('/sys/module/kdlock_km/sections')
                result['provider_sections'] = {p.name: p.read_text().strip() for p in sections.iterdir()}
                (out / 'kallsyms').write_bytes(Path('/proc/kallsyms').read_bytes())
            assert (parameters / 'service_trace').read_text().strip() == 'N'
            (parameters / 'rwsem_provider_mode').write_text('prepare\n')
            assert not rt.registry() and not bench.execution.device_writers()
            (parameters / 'rwsem_provider_mode').write_text('activate\n')
            owner = controller.Controller.__new__(controller.Controller)
            owner.args, owner.model, owner.files, owner.audit = args, out, files, audit
            owner.binaries = dict(provider=provider)
            class QuiescentSession(bench.execution.ExecutionSession):
                def verify(self, *, allow_identity_probe=False):
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            return super().verify(allow_identity_probe=allow_identity_probe)
                        except rt.Failure as error:
                            # Setup may overlap a finishing background request.
                            # Retry this exact boundary, retaining every check.
                            if (str(error) != 'reached source/family/registry state is not drained' or
                                    bench.execution.reached_observations()['unsupported'] or
                                    time.monotonic() >= deadline):
                                raise
                            time.sleep(0.005)
            prepared = owner.reached_receipt([])
            exact = QuiescentSession(prepared.path, prepared.sha256)
            exact.verify()
            result['reached_before'] = bench.execution.reached_observations()
            result['jit_before'] = jit_observations(parameters)
            result['jit_cache_before'] = (parameters / 'reached_jit_cache').read_text().strip()
            result['execution_session'] = exact.identity()
            result['prior_delegation_proof'] = c['delegation_proof']
        def verify():
            bench.verify_boot(args)
            bench.verified_files(files)
        rt.write_json(result_path, dict(result, state='RUNNING'))
        application = bench.run_point(out / 'application', dict(model=c['model'], workers=c['workers'],
            round=0, nominal_seconds=2), inputs, verify, execution_session=exact)
        result['application'] = application
        result['score_class'] = 'profile-diagnostic' if c['profile'] else 'untraced-throughput'
        result['upstream'] = bench.parse_output((out / 'application/upstream.log').read_text(), c['workers'])
        if profiler is not None:
            result['profiler']['returncode'] = profiler.wait(timeout=20)
            profile_log.close()
            assert profiler.returncode == 0
            result['profiler']['data_sha256'] = rt.digest(out / 'perf.data')
            command = ['perf', 'report', '--stdio', '--no-children', '--sort', 'comm,dso,symbol',
                       '-i', str(out / 'perf.data'), '--percent-limit', '0.2', '--time',
                       '%.9f,%.9f' % (application['started_ns'] / 1e9,
                           (application['started_ns'] + application['process_elapsed_ns']) / 1e9)]
            with (out / 'perf-report.txt').open('w') as report:
                r = subprocess.run(command, stdout=report, stderr=subprocess.STDOUT, timeout=45)
            assert r.returncode == 0
        verify()
        if exact is not None:
            exact.verify()
            after = bench.execution.reached_observations()
            assert after['active'] == after['unsupported'] == 0 and after['roots'] == after['completions']
            assert after['roots'] > result['reached_before']['roots']
            result['reached_after'] = after
            result['jit_after'] = jit_observations(controller.PARAMETERS)
            result['jit_cache_after'] = (controller.PARAMETERS / 'reached_jit_cache').read_text().strip()
            result['jit_delta'] = {name: result['jit_after'][name] - result['jit_before'][name]
                                   for name in result['jit_after']}
            assert result['jit_delta']['entries'] >= result['jit_delta']['retired'] > 0
            assert result['jit_delta']['interpreted'] == 0
            (controller.PARAMETERS / 'rwsem_provider_mode').write_text('deactivate\n')
            progress = dict(started_ns=time.monotonic_ns(),
                bindings_before=int((controller.PARAMETERS / 'rwsem_provider_bindings').read_text()), cpus=[])
            result['postrun_cpu_progress'] = progress
            deadline = time.monotonic() + 5
            for cpu in rt.cpu_list(Path('/sys/devices/system/cpu/online').read_text().strip()):
                remaining = deadline - time.monotonic()
                assert remaining > 0, 'postrun CPU progress exceeded its bound'
                subprocess.run(['taskset', '-c', str(cpu), '/usr/bin/true'], check=True,
                               timeout=remaining, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                progress['cpus'].append(cpu)
            progress.update(finished_ns=time.monotonic_ns(),
                bindings_after=int((controller.PARAMETERS / 'rwsem_provider_bindings').read_text()))
            result.update(state='MEASURED_RETIREMENT_PENDING', factory_active=False,
                          retirement='fresh process after controller exit required')
        else:
            bench.idle()
            result.update(state='COMPLETE', passed=True, drained=True, final_idle=True)
        controller.source_manifest(args)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        if out.exists():
            rt.write_json(result_path, result)
        print(json.dumps({key: result.get(key) for key in
            ('state', 'passed', 'drained', 'mode', 'model', 'workers', 'profile', 'upstream', 'error')}), flush=True)


if __name__ == '__main__':
    main()
