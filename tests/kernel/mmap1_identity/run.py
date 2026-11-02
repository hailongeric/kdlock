#!/usr/bin/env python3
"""Unscored object identity for unchanged mmap1; execution only in the VM."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('unchanged_mmap1_runner', ROOT/'bench/mmap1/run.py')
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)
rt = bench.rt
CAPACITY = 128
HEADER = ('abi', 'count', 'overflow', 'errors', 'stopped', 'refs_acquired', 'refs_released')
FIELDS = ('tid', 'tgid', 'start_boottime_ns', 'mm', 'lock', 'backing', 'use_kd', 'cpu')
SIZE = 8*(len(HEADER)+CAPACITY*len(FIELDS))
STOP = (2 << 30) | (SIZE << 16) | (ord('M') << 8) | 0x79


def decode(data):
    rt.require(len(data) == SIZE, 'invalid identity ioctl length')
    values = struct.unpack('='+str(SIZE//8)+'Q', data)
    result = dict(zip(HEADER, values[:len(HEADER)]))
    rt.require(result['abi'] == 1 and 0 < result['count'] <= CAPACITY and
               result['overflow'] == result['errors'] == 0 and result['stopped'] == 1 and
               result['refs_acquired'] == result['refs_released'] == result['count'],
               'identity observation incomplete or references unbalanced')
    rows = values[len(HEADER):]
    result['records'] = [dict(zip(FIELDS, rows[i*len(FIELDS):(i+1)*len(FIELDS)]))
                         for i in range(result['count'])]
    rt.require(not any(rows[result['count']*len(FIELDS):]), 'nonzero unused observation slot')
    return result


def stop_client():
    first, second = bytearray(SIZE), bytearray(SIZE)
    with open('/dev/kd_mmap1_identity', 'rb', buffering=0) as device:
        fcntl.ioctl(device, STOP, first, True)
        fcntl.ioctl(device, STOP, second, True)
    rt.require(first == second, 'stop is not stable/idempotent')
    print(json.dumps(dict(decode(first), repeat_equal=True)), flush=True)


def validate(snapshot, session, mode, ticks):
    rt.require(snapshot.get('repeat_equal') is True and snapshot.get('abi') == 1 and
               snapshot.get('stopped') == 1 and snapshot.get('errors') == snapshot.get('overflow') == 0 and
               snapshot.get('count') == snapshot.get('refs_acquired') == snapshot.get('refs_released') and
               0 < snapshot['count'] <= CAPACITY, 'unstable or unbalanced stopped observer')
    rt.require(session.get('passed') is True and session.get('drained') is True and
               session.get('scored') is False and session.get('instrumentation') == 'identity-kprobe' and
               session.get('output') == dict(output_valid=True, measured_samples=2),
               'exact normal unscored application lifetime required')
    workers = session['workers_observed']
    rows = snapshot['records']
    rt.require(len(workers) == session['workers'] >= 2 and len(rows) == len(workers) == snapshot['count'],
               'worker/identity count differs')
    rt.require(len({row['tid'] for row in rows}) == len(rows) and
               {row['tid'] for row in rows} == {row['tid'] for row in workers}, 'missing/duplicate/extra task identity')
    by_tid = {row['tid']:row for row in rows}
    for worker in workers:
        row = by_tid[worker['tid']]
        expected_tgid = session['pid'] if session['model'] == 'threads' else row['tid']
        rt.require(row['tgid'] == expected_tgid and
                   row['start_boottime_ns']*ticks//1_000_000_000 == worker['start_ticks'] and
                   worker['cpus'] == [row['cpu']] and row['use_kd'] == int(mode == 'kd') and
                   row['mm'] != 0 and row['lock'] != 0 and row['backing'] != 0,
                   'actual task lifetime/CPU/object/backend differs')
    unique = len({row['mm'] for row in rows})
    expected = 1 if session['model'] == 'threads' else len(workers)
    rt.require(unique == expected and len({row['lock'] for row in rows}) == expected and
               len({row['backing'] for row in rows}) == expected, 'application mm/lock sharing differs')
    # Each retained mm must map to exactly one lock/backend in this diagnostic;
    # no numerical offset is guessed from a different build or object type.
    rt.require(all(len({(r['lock'], r['backing'], r['use_kd']) for r in rows if r['mm'] == address}) == 1
                   for address in {r['mm'] for r in rows}), 'one mm has inconsistent lock bindings')
    return dict(passed=True, workers=len(workers), unique_mms=unique,
                actual_mmap_lock_observed=True, records=rows,
                scope='these diagnostic process lifetimes only', delegated_execution_proved=False)


def main():
    if sys.argv[1:] == ['--stop-client']:
        stop_client()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    bench.arguments(parser)
    args = parser.parse_args()
    args.inputs = args.inputs.resolve()
    bench.guest(args)
    # Kernel task_pid_nr and /proc IDs must refer to the same PID namespace.
    namespace = next(line for line in Path('/proc/self/status').read_text().splitlines()
                     if line.startswith('NSpid:'))
    rt.require(len(namespace.split()) == 2, 'initial guest PID namespace required')
    rt.require(os.stat('/proc/self/ns/time').st_ino == os.stat('/proc/1/ns/time').st_ino,
               'initial guest time namespace required for exact task start times')
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external observation output required')
    bench.idle()
    out.mkdir(parents=True)
    result = dict(schema=1, scope='diagnostic-class-proof', state='PREPARATION',
                  passed=False, drained=False, accepted=False, mode=args.mode, boot_id=args.boot_id,
                  inputs_sha256=rt.digest(args.inputs), models={}, files={}, instrumentation='identity-kprobe',
                  clock_ticks=os.sysconf('SC_CLK_TCK'),
                  scored=False, host_endpoint='PENDING')
    rt.write_json(out/'result.json', result)
    fd = None
    messages = ''
    def logs():
        nonlocal messages
        if fd is None:
            return
        while True:
            try:
                messages += os.read(fd, 1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:
                break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages), 'kernel warning/fault; retain observer')
    try:
        result.update(bench.admit(args, out))
        inputs = bench.inputs_from(args.inputs)
        files = bench.freeze_support(out)
        files[str(args.inputs)] = rt.digest(args.inputs)
        files[str(args.inputs.parent/'result.json')] = rt.digest(args.inputs.parent/'result.json')
        files.update(inputs['files'])
        source = out/'source'
        source.mkdir()
        source_hashes = {}
        for original in sorted((ROOT/'tests/kernel/mmap1_identity/payload').iterdir()):
            # Kbuild regenerates .mod.c; it is a build product, never a source input.
            if original.name.endswith('.mod.c') or (
                    original.name != 'Makefile' and original.suffix not in ('.c', '.h', '.inc')):
                continue
            copied = source/original.name
            shutil.copyfile(original, copied)
            files[str(original)] = files[str(copied)] = rt.digest(copied)
            source_hashes[original.name] = rt.digest(copied)
        rt.write_json(out/'source-sha256.json', source_hashes)
        rt.command(['make', '-C', source, 'KDIR='+str(args.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'],
                   out/'build.log', timeout=180)
        module = source/'kd_mmap1_identity.ko'
        files[str(module)] = rt.digest(module)
        vermagic = rt.command(['modinfo', '-F', 'vermagic', module], out/'vermagic.log')
        rt.require(vermagic.split()[0] == os.uname().release, 'observer build release differs')
        result.update(module_sha256=rt.digest(module), source_sha256=source_hashes)
        def verify():
            bench.verify_boot(args)
            bench.verified_files(files)
        verify()
        fd = os.open('/dev/kmsg', os.O_RDONLY|os.O_NONBLOCK)
        os.lseek(fd, 0, os.SEEK_END)
        result['state'] = 'RUNNING'
        for model in bench.MODELS:
            bench.idle()
            rt.command(['insmod', module, 'target=mmap1_'+model], out/(model+'-load.log'))
            logs()
            session = bench.run_point(out/model, dict(model=model, workers=2, round=0, nominal_seconds=2),
                                      inputs, verify, diagnostic=True)
            data = rt.command([sys.executable, Path(__file__).resolve(), '--stop-client'],
                              out/(model+'-snapshot.json'), timeout=30)
            snapshot = json.loads(data)
            logs()
            result['models'][model] = validate(snapshot, session, args.mode, os.sysconf('SC_CLK_TCK'))
            result['models'][model].update(session_result_sha256=rt.digest(out/model/'result.json'),
                                          snapshot_sha256=rt.digest(out/(model+'-snapshot.json')),
                                          session_result=str(out/model/'result.json'),
                                          snapshot=str(out/(model+'-snapshot.json')))
            verify()
            rt.command(['rmmod', 'kd_mmap1_identity'], out/(model+'-unload.log'))
            logs()
            bench.idle()
            for path in (out/model/'result.json', out/model/'upstream.log', out/(model+'-snapshot.json')):
                files[str(path)] = rt.digest(path)
            rt.write_json(out/'result.json', result)
        verify()
        result.update(state='COMPLETE', passed=True, drained=True, final_idle=True, files=files)
    except BaseException as error:
        result.update(state='FAILED', passed=False, error=repr(error))
        raise
    finally:
        try:
            logs()
        except BaseException as error:
            result.update(state='FAILED', passed=False, log_error=repr(error))
            raise
        finally:
            if fd is not None:
                os.close(fd)
            rt.write_json(out/'result.json', result)


if __name__ == '__main__':
    main()
