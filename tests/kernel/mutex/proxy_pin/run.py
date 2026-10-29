#!/usr/bin/env python3
"""Guest-only queued producer scheduling probe; no JIT or timing claim."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

MODULE = 'kd_mutex_proxy_pin_probe'
PREFIX = 'kd_mutex_proxy_pin: queued=1 scheduled=1 effects=4 warm=400000 idle=1 context=1 result=0'
CONTEXT = re.compile(r'kd_mutex_proxy_context: role=(\d+) phase=(\d+) cpu=(\d+) '
                     r'preempt=(\d+) migration=(\d+) irq=(\d+) valid=(\d+)')


def contexts(messages):
    fields = ('role', 'phase', 'cpu', 'preempt', 'migration', 'irq', 'valid')
    rows = [dict(zip(fields, map(int, match))) for match in CONTEXT.findall(messages)]
    expected = {(role, phase) for role in range(5) for phase in range(3)
                if (role, phase) != (4, 1)}
    rt.require(len(rows) == len(expected) and
               {(row['role'], row['phase']) for row in rows} == expected,
               'missing or duplicate joined-task context receipt')
    rt.require(all(row['valid'] == 1 and not row['preempt'] and not row['migration'] and
                   not row['irq'] and row['cpu'] == (3 if row['role'] == 4 else row['role'])
                   for row in rows), 'task context or CPU placement was not restored')
    return rows


def sources(root):
    result = {}
    for directory in ('include', 'kernel_module', 'tests/kernel/mutex/proxy_pin',
                      'bench/spin_cacheline', 'kernel_baseline',
                      'kernel_integration/linux70', 'disassem', 'tests/protocols'):
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if (path.is_file() and not path.name.endswith('.mod.c') and
                not any(part.startswith('.') or part == '__pycache__' for part in relative.parts) and
                (path.suffix in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch') or
                 path.name == 'Makefile')):
                result[str(relative)] = rt.digest(path)
    return result


def idle():
    rt.idle()
    rt.require(not Path('/sys/module', MODULE).exists(), 'existing scheduling probe')
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            rt.require(path.read_text().strip() != 'kd_proxy', 'existing probe task')
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed recovery guest required')
    idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    result = dict(passed=False, drained=False, final_idle=False, jit_bodies=0,
                  snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'])
    messages = ''
    fd = None
    chunks, log_errors = [], []
    stop = threading.Event()
    collector = None

    def collect_log():
        # Drain concurrently with module init: the real contention warmup can
        # otherwise overwrite the kernel ring before insmod returns. Any lost
        # records still fail the run; continuing collection never waives them.
        while True:
            try:
                chunks.append(os.read(fd, 1 << 20).decode(errors='replace') + '\n')
            except BlockingIOError:
                if stop.is_set():
                    return
                stop.wait(0.005)
            except OSError as error:
                log_errors.append(str(error))
                break

    def check_log():
        nonlocal messages
        messages = ''.join(chunks)
        (out / 'kernel.log').write_text(messages)
        rt.require(not log_errors, f'kernel log coverage failed: {log_errors}')
        if rt.FAULT.search(messages):
            raise rt.Failure('KERNEL_FAULT', 'kernel fault; retain modules', unsafe=True)

    try:
        result['kernel_identity'] = kernel_identity.capture(args, out, rt.command)
        source = out / 'source'
        frozen = sources(ROOT)
        for relative in frozen:
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        rt.write_json(out / 'source-sha256.json', frozen)
        provider = source / 'kernel_module/kdlock_km.ko'
        payload = source / 'tests/kernel/mutex/proxy_pin/payload' / (MODULE + '.ko')
        for name, binary in (('provider', provider), ('probe', payload)):
            rt.command(['make', '-C', binary.parent, f'KDIR={args.kernel_source}',
                        'W=1', 'KDLOCK_SELFTEST=0', 'UBSAN_SANITIZE=n'],
                       out / f'build-{name}.log', timeout=180)
        result['ready_policy'] = {}
        for field, expected in (('mutex_spin_budget', '65536'), ('mutex_ready_window', '8')):
            value = rt.command(['modinfo', '-F', field, provider], out / (field + '.txt')).strip()
            rt.require(value == expected, 'unexpected ready-spin policy: ' + field)
            result['ready_policy'][field] = int(value)
        rt.require(sources(ROOT) == sources(source) == frozen, 'source inputs changed')
        binaries = {str(path): rt.digest(path) for path in (provider, payload)}
        rt.write_json(out / 'binary-sha256.json', binaries)
        idle()
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        collector = threading.Thread(target=collect_log, name='kernel-log', daemon=True)
        collector.start()
        rt.command(['insmod', provider, 'target_process=kd_proxy'], out / 'load-provider.log')
        check_log()
        rt.command(['taskset', '-c', '63', 'insmod', payload], out / 'load-probe.log', timeout=90)
        # The synchronous probe has ended; allow the reader to consume its final
        # record before validating it. This is not a worker drain assumption.
        for _ in range(100):
            if any(PREFIX in chunk for chunk in chunks) or log_errors:
                break
            stop.wait(0.01)
        check_log()
        rt.require(messages.count(PREFIX) == 1, 'missing exact scheduling/drain receipt')
        result['contexts'] = contexts(messages)
        rt.command(['rmmod', MODULE], out / 'unload-probe.log')
        check_log()
        retired = json.loads(rt.command(
            [sys.executable, source / 'disassem/device_session.py', 'retire'], out / 'retire.log'))
        result['source_retirement'] = retired
        rt.require(retired == dict(state=2, modules=0, frames=0, writers=0), 'source drain failed')
        rt.command(['rmmod', 'kdlock_km'], out / 'unload-provider.log')
        check_log()
        rt.require(sources(ROOT) == sources(source) == frozen and
                   all(rt.digest(Path(path)) == digest for path, digest in binaries.items()),
                   'frozen inputs changed')
        idle()
        result.update(passed=True, drained=True, final_idle=True)
    except Exception as error:
        result.update(status=getattr(error, 'status', 'RUN_FAILED'), error=str(error))
        try:
            check_log()
        except Exception as log_error:
            result['kernel_log_error'] = str(log_error)
        result['modules_remaining'] = [name for name in (MODULE, 'kdlock_km')
                                       if Path('/sys/module', name).exists()]
        print(f'FAIL: {error}; no failure cleanup attempted', file=sys.stderr)
    finally:
        if collector is not None:
            stop.set()
            collector.join(timeout=5)
            if collector.is_alive():
                result.update(passed=False, kernel_log_error='collector did not stop')
            final_messages = ''.join(chunks)
            (out / 'kernel.log').write_text(final_messages)
            if log_errors or rt.FAULT.search(final_messages):
                result.update(passed=False, kernel_log_error=str(log_errors) or 'kernel fault')
        if fd is not None:
            os.close(fd)
        rt.write_json(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
