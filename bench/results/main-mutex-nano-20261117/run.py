#!/usr/bin/env python3
"""Matched ordinary mutex measurements in the frozen main-final guest."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import struct
import subprocess
import sys
import time
import traceback

ROOT = Path('/mnt/kdlock-builds2/main-spin-local-4669a085-20261117')
REPO = ROOT / 'main-final-repo'
BOOT = 'fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d'
RELEASE = '7.0.0-38-kdlocalspin6'
SOURCE = '18dad4a1c372d77a1155db671d56c148918344da'
BOOT_PATH = Path('/proc/sys/kernel/random/boot_id')
PARAM = Path('/sys/module/kernel/parameters')
SYS_MOD = Path('/sys/module')
TC = 'tclock_mutex_backend_km'
TC_PARAM = SYS_MOD / TC / 'parameters'
THRESHOLD = PARAM / 'kd_deleg_enter_sleep'
DEFAULTS = dict(kd_deleg_enter_sleep='3', kd_deleg_enter='5', kd_deleg_exit='2',
                kd_adapt='Y', kd_numa='Y', kd_batch='4096', kd_numa_after='32',
                kd_spin_queue_phase='Y', kd_spin_phase_wait='0', kd_xchg='1',
                kd_vdown='1', kd_cldemote='3', kd_handoff_running='1', kd_api='0', kd_mm='N')
MODULES = {family: module for family, module in (
    ('spin', 'tclock_backend_km'), ('mutex', TC), ('rwlock', 'tclock_rwlock_backend_km'),
    ('rwsem', 'tclock_rwsem_backend_km'))}
STANDARD_WORKERS = (1, 2, 3, 4, 5, 6, 8, 16, 32)
TUNING_WORKERS = (4, 5, 8, 32)
COUNTERS = ('delegated', 'handback', 'offered', 'sessions', 'plain', 'numa_deferred',
            'cl_offered', 'cl_done', 'head_sleep', 'parked', 'handoff', 'stop_plain',
            'mode_enter', 'mode_exit', 'hb_frontier', 'hb_acquire', 'hb_miss')
WARN = re.compile(r'BUG:|WARNING:|Oops:|soft lockup|hard LOCKUP|Kernel panic|general protection fault|blocked for more than', re.I)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'evidence-main-mutex')
args = parser.parse_args()
E = args.output

def read(path):
    return Path(path).read_text().strip()

def check(condition, message):
    if not condition:
        raise RuntimeError(str(message))

def save(name, value):
    (E / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def sha(path):
    with open(path, 'rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
        return digest.hexdigest()

def saved_cmd(name, command, timeout=60):
    run = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    (E / name).write_text(run.stdout + run.stderr)
    check(run.returncode == 0, (command, run.returncode, run.stderr[-512:]))
    return run.stdout

def progress(message):
    line = 'KDMAIN_MUTEX_PROGRESS ' + message
    print(line, flush=True)
    with open('/dev/ttyS0', 'w') as port:
        port.write('\n' + line + '\n')

def modules():
    return {line.split()[0] for line in read('/proc/modules').splitlines()}

def warn_check(dmesg):
    matches = [line for line in dmesg.splitlines() if WARN.search(line)]
    if matches:
        (E / 'warning-log.txt').write_text(dmesg)
        raise RuntimeError(matches[:5])

def idle():
    for mod in MODULES.values():
        if mod in loaded:
            check(read(SYS_MOD / mod / 'parameters/quiescent') == '1', mod + ' still active')

def tc_stats():
    return {k: int(read(TC_PARAM / k)) for k in ('delegated', 'batches', 'parks')}

def delta(after, before):
    check(set(after) == set(before), 'counter schema changed')
    return {k: after[k] - before[k] for k in before if k != 'delegation'}

def checked_point(phase, backend, workers, lines, ms, rnd, policy, family='mutex', active=True):
    first = 4 if workers == 32 else 0
    if active:
        check(daemon is not None and daemon.poll() is None, 'daemon stopped')
    before = nano.kd_stats()
    check(set(COUNTERS) <= before.keys() and before.get('delegation') == int(active), before)
    tc_before = tc_stats()
    effective = {key: read(PARAM / key) for key in DEFAULTS}
    check(all(effective[key] == value for key, value in DEFAULTS.items() if key != THRESHOLD.name), effective)
    request = struct.pack(nano.IN_FMT, nano.FAMILY[family], nano.BACKEND[backend],
                          lines, 100, 256, workers, first, ms, 0, 0)
    buffer = bytearray(struct.calcsize(nano.RUN_FMT))
    buffer[:len(request)] = request
    started = time.time()
    fcntl.ioctl(fd, nano.IOC, buffer, True)
    after = nano.kd_stats()
    kd_delta = delta(after, before)
    tc_delta = delta(tc_stats(), tc_before)
    fields = struct.unpack(nano.RUN_FMT, buffer)
    elapsed, ops, writes, mismatches, total_delta = fields[10:15]
    wops = fields[15:15 + workers]
    wwr = fields[15 + nano.MAXW:15 + nano.MAXW + workers]
    ok = (elapsed > 0 and all(wops) and wops == wwr and sum(wops) == ops == writes
          and mismatches == 0 and total_delta == writes * lines and sum(wwr) == writes)
    result = dict(phase=phase, policy=policy, backend=backend, family=family, workers=workers,
                  lines=lines, write_pct=100, post=256, first_cpu=first, ms=ms, round=rnd,
                  time=started, boot_id=BOOT, kernel=RELEASE, source=SOURCE, ok=ok,
                  mops=ops * 1000 / elapsed if elapsed else 0, elapsed_ns=elapsed,
                  ops=ops, writes=writes, sum_delta=total_delta, torn_reads=mismatches,
                  worker_ops=wops, worker_writes=wwr, min_worker_ops=min(wops),
                  max_worker_ops=max(wops), delegation=after['delegation'], kd_delta=kd_delta,
                  execution_counts={k: kd_delta[k] for k in COUNTERS}, tc_delta=tc_delta,
                  parameters=effective)
    log.write(json.dumps(result) + '\n')
    check(ok, ('mutex data or progress check', result))
    check(after['delegation'] == int(active), 'delegation mode changed')
    if backend == 'tclock':
        idle()
    else:
        check(not any(tc_delta.values()), ('unexpected TCLock activity', tc_delta))
    if backend == 'kd' and workers == 1:
        check(kd_delta['offered'] == 0, ('single-worker offers', kd_delta))
    warn_check(subprocess.check_output(['dmesg'], text=True, timeout=10))
    return result

def paired_grid(phase, workers_set, modes):
    for rnd in range(3):
        progress(f'{phase} round={rnd}')
        for width in (1, 16):
            for w in workers_set:
                rotation = (rnd + w) % len(modes)
                for backend, threshold in modes[rotation:] + modes[:rotation]:
                    if read(THRESHOLD) != str(threshold):
                        THRESHOLD.write_text(str(threshold))
                    check(read(THRESHOLD) == str(threshold), 'threshold write failed')
                    policy = 'default' if phase == 'three-way' else 'enter-' + str(threshold)
                    for kind, duration in ((phase + '-warmup', 250), (phase, 1000)):
                        checked_point(kind, backend, w, width, duration, rnd, policy)

def checked_inputs():
    manifest = ROOT / 'main-final-identity.json'
    signed = ROOT / 'signed-artifacts-main-final.json'
    check(sha(manifest) == '76ad9656bf6c88b9d2b36b618bacb78297bc8b7b3c5b318c994fb0005ea83392', manifest)
    check(sha(signed) == 'e91e6a66f077fc2d59d6f682ccdf3125fa97889de1e7f583d715d5008bb656c7', signed)
    identity = json.loads(manifest.read_bytes())
    artifacts = json.loads(signed.read_bytes())
    check(identity['commit'] == SOURCE and artifacts['release'] == RELEASE, 'frozen build')
    hashes = {}
    for name, expected in identity['files'].items():
        path = REPO / name
        hashes[str(path)] = sha(path)
        check(hashes[str(path)] == expected, str(path))
    for path in modpaths:
        expected = [row['signed_sha256'] for row in artifacts['modules'] if row['path'] == str(path)]
        hashes[str(path)] = sha(path)
        check(expected == [hashes[str(path)]], str(path))
    for name, key in [('.config', 'config_sha256'), ('arch/x86/boot/bzImage', 'kernel_sha256')]:
        path = ROOT / 'main-final-out' / name
        hashes[str(path)] = sha(path)
        check(hashes[str(path)] == artifacts[key], str(path))
    hashes[str(manifest)] = sha(manifest)
    hashes[str(signed)] = sha(signed)
    hashes[str(Path(__file__).resolve())] = sha(__file__)
    save('verified-inputs.json', hashes)

def symbol_rows():
    result = {}
    for line in read('/proc/kallsyms').splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] in ('[kd_bench]', '[' + TC + ']'):
            result[(parts[2], parts[3][1:-1])] = parts[0]
    return result

def validate_route():
    symbols = symbol_rows()
    required = [(sym, TC) for sym in ('komb_mutex_lock', 'komb_mutex_unlock',
                                      'tc_mutex_worker_register', 'tc_mutex_workers_drain')]
    required += [(sym, 'kd_bench') for sym in ('t_mutex', 'tmutex_w', 'kmutex_w', 'nmutex_w', 'kmix_mix')]
    found = {f'{mod}:{sym}': symbols.get((sym, mod)) for sym, mod in required}
    check(all(value and int(value, 16) for value in found.values()), found)
    check(int(read(TC_PARAM / 'target_lock'), 0) == 0, 'mutex diagnostic target in use')
    addr = int(found['kd_bench:t_mutex'], 16)
    (TC_PARAM / 'target_lock').write_text(hex(addr))
    global bound
    bound = True
    check(int(read(TC_PARAM / 'target_lock'), 0) == addr, 'mutex diagnostic target failed')
    idle()
    found['clobber_fixture_address'] = symbols.get(('kmutex_cl_w', 'kd_bench'))
    found['batch_size'] = read(TC_PARAM / 'komb_batch_size')
    found['target_lock'] = hex(addr)
    save('mutex-provider.json', found)
    return found

def clean():
    errors = []
    def attempt(context, operation):
        try:
            operation()
            return True
        except Exception as exc:
            errors.append([context, repr(exc)])
            return False
    def stop_daemon():
        if daemon.poll() is None:
            daemon.send_signal(signal.SIGINT)
        check(daemon.wait(timeout=30) == 0, 'daemon exit')
        check(nano.kd_stats().get('delegation') == 0, 'delegation still active')
    if daemon is not None:
        attempt('stop daemon', stop_daemon)
    if dlog is not None:
        dlog.close()
    if fd is not None:
        os.close(fd)
    if initial_params is not None and read(THRESHOLD) != initial_params['kd_deleg_enter_sleep']:
        attempt('restore threshold', lambda: THRESHOLD.write_text(initial_params['kd_deleg_enter_sleep']))
    safe = attempt('verify quiescence', idle) and (daemon is None or daemon.poll() is not None)
    if safe and bound:
        def clear_target():
            (TC_PARAM / 'target_lock').write_text('0')
            check(int(read(TC_PARAM / 'target_lock'), 0) == 0, 'target still set')
        safe = attempt('clear diagnostic target', clear_target)
    unloaded = []
    if safe:
        for mod in reversed(loaded):
            if not attempt('rmmod ' + mod, lambda: saved_cmd('rmmod-' + mod + '.txt', ['rmmod', mod])):
                break
            unloaded.append(mod)
    final = dict(boot_id=read(BOOT_PATH), modules=sorted(modules()), unloaded=unloaded,
                 initial_params=initial_params, final_params={p: read(PARAM / p) for p in DEFAULTS},
                 taint=read('/proc/sys/kernel/tainted'), daemon_rc=daemon.returncode if daemon else None,
                 cleanup_errors=errors)
    attempt('kernel messages', lambda: warn_check(saved_cmd('dmesg-after.txt', ['dmesg'])))
    if initial_modules is not None:
        attempt('modules restored', lambda: check(initial_modules == modules(), ('modules', modules())))
    if initial_params is not None:
        attempt('parameters restored', lambda: check(initial_params == final['final_params'], final))
    attempt('boot unchanged', lambda: check(final['boot_id'] == BOOT, final['boot_id']))
    attempt('taint unchanged', lambda: check(final['taint'] == initial_taint, final['taint']))
    if 'nano' in globals():
        save('stats-after.json', nano.kd_stats())
    save('cleanup.json', final)
    return errors

check(platform.release() == RELEASE and read(BOOT_PATH) == BOOT, 'requires frozen kernel and boot')
check(read('/sys/class/block/vda/serial') == 'kd16-root' and
      read('/sys/class/block/vdb/serial') == 'kd16-builds-current', 'guest disks')
os.sched_setaffinity(0, {38, 39})
check(os.sched_getaffinity(0) == {38, 39}, 'controller affinity')
E.mkdir(exist_ok=False)
os.environ['PYTHONPATH'] = str(ROOT / 'python')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
modpaths = [REPO / 'local-tclock' / family / (mod + '.ko') for family, mod in MODULES.items()]
modpaths.append(REPO / 'bench/kd_bench.ko')
loaded, bound = [], False
fd = daemon = dlog = initial_params = initial_modules = None
initial_taint = read('/proc/sys/kernel/tainted')
start = time.time()
failure = None
with (E / 'points.jsonl').open('x', buffering=1) as log:
    try:
        checked_inputs()
        sys.path.insert(0, str(REPO / 'bench'))
        import run_nano as nano
        initial_modules = modules()
        check(initial_modules <= {'nls_iso8859_1'} and initial_taint in ('0', '4096'), initial_modules)
        check(read('/sys/kernel/debug/tracing/current_tracer') == 'nop', 'tracing active')
        check(read('/sys/kernel/debug/sched/preempt') == 'full (lazy)', 'preemption')
        check(read('/sys/devices/system/cpu/online') == '0-39', 'online CPUs')
        check(read('/sys/devices/system/node/node0/cpulist') == '0-19' and
              read('/sys/devices/system/node/node1/cpulist') == '20-39', 'NUMA topology')
        initial_params = {p: read(PARAM / p) for p in DEFAULTS}
        check(initial_params == DEFAULTS, initial_params)
        check(nano.kd_stats().get('delegation') == 0, 'delegation already enabled')
        save('identity.json', dict(source=SOURCE, boot_id=BOOT, kernel=RELEASE, build=platform.version(),
                                   cpus=sorted(os.sched_getaffinity(0)), parameters=initial_params,
                                   initial_modules=sorted(initial_modules), taint=initial_taint,
                                   preemption='full (lazy)', tracer='nop', start=start,
                                   compact_entry=False, post=256, standard_workers=STANDARD_WORKERS,
                                   tuning_workers=TUNING_WORKERS, thresholds=[2,3,5]))
        saved_cmd('topology.txt', ['lscpu', '-e'])
        warn_check(saved_cmd('dmesg-before.txt', ['dmesg']))
        for path in modpaths:
            saved_cmd('insmod-' + path.stem + '.txt', ['insmod', str(path)])
            loaded.append(path.stem)
        found = validate_route()
        fd = os.open('/dev/kdbench', os.O_RDWR)
        failures = fcntl.ioctl(fd, nano.IOC_APITEST)
        save('api.json', {'failed_checks': failures})
        check(failures == 0, 'API checks failed')
        dry_funcs = ['kmutex_w', 'kmix_mix']
        if found['clobber_fixture_address']:
            dry_funcs.append('kmutex_cl_w')
        dry = saved_cmd('dryrun.txt', [sys.executable, str(REPO / 'jit/kd_dryrun.py'), *dry_funcs, '--disasm'])
        for func in dry_funcs:
            check(re.search(r'^' + func + r' site .*: [1-9]\d* insns, [1-9]\d* bytes', dry, re.M),
                  ('missing translated site', func))
        dlog = (E / 'daemon.log').open('x')
        daemon = subprocess.Popen([sys.executable, '-u', str(REPO / 'jit/kd_daemon.py'),
                                   '--state', str(E / 'learned.json'), '-v'], stdout=dlog,
                                  stderr=subprocess.STDOUT)
        (E / 'daemon.pid').write_text(str(daemon.pid))
        for _ in range(80):
            if nano.kd_stats().get('delegation') == 1:
                break
            check(daemon.poll() is None, 'daemon start failed')
            time.sleep(.1)
        progress('learning')
        learned = []
        for attempt in range(8):
            result = checked_point('learning', 'kd', 32, 1, 600, attempt, 'default')
            learned.append(result['kd_delta']['delegated'])
            if learned[-1]:
                break
        save('learning.json', {'delegated_by_attempt': learned})
        # A zero-delegation run remains measurable; the reason and counts travel with the data.
        paired_grid('three-way', STANDARD_WORKERS, [('native',3), ('kd',3), ('tclock',3)])
        paired_grid('threshold', TUNING_WORKERS,
                    [('native',3), ('kd',2), ('tclock',3), ('kd',5), ('kd',3)])
        THRESHOLD.write_text('3')
        save('measurements-complete.json', {'finish': time.time(), 'standard_rows': 162, 'threshold_rows': 120})
        progress('mutex functional checks')
        evidence = {}
        for family in ('mutex_cl', 'mix'):
            checked_point('functional-control', 'native', 8, 1, 400, 0, 'default', family)
            rows = []
            for rnd, w in enumerate((8, 32, 32, 32)):
                row = checked_point('functional-kd', 'kd', w, 1, 750, rnd, 'default', family)
                rows.append(row['execution_counts'])
                if w == 32 and (row['kd_delta']['handback'] if family == 'mix' else row['kd_delta']['delegated']):
                    break
            evidence[family] = rows
            save('checks.json', evidence)
        check(all(r['cl_offered'] == r['cl_done'] == 0 for r in evidence['mutex_cl']),
              'unexpected compact-state activity on frozen config')
        progress('cleanup')
    except BaseException:
        failure = traceback.format_exc()
        print(failure, file=sys.stderr, flush=True)
    finally:
        cleanup_errors = clean()
        receipt = dict(status='failed' if failure or cleanup_errors else 'completed',
                       error=failure, cleanup_errors=cleanup_errors, start=start, finish=time.time(),
                       boot_id=read(BOOT_PATH))
        save('result.json', receipt)
        print('KDMAIN_MUTEX_RESULT ' + json.dumps(receipt), flush=True)
sys.exit(0 if receipt['status'] == 'completed' else 1)
