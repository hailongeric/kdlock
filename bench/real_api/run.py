#!/usr/bin/env python3
"""Matched real-syscall comparison, run only in the recorded recovery guest."""
import argparse
import fcntl
import hashlib
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
                           status, children, PROVIDER, RETIRE, info)
from bench_session import Session
from peak import analyze_peak
from summarize import write_json
import kernel_identity
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
from context_audit import audit as audit_tclock
from mutex_api_audit import audit_public_entries
from evidence import helper_ready, jit_evidence

TC = ROOT / 'tclock_backend/tclock_backend_km.ko'
GUARD = ROOT / 'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'
PARAM = Path('/sys/module/real_api/parameters')
MUTEX_KINDS = {'pipebytes', 'pipecap', 'seek'}


def lock_kind(kind):
    return 'rwlock' if kind in ('utsname', 'xattr') else 'mutex' if kind in MUTEX_KINDS else 'spin'


def tc_name(family):
    return 'tclock_backend_km' if family == 'spin' else f'tclock_{family}_backend_km'


def source_parameters(spec, ready):
    arguments = ['target_path=' + ready['path']]
    if spec['kind'] in {'setfd', 'utsname', 'xattr'} | MUTEX_KINDS:
        arguments += ['target_pid=' + str(ready['pid'])]
    if spec['kind'] == 'utsname':
        arguments += ['domain=' + str(int(spec['query'] == 'domain'))]
    return arguments


def sources():
    result = {}
    for folder in ('include', 'kernel_module', 'daemon', 'disassem', 'tclock_backend',
                   'bench/real_api', 'bench/spin_cacheline', 'bench/tclock_compare',
                   'workload_modules/real_api', 'kernel_baseline',
                   'kernel_integration/linux70', 'tests/protocols'):
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
    env = dict(os.environ, KDIR=str(args.kernel_source))
    if args.build_from:
        previous = args.build_from.resolve()
        require(json.loads((previous/'source-sha256.json').read_text()) == sources(),
                'source changed since --build-from')
        previous_args = json.loads((previous/'environment.json').read_text())['arguments']
        require(previous_args.get('mutex_lock_offset') == args.mutex_lock_offset,
                'mutex placement changed since --build-from')
        require(previous_args.get('mutex_api', 'outer') == args.mutex_api,
                'mutex API changed since --build-from')
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
            for name in ('module.c', 'mutex.c', 'uts.c', 'xattr.c', 'control.h', 'Makefile'):
                shutil.copyfile(ROOT/'workload_modules/real_api'/name, dest/name)
            tc_folder = build_dir/('tclock-'+lock_kind(kind))
            symvers = (PROVIDER.parent/'Module.symvers' if backend == 'kdlock' else tc_folder/'Module.symvers')
            cmd = ['make', '-C', dest, f'RB_BACKEND={backend}', f'RB_KIND={kind.upper()}',
                   f'RB_MUTEX_API={args.mutex_api}',
                   f'KDLOCK_INCLUDE={ROOT}/include', f'TCLOCK_INCLUDE={tc_folder}/include']
            if backend == 'kdlock' and kind in MUTEX_KINDS and args.mutex_lock_offset is not None:
                cmd += [f'RB_MUTEX_LOCK_OFFSET={args.mutex_lock_offset}']
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
            if name == 'kdlock_km.ko' or (name.startswith('kdlock-') and any(k in name for k in MUTEX_KINDS)):
                require(not re.search(r'\bU (?:atomic_dec_and_mutex_lock|mutex\w*|__mutex\w*|kd_mutex_(?:lock|unlock)_clobber_v1|osq_lock|osq_unlock)\b', imports),
                        'KD-only module imports a Linux mutex API: '+name)
    write_json(out/'build-configuration.json', metadata)
    for kind in sorted(set(args.kinds) & MUTEX_KINDS):
        module = build_dir/('kdlock-'+kind)/'real_api.ko'
        compiled_api = command(['modinfo', '-F', 'kd_mutex_api', module],
                               out/f'kdlock-{kind}-mutex-api.txt').strip()
        require(compiled_api == args.mutex_api, 'compiled mutex API differs')
        if args.mutex_api == 'public':
            imports = command(['nm', '-u', module], out/f'kdlock-{kind}-public-imports.txt')
            require({'kd_mutex_direct_lock_clobber_v1',
                     'kd_mutex_direct_unlock_clobber_v1', 'kd_mutex_prepare'} <= set(imports.split()),
                    'public mutex caller is missing a DIRECT endpoint')
            require(not set(imports.split()) & {
                'kd_mutex_outer_contended_clobber_v1', 'kd_mutex_local_unlock',
                'kd_mutex_api_lock', 'kd_mutex_api_unlock'},
                'public mutex caller imports another call shell')
            write_json(out/f'kdlock-{kind}-public-entries.json',
                       audit_public_entries(module, {'rb_entry': 'rb_body'}))
    if args.mutex_lock_offset is not None:
        placement = {}
        for kind in args.kinds:
            module = build_dir/('kdlock-'+kind)/'real_api.ko'
            value = command(['modinfo', '-F', 'kd_mutex_lock_offset', module],
                            out/f'kdlock-{kind}-mutex-lock-offset.txt').strip()
            require(value == str(args.mutex_lock_offset), 'compiled mutex placement differs')
            placement[kind] = dict(offset=int(value), cache_line_bytes=64, storage_bytes=128)
        write_json(out/'mutex-lock-placement-build.json', placement)
    # Capture the exact real implementations, not just a moving upstream URL.
    kernel_source = kernel_identity.source_directory(Path(args.kernel_source),
                                                      Path(args.kernel_baseline))
    for relative in ('fs/xattr.c', 'fs/locks.c', 'fs/file.c', 'fs/fcntl.c', 'fs/pipe.c',
                     'fs/read_write.c', 'mm/shmem.c', 'include/linux/pipe_fs_i.h', 'include/linux/fs.h',
                     'kernel/sys.c', 'kernel/utsname_sysctl.c', 'include/linux/utsname.h',
                     'include/linux/fdtable.h', 'include/linux/shmem_fs.h', 'include/linux/xattr.h',
                     'include/linux/filelock.h'):
        p = out/'kernel-inputs'/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kernel_source/relative, p)
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

    def has_delegation_entry(self):
        # Linux 7 xattr lookup holds shared read ownership throughout its
        # native rb-tree search. KD readers run locally and publish no image.
        return self.record.get('kind') != 'xattr'

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
                require(not children(self.daemon.pid), 'translator raced daemon pause', 'UNDRAINED')
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
                publication = self.publication()
                self.record['publication'] = publication
                history = self.record.setdefault('publications', [])
                archive = self.path/'publications'/f'{len(history):02d}'
                archive.mkdir(parents=True)
                entry = publication['entry']
                folder = self.path/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
                for name in publication['images']:
                    shutil.copyfile(folder/name, archive/name)
                history.append(dict(path=str(archive.relative_to(self.path)), **publication))
                self.save()
                return
            if time.monotonic() >= deadline:
                raise Failure('TRANSLATION_TIMEOUT', 'no JIT publication after 90 seconds')
            time.sleep(.1)

    def learn_helpers(self):
        s = self.record
        counts = Path('/sys/module/kdlock_km/parameters')
        s['learning_waves'] = []
        for wave in range(s['helper_waves']):
            self.pause_daemon()
            before = int((counts/'bench_jit_bodies').read_text())
            complete_before = int((counts/'bench_jit_completions').read_text())
            warm = self.tell('learn', label=f'learning-{wave}')
            require(warm['ok'] and [w['cpu'] for w in warm['workers']] == s['helper_cpus'] and
                    warm['completed'] == sum(w['completed'] for w in warm['workers']) and
                    all(w['cpu'] == w['observed_cpu'] and w['error'] == 0 and
                        w['completed'] >= s['warmup'] and
                        w['finished_ns'] >= warm['started_ns'] + s['warmup_ms']*1000000
                        for w in warm['workers']),
                    'helper-learning syscall oracle or cohort failed', 'DATA_ERROR')
            evidence = jit_evidence(int((counts/'bench_jit_bodies').read_text()) - before,
                int((counts/'bench_jit_completions').read_text()) - complete_before,
                warm['completed'], enabled=True)
            state = status()
            require(state['frames'] == 0 and state['writers'] == 1,
                    'learning wave did not drain to the paused daemon lease', 'UNDRAINED')
            reg = registry()
            s['learning_waves'].append(dict(registry=reg, cpus=s['helper_cpus'], **evidence))
            self.save()
            os.kill(self.daemon.pid, signal.SIGCONT)
            if helper_ready(reg, evidence):
                return
            if not (len(reg) == 1 and reg[0]['status'] == 0):
                self.await_publication()
        raise Failure('PREPARATION_FAILED',
                      'helper learning did not establish complete delegation within configured waves')

    def prepare(self):
        s = self.record
        argv = [self.out/'build/client', s['kind'], s['query'], s['entries'], s['value_size'],
                ','.join(map(str, s['cpus'])), s['collector_cpu'], s['duration_ms'],
                s['warmup'], s['warmup_ms']]
        if s['helper_cpus']:
            argv.append(','.join(map(str, s['helper_cpus'])))
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
            self.run(['insmod', self.out/'build/kdlock_km.ko', 'bench_quiet=1', 'bench_complete_probe=1', 'jit_timing=0',
                      'hotlock_stats=1', 'target_process=sc_worker', 'spin_entry_ratio_limit=2',
                      'spin_prefetch=2'], 'load-kd.log')
            self.loaded_kd = True
        if s['arm'] == 'tclock':
            self.run(['insmod', self.out/'build'/(self.tc_module+'.ko'), 'komb_batch_size=1024'], 'load-tc.log')
            self.loaded_tc = True
        if s['arm'] != 'stock':
            load = ['insmod', self.workload_module, *source_parameters(s, ready)]
            self.run(load, 'load-source.log')
            self.loaded_source = True
            if s['kind'] in MUTEX_KINDS:
                require(self.tell('bind')['bound'], 'client control bind failed')
                self.control_bound = True
            s['lock_addr'] = int((PARAM/'lock_addr').read_text())
            if s.get('mutex_lock_offset') is not None:
                require(s['lock_addr'] % 64 == s['mutex_lock_offset'],
                        'loaded mutex placement differs')
                s['mutex_lock_placement'] = dict(offset=s['lock_addr'] % 64,
                                                cache_line_bytes=64, storage_bytes=128)
            s['gate_addr'] = (int((PARAM/'gate_addr').read_text())
                              if s['kind'] in ('utsname', 'xattr') else s['lock_addr'])
            if self.loaded_tc:
                (self.tc_params/'target_lock').write_text(str(s['lock_addr']))
            if self.loaded_kd:
                params = Path('/sys/module/kdlock_km/parameters')
                (params/'bench_lock_addr').write_text(str(s['gate_addr']))
                s['probe_parameters'] = {name: (params/name).read_text().strip()
                    for name in ('bench_complete_probe', 'bench_lock_addr')}
                require(s['probe_parameters']['bench_complete_probe'] in ('Y', '1') and
                        int(s['probe_parameters']['bench_lock_addr'], 0) == s['gate_addr'],
                        'KD completion probe configuration differs')
            (PARAM/'prepare').write_text('1')
        if self.loaded_kd and self.has_delegation_entry():
            sym = [line.split() for line in Path('/proc/kallsyms').read_text().splitlines()]
            begin = [int(v[0], 16) for v in sym if len(v) == 4 and v[2:] == ['rb_body', '[real_api]']]
            nm = self.run(['nm', '-S', self.workload_module], 'symbols.txt')
            sizes = [int(v[1], 16) for line in nm.splitlines()
                     if len(v := line.split()) == 4 and v[3] == 'rb_body']
            require(len(begin) == len(sizes) == 1, 'missing body symbol')
            s['entry_range'] = [begin[0], begin[0]+sizes[0]]
            self.start_daemon()
            self.await_publication()
            # A helper miss is learned only after every caller has joined.
            # The stopped daemon cannot replace an image while workers use it.
            # A final equal-size warmup follows these preparation-only waves.
            s['learning_waves'] = []
            if s['kind'] == 'xattr' and s['helper_waves']:
                self.learn_helpers()
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
        if self.loaded_kd and self.has_delegation_entry():
            s['published_before'] = self.publication()
            require(s['published_before']['source']['writers'] == 0,
                    'translator writer remains before measurement', 'UNDRAINED')
        before = int((PARAM/'calls').read_text()) if self.loaded_source else 0
        jit = Path('/sys/module/kdlock_km/parameters/bench_jit_bodies')
        complete = Path('/sys/module/kdlock_km/parameters/bench_jit_completions')
        address_guard = Path('/sys/module/kdlock_km/parameters/address_guard_count')
        jbefore = int(jit.read_text()) if self.loaded_kd else 0
        complete_before = int(complete.read_text()) if self.loaded_kd else 0
        s['address_guards_before'] = (int(address_guard.read_text())
                                      if self.loaded_kd and address_guard.exists() else None)
        tc_delegated = self.tc_params/'delegated'
        tc_before = int(tc_delegated.read_text()) if self.loaded_tc and tc_delegated.exists() else None
        s['execution_status'] = 'MEASURING'
        self.save()
        m = self.tell('measure')
        s['measurement'] = m
        require(m['ok'] and m['completed'] == sum(w['completed'] for w in m['workers']) and
                all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] for w in m['workers']),
                'syscall result or affinity mismatch', 'DATA_ERROR')
        m['peak'] = analyze_peak(m, s)
        s['whole_throughput_ops_s'] = m['completed']*1e9/m['wall_ns']
        s['peak_throughput_ops_s'] = m['peak']['throughput_ops_s']
        s['redirected_calls'] = int((PARAM/'calls').read_text())-before if self.loaded_source else 0
        require(not self.loaded_source or s['redirected_calls'] == m['completed'],
                'not every measured syscall reached substituted critical section', 'DATA_ERROR')
        if s['kind'] == 'utsname':
            require(m['reads'] + m['writes'] == m['completed'],
                    'invalid rwlock operation accounting', 'DATA_ERROR')
        s.update(jit_evidence(int(jit.read_text()) - jbefore if self.loaded_kd else 0,
            int(complete.read_text()) - complete_before if self.loaded_kd else 0,
            0 if s['kind'] == 'xattr' else m['writes'] if s['kind'] == 'utsname' else m['completed'],
            enabled=self.loaded_kd))
        s['local_reader_operations'] = (m['completed'] if s['kind'] == 'xattr' else
                                         m['reads'] if s['kind'] == 'utsname' else 0)
        s['registry_after'] = registry() if self.loaded_kd else []
        if self.loaded_kd and not self.has_delegation_entry():
            require(not s['registry_after'], 'local-reader workload published a JIT entry', 'DATA_ERROR')
        s['address_guards_after'] = (int(address_guard.read_text())
                                     if s['address_guards_before'] is not None else None)
        s['address_guard_exits'] = (s['address_guards_after'] - s['address_guards_before']
                                    if s['address_guards_before'] is not None else None)
        if self.loaded_kd and self.has_delegation_entry():
            s['published_after'] = self.publication()
            require(s['published_after']['source']['writers'] == 0,
                    'translator writer remains after measurement', 'UNDRAINED')
            require(s['published_before']['entry'] == s['published_after']['entry'] and
                    s['published_before']['images'] == s['published_after']['images'],
                    'published image changed during measurement', 'DATA_ERROR')
        s['tclock_delegation'] = (int(tc_delegated.read_text())-tc_before if tc_before is not None else
                                  'UNMEASURED' if self.loaded_tc else 'NOT_APPLICABLE')
        self.faults()
        require(self.tell('check', label='check-after')['check'], 'post-measurement data oracle failed')
        self.save()
        require(not s['require_jit'] or s['jit_completions'] > 0,
                'required complete KD body did not execute', 'NO_JIT')

    def cleanup(self):
        self.faults()
        # Only command replies after pthread_join permit this path. Timeouts
        # deliberately retain the client (and OFD owner), module and evidence.
        if self.loaded_source and self.record.get('kind') in ('xattr', 'utsname'):
            require((PARAM/'quiescent').is_file(), 'reader/writer drain interface missing', 'UNDRAINED')
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
    """Retain the dedicated collector and reject duplicate cohort identities."""
    cpus = list(map(int, args.cpus.split(',')))
    require(bool(cpus) and bool(args.threads) and len(set(cpus)) == len(cpus) and
            len(set(args.threads)) == len(args.threads) and
            0 < min(args.threads) <= max(args.threads) <= min(63, len(cpus)) and
            args.collector_cpu not in cpus[:max(args.threads)],
            'invalid worker/collector CPUs')
    require(min(cpus) >= 0 and max(cpus) < 1024 and 0 <= args.collector_cpu < 1024,
            'CPU outside supported affinity mask')
    return cpus


def make_plan(args):
    cpus = worker_cpus(args)
    mutex_api = getattr(args, 'mutex_api', 'outer')
    require(mutex_api in ('outer', 'public') and
            (mutex_api == 'outer' or set(args.kinds) <= MUTEX_KINDS),
            'public mutex API requires only mutex workloads')
    require(args.mutex_lock_offset is None or
            (args.backends == ['kdlock'] and set(args.kinds) <= MUTEX_KINDS),
            '--mutex-lock-offset requires only KD mutex workloads')
    require(args.repeats > 0 and 0 <= args.helper_waves <= 16,
            'invalid repeat/helper configuration')
    require(2 <= args.helper_workers <= 16, 'helper workers must be 2..16')
    helper_cpus = cpus[:min(args.helper_workers, len(cpus))]
    if 'xattr' in args.kinds and args.helper_waves:
        raise Failure('INVALID_PLAN', 'Linux 7 xattr readers execute locally; helper learning is unsupported')
    require(not args.require_jit or 'xattr' not in args.kinds,
            'Linux 7 xattr shared readers have no delegatable body')
    require(not args.require_jit or ('kdlock' in args.backends and max(args.threads) > 1),
            '--require-jit needs a multithreaded KD case')
    for field in ('kinds', 'queries', 'entries', 'backends'):
        values = getattr(args, field)
        require(bool(values) and len(set(values)) == len(values),
                'empty or duplicate plan dimension: ' + field)
    plan = []
    for kind, query, count, n, repeat in itertools.product(args.kinds, args.queries, args.entries, args.threads, range(args.repeats)):
        order = args.backends[repeat % len(args.backends):] + args.backends[:repeat % len(args.backends)]
        for arm in order:
            suffix = '-public' if arm == 'kdlock' and mutex_api == 'public' else ''
            plan.append(dict(name=f'{kind}-{query}-n{count}-t{n:02d}-r{repeat}-{arm}{suffix}', kind=kind,
                query=query, entries=count, threads=n, repeat=repeat, arm=arm, value_size=args.value_size,
                cpus=cpus[:n], collector_cpu=args.collector_cpu, duration_ms=args.duration_ms,
                peak_window_ms=300, peak_settle_ms=300, sample_ms=10,
                warmup=args.warmup, warmup_ms=args.warmup_ms,
                helper_waves=args.helper_waves,
                helper_cpus=helper_cpus if kind == 'xattr' and args.helper_waves else [],
                jit_evidence_version=2,
                jit_completion_probe=arm == 'kdlock',
                workload_revision='xattr-rbtree-read-v1' if kind == 'xattr' else 'linux70-v1',
                require_jit=args.require_jit and arm == 'kdlock' and n > 1,
                syscalls_per_op=2 if kind == 'setfd' else 1,
                file_descriptions='per-worker' if kind in ('setfd', 'pipebytes', 'pipecap') else 'shared-query',
                lock_kind=lock_kind(kind),
                entry_abi=({'spin': 1, 'mutex': 2, 'rwlock': 3}[lock_kind(kind)]
                           if arm == 'kdlock' and kind != 'xattr' else 0),
                caller_abi='clobber' if arm == 'kdlock' and kind != 'xattr' else 'c',
                caller_shell=(('mutex_public_direct' if mutex_api == 'public' else 'mutex_outer_cookie')
                              if arm == 'kdlock' and kind in MUTEX_KINDS else
                              'local_reader' if kind == 'xattr' else
                              'explicit_clobber' if arm == 'kdlock' else 'c'),
                cookie_storage=(('provider_acquisition_ledger' if mutex_api == 'public' else 'outer_acquisition_local')
                                if arm == 'kdlock' and kind in MUTEX_KINDS else 'not_applicable'),
                mutex_implementation=('kd-only-legacy' if arm == 'kdlock' and kind in MUTEX_KINDS
                                      else 'not_applicable'),
                mutex_lock_offset=args.mutex_lock_offset))
    if args.mutex_lock_offset is not None:
        for spec in plan:
            spec['diagnostic'] = True
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build-from', type=Path)
    p.add_argument('--build-only', action='store_true',
                   help='freeze and audit binaries without loading modules or running sessions')
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
    p.add_argument('--mutex-api', choices=('outer', 'public'), default='outer',
                   help='KD mutex compiled caller; public invokes kd_mutex_lock/unlock')
    p.add_argument('--duration-ms', type=int, default=2000)
    p.add_argument('--warmup', type=int, default=48000)
    p.add_argument('--warmup-ms', type=int, default=1000)
    p.add_argument('--helper-waves', type=int, default=0,
                   help='legacy helper-learning selection; Linux 7 xattr requires zero')
    p.add_argument('--helper-workers', type=int, default=8,
                   help='separate bounded xattr preparation cohort, including single-worker cases')
    p.add_argument('--require-jit', action='store_true',
                   help='require a returned KD body in every multithreaded KD measurement')
    p.add_argument('--mutex-lock-offset', type=int, choices=[0, 32, 40, 56],
                   help='diagnostic KD mutex placement within dedicated two-cache-line storage; '
                        'default retains the ordinary object and natural linker placement')
    kernel_identity.arguments(p)
    args = p.parse_args()
    out = args.output.resolve()
    require(out != ROOT and ROOT not in out.parents and not out.exists(), 'output must be new and outside checkout')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'confirm a real current-topology monitor snapshot before live execution')
    idle()
    for name in ('real_api', 'tclock_backend_km', 'tclock_mutex_backend_km', 'tclock_rwlock_backend_km', 'tc_allocator_guard'):
        require(not Path('/sys/module', name).exists(), 'existing module: '+name)
    plan = make_plan(args)
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
    identity = kernel_identity.capture(args, out, command)
    require(identity.get('schema') == 2 and identity.get('runtime_policy_verified') is True,
            'exact Linux 7 kernel and runtime policy verification required')
    write_json(out/'kernel-identity.json', identity)
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
    # Bind every exported sample to the frozen source and captured kernel /
    # topology, so combining reports cannot silently combine different builds.
    source_identity = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    for spec in plan:
        spec.update(source_identity=source_identity,
                    kernel_identity=digest(out/'kernel-identity.json'),
                    topology_identity=digest(out/'topology.txt'))
    write_json(out/'plan.json', plan)
    if args.build_only:
        write_json(out/'build-ready.json', dict(passed=True, sessions_run=0,
                                               mutex_api=args.mutex_api))
        return
    try:
        for i, spec in enumerate(plan):
            print(f'{i+1}/{len(plan)} {spec["name"]}', flush=True)
            session = SyscallSession(out, spec)
            session.execute()
            r = session.record
            print(f'  {r["whole_throughput_ops_s"]/1e6:.3f} M/s; peak {r["peak_throughput_ops_s"]/1e6:.3f}; '
                  f'JIT entries {r["jit_bodies"]}, complete {r["jit_completions"]}', flush=True)
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
