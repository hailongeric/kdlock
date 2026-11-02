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
import re

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('unchanged_mmap1_runner', ROOT/'bench/mmap1/run.py')
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)
rt = bench.rt
CAPACITY = 128
HEADER = ('abi', 'count', 'overflow', 'errors', 'stopped', 'refs_acquired', 'refs_released')
FIELDS = ('tid', 'tgid', 'start_boottime_ns', 'mm', 'lock', 'backing', 'use_kd', 'cpu', 'provider', 'route')
SIZE = 8*(len(HEADER)+CAPACITY*len(FIELDS))
STOP = (2 << 30) | (SIZE << 16) | (ord('M') << 8) | 0x79


def decode(data):
    rt.require(len(data) == SIZE, 'invalid identity ioctl length')
    values = struct.unpack('='+str(SIZE//8)+'Q', data)
    result = dict(zip(HEADER, values[:len(HEADER)]))
    rt.require(result['abi'] == 2 and 0 < result['count'] <= CAPACITY and
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


def validate(snapshot, session, mode, ticks, *, provider=None):
    rt.require(snapshot.get('repeat_equal') is True and snapshot.get('abi') == 2 and
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
        route = 0 if mode == 'native' else (2 if row['provider'] else 1)
        rt.require(row['route'] == route and (mode != 'native' or row['provider'] == 0) and
                   (provider is None or row['provider'] == provider),
                   'immutable provider binding/route differs')
    unique = len({row['mm'] for row in rows})
    expected = 1 if session['model'] == 'threads' else len(workers)
    rt.require(unique == expected and len({row['lock'] for row in rows}) == expected and
               len({row['backing'] for row in rows}) == expected, 'application mm/lock sharing differs')
    # Each retained mm must map to exactly one lock/backend in this diagnostic;
    # no numerical offset is guessed from a different build or object type.
    rt.require(all(len({(r['lock'], r['backing'], r['use_kd'], r['provider'], r['route'])
                       for r in rows if r['mm'] == address}) == 1
                   for address in {r['mm'] for r in rows}), 'one mm has inconsistent lock bindings')
    return dict(passed=True, workers=len(workers), unique_mms=unique,
                actual_mmap_lock_observed=True, records=rows,
                immutable_provider_observed=True, provider_routes=sorted({row['route'] for row in rows}),
                scope='these diagnostic process lifetimes only', delegated_execution_proved=False)


def validate_delegated(snapshot, session, ticks, messages, entry_sites, provider):
    """Join completed runtime requests to these exact observed MM lifetimes.

    entry_sites is a separately retained source/build audit map with nonempty
    mmap and munmap entry sets. Full trace collection/drain is the controller's
    obligation. This function refuses unmatched selected enter/returned pairs.
    """
    rt.require(type(provider) is int and provider > 0 and set(entry_sites) == {'mmap', 'munmap'} and
               all(entry_sites.values()), 'exact module provider and audited entry sites required')
    sites = {}
    for label, entries in entry_sites.items():
        for entry in entries:
            rt.require(type(entry) is int and entry > 0 and entry not in sites,
                       'entry-site audit overlaps or contains invalid entries')
            sites[entry] = label
    identity = validate(snapshot, session, 'kd', ticks, provider=provider)
    rt.require(identity['provider_routes'] == [2], 'diagnostic workers are not bound to the module provider')
    parser = bench.common.module('mmap1_retained_trace_parser', ROOT/'tests/kernel/jit_continuation/killable_mode.py')
    by_tid = {row['tid']: row for row in snapshot['records']}
    requests, completed, seen = {}, [], set()
    canceled = 0
    for position, line in enumerate(messages.splitlines()):
        for event in parser.trace_events(line):
            if event['origin'] not in by_tid or event['depth'] != 0 or event['entry'] not in sites:
                continue
            task = by_tid[event['origin']]
            rt.require(event['object'] == task['backing'] and event['may_delegate'] and
                       event['identity'] > 0 and event['generation'] > 0,
                       'runtime request did not use the observed task MM lock')
            stamp = re.match(r'^\d+,\d+,(\d+),[^;]*;', line)
            event = dict(event, trace_position=position,
                         timestamp_ns=int(stamp[1]) * 1000 if stamp else None)
            key = (event['origin'], event['identity'], event['generation'])
            if event['event'] == 'cancel':
                rt.require(key not in seen, 'entered/repeated request was labeled pre-body cancellation')
                seen.add(key)
                canceled += 1
                continue
            if event['event'] == 'enter':
                rt.require(key not in seen and event['executor'] != event['origin'],
                           'runtime request repeated entry or executed on its origin')
                seen.add(key)
                requests[key] = [event]
                continue
            rt.require(key in requests, 'runtime root event has no captured entry')
            prior = requests[key]
            rt.require(all(event[name] == prior[0][name] for name in
                           ('origin', 'executor', 'identity', 'generation', 'object', 'entry')),
                       'runtime request changed executor, image entry or lock identity')
            prior.append(event)
            if event['event'] != 'returned':
                continue
            stages = [row['event'] for row in prior]
            rt.require(stages == ['enter', 'release', 'returned'] or
                       stages == ['enter', 'downgrade', 'read_release', 'returned'],
                       'runtime write/downgraded read-tail release sequence differs')
            start, end = prior[0]['timestamp_ns'], event['timestamp_ns']
            rt.require(start is None or end is None or end >= start, 'runtime event clock reversed')
            completed.append(dict(operation=sites[event['entry']], origin=event['origin'],
                executor=event['executor'], identity=event['identity'], generation=event['generation'],
                mm=task['mm'], lock=task['lock'], backing=task['backing'], provider=provider,
                worker_start_boottime_ns=task['start_boottime_ns'], entry=event['entry'], events=prior,
                request_wall_ns=end - start if start is not None and end is not None else None))
            del requests[key]
    rt.require(not requests and completed, 'runtime trace has incomplete or absent returned requests')
    for tid in by_tid:
        rt.require({row['operation'] for row in completed if row['origin'] == tid} == {'mmap', 'munmap'},
                   'each diagnostic worker needs returned other-task mmap and munmap requests')
    downgraded = [row for row in completed if any(event['event'] == 'downgrade' for event in row['events'])]
    later = []
    for old in downgraded:
        release = next(event for event in old['events'] if event['event'] == 'read_release')
        for new in completed:
            if old is not new and old['executor'] == new['executor'] and old['backing'] == new['backing'] and \
                    new['events'][0]['trace_position'] > release['trace_position']:
                later.append(dict(read_request=[old['identity'], old['generation']],
                                  later_writer=[new['identity'], new['generation']], executor=old['executor']))
                break
    return dict(identity=identity, delegated_execution_proved=True, completed_requests=completed,
                completed_request_count=len(completed), canceled_before_body=canceled,
                downgraded_read_tails=len(downgraded), later_same_executor_writers=later,
                fresh_reader_drain_observed=False, physical_batch_length_measured=False,
                all_application_invocations_accounted=False,
                request_wall_time_unit='monotonic kmsg timestamp ns; includes Native service waits',
                scope='these diagnostic task/MM lifetimes and captured audited entries only')


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
