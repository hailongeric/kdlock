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
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True


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
            assert (parameters / 'rwsem_provider_bindings').read_text().strip() == '0'
            assert rt.status() == dict(state=0, modules=0, frames=0, writers=0)
            provider = Path(c['provider'])
            assert rt.digest(provider) == c['provider_sha256']
            assert rt.digest(bench.execution.NOTE) == bench.execution.module_note_sha256(provider)
            stats = bench.execution.reached_observations()
            assert stats['active'] == stats['unsupported'] == 0 and stats['roots'] == stats['completions']
            result['final_reached'] = stats
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
                '-g', '--clockid', 'mono', '-o', str(out / 'perf.data'), '--', 'sleep', '20']
            profiler = subprocess.Popen(command, stdout=profile_log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            result['profiler'] = dict(argv=command, pid=profiler.pid, started_ns=time.monotonic_ns())
            time.sleep(0.25)
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
            (controller.PARAMETERS / 'rwsem_provider_mode').write_text('deactivate\n')
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
