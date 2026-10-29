#!/usr/bin/env python3
"""Guest-only original-body syscall comparison with immutable object binding."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'bench/mmap_fault'))
import timing as common
rt, identity, platform = common.rt, common.kernel_identity, common.mm_platform
from bench_session import Session
from provider.prepare import prepare as prepare_provider
WORKERS = tuple(range(1, 9))+tuple(range(12, 61, 4))
CASES = {'setfd': ('toggle', 1, 1), 'pipebytes': ('query', 16, 2),
         'pipecap': ('query', 16, 3)}
PARAM = Path('/sys/module/kdlock_km/parameters')


def plan(functional=False):
    return [dict(name=f'{kind}-{arm}-n{n:02d}-r00', kind=kind, arm=arm,
                 cpus=list(range(n)), workers=n, round=0, collector_cpu=63,
                 duration_ms=2000, query=CASES[kind][0], entries=CASES[kind][1],
                 site=CASES[kind][2], instrumentation='completion' if functional else 'none')
            for kind in CASES for n in ((16,) if functional else WORKERS)
            for arm in ('native', 'kd')]


def source_files():
    result = {}
    for directory in ('include', 'kernel_module', 'daemon', 'disassem',
                      'bench/kernel_api', 'bench/real_api', 'bench/spin_cacheline',
                      'bench/tclock_compare/allocator_guard', 'bench/mmap_fault',
                      'bench/mmap_writer', 'bench/basic', 'kernel_baseline',
                      'kernel_integration', 'tests/protocols'):
        for path in (ROOT/directory).rglob('*'):
            relative = path.relative_to(ROOT)
            if (path.is_file() and not any(p.startswith('.') or p == '__pycache__' for p in relative.parts)
                    and not path.name.endswith('.mod.c') and
                    (path.suffix in ('.py', '.c', '.h', '.inc', '.S', '.def', '.json', '.patch', '.md') or
                     path.name in ('Makefile', 'requirements.txt', 'guest.config'))):
                result[str(relative)] = rt.digest(path)
    # Only the shared client control header; no copied-body workload is built.
    name = 'workload_modules/real_api/control.h'
    result[name] = rt.digest(ROOT/name)
    return result


def verify_files(files):
    for path, digest in files.items():
        rt.require(rt.digest(Path(path)) == digest, 'frozen input changed: '+path)


def build(out, args):
    source = out/'source'
    hashes = source_files()
    files = {}
    for name, expected in hashes.items():
        dest = source/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, dest)
        rt.require(rt.digest(dest) == expected, 'source copy differs')
        files[str(ROOT/name)] = files[str(dest)] = expected
    rt.write_json(out/'source-sha256.json', hashes)
    prepare_provider(out/'build/provider', source)
    provider = out/'build/provider/kernel_module/kdlock_km.ko'
    rt.command(['make', '-C', provider.parent, 'KDIR='+str(args.kernel_source), 'W=1',
                'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024',
                'KDLOCK_MUTEX_BATCH=1024', 'KDLOCK_MUTEX_NUMA_BOUNDARY=1024',
                'KDLOCK_MUTEX_DIAGNOSTICS=0', 'UBSAN_SANITIZE=n'], out/'build-provider.log', timeout=300)
    rt.command(['make', '-C', source/'daemon'], out/'build-daemon.log', timeout=120)
    rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-std=gnu11', '-pthread',
                source/'bench/real_api/client.c', '-o', out/'build/client'], out/'build-client.log', timeout=60)
    guard = source/'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'
    rt.command(['make', '-C', guard.parent, 'KDIR='+str(args.kernel_source)], out/'build-guard.log', timeout=120)
    binaries = dict(provider=provider, daemon=source/'daemon/daemon', client=out/'build/client', guard=guard)
    for path in binaries.values():
        files[str(path)] = rt.digest(path)
    rt.require('kd_api_register_provider' in rt.command(['nm', '-u', provider], out/'provider-imports.log'),
               'provider was not built against enabled API binding')
    rt.write_json(out/'binaries.json', {k:dict(path=str(v), sha256=files[str(v)]) for k,v in binaries.items()})
    verify_files(files)
    return binaries, files


def validate_phase(row, spec, timed):
    workers = row.get('workers', [])
    rt.require(row.get('ok') is True and row.get('phase') == ('measure' if timed else 'warmup') and
               [w['cpu'] for w in workers] == spec['cpus'] and
               row['completed'] == sum(w['completed'] for w in workers) and
               row['collector_cpu'] == row['collector_observed_cpu'] == 63 and not row['collector_error'],
               'syscall effects, operation count or collector affinity differs')
    rt.require(all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] > 0 and
                   row['started_ns'] <= w['active_started_ns'] <= w['finished_ns'] and w['finished_ns'] >= row['deadline_ns']
                   for w in workers), 'worker progress, placement or interval differs')
    rt.require(row['finished_ns'] == max(w['finished_ns'] for w in workers) and
               row['wall_ns'] == row['finished_ns']-row['started_ns'] and
               row['duration_ns'] == (2_000_000_000 if timed else 1_000_000_000) and
               row['deadline_ns'] == row['started_ns']+row['duration_ns'], 'phase timing conservation failed')
    return row['completed']*1e9/row['wall_ns']


def validate_functional(previous):
    expected = plan(True)
    rows = previous.get('sessions', [])
    rt.require(len(rows) == len(expected), 'functional session set incomplete')
    for row, spec in zip(rows, expected):
        rt.require(all(row.get(key) == value for key, value in spec.items()) and
                   row.get('passed') is True and row.get('drained') is True and
                   row.get('execution_status') == 'COMPLETE' and
                   row.get('retired') == dict(state=2, modules=0, frames=0, writers=0),
                   'functional session identity or drain differs')
        warmups = row.get('warmups', [])
        rt.require(bool(warmups), 'functional warmups missing')
        calculated = {key:sum(w['after'][counter]-w['before'][counter] for w in warmups)
                      for key,counter in (('entered','bench_jit_bodies'),('returned','bench_jit_completions'))}
        observation = row.get('functional_jit', {})
        rt.require(observation == calculated, 'functional counter conservation failed')
        entered, returned = observation.get('entered'), observation.get('returned')
        rt.require(type(entered) is int and entered == returned and
                   (entered > 0 if spec['arm'] == 'kd' else entered == 0),
                   'functional returned-body observation missing')
        binding = row.get('binding', {})
        rt.require(binding.get('backend') == int(spec['arm'] == 'kd') and
                   binding.get('kind') == (1 if spec['kind'] == 'setfd' else 2) and
                   binding.get('lock') and binding.get('object') and
                   bool(binding.get('provider')) == (spec['arm'] == 'kd'),
                   'functional object binding differs')


class BoundSession(Session):
    def __init__(self, out, spec, binaries, verify, functional):
        super().__init__(out, spec)
        self.out, self.binaries, self.verify, self.functional = out, binaries, verify, functional
        self.translation_source = out/'source'
        self.daemon_binary = binaries['daemon']
        self.client = None

    def reply(self, label, timeout=120):
        deadline, data = time.monotonic()+timeout, bytearray()
        while True:
            left = deadline-time.monotonic()
            if left <= 0 or not select.select([self.client.stdout], [], [], left)[0]:
                raise rt.Failure('TIMEOUT', 'client lifetime unknown at '+label, unsafe=True)
            piece = os.read(self.client.stdout.fileno(), 65536)
            if not piece:
                raise rt.Failure('CLIENT_FAILED', 'missing joined reply at '+label, unsafe=True)
            data.extend(piece)
            if data.endswith(b'\n'):
                break
        (self.path/(label+'.json')).write_bytes(data)
        self.faults()
        return json.loads(data)

    def tell(self, action, label=None):
        self.client.stdin.write((action+'\n').encode())
        self.client.stdin.flush()
        return self.reply(label or action)

    def start_daemon(self):
        workspace = self.path/'workspace'
        (workspace/'daemon').mkdir(parents=True)
        for directory in ('disassem','include'):
            (workspace/directory).symlink_to(self.translation_source/directory, target_is_directory=True)
        self.daemon_log = (self.path/'daemon.log').open('w')
        env = dict(os.environ, KD_JIT_BODY_WITNESS=str(int(self.functional)))
        env.pop('KD_DEVICE_FD',None)
        self.daemon = subprocess.Popen([self.daemon_binary,'--quiet','--metrics','--mode','per-tgid'],
            cwd=workspace/'daemon',env=env,stdout=self.daemon_log,stderr=subprocess.STDOUT,start_new_session=True)
        self.record['daemon_pid'] = self.daemon.pid
        self.save()

    def counts(self, label=None):
        return {name:int((PARAM/name).read_text()) for name in ('bench_jit_bodies','bench_jit_completions')}

    def published(self):
        rows = rt.registry()
        expected = self.record['binding']['entries']
        rt.require(len(rows) == 3 and {r['entry'] for r in rows} == set(expected) and
                   all(r['status'] == 0 and r['code'] and r['pid'] == 0 and
                       r['entry_abi'] == (1 if r['entry'] == expected[0] else 2) and
                       r['lock_kind'] == (1 if r['entry'] == expected[0] else 2) for r in rows),
                   'exact original-body entries are not all NORMAL')
        files = sorted((self.path/'workspace').rglob('jit.bin'))
        rt.require(len(files) == 3, 'missing or extra emitted images')
        return dict(registry=rows, images={str(p.relative_to(self.path)):rt.digest(p) for p in files})

    def prepare(self):
        self.verify()
        self.run(['insmod', self.binaries['guard']], 'load-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-guard.log')
        # The same prepared provider is used by both arms. Native objects
        # never call it, but setup/query control and parameters stay matched.
        self.run(['insmod', self.binaries['provider'], 'bench_quiet=1',
                  'bench_complete_probe='+str(int(self.functional)), 'jit_timing=0',
                  'hotlock_stats=0', 'target_process=sc_worker'], 'load-provider.log')
        self.loaded_kd = True
        s = self.record
        argv = list(map(str, [self.binaries['client'], s['kind'], s['query'], s['entries'], 64,
               ','.join(map(str,s['cpus'])), 63, 2000, 48000, 1000, s['arm']]))
        self.client_log = (self.path/'client.stderr').open('w')
        self.client = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=self.client_log, start_new_session=True, bufsize=0)
        s.update(client_command=argv, client_pid=self.client.pid)
        self.save()
        ready = self.reply('ready')
        binding = ready.get('binding', {})
        rt.require(ready.get('ready') is True and ready['pid'] == self.client.pid and
                   binding.get('version') == 1 and binding.get('kind') == (1 if s['kind'] == 'setfd' else 2) and
                   binding.get('backend') == int(s['arm'] == 'kd') and binding.get('object') and
                   binding.get('lock') and bool(binding.get('provider')) == (s['arm'] == 'kd') and
                   len(set(binding.get('entries', []))) == 3 and all(binding['entries']), 'object binding differs')
        s['binding'] = binding
        if self.functional:
            (PARAM/'bench_lock_addr').write_text(str(binding['lock'])+'\n')
        rt.require(int((PARAM/'bench_lock_addr').read_text(),0) == (binding['lock'] if self.functional else 0) and
                   (PARAM/'bench_complete_probe').read_text().strip() == ('Y' if self.functional else 'N') and
                   (PARAM/'jit_timing').read_text().strip() == 'N' and
                   (PARAM/'hotlock_stats').read_text().strip() == 'N', 'observation parameters differ')
        rt.require(self.tell('check')['check'], 'preparation syscall oracle failed')
        # Source images are prepared once per fresh provider session. Each
        # invocation remains unscored until its joined warmup and ready image.
        self.start_daemon()
        s['warmups'] = []
        for wave in range(4):
            deadline = time.monotonic()+120
            while True:
                self.faults()
                rt.require(self.daemon.poll() is None, 'translator daemon exited')
                log = (self.path/'daemon.log').read_text()
                rt.require(not re.search(r'\[KD_JIT\]\[ERROR\]|Traceback|command failed', log), 'translation failed')
                if all(row['status'] == 0 for row in rt.registry()) and not rt.children(self.daemon.pid):
                    break
                rt.require(time.monotonic() < deadline, 'translation publication timeout')
                time.sleep(.1)
            before = self.counts()
            warm = self.tell('warmup', f'warmup-{wave}')
            validate_phase(warm, s, False)
            after = self.counts()
            s['warmups'].append(dict(completed=warm['completed'], before=before, after=after))
            self.save()
            if all(row['status'] == 0 for row in rt.registry()) and not rt.children(self.daemon.pid):
                break
        else:
            raise rt.Failure('PREPARATION_FAILED', 'bounded helper preparation exhausted')
        self.stop_daemon()
        s['publication'] = self.published()
        rt.require(rt.status()['frames'] == rt.status()['writers'] == 0, 'preparation has active frames/writers')
        if self.functional:
            entered = sum(w['after']['bench_jit_bodies']-w['before']['bench_jit_bodies'] for w in s['warmups'])
            returned = sum(w['after']['bench_jit_completions']-w['before']['bench_jit_completions'] for w in s['warmups'])
            rt.require(entered == returned and (entered > 0 if s['arm'] == 'kd' else entered == 0),
                       'functional returned-body observation failed')
            s['functional_jit'] = dict(entered=entered, returned=returned)
        s['parameters'] = rt.parameters()
        self.verify()
        self.save()

    def measure(self):
        self.record['execution_status'] = 'MEASURING'
        self.save()
        before = self.counts()
        row = self.tell('measure')
        score = validate_phase(row, self.record, True)
        rt.require(before == self.counts(), 'scored path unexpectedly enabled body observations')
        rt.require(self.published() == self.record['publication'], 'image changed during scored interval')
        self.record.update(measurement=row, whole_throughput_ops_s=score,
                           jit_execution='not-observed-in-scored-session')
        rt.require(self.tell('check', 'check-after')['check'], 'post-measurement syscall oracle failed')
        self.verify()
        self.save()

    def cleanup(self):
        self.faults()
        # Joined replies precede normal process exit. Bound objects retain
        # their provider references until real file-table/pipe destruction.
        self.client.stdin.write(b'quit\n')
        self.client.stdin.close()
        try:
            code = self.client.wait(timeout=30)
        except subprocess.TimeoutExpired as error:
            raise rt.Failure('UNDRAINED', 'client did not exit normally', unsafe=True) from error
        rt.require(code == 0, 'client exit failed')
        self.client.stdout.close()
        self.client_log.close()
        self.client = None
        self.stop_daemon()
        deadline = time.monotonic()+10
        while int(Path('/sys/module/kdlock_km/refcnt').read_text()) != 0:
            rt.require(time.monotonic() < deadline, 'bound object/device references remain', 'UNDRAINED')
            time.sleep(.01)
        rt.require(rt.status()['frames'] == rt.status()['writers'] == 0, 'frames/writers remain', 'UNDRAINED')
        fd = os.open('/dev/kd_dev', os.O_RDONLY|os.O_CLOEXEC)
        try:
            fcntl.ioctl(fd, rt.RETIRE)
            self.record['retired'] = rt.info(fd)
        finally:
            os.close(fd)
        rt.require(self.record['retired'] == dict(state=2,modules=0,frames=0,writers=0), 'retirement incomplete')
        self.run(['rmmod','kdlock_km'], 'unload-provider.log')
        self.loaded_kd = False
        self.faults()
        self.record.update(drained=True, execution_status='COMPLETE', passed=True)
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('functional','measure'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--functional-result', type=Path)
    platform.arguments(parser)
    identity.arguments(parser)
    args = parser.parse_args()
    rt.require(args.kernel_variant == 'kdscope1-native', 'reviewed enabled-API kernel in Native MM mode required')
    platform.guest(args.boot_id, release='7.0.0-38-kdscope1')
    rt.idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    result = dict(schema=1, action=args.action, passed=False, drained=False, accepted=False,
                  boot_id=args.boot_id, single_round=True, host_endpoint='PENDING', sessions=[])
    try:
        result['host'] = common.host_check(args.host_state, out, True, args.boot_id,
                                          reference=args.host_reference, reference_sha256=args.host_reference_sha256)
        result['kernel_identity'] = identity.capture(args, out, rt.command)
        rt.require(result['kernel_identity'].get('schema') == 2 and
                   result['kernel_identity'].get('runtime_policy_verified') is True, 'verified running schema2 required')
        if args.action == 'measure':
            rt.require(args.functional_result is not None, 'functional evidence required')
            previous = json.loads(args.functional_result.read_text())
            rt.require(previous.get('passed') is True and previous.get('drained') is True and
                       previous.get('action') == 'functional' and previous.get('boot_id') == args.boot_id and
                       previous.get('kernel_identity') == result['kernel_identity'], 'functional identity differs')
            validate_functional(previous)
            rt.require(previous.get('source_sha256') == source_files(),
                       'functional source generation differs')
            verify_files(previous['files'])
            files = dict(previous['files'])
            source = out/'source'
            for name, digest in previous['source_sha256'].items():
                dest = source/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,dest)
                files[str(dest)] = digest
            rt.write_json(out/'source-sha256.json',previous['source_sha256'])
            binary_data = json.loads((args.functional_result.parent/'binaries.json').read_text())
            rt.require(set(binary_data) == {'provider','daemon','client','guard'}, 'prepared binary set differs')
            binaries = {key:Path(value['path']) for key,value in binary_data.items()}
            rt.require(all(previous['files'].get(value['path']) == value['sha256']
                           for value in binary_data.values()), 'unbound prepared binary')
            files[str((args.functional_result.parent/'binaries.json').resolve())] = rt.digest(args.functional_result.parent/'binaries.json')
            files[str(args.functional_result.resolve())] = rt.digest(args.functional_result)
            rt.write_json(out/'binaries.json',binary_data)
        else:
            binaries, files = build(out,args)
        def verify():
            platform.guest(args.boot_id, release='7.0.0-38-kdscope1')
            policy = result['kernel_identity']['runtime_policy']
            rt.require(Path('/proc/cmdline').read_text().strip() == policy['cmdline'] and
                       Path('/sys/kernel/debug/sched/preempt').read_text().strip() == policy['preempt_control'],
                       'running command line/preemption policy changed')
            verify_files(files)
        result['files'] = files
        result['source_sha256'] = json.loads((out/'source-sha256.json').read_text())
        work = plan(args.action == 'functional')
        rt.write_json(out/'plan.json',work)
        rt.write_json(out/'result.json',result)
        for spec in work:
            rt.idle()
            print('START',spec['name'],flush=True)
            session = BoundSession(out,spec,binaries,verify,args.action == 'functional')
            try:
                session.prepare()
                if args.action == 'measure': session.measure()
                session.cleanup()
                result['sessions'].append(session.record)
                for receipt in session.path.glob('*.json'):
                    files[str(receipt)] = rt.digest(receipt)
            except BaseException as error:
                session.record.update(execution_status='FAILED',passed=False,error=repr(error))
                session.save()
                raise
            finally:
                os.close(session.kmsg)
            rt.write_json(out/'result.json',result)
            print('FINISH',spec['name'],flush=True)
        verify()
        rt.idle()
        result.update(passed=True,drained=True,final_idle=True)
    except BaseException as error:
        result.update(passed=False,error=repr(error))
        raise
    finally:
        rt.write_json(out/'result.json',result)


if __name__ == '__main__':
    main()
