#!/usr/bin/env python3
"""Guest-only compact KD mutex layout and ordinary API checks; no JIT claims."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


EXPECTED = dict(operations='160000', workers='8', objects='2048', lock_size='32',
                lock_align='8', containing_layout='PASS', address_reuse='PASS',
                no_destroy='PASS', no_aux='PASS', interruptible='EINTR',
                killable='EINTR', ring_cancel='PASS', ring_handoff='PASS',
                nested_sleep='PASS', io='PASS', drain='PASS')
MODULES = ('kd_mutex_local_probe', 'rwsem_probe', 'rwlock_bench', 'rwlock_test',
           'real_api', 'tclock_backend_km', 'tclock_mutex_backend_km',
           'tclock_rwlock_backend_km', 'tc_allocator_guard', 'kd_spin_irq_api_test')


def idle():
    rt.idle()
    for name in MODULES:
        rt.require(not Path('/sys/module', name).exists(), 'existing module: ' + name)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = path.read_text().strip()
        except FileNotFoundError:
            continue
        rt.require(name not in ('rb_worker', 'kd_rwsem_probe', 'kd_rwsem_cancel', 'kd-cancel')
                   and not name.startswith(('kd-local/', 'kd_mtask_', 'kd_irq_api/')),
                   f'existing task: {path}: {name}')


def sources(root):
    hashes = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/mutex/local',
                      'bench/spin_cacheline', 'kernel_baseline', 'disassem', 'tests/protocols'):
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in relative.parts)
                    or path.name.endswith('.mod.c') or
                    (path.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
                     and path.name != 'Makefile')):
                continue
            hashes[str(relative)] = rt.digest(path)
    return hashes


def verify_inputs(source, hashes, binaries=None):
    rt.require(sources(ROOT) == hashes, 'source inputs changed after snapshot')
    rt.require(sources(source) == hashes, 'frozen source differs from snapshot')
    if binaries is not None:
        rt.require(all(rt.digest(Path(path)) == expected for path, expected in binaries.items()),
                   'frozen binary changed')


def probe_result(messages):
    records = [line.split('KD_LOCAL_PROBE PASS ', 1)[1].strip()
               for line in messages.splitlines() if 'KD_LOCAL_PROBE PASS ' in line]
    rt.require(len(records) == 1, 'expected one joined, drained ordinary mutex PASS record',
               'PROBE_FAILED')
    fields = records[0].split()
    rt.require(all(field.count('=') == 1 for field in fields),
               'malformed ordinary mutex PASS record', 'PROBE_FAILED')
    result = dict(field.split('=') for field in fields)
    rt.require(len(fields) == len(result) and result == EXPECTED,
               f'ordinary mutex result differs: {result}', 'PROBE_FAILED')
    return {key: int(value) if value.isdecimal() else value for key, value in result.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    idle()
    rt.require(set(range(8)).issubset(rt.cpu_list(
        Path('/sys/devices/system/cpu/online').read_text().strip())), 'probe requires online CPUs 0-7')
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, final_idle=False, jit_bodies=0,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], execution='ordinary-local')
    fd = None
    messages = ''

    def check_log():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1 << 20).decode(errors='replace') + '\n'
            except BlockingIOError:
                break
        (out / 'kernel.log').write_text(messages)
        if rt.FAULT.search(messages):
            raise rt.Failure('KERNEL_FAULT', 'kernel fault; retain modules', unsafe=True)

    try:
        result['kernel_identity'] = kernel_identity.capture(args, out, rt.command)
        source = out / 'source'
        hashes = sources(ROOT)
        for relative in hashes:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        verify_inputs(source, hashes)
        rt.write_json(out / 'source-sha256.json', hashes)
        provider = source / 'kernel_module/kdlock_km.ko'
        module = source / 'tests/kernel/mutex/local/kd_mutex_local_probe.ko'
        rt.command(['make', '-C', provider.parent, f'KDIR={args.kernel_source}', 'W=1',
                    'KDLOCK_SELFTEST=0', 'UBSAN_SANITIZE=n'], out / 'build-provider.log', timeout=180)
        rt.command(['make', '-C', module.parent, f'KDIR={args.kernel_source}', 'W=1'],
                   out / 'build-probe.log', timeout=180)
        binaries = {str(path): rt.digest(path) for path in (provider, module)}
        verify_inputs(source, hashes, binaries)
        result['binaries'] = {str(path.relative_to(out)): binaries[str(path)]
                              for path in (provider, module)}
        rt.write_json(out / 'binary-sha256.json', result['binaries'])
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        rt.command(['insmod', provider], out / 'load-provider.log')
        check_log()
        # Module init returns PASS only after all ordinary workers have joined
        # and exact physical/auxiliary drain checks succeeded. A timeout leaves
        # insmod and both modules untouched for diagnosis; it never implies drain.
        rt.command(['insmod', module], out / 'load-probe.log', timeout=60)
        check_log()
        result['probe'] = probe_result(messages)
        verify_inputs(source, hashes, binaries)
        rt.command(['rmmod', 'kd_mutex_local_probe'], out / 'unload-probe.log')
        check_log()
        retired = rt.command([sys.executable, source / 'disassem/device_session.py', 'retire'],
                             out / 'retire.log')
        result['source_retirement'] = json.loads(retired)
        rt.require(result['source_retirement'] == dict(state=2, modules=0, frames=0, writers=0),
                   'source retirement did not prove exact drain', 'DRAIN_FAILED')
        check_log()
        rt.command(['rmmod', 'kdlock_km'], out / 'unload-provider.log')
        check_log()
        verify_inputs(source, hashes, binaries)
        idle()
        result.update(passed=True, drained=True, final_idle=True)
    except Exception as error:
        result.update(status=getattr(error, 'status', 'RUN_FAILED'), error=str(error))
        try:
            check_log()
        except Exception as log_error:
            result['kernel_log_error'] = str(log_error)
        result['modules_remaining'] = [name for name in ('kdlock_km', *MODULES)
                                       if Path('/sys/module', name).exists()]
        print(f'FAIL: {error}; no failure cleanup attempted', file=sys.stderr)
    finally:
        if fd is not None:
            os.close(fd)
        rt.write_json(out / 'result.json', result)
    if not result['passed']:
        return 1
    print('PASS: native mutex layout, ordinary API exclusion, sleeping owners, cancellation, '
          'address reuse without destroy, no auxiliary records and final idle')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
