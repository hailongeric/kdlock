#!/usr/bin/env python3
"""Matched real-syscall comparison, run only in the recorded recovery guest."""
import argparse
import fcntl
import itertools
import json
import os
from pathlib import Path
import re
import select
import signal
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
from bench_runtime import (Failure, require, command, digest, idle, registry,
                           status, children, PROVIDER, RETIRE, info, parameters)
from bench_session import Session
from peak import analyze_peak
from summarize import write_json
import kernel_identity
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
from context_audit import audit as audit_tclock

TC = ROOT / 'tclock_backend/tclock_backend_km.ko'
GUARD = ROOT / 'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'
PARAM = Path('/sys/module/real_api/parameters')
MUTEX_KINDS = {'pipebytes', 'pipecap', 'seek'}


def owned_mutex_parameters(spec):
    return dict(owned_mutex_spin_limit=spec['mutex_spin_limit'],
                owned_mutex_reuse_spins=spec['owned_mutex_reuse_spins'],
                owned_mutex_adaptive=int(spec.get('owned_mutex_adaptive', False)),
                owned_mutex_origin_spin=0, owned_mutex_numa=int(spec.get('owned_mutex_numa', False)),
                owned_mutex_self_route=0, owned_mutex_native_after_control=0,
                owned_mutex_refill=0, owned_mutex_preflight_spins=0,
                owned_mutex_preflight_queue=0)


def check_owned_mutex_parameters(params, spec):
    def number(value):
        return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value, 0)
    require(all(key in params and number(params[key]) == value
                for key, value in owned_mutex_parameters(spec).items()) and
            params.get('owned_mutex_protocol') ==
            ('contention_adaptive_v8' if spec.get('owned_mutex_adaptive', False) else 'linux_local_split_v1' if spec.get('owned_mutex_object_bytes', 32) == 128 else 'linux_local_first_v1'),
            'KD owned mutex parameters differ')


def audit_owned_mutex_imports(imported):
    symbols = set(imported.split())
    expected = {'kd_owned_mutex_prepare', 'kd_mutex_init', 'kd_owned_mutex_is_idle',
                'kd_owned_mutex_outer_lock_cabi_v2', 'kd_owned_mutex_outer_unlock_cabi_v2'}
    require(expected <= symbols and not symbols.intersection({
        'mutex_lock', 'mutex_unlock', '__mutex_lock_slowpath', '__mutex_unlock_slowpath',
        'kd_owned_mutex_outer_contended_clobber_v1', 'kd_owned_mutex_outer_unlock_v1'}),
        'API mutex caller does not exclusively use the owned ABI4 protocol')


def lock_kind(kind):
    return 'rwlock' if kind == 'utsname' else 'mutex' if kind in MUTEX_KINDS else 'spin'


def tc_name(family):
    return 'tclock_backend_km' if family == 'spin' else f'tclock_{family}_backend_km'


def sources():
    result = {}
    for folder in ('include', 'kernel_module', 'daemon', 'disassem', 'tclock_backend',
                   'bench/real_api', 'bench/spin_cacheline', 'bench/tclock_compare',
                   'workload_modules/real_api', 'kernel_baseline', 'tests/protocols'):
        for p in (ROOT / folder).rglob('*'):
            relative = p.relative_to(ROOT)
            if (p.is_file() and not any(s.startswith('.') or s == '__pycache__' for s in relative.parts)
                    and not p.name.endswith('.mod.c') and
                    (p.suffix in ('.c', '.h', '.inc', '.py', '.S', '.def', '.patch', '.json', '.md')
                     or p.name in ('Makefile', 'requirements.txt'))):
                result[str(relative)] = digest(p)
    return result


def build(out, args):
    build_dir = out / 'build'
    build_dir.mkdir()
    env = dict(os.environ, KDIR=args.kernel_source)
    if args.build_from:
        previous = args.build_from.resolve()
        require(json.loads((previous/'source-sha256.json').read_text()) == sources(),
                'source changed since --build-from')
        old = json.loads((previous/'binaries.json').read_text())
        for name, item in old.items():
            require(digest(Path(item['path'])) == item['sha256'], 'frozen binary changed: ' + name)
        # Each run keeps its own binary copy and hash record.
        shutil.copytree(previous/'build', build_dir, dirs_exist_ok=True)
    else:
        command(['make', '-C', ROOT/'bench/spin_cacheline', 'provider',
                 'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024', 'UBSAN_SANITIZE=n'],
                out/'build-kd.log', timeout=300, env=env)
        command(['make', '-C', ROOT/'daemon'], out/'build-daemon.log', timeout=120, env=env)
        for family in sorted({lock_kind(k) for k in args.kinds}):
            folder = build_dir/('tclock-'+family)
            shutil.copytree(out/'source/tclock_backend', folder)
            command(['make', '-C', folder, 'TCLOCK_NUMA=1',
                     f'TCLOCK_MUTEX={int(family == "mutex")}', f'TCLOCK_RWLOCK={int(family == "rwlock")}'],
                    out/f'build-tclock-{family}.log', timeout=180, env=env)
            shutil.copyfile(folder/(tc_name(family)+'.ko'), build_dir/(tc_name(family)+'.ko'))
        command(['make', '-C', ROOT/'bench/tclock_compare/allocator_guard'],
                out/'build-guard.log', timeout=120, env=env)
        command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-std=gnu11',
                 '-pthread', ROOT/'bench/real_api/client.c', '-o', build_dir/'client'],
                out/'build-client.log', timeout=60)
        for backend, kind in itertools.product(('native', 'tclock', 'kdlock'), args.kinds):
            dest = build_dir / (backend + '-' + kind)
            dest.mkdir()
            for name in ('module.c', 'mutex.c', 'uts.c', 'control.h', 'Makefile'):
                shutil.copyfile(ROOT/'workload_modules/real_api'/name, dest/name)
            tc_folder = build_dir/('tclock-'+lock_kind(kind))
            symvers = (PROVIDER.parent/'Module.symvers' if backend == 'kdlock' else tc_folder/'Module.symvers')
            cmd = ['make', '-C', dest, f'RB_BACKEND={backend}', f'RB_KIND={kind.upper()}',
                   f'KDLOCK_INCLUDE={ROOT}/include', f'TCLOCK_INCLUDE={tc_folder}/include']
            if backend != 'native':
                cmd += [f'KBUILD_EXTRA_SYMBOLS={symvers}']
            command(cmd, out/f'build-{backend}-{kind}.log', timeout=120, env=env)
            command(['objdump', '-dr', dest/'real_api.ko'],
                    dest/'assembly.txt', timeout=30)
        for name, p in (('kdlock_km.ko', PROVIDER),
                        ('tc_allocator_guard.ko', GUARD), ('daemon', ROOT/'daemon/daemon')):
            shutil.copyfile(p, build_dir/name)
            (build_dir/name).chmod(p.stat().st_mode)
    binaries = {str(p.relative_to(build_dir)): dict(path=str(p), sha256=digest(p))
                for p in build_dir.rglob('*') if p.is_file() and
                (p.suffix == '.ko' or p.name in ('client', 'daemon'))}
    write_json(out/'binaries.json', binaries)
    for family in sorted({lock_kind(k) for k in args.kinds}):
        tc_assembly = command(['objdump', '-dr', '--no-show-raw-insn',
                               build_dir/(tc_name(family)+'.ko')], out/f'tclock-{family}-assembly.txt')
        write_json(out/f'tclock-{family}-context-audit.json', audit_tclock(tc_assembly, family))
    metadata = {}
    for backend in ['kdlock_km'] + [tc_name(f) for f in sorted({lock_kind(k) for k in args.kinds})]:
        module = build_dir/(backend+'.ko')
        fields = (('spin_numa', 'spin_batch') if backend == 'kdlock_km' else
                  ('mutex_numa',) if 'mutex' in backend else
                  ('rwlock_numa',) if 'rwlock' in backend else ('spin_numa',))
        metadata[backend] = {}
        for field in fields:
            value = command(['modinfo', '-F', field, module], out/f'{backend}-{field}.txt').strip()
            require(value == ('1024' if field == 'spin_batch' else '1'), 'compiled configuration differs')
            metadata[backend][field] = value
    for name, binary in binaries.items():
        if name.endswith('.ko') and name != 'tc_allocator_guard.ko':
            imports = command(['nm', '-u', binary['path']],
                              out/('imports-'+name.replace('/', '-')+'.txt'))
            require('__ubsan_' not in imports, 'timed module still imports UBSAN: '+name)
            if name.startswith('kdlock-') and name.split('/')[0][7:] in MUTEX_KINDS:
                audit_owned_mutex_imports(imports)
                expected = dict(mutex_implementation='owned-v1',
                                owned_caller_policy='c_abi_v2', owned_entry_abi='4')
                for field, value in expected.items():
                    actual = command(['modinfo', '-F', field, Path(binary['path'])],
                                     out/(name.replace('/', '-')+'-'+field+'.txt')).strip()
                    require(actual == value, 'API mutex caller identity differs: '+field)
    write_json(out/'build-configuration.json', metadata)
    # Capture the exact real implementations, not just a moving upstream URL.
    for relative in ('fs/xattr.c', 'fs/locks.c', 'fs/file.c', 'fs/fcntl.c', 'fs/pipe.c',
                     'fs/read_write.c', 'mm/shmem.c', 'include/linux/pipe_fs_i.h', 'include/linux/fs.h',
                     'kernel/sys.c', 'kernel/utsname_sysctl.c', 'include/linux/utsname.h',
                     'include/linux/fdtable.h', 'include/linux/shmem_fs.h', 'include/linux/xattr.h'):
        p = out/'kernel-inputs'/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(args.kernel_source)/relative, p)
    write_json(out/'kernel-inputs-sha256.json',
               {str(p.relative_to(out/'kernel-inputs')): digest(p)
                for p in (out/'kernel-inputs').rglob('*') if p.is_file()})


class SyscallSession(Session):
    def __init__(self, out, spec):
        super().__init__(out, spec, workload_module=out/'build'/
                         (spec['arm']+'-'+spec['kind'])/'real_api.ko')
        self.out = out
        self.client = None
        self.loaded_tc = False
        self.tc_module = tc_name(spec['lock_kind'])
        self.tc_params = Path('/sys/module', self.tc_module, 'parameters')
        self.control_bound = False

    def start_daemon(self):
        workspace = self.path/'workspace'
        (workspace/'daemon').mkdir(parents=True)
        for directory in ('disassem', 'include'):
            (workspace/directory).symlink_to(self.out/'source'/directory, target_is_directory=True)
        self.daemon_log = (self.path/'daemon.log').open('w')
        env = dict(os.environ, KD_JIT_BODY_WITNESS='1')
        env.pop('KD_DEVICE_FD', None)
        self.daemon = subprocess.Popen([self.out/'build/daemon', '--quiet', '--metrics',
                                        '--mode', 'per-tgid'], cwd=workspace/'daemon', env=env,
                                       stdout=self.daemon_log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        self.record['daemon_pid'] = self.daemon.pid
        self.save()

    def client_reply(self, label, timeout=180):
        # Unbuffered binary pipes avoid select/text-buffer read-ahead races.
        deadline = time.monotonic() + timeout
        data = bytearray()
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.client.stdout], [], [], max(0, left))[0]:
                raise Failure('TIMEOUT', f'client PID {self.client.pid} did not finish {label}', unsafe=True)
            piece = os.read(self.client.stdout.fileno(), 65536)
            if not piece:
                raise Failure('CLIENT_FAILED', f'client exited during {label}; retain object/module for diagnosis', unsafe=True)
            data.extend(piece)
            if data.endswith(b'\n'):
                break
        (self.path/(label+'.json')).write_bytes(data)
        return json.loads(data)

    def tell(self, action, timeout=180, label=None):
        self.client.stdin.write((action+'\n').encode())
        self.client.stdin.flush()
        return self.client_reply(label or action, timeout)

    def pause_daemon(self):
        require(not children(self.daemon.pid), 'translator still active before learning wave', 'UNDRAINED')
        os.kill(self.daemon.pid, signal.SIGSTOP)
        deadline = time.monotonic()+5
        while True:
            state = Path(f'/proc/{self.daemon.pid}/status').read_text()
            if re.search(r'^State:\s+T', state, re.M):
                return
            require(time.monotonic() < deadline, 'daemon did not stop between learning waves')
            time.sleep(.01)

    def await_publication(self):
        deadline = time.monotonic()+90
        while True:
            self.faults()
            require(self.daemon.poll() is None, 'daemon exited')
            log = (self.path/'daemon.log').read_text()
            require(not re.search(r'\[KD_JIT\]\[ERROR\]|Traceback|command failed', log), 'JIT translation failed')
            metrics = [json.loads(line.split(' ', 1)[1]) for line in log.splitlines()
                       if line.startswith('KD_TRANSLATION_METRICS ')]
            require(all(m['result'] == 0 and m['status'] == 0 for m in metrics), 'JIT translation refused')
            reg = registry()
            if len(reg) == 1 and reg[0]['status'] == 0 and metrics and not children(self.daemon.pid):
                self.record['translation'] = metrics
                self.record['publication'] = self.publication()
                return
            if time.monotonic() >= deadline:
                raise Failure('TRANSLATION_TIMEOUT', 'no JIT publication after 90 seconds')
            time.sleep(.1)

    def prepare(self):
        s = self.record
        argv = [self.out/'build/client', s['kind'], s['query'], s['entries'], s['value_size'],
                ','.join(map(str, s['cpus'])), s['collector_cpu'], s['duration_ms'],
                s['warmup'], s['warmup_ms']]
        self.client_log = (self.path/'client.stderr').open('w')
        self.client = subprocess.Popen(list(map(str, argv)), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=self.client_log,
                                       start_new_session=True, bufsize=0)
        s['client_command'] = list(map(str, argv))
        s['client_pid'] = self.client.pid
        self.save()
        ready = self.client_reply('ready')
        require(ready['ready'] and ready['pid'] == self.client.pid, 'client setup failed')
        self.run(['insmod', self.out/'build/tc_allocator_guard.ko'], 'load-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-guard.log')
        if s['arm'] == 'kdlock':
            owned_params = ([f'{key}={value}' for key, value in owned_mutex_parameters(s).items()]
                            if s['lock_kind'] == 'mutex' else [])
            self.run(['insmod', self.out/'build/kdlock_km.ko', 'bench_quiet=1', 'jit_timing=0',
                      'hotlock_stats=1', 'target_process=sc_worker', 'spin_entry_ratio_limit=2',
                      'spin_prefetch=2', *owned_params], 'load-kd.log')
            self.loaded_kd = True
        if s['arm'] == 'tclock':
            self.run(['insmod', self.out/'build'/(self.tc_module+'.ko'), 'komb_batch_size=1024'], 'load-tc.log')
            self.loaded_tc = True
        if s['arm'] != 'stock':
            load = ['insmod', self.workload_module, 'target_path='+ready['path']]
            if s['kind'] in {'setfd', 'utsname'} | MUTEX_KINDS:
                load += ['target_pid='+str(ready['pid'])]
            if s['kind'] == 'utsname':
                load += ['domain='+str(int(s['query'] == 'domain'))]
            self.run(load, 'load-source.log')
            self.loaded_source = True
            if s['kind'] in MUTEX_KINDS:
                require(self.tell('bind')['bound'], 'client control bind failed')
                self.control_bound = True
            s['lock_addr'] = int((PARAM/'lock_addr').read_text())
            s['gate_addr'] = int((PARAM/'gate_addr').read_text()) if s['kind'] == 'utsname' else s['lock_addr']
            if self.loaded_tc:
                (self.tc_params/'target_lock').write_text(str(s['lock_addr']))
            if self.loaded_kd:
                Path('/sys/module/kdlock_km/parameters/bench_lock_addr').write_text(str(s['gate_addr']))
            (PARAM/'prepare').write_text('1')
        if self.loaded_kd:
            s['parameters'] = parameters()
            if s['lock_kind'] == 'mutex':
                check_owned_mutex_parameters(s['parameters'], s)
            sym = [line.split() for line in Path('/proc/kallsyms').read_text().splitlines()]
            begin = [int(v[0], 16) for v in sym if len(v) == 4 and v[2:] == ['rb_body', '[real_api]']]
            nm = self.run(['nm', '-S', self.workload_module], 'symbols.txt')
            sizes = [int(v[1], 16) for line in nm.splitlines()
                     if len(v := line.split()) == 4 and v[3] == 'rb_body']
            require(len(begin) == len(sizes) == 1, 'missing body symbol')
            s['entry_range'] = [begin[0], begin[0]+sizes[0]]
            self.start_daemon()
            self.await_publication()
            s['learning_waves'] = []
            # A helper miss is learned only after every caller has joined.
            # The stopped daemon cannot replace an image while workers use it.
            # A final equal-size warmup follows these preparation-only waves.
            if s['kind'] == 'xattr' and s['threads'] > 1 and s['helper_waves']:
                for wave in range(s['helper_waves']):
                    self.pause_daemon()
                    warm = self.tell('warmup', label=f'learning-{wave}')
                    require(warm['ok'], 'helper-learning syscall oracle failed', 'DATA_ERROR')
                    state = status()
                    require(state['frames'] == 0 and state['writers'] == 1,
                            'learning wave did not drain to the paused daemon lease', 'UNDRAINED')
                    reg = registry()
                    s['learning_waves'].append(reg)
                    os.kill(self.daemon.pid, signal.SIGCONT)
                    if len(reg) == 1 and reg[0]['status'] == 0:
                        break
                    self.await_publication()
                else:
                    require(len(reg) == 1 and reg[0]['status'] == 0, 'helper learning did not converge')
            self.stop_daemon()
        require(self.tell('check', label='check-before')['check'], 'redirected syscall result differs')
        warm = self.tell('warmup')
        require(warm['ok'] and len(warm['workers']) == s['threads'] and
                all(w['completed'] >= s['warmup'] and
                    w['finished_ns'] >= warm['started_ns'] + s['warmup_ms']*1000000
                    for w in warm['workers']), 'warmup failed')
        self.faults()
        self.save()

    def measure(self):
        s = self.record
        if self.loaded_kd:
            s['published_before'] = self.publication()
            require(s['published_before']['source']['writers'] == 0,
                    'translator writer remains before measurement', 'UNDRAINED')
        before = int((PARAM/'calls').read_text()) if self.loaded_source else 0
        jit = Path('/sys/module/kdlock_km/parameters/bench_jit_bodies')
        jbefore = int(jit.read_text()) if self.loaded_kd else 0
        if self.loaded_kd:
            s['mutex_wait_before'] = self.mutex_wait_stats()
        tc_delegated = self.tc_params/'delegated'
        tc_before = int(tc_delegated.read_text()) if self.loaded_tc and tc_delegated.exists() else None
        s['execution_status'] = 'MEASURING'
        self.save()
        m = self.tell('measure')
        s['measurement'] = m
        if self.loaded_kd:
            s['mutex_wait_after'] = self.mutex_wait_stats()
            s['mutex_wait_delta'] = {key: value - s['mutex_wait_before'][key]
                for key, value in s['mutex_wait_after'].items()}
        require(m['ok'] and m['completed'] == sum(w['completed'] for w in m['workers']) and
                all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] for w in m['workers']),
                'syscall result or affinity mismatch', 'DATA_ERROR')
        m['peak'] = analyze_peak(m, s)
        s['whole_throughput_ops_s'] = m['completed']*1e9/m['wall_ns']
        s['peak_throughput_ops_s'] = m['peak']['throughput_ops_s']
        s['redirected_calls'] = int((PARAM/'calls').read_text())-before if self.loaded_source else 0
        require(not self.loaded_source or s['redirected_calls'] == m['completed'],
                'not every measured syscall reached substituted critical section', 'DATA_ERROR')
        s['jit_bodies'] = int(jit.read_text())-jbefore if self.loaded_kd else 0
        require(0 <= s['jit_bodies'] <= m['completed'], 'invalid JIT count')
        if s['kind'] == 'utsname':
            require(m['reads'] + m['writes'] == m['completed'] and s['jit_bodies'] <= m['writes'],
                    'invalid rwlock operation/JIT accounting', 'DATA_ERROR')
        s['jit_eligible_operations'] = m['writes'] if s['kind'] == 'utsname' else m['completed']
        s['jit_share'] = s['jit_bodies']/s['jit_eligible_operations'] if s['jit_eligible_operations'] else 0
        s['jit_status'] = ('PASS' if s['jit_bodies'] else 'NO_JIT') if self.loaded_kd else 'NOT_APPLICABLE'
        s['registry_after'] = registry() if self.loaded_kd else []
        if self.loaded_kd:
            s['published_after'] = self.publication()
            require(s['published_before']['entry'] == s['published_after']['entry'] and
                    s['published_before']['images'] == s['published_after']['images'],
                    'published image changed during measurement', 'DATA_ERROR')
        s['tclock_delegation'] = (int(tc_delegated.read_text())-tc_before if tc_before is not None else
                                  'UNMEASURED' if self.loaded_tc else 'NOT_APPLICABLE')
        self.faults()
        require(self.tell('check', label='check-after')['check'], 'post-measurement data oracle failed')
        self.save()

    def cleanup(self):
        self.faults()
        # Only command replies after pthread_join permit this path. Timeouts
        # deliberately retain the client (and OFD owner), module and evidence.
        if self.loaded_source and (PARAM/'quiescent').exists():
            self.record['source_quiescent'] = (PARAM/'quiescent').read_text().strip() == '1'
            require(self.record['source_quiescent'], 'source reader/writer state still active', 'UNDRAINED')
        if self.loaded_tc:
            q = self.tc_params/'quiescent'
            require(q.read_text().strip() == '1', 'TCLock not quiescent', 'UNDRAINED')
            (self.tc_params/'target_lock').write_text('0')
        if self.control_bound:
            require(self.tell('unbind')['unbound'], 'client control unbind failed')
            self.control_bound = False
        if self.loaded_kd:
            if self.daemon is not None and self.daemon.poll() is None:
                os.kill(self.daemon.pid, signal.SIGCONT)
            self.stop_daemon()
            require(status()['frames'] == status()['writers'] == 0, 'KD still active', 'UNDRAINED')
            fd = os.open('/dev/kd_dev', os.O_RDONLY | os.O_CLOEXEC)
            try:
                fcntl.ioctl(fd, RETIRE)
                self.record['retired'] = info(fd)
            finally:
                os.close(fd)
            require(self.record['retired'] == dict(state=2, modules=0, frames=0, writers=0),
                    'KD retirement incomplete', 'UNDRAINED')
        if self.loaded_source:
            self.run(['rmmod', 'real_api'], 'unload-source.log')
            self.loaded_source = False
        if self.loaded_tc:
            self.run(['rmmod', self.tc_module], 'unload-tc.log')
            self.loaded_tc = False
        if self.loaded_kd:
            self.run(['rmmod', 'kdlock_km'], 'unload-kd.log')
            self.loaded_kd = False
        if self.client is not None:
            self.client.stdin.write(b'quit\n')
            self.client.stdin.close()
            try:
                result = self.client.wait(timeout=10)
            except subprocess.TimeoutExpired as error:
                raise Failure('UNDRAINED', 'client did not exit', unsafe=True) from error
            require(result == 0, 'client exit failed')
            self.client.stdout.close()
            self.client_log.close()
            self.client = None
        self.faults()
        self.record['drained'] = True


def worker_cpus(args):
    cpus = list(map(int, args.cpus.split(',')))
    require(len(set(cpus)) == len(cpus) and
            len(set(args.threads)) == len(args.threads) and
            0 < min(args.threads) <= max(args.threads) <= min(64, len(cpus)) and
            args.collector_cpu not in cpus[:max(args.threads)], 'invalid worker/collector CPUs')
    require(min(cpus) >= 0 and max(cpus) < 1024 and 0 <= args.collector_cpu < 1024,
            'CPU outside supported affinity mask')
    return cpus


def make_plan(args):
    cpus = worker_cpus(args)
    plan = []
    for kind, query, count, n, repeat in itertools.product(args.kinds, args.queries, args.entries, args.threads, range(args.repeats)):
        order = args.backends[repeat % len(args.backends):] + args.backends[:repeat % len(args.backends)]
        for arm in order:
            owned = arm == 'kdlock' and kind in MUTEX_KINDS
            plan.append(dict(name=f'{kind}-{query}-n{count}-t{n:02d}-r{repeat}-{arm}', kind=kind,
                query=query, entries=count, threads=n, repeat=repeat, arm=arm, value_size=args.value_size,
                cpus=cpus[:n], collector_cpu=args.collector_cpu, duration_ms=args.duration_ms,
                peak_window_ms=300, peak_settle_ms=300, sample_ms=10,
                warmup=args.warmup, warmup_ms=args.warmup_ms,
                helper_waves=args.helper_waves,
                syscalls_per_op=2 if kind == 'setfd' else 1,
                file_descriptions='per-worker' if kind in ('setfd', 'pipebytes', 'pipecap') else 'shared-query',
                lock_kind=lock_kind(kind),
                registry_lock_kind=3 if owned else 1 if arm == 'kdlock' else 0,
                entry_abi=(4 if owned else {'spin': 1, 'rwlock': 3}[lock_kind(kind)]
                           if arm == 'kdlock' else 0),
                caller_abi='clobber' if arm == 'kdlock' and not owned else 'c',
                mutex_implementation='owned-v1' if owned else 'not_applicable',
                mutex_wait_mode='blocking' if owned else 'not_applicable',
                mutex_spin_limit=getattr(args, 'mutex_spin_limit', 4096) if owned else 0,
                owned_mutex_reuse_spins=getattr(args, 'owned_mutex_reuse_spins', 32) if owned else 0,
                owned_mutex_adaptive=getattr(args, 'owned_mutex_adaptive', False) if owned else False,
                owned_mutex_object_bytes=128 if owned else None,
                owned_mutex_origin_spin=False,
                owned_mutex_numa=getattr(args, 'owned_mutex_numa', False) if owned else False))
    require(plan, 'no API sessions selected')
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build-from', type=Path)
    p.add_argument('--kinds', nargs='+', choices=['xattr', 'ofd', 'setfd', 'utsname', *sorted(MUTEX_KINDS)], default=['ofd'])
    p.add_argument('--queries', nargs='+', choices=['tail', 'miss', 'front', 'size', 'toggle', 'query', 'set', 'end', 'host', 'domain'], default=['tail'])
    p.add_argument('--entries', nargs='+', type=int, default=[16, 128])
    p.add_argument('--value-size', type=int, default=64)
    p.add_argument('--threads', nargs='+', type=int, default=[1, 8, 16, 32, 48, 60])
    p.add_argument('--cpus', default=','.join(map(str, range(63))))
    p.add_argument('--collector-cpu', type=int, default=63)
    p.add_argument('--backends', nargs='+', choices=['native', 'tclock', 'kdlock', 'stock'],
                   default=['native', 'tclock', 'kdlock'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--duration-ms', type=int, default=2000)
    p.add_argument('--warmup', type=int, default=48000)
    p.add_argument('--warmup-ms', type=int, default=1000)
    p.add_argument('--helper-waves', type=int, default=4)
    p.add_argument('--mutex-spin-limit', type=int, default=4096,
                   help='owned mutex result polling budget before blocking')
    p.add_argument('--owned-mutex-reuse-spins', type=int, choices=(0, 8, 32, 128), default=32,
                   help='owned ABI4 release reuse allowance')
    p.add_argument('--owned-mutex-adaptive', action='store_true',
                   help='offer owned ABI4 delegation when the OSQ is crowded')
    p.add_argument('--owned-mutex-numa', action='store_true',
                   help='prefer an eligible local delegate within the bounded FIFO window')
    p.add_argument('--kernel-source', default='/root/linux-6.1.159-kdclobber2')
    p.add_argument('--kernel-baseline', default='/root/kdlock-kernel-baselines/mutex-clobber2-20260919')
    args = p.parse_args()
    out = args.output.resolve()
    require(out != ROOT and ROOT not in out.parents and not out.exists(), 'output must be new and outside checkout')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'confirm a real current-topology monitor snapshot before live execution')
    idle()
    for name in ('real_api', 'tclock_backend_km', 'tclock_mutex_backend_km', 'tclock_rwlock_backend_km', 'tc_allocator_guard'):
        require(not Path('/sys/module', name).exists(), 'existing module: '+name)
    worker_cpus(args)
    require(args.repeats > 0 and 0 <= args.helper_waves <= 16, 'invalid repeat/helper configuration')
    require(0 <= args.mutex_spin_limit <= 1048576, 'invalid owned mutex result polling budget')
    require(1 <= min(args.entries) <= max(args.entries) <= 4096
            and 1 <= args.value_size <= 4096 and 700 <= args.duration_ms <= 10000
            and args.warmup > 0 and 0 <= args.warmup_ms <= 10000, 'invalid workload bounds')
    for kind, query in itertools.product(args.kinds, args.queries):
        allowed = {'setfd': {'toggle'}, 'seek': {'set', 'end'},
                   'pipebytes': {'query'}, 'pipecap': {'query'},
                   'utsname': {'host', 'domain'},
                   'ofd': {'tail', 'front', 'miss'}, 'xattr': {'tail', 'front', 'miss', 'size'}}
        require(query in allowed[kind], f'invalid query {query} for {kind}')
    if 'utsname' in args.kinds:
        require(max(args.entries) <= 100 and args.value_size == 64, 'UTS requires write percentages 1..100 and 64-byte names')
    require('nopvspin' in Path('/proc/cmdline').read_text().split(), 'nopvspin missing')
    out.mkdir(parents=True)
    command([sys.executable, ROOT/'bench/spin_cacheline/kernel_identity.py',
             '--kernel-source', args.kernel_source, '--kernel-baseline', args.kernel_baseline],
            out/'kernel-identity.json', timeout=120)
    command(['lscpu', '-J'], out/'lscpu.json')
    command(['lscpu', '-e=CPU,NODE,SOCKET,CORE,ONLINE'], out/'topology.txt')
    command(['dmesg'], out/'dmesg-before.txt')
    write_json(out/'environment.json', dict(snapshot=os.environ['KDLOCK_SNAPSHOT_TAG'],
        uname=list(os.uname()), cmdline=Path('/proc/cmdline').read_text().strip(),
        arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}))
    frozen = sources()
    for relative in frozen:
        target = out/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
    write_json(out/'source-sha256.json', frozen)
    build(out, args)
    require(sources() == frozen, 'source changed during build')
    plan = make_plan(args)
    write_json(out/'plan.json', plan)
    try:
        for i, spec in enumerate(plan):
            print(f'{i+1}/{len(plan)} {spec["name"]}', flush=True)
            session = SyscallSession(out, spec)
            session.execute()
            r = session.record
            print(f'  {r["whole_throughput_ops_s"]/1e6:.3f} M/s; peak {r["peak_throughput_ops_s"]/1e6:.3f}; JIT {r["jit_bodies"]}', flush=True)
    finally:
        records = [json.loads((out/s['name']/'session.json').read_text())
                   if (out/s['name']/'session.json').exists() else dict(s, execution_status='NOT_RUN', drained=False)
                   for s in plan]
        write_json(out/'records.json', records)
    require(sources() == frozen, 'source changed during measurements')
    command(['dmesg'], out/'dmesg-after.txt')
    print('All sessions completed and drained.', flush=True)


if __name__ == '__main__':
    main()
