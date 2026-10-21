#!/usr/bin/env python3
"""One unscored mmap16 profile; keep frozen work and all admission/drain checks.

The endpoint follows the normal exit of perf and its child, before export or
cleanup. Recorder flush is part of this diagnostic boundary, not the original
plain-client endpoint. A timeout leaves both processes and payload intact.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
if ROOT.exists():
    sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
import serial

plain = serial.plain
rt = plain.rt
PERF = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf')
PERF_SHA = 'be41fc3678db80aa92593a72034ebd6ec4c574c2dca2523f294dff5a0667aca3'
INPUTS_SHA = '69271dff3cbb70e098a0b7157125b32a97ee7499b5903a539d0259bc5dff9b6f'
SELF = ROOT / 'bench/mmap_lock/contention_profile.py'


def perf_args(client, out):
    return ['taskset', '-c', '63', str(PERF), 'record', '--quiet',
            '--clockid', 'mono', '--sample-cpu', '--call-graph', 'fp',
            '--kernel-callchains', '--strict-freq', '--no-buildid-cache',
            '-e', 'cpu-clock:k', '-F', '99', '--inherit', '-m', '128',
            '-o', str(out / 'perf.data'), '--', str(client), '16', 'plain']


def settings():
    return {name: (Path('/proc/sys/kernel') / name).read_text()
            for name in ('perf_event_paranoid', 'perf_event_max_sample_rate',
                         'perf_event_mlock_kb', 'perf_event_max_stack')}


def record_client(args, out):
    receipt = dict(argv=args, started_ns=time.monotonic_ns(), timeout_seconds=120,
                   state='STARTING')
    path = out / 'record-command.json'
    rt.write_json(path, receipt)
    with (out / 'client.log').open('wb') as output, (out / 'perf-record.log').open('wb') as errors:
        child = subprocess.Popen(args, stdout=output, stderr=errors, start_new_session=True)
        receipt.update(pid=child.pid, state='RUNNING')
        rt.write_json(path, receipt)
        try:
            code = child.wait(timeout=120)
        except subprocess.TimeoutExpired as error:
            receipt.update(state='UNKNOWN_DRAIN', error=repr(error))
            rt.write_json(path, receipt)
            raise rt.Failure('TIMEOUT', f'PID {child.pid}; retain recorder, child and payload', unsafe=True) from error
    receipt.update(state='EXITED', returncode=code, finished_ns=time.monotonic_ns())
    rt.write_json(path, receipt)
    rt.require(code == 0, 'recorder/client failed; inspect retained state before cleanup')


def run(a):
    out = a.output
    rt.require(not out.exists() and not out.resolve().is_relative_to(a.inputs.resolve().parent),
               'new output outside frozen inputs required')
    out.mkdir()
    result = dict(passed=False, drained=False, accepted=False, state='ADMISSION',
                  diagnostic=True, diagnostic_kind='mmap16-cpu-clock-k-99hz-stacks',
                  endpoint_boundary='RECORDER_EXIT_INCLUDING_FLUSH', task='mmap', threads=16,
                  p95_status='DEFERRED', seven_mutex_causes='UNRESOLVED')
    try:
        rt.require(rt.digest(a.inputs) == INPUTS_SHA, 'original frozen inputs required')
        inputs = plain.prepared_inputs(a.inputs)
        validated = serial.prerequisites(a.inputs, a.validated)
        a.action = 'measure'  # Invoke every original environment predicate.
        result.update(plain.profile(a, out))
        identity = plain.common.kernel_identity.capture(argparse.Namespace(
            kernel_source=plain.SOURCE, kernel_baseline=plain.BUNDLE), out, rt.command)
        rt.require(identity['running_build_id'] == plain.BUILD_ID and
                   rt.digest(plain.BUNDLE / 'manifest.json') == plain.MANIFEST_SHA and
                   rt.digest(plain.SOURCE / 'vmlinux') == plain.mapping.SITES['vmlinux_sha256'],
                   'candidate image differs')
        rt.require(rt.digest(PERF) == PERF_SHA, 'retained perf tool changed')
        result.update(kernel_identity=identity, inputs=serial.binding(a.inputs),
            inputs_sha256=INPUTS_SHA, validated=validated, transition=serial.binding(a.transition),
            driver_sha256=rt.digest(Path(__file__)), admission_host_sha256=rt.digest(a.host_state),
            controls=[serial.binding(p) for p in (SELF, ROOT/'bench/mmap_lock/serial.py',
                      serial.CONTROL, serial.BOUNDARY, PERF)], settings=settings(),
            module='kd_mmap_writer_native', spec=plain.specification('mmap',16,a.mode))
        rt.command([PERF, '--version'], out / 'perf-version.log')
        for name in ('kallsyms','modules'):
            (out / name).write_bytes(Path('/proc', name).read_bytes())
        serial.fault_check(out, 'before-load-dmesg')
        rt.command(['insmod', inputs['binaries']['writer_payload'], 'observe=0'], out / 'load.log')
        serial.fault_check(out, 'after-load-dmesg')
        rt.require(serial.health(result['module']) == serial.expected_health('mmap',0),
                   'payload starts with retained references')
        # Module symbols must be captured while this exact payload is loaded.
        (out / 'kallsyms').write_bytes(Path('/proc/kallsyms').read_bytes())
        (out / 'modules-loaded').write_bytes(Path('/proc/modules').read_bytes())
        rt.write_json(out / 'payload-sections.json', {p.name:p.read_text().strip()
            for p in Path('/sys/module/kd_mmap_writer_native/sections').iterdir()})
        result['state'] = 'CLIENT_RUNNING'
        rt.write_json(out / 'client-result.json', result)
        record_client(perf_args(inputs['binaries']['writer_plain'], out), out)
        # No validation, export, hash scan or unload before the fixed endpoint.
        result.update(passed=True, state='CLIENT_RETURNED', cleanup_pending=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'client-result.json', result)


def finish(a):
    out = a.output
    rt.require(not (out / 'result.json').exists(), 'completed receipt already exists')
    client = plain.common.load(out / 'client-result.json')
    result = dict(client, passed=False, drained=False, accepted=False, profile_usable=False)
    try:
        rt.require(client['passed'] and client['state'] == 'CLIENT_RETURNED' and
            client['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
            client['driver_sha256'] == rt.digest(Path(__file__)), 'matching normal return required')
        serial.verify_binding(client['inputs'])
        serial.verify_binding(client['transition'])
        for row in client['validated']:
            serial.verify_binding(row)
        for row in client['controls']:
            rt.require(rt.digest(Path(row['path'])) == row['sha256'], 'diagnostic control changed')
        inputs = plain.prepared_inputs(Path(client['inputs']['path']))
        controller = plain.common.load(out / 'controller.json')
        host = plain.common.load(out / 'host-endpoint.json')
        rt.require(controller['driver_sha256'] == rt.digest(serial.CONTROL) and
            controller['admission_sha256'] == client['admission_host_sha256'] and
            0 <= controller['admission_age_seconds'] <= 300, 'controller/admission binding differs')
        endpoint = dict(checked=True, passed=False, immediate=controller.get('immediate',False),
            result_sha256=rt.digest(out/'client-result.json'), host_sha256=rt.digest(out/'host-endpoint.json'),
            boundary=client['endpoint_boundary'])
        boundary = runpy.run_path(str(serial.BOUNDARY))
        boundary['endpoint_link'](endpoint,controller,host,endpoint['result_sha256'],
                                  endpoint['host_sha256'],str(out/'client-result.json'))
        try:
            endpoint['comparison'] = serial.endpoint_check(host,
                plain.common.load(out/'environment.json'), plain.common.load(out/'topology.json'))
            endpoint['passed'] = True
        except (rt.Failure,ValueError) as error:
            endpoint['error'] = repr(error)
        rt.write_json(out/'endpoint.json', endpoint)
        measurement, health = serial.validate_and_unload(out, client)
        plain.common.verify_maps(inputs['files'])
        plain.common.idle(Path('/root'))
        modules = sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
        rt.require(modules == client['modules'] and settings() == client['settings'],
                   'module set or perf settings changed')
        result.update(drained=True, final_idle=True, cleanup_pending=False, measurement=measurement,
                      health=health, endpoint=endpoint, host_endpoint='PASS' if endpoint['passed'] else 'FAIL')
        # Raw capture stays in the guest. Export and static analysis run on the
        # source host after archiving, using these exact symbols and objects.
        result.update(passed=True, state='COMPLETE_DIAGNOSTIC', profile_review='PENDING_OFFLINE',
            artifacts={name:rt.digest(out/name) for name in ('perf.data','perf-record.log',
                'kallsyms','modules-loaded','payload-sections.json','client.log')})
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out/'result.json', result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('run','finish'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host-state',type=Path)
    p.add_argument('--boot-id')
    p.add_argument('--mode',choices=('native','kd'))
    p.add_argument('--transition',type=Path)
    p.add_argument('--inputs',type=Path)
    p.add_argument('--validated',type=Path,nargs=2)
    a = p.parse_args()
    rt.require(not Path(__file__).resolve().is_relative_to(ROOT) and
        not a.output.resolve().is_relative_to(ROOT) and rt.digest(Path(__file__)) == rt.digest(SELF),
        'byte-matched external diagnostic driver/output required')
    (run if a.action == 'run' else finish)(a)


if __name__ == '__main__':
    main()
