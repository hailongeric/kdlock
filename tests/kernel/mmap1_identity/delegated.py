#!/usr/bin/env python3
"""Unscored unchanged mmap1 with an explicitly prepared generic provider.

Build/load/execution belong only in the designated VM. Failure retains live
state; this controller never kills a workload or forces module unload.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
from bench_session import Session
from provider.prepare import prepare as prepare_provider
from device_session import query_capabilities

spec = importlib.util.spec_from_file_location('mmap1_delegated_bench', ROOT / 'bench/mmap1/run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
observer = bench.common.module('mmap1_delegated_observer', ROOT / 'tests/kernel/mmap1_identity/run.py')
sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
primitives = bench.common.module('mmap1_delegated_primitives', ROOT / 'tests/kernel/jit_continuation/helper_mode.py')
memory = bench.common.module('mmap1_delegated_memory', ROOT / 'tests/kernel/jit_continuation/memory_mode.py')
pairs = bench.common.module('mmap1_syscall_pairs', ROOT / 'tests/kernel/mmap1_identity/syscall_pairs.py')
PARAMETERS = Path('/sys/module/kdlock_km/parameters')
KERNEL_COMPONENT = '1ab7124abb6140752c1f0bb6e862144d426a3875'
KERNEL_BUILD_ID = '5f2fce72a33480f6e79a79b374b21a0db377ecd1'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
GIB = 1024 ** 3


def reference(path):
    return dict(path=str(path), sha256=rt.digest(path))


def checked(path, wanted):
    rt.require(path.is_absolute() and path.is_file() and not path.is_symlink() and
               re.fullmatch('[0-9a-f]{64}', wanted) and rt.digest(path) == wanted,
               'exact input differs: ' + str(path))
    return bench.load(path)


def process_group(group):
    rows = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            words = path.read_text().rsplit(')', 1)[1].split()
            if int(words[2]) == group:
                rows.append(dict(pid=int(path.parent.name), start_ticks=int(words[19]), state=words[0]))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def source_manifest(args):
    state = checked(args.source_state, args.source_state_sha256)
    rows = checked(args.source_manifest, args.source_manifest_sha256)
    rt.require(re.fullmatch('[0-9a-f]{40}', args.source_commit) and
               state['git_head'] == args.source_commit and state['git_status'] == '' and
               state['files'] == len(rows) and not state['omitted_missing_tracked_paths'] and rows,
               'complete clean exact runtime source snapshot required')
    for name, wanted in rows.items():
        path = Path(name)
        rt.require(not path.is_absolute() and all(part not in ('.', '..') for part in path.parts) and
                   str(path) == name and re.fullmatch('[0-9a-f]{64}', wanted), 'invalid runtime source manifest member')
        original = ROOT / path
        rt.require(original.is_file() and not original.is_symlink() and rt.digest(original) == wanted,
                   'runtime source differs: ' + name)
    return rows


def copy_source(out, rows):
    target = out / 'source'
    target.mkdir()
    copied = {}
    prefixes = ('include/', 'kernel_module/', 'daemon/', 'disassem/', 'bench/', 'tests/', 'kernel_integration/linux70/')
    extensions = ('.py', '.c', '.h', '.inc', '.S', '.def', '.json', '.md', '.patch')
    for name, wanted in rows.items():
        path = Path(name)
        if (not name.startswith(prefixes) or name.startswith('bench/results/') or
                any(part.startswith('.') or part == '__pycache__' for part in path.parts) or
                path.name.endswith('.mod.c') or
                not (name.endswith(extensions) or path.name in ('Makefile', 'requirements.txt'))):
            continue
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        copied[str(ROOT / name)] = copied[str(destination)] = wanted
    rt.require(str(target / 'bench/mmap1/execution_session.py') in copied and
               str(target / 'bench/mmap1/kernel_log.py') in copied and
               str(target / 'tests/kernel/mmap1_identity/delegated.py') in copied,
               'required controller/session/collector source omitted')
    rt.write_json(out / 'source-sha256.json', {str(Path(name).relative_to(target)): wanted
        for name, wanted in copied.items() if Path(name).is_relative_to(target)})
    return target, copied


def site_audit(args, binding):
    audit = checked(args.sites, args.sites_sha256)
    rt.require(audit.get('schema') == 1 and
               audit['kernel_component_source_commit'] == KERNEL_COMPONENT and
               audit['vmlinux']['build_id'] == binding['build_id'] == KERNEL_BUILD_ID and
               audit['vmlinux']['sha256'] == binding['build_files']['vmlinux'] and
               audit['vmlinux']['bytes'] == (args.kernel_source / 'vmlinux').stat().st_size and
               re.fullmatch('[0-9a-f]{64}', audit['section']['sha256']), 'exact 380G10 producer-kernel site audit required')
    rows = audit['records']
    rt.require(rows and len({row['entry'] for row in rows}) == len(rows) and all(
        type(row['entry']) is int and row['entry'] > 0 and row['operation'] in (1, 3) and
        row['reserved'] == 0 and isinstance(row['function'], str) and row['function'] and
        row['aliases'] and len(row['aliases']) == len(set(row['aliases'])) and row['function'] in row['aliases'] and
        all(isinstance(alias, str) and alias for alias in row['aliases']) for row in rows) and
        audit['section']['end'] - audit['section']['start'] == 16 * len(rows),
        'complete distinct builtin writer-site records required')
    expected = {'mmap': sorted(row['entry'] for row in rows if 'vm_mmap_pgoff' in row['aliases']),
                'munmap': sorted(row['entry'] for row in rows if '__vm_munmap' in row['aliases'])}
    rt.require(set(audit['entry_sites']) == set(expected) and all(expected.values()) and
               all(sorted(audit['entry_sites'][name]) == entries for name, entries in expected.items()),
               'audited mmap/munmap entries differ from complete site table')
    return audit


def require_observed_continuation(proof):
    rt.require(proof['downgraded_read_tails'] > 0,
               'application diagnostic observed no delegated downgraded read tail', 'DATA_ERROR')
    rt.require(proof['later_same_executor_writers'],
               'application diagnostic observed no later writer on the same executor and object', 'DATA_ERROR')
    return dict(downgraded_read_tails=proof['downgraded_read_tails'],
                later_same_executor_writer_pairs=len(proof['later_same_executor_writers']),
                scope='positive trace observations; fresh reader drainage is not inferred')


class Daemon:
    """Use the maintained workspace and normal daemon start/stop methods."""
    def __init__(self, path, source, binary):
        self.path, self.translation_source, self.daemon_binary = path, source, binary
        self.record = {}
        self.daemon = self.daemon_log = None

    def save(self):
        rt.write_json(self.path / 'daemon-session.json', self.record)

    def start(self):
        # Session uses the inherited environment for its Python child. Select
        # the same pinned interpreter used by this controller before spawning.
        previous = os.environ.get('PATH')
        os.environ['PATH'] = str(Path(sys.executable).parent) + ':/usr/sbin:/usr/bin:/sbin:/bin'
        try:
            Session.start_daemon(self)
        finally:
            if previous is None:
                os.environ.pop('PATH', None)
            else:
                os.environ['PATH'] = previous

    def stop(self):
        Session.stop_daemon(self)


class Controller:
    def __init__(self, args, out, files, source, audit, binaries):
        self.args, self.out, self.files, self.source, self.audit, self.binaries = args, out, files, source, audit, binaries
        self.result = dict(schema=1, passed=False, drained=False, accepted=False, scored=False,
            state='STARTING', runtime_source_commit=args.source_commit, kernel_component_source_commit=KERNEL_COMPONENT,
            boot_id=args.boot_id, models={}, commands=[], host_endpoint='PENDING', workload_modified=False)
        self.collector = self.log_fd = None
        self.model = None
        self.save()

    def save(self):
        rt.write_json(self.out / 'result.json', self.result)

    def verify(self):
        bench.verify_boot(self.args)
        bench.verified_files(self.files)
        if self.collector is not None:
            rt.require(not self.collector.first_error and not self.collector.fault and
                       self.collector.thread.is_alive(), 'continuous controller kernel log incomplete/faulted')

    def run(self, name, argv, timeout=180, cwd=None):
        self.verify()
        row = dict(name=name, argv=list(map(str, argv)), started_ns=time.monotonic_ns(), timeout_seconds=timeout)
        self.result['commands'].append(row)
        self.result['drained'] = False
        self.save()
        logfile = (self.model or self.out) / (name + '.log')
        with logfile.open('xb') as log:
            child = subprocess.Popen(row['argv'], cwd=cwd or ROOT, env=self.env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            row.update(pid=child.pid, process_group=child.pid)
            self.save()
            try:
                row['returncode'] = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                row.update(timed_out=True, remaining=process_group(child.pid))
                self.save()
                raise rt.Failure('TIMEOUT', 'command lifetime unknown; outputs and live state retained', unsafe=True)
        row.update(remaining=process_group(child.pid), log=reference(logfile), finished_ns=time.monotonic_ns())
        self.save()
        rt.require(row['returncode'] == 0 and not row['remaining'], 'command failed or did not drain: ' + name)
        self.verify()
        return logfile.read_text()

    def wait(self, label, predicate, timeout=30):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            self.verify()
            last = predicate()
            if last:
                return last
            time.sleep(0.05)
        self.result['last_wait'] = dict(label=label, timeout_seconds=timeout, source=rt.status(),
                                      parameters=rt.parameters(), registry=rt.registry())
        self.save()
        raise rt.Failure('TIMEOUT', label + ' did not complete; live state retained', unsafe=True)

    def prepare(self):
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', LC_ALL='C',
            PATH=str(Path(sys.executable).parent) + ':/usr/sbin:/usr/bin:/sbin:/bin', TMPDIR=str(self.out / 'tmp'))
        self.env.pop('KD_DEVICE_FD', None)
        (self.out / 'tmp').mkdir()
        provider_dir = self.out / 'build/provider'
        rt.require(not provider_dir.exists(), 'fresh private provider required')
        prepared = prepare_provider(provider_dir, self.source)
        rt.write_json(self.out / 'provider-preparation.json', prepared)
        self.run('build-provider', ['make', '-C', provider_dir / 'kernel_module',
            'KDIR=' + str(self.args.kernel_source), 'W=1', 'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1',
            'KDLOCK_SPIN_BATCH=1024', 'UBSAN_SANITIZE=n'])
        self.run('build-daemon', ['make', '-C', self.source / 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'])
        probe = self.out / 'build/probe'
        probe.mkdir()
        for path in (self.source / 'tests/kernel/mmap1_identity/payload').iterdir():
            if path.name == 'Makefile' or path.suffix in ('.c', '.h', '.inc') and not path.name.endswith('.mod.c'):
                shutil.copyfile(path, probe / path.name)
        self.run('build-probe', ['make', '-C', probe, 'KDIR=' + str(self.args.kernel_source), 'W=1', 'UBSAN_SANITIZE=n'])
        self.binaries.update(provider=provider_dir / 'kernel_module/kdlock_km.ko',
                             daemon=self.source / 'daemon/daemon', probe=probe / 'kd_mmap1_identity.ko')
        for name in ('provider', 'probe'):
            module = self.binaries[name]
            text = self.run(name + '-vermagic', ['modinfo', '-F', 'vermagic', module], 30)
            rt.require(text.split()[0] == os.uname().release, 'built module release differs')
        for name, path in self.binaries.items():
            self.files[str(path)] = rt.digest(path)
        for path in provider_dir.rglob('*'):
            if path.is_file() and (path.suffix in ('.c', '.h', '.inc', '.S', '.def', '.json') or path.name == 'Makefile'):
                self.files[str(path)] = rt.digest(path)
        rt.write_json(self.out / 'binary-sha256.json', {name: reference(path) for name, path in self.binaries.items()})

    def session_receipt(self, daemon, rows):
        execution = bench.execution
        actual_daemon = execution.task_identity(daemon.daemon.pid)
        preparer = execution.task_identity(os.getpid())
        for actual in (actual_daemon, preparer):
            actual['executable_sha256'] = rt.digest(Path(actual['executable']))
            self.files[actual['executable']] = actual['executable_sha256']
        writers = execution.device_writers()
        rt.require(len(writers) == 1 and writers[0]['pid'] == actual_daemon['pid'] and
                   writers[0]['start_ticks'] == actual_daemon['start_ticks'], 'sole exact daemon writer required')
        actual_daemon['device_writer'] = writers[0]
        source = rt.status()
        rt.require(source['state'] == 0 and source['frames'] == 0 and source['writers'] == 1,
                   'prewarmed source ledger is not quiescent')
        parameters = rt.parameters()
        selected = {name: parameters[name] for name in ('rwsem_provider_active', 'rwsem_provider_mode',
                                                       'jit_timing', 'service_trace', 'bench_quiet', 'bench_complete_probe')}
        value = dict(schema=1, boot_id=self.args.boot_id, provider=dict(path=str(self.binaries['provider']),
            sha256=rt.digest(self.binaries['provider']), note_sha256=execution.module_note_sha256(self.binaries['provider'])),
            daemon=actual_daemon, preparer=preparer, parameters=selected, registry=rows,
            source={name: source[name] for name in ('state', 'modules', 'writers')}, files=dict(self.files))
        path = self.model / 'execution-session.json'
        rt.write_json(path, value)
        return execution.ExecutionSession(path, rt.digest(path))

    def ready(self, daemon):
        rows = rt.registry()
        rt.write_json(self.model / 'registry-progress.json', rows)
        wanted = {row['entry'] for row in self.audit['records']}
        rt.require({row['entry'] for row in rows} == wanted and len(rows) == len(wanted) and all(
            row['pid'] == 0 and row['tgid'] == os.getpid() and row['entry_abi'] == 2 and row['lock_kind'] == 2
            for row in rows), 'all-site registry identity differs')
        rt.require(all(row['status'] in (-1, 0) for row in rows), 'prewarm site failed or became Native-only')
        rt.require(daemon.daemon.poll() is None, 'translation daemon exited during preparation')
        return rows if all(row['status'] == 0 and row['code'] > 0 and row['generation'] > 0 for row in rows) and \
            not rt.children(daemon.daemon.pid) and rt.status()['writers'] == 1 else None

    def stop_observer(self):
        first, second = bytearray(observer.SIZE), bytearray(observer.SIZE)
        with open('/dev/kd_mmap1_identity', 'rb', buffering=0) as device:
            fcntl.ioctl(device, observer.STOP, first, True)
            fcntl.ioctl(device, observer.STOP, second, True)
        rt.require(first == second, 'observer STOP is not stable/idempotent')
        (self.model / 'snapshot.bin').write_bytes(first)
        snapshot = dict(observer.decode(first), repeat_equal=True)
        rt.write_json(self.model / 'snapshot.json', snapshot)
        return snapshot

    def validate_services(self, proof, rows, messages, snapshot):
        generations = {row['entry']: row['generation'] for row in rows}
        workers = {row['tid']: row for row in snapshot['records']}
        key = lambda row: tuple(row[name] for name in ('origin', 'identity', 'generation'))
        roots = {}
        for event in primitives.trace_events(messages):
            if event['origin'] in workers and event['depth'] == 0:
                roots.setdefault(key(event), []).append(event)
        complete = {}
        for identity, group in roots.items():
            if [row['event'] for row in group] == ['cancel']:
                continue
            first = group[0]
            rt.require([row['event'] for row in group] in (['enter', 'release', 'returned'],
                ['enter', 'downgrade', 'read_release', 'returned']) and
                first['executor'] != first['origin'] and first['may_delegate'] and
                first['entry'] in generations and first['object'] == workers[first['origin']]['backing'] and
                first['identity'] > 0 and first['generation'] > 0 and all(all(
                    row[name] == first[name] for name in ('origin', 'executor', 'identity', 'generation', 'object', 'entry'))
                    for row in group), 'captured worker MM root incomplete or identity changed')
            complete[identity] = first
        audited = {key(row) for row in proof['completed_requests']}
        rt.require(audited <= complete.keys(), 'audited returned roots missing from complete worker roots')
        counts = {}
        for family, events in (('primitive', primitives.primitive_events(messages)),
                               ('memory', memory.memory_events(messages))):
            selected = {}
            for event in events:
                if event['origin'] in workers:
                    rt.require(key(event) in complete, 'service event has no complete captured worker root')
                    selected.setdefault(key(event), []).append(event)
            transactions = 0
            for identity, events in selected.items():
                root = complete[identity]
                sequences = sorted({event['sequence'] for event in events})
                rt.require(sequences == list(range(1, len(sequences) + 1)), 'service sequence gap or invalid initial sequence')
                rt.require([event['sequence'] for event in events] ==
                           [sequence for sequence in sequences for _ in range(4)], 'service transaction interleaved/incomplete')
                for sequence in sequences:
                    part = [event for event in events if event['sequence'] == sequence]
                    if family == 'primitive':
                        primitives.validate_transaction(part, root, root['origin'], part[0]['target'],
                            generations[root['entry']], None, sequence=sequence, final=part[-1]['stage'] == 'complete')
                    else:
                        first = part[0]
                        fields = ('origin', 'executor', 'identity', 'generation', 'sequence', 'image_generation',
                                  'ip', 'next', 'sp', 'offset', 'width', 'operation', 'preempt_operand',
                                  'preempt_seq', 'preempt_object', 'input_flags', 'destination', 'read')
                        rt.require([event['stage'] for event in part] in (['request', 'enter', 'done', 'resume'],
                                   ['request', 'enter', 'done', 'complete']) and
                            first['image_generation'] == generations[root['entry']] and
                            first['executor'] == root['executor'] and first['ip'] > 0 and
                            first['next'] > first['ip'] and first['sp'] > 0 and
                            first['operation'] in (1, 2, 3, 4) and first['width'] in (16, 32, 64) and
                            first['read'] == int(first['operation'] >= 3) and
                            all(all(event[name] == first[name] for name in fields) for event in part) and
                            [event['task'] for event in part] == [root['executor'], root['origin'], root['origin'], root['executor']] and
                            part[2]['output_flags'] == part[3]['output_flags'] and part[2]['value'] == part[3]['value'],
                            'GS transaction instruction/context/result identity differs')
                    transactions += 1
            counts[family + '_transactions'] = transactions
        return dict(counts, captured_worker_roots=len(complete), other_worker_roots=len(complete.keys() - audited),
                    scope='complete captured worker MM roots; no expected source transaction count inferred')

    def model_run(self, model, inputs):
        bench.idle()
        self.model = self.out / model
        self.model.mkdir()
        record = dict(state='PREPARING', passed=False, drained=False, scored=False, model=model)
        self.result['models'][model] = record
        self.save()
        logdir = self.model / 'lifecycle-log'
        logdir.mkdir()
        self.log_fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        os.lseek(self.log_fd, 0, os.SEEK_END)
        self.collector = bench.kernel_log.DiagnosticKernelLog(self.log_fd, logdir, rt.FAULT)
        try:
            self.collector.start()
            self.run('load-provider', ['insmod', self.binaries['provider'], 'bench_quiet=1',
                'bench_complete_probe=0', 'jit_timing=0', 'hotlock_stats=0'])
            record['provider_loaded'] = True
            rt.require((PARAMETERS / 'rwsem_provider_active').read_text().strip() == 'N' and
                       (PARAMETERS / 'rwsem_provider_bindings').read_text().strip() == '0', 'factory was not initially inactive')
            with open('/dev/kd_dev', 'rb', buffering=0) as device:
                record['capabilities'] = query_capabilities(device.fileno())
            rt.require(all(record['capabilities'].get(name) for name in
                           ('origin_call', 'origin_memory', 'origin_context_read', 'indirect_tail')), 'required retained MM context service unavailable')
            daemon = Daemon(self.model, self.source, self.binaries['daemon'])
            daemon.start()
            record['daemon_pid'] = daemon.daemon.pid
            self.run('load-observer', ['insmod', self.binaries['probe'], 'target=mmap1_' + model, 'pair_limit=8'])
            record['observer_loaded'] = True
            (PARAMETERS / 'rwsem_provider_mode').write_text('prepare\n')
            rows = self.wait('all builtin writer sites ready', lambda: self.ready(daemon), timeout=600)
            image_files = {}
            for row in rows:
                folder = self.model / 'workspace/daemon' / hex(row['entry']) / str(row['tgid']) / 'asm'
                for name in ('jit.bin', 'jit.S', 'bin.txt'):
                    path = folder / name
                    rt.require(path.is_file() and path.stat().st_size > 0, 'prepared site image artifact missing')
                    image_files[str(path)] = rt.digest(path)
            self.files.update(image_files)
            rt.write_json(self.model / 'ready-registry.json', rows)
            rt.write_json(self.model / 'image-sha256.json', image_files)
            (PARAMETERS / 'service_trace').write_text('1\n')
            (PARAMETERS / 'rwsem_provider_mode').write_text('activate\n')
            record['factory_active'] = True
            exact_session = self.session_receipt(daemon, rows)
            exact_session.verify(allow_identity_probe=True)
            record.update(state='APPLICATION', execution_session=exact_session.identity())
            self.save()
            session = bench.run_point(self.model / 'application', dict(model=model, workers=2, round=0, nominal_seconds=2),
                inputs, self.verify, diagnostic=True, execution_session=exact_session)
            snapshot = self.stop_observer()
            symbols = [int(line.split()[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
                       if len(line.split()) == 4 and line.split()[2:] == ['kd_rwsem_ops', '[kdlock_km]']]
            rt.require(len(symbols) == 1 and symbols[0] > 0, 'exact live module provider symbol missing/ambiguous')
            messages = (self.model / 'application/kernel.log').read_text()
            rt.require('kd_service event=local_image ' not in messages and
                       'kd_service unsupported continuation:' not in messages, 'an actual MM continuation could not delegate')
            proof = observer.validate_delegated(snapshot, session, os.sysconf('SC_CLK_TCK'), messages,
                                                self.audit['entry_sites'], symbols[0])
            proof['service_transactions'] = self.validate_services(proof, rows, messages, snapshot)
            lifecycle = logdir / 'kernel.log'
            self.wait('syscall pair STOP summary', lambda:
                'kd_mm_pair: event=stop ' in lifecycle.read_text(), timeout=2)
            proof['syscall_pairs'] = pairs.validate(lifecycle.read_text(), snapshot, proof,
                                                   self.audit['entry_sites'], 8)
            rt.write_json(self.model / 'delegated-proof.json', proof)
            record.update(proof=reference(self.model / 'delegated-proof.json'), application=reference(self.model / 'application/result.json'),
                snapshot=reference(self.model / 'snapshot.json'), completed_requests=proof['completed_request_count'],
                downgraded_read_tails=proof['downgraded_read_tails'], state='DRAINING')
            self.save()
            record['continuation_criterion'] = require_observed_continuation(proof)
            self.save()
            exact_session.verify(allow_identity_probe=True)
            (PARAMETERS / 'rwsem_provider_mode').write_text('deactivate\n')
            record['factory_active'] = False
            self.wait('provider bindings and execution frames drain', lambda:
                (PARAMETERS / 'rwsem_provider_active').read_text().strip() == 'N' and
                (PARAMETERS / 'rwsem_provider_bindings').read_text().strip() == '0' and
                rt.status()['frames'] == 0, timeout=30)
            record['binding_drain'] = dict(bindings=0, source=rt.status())
            daemon.stop()
            record['daemon_closed'] = True
            self.wait('daemon writer drain', lambda: rt.status()['writers'] == 0, timeout=10)
            with open('/dev/kd_dev', 'rb', buffering=0) as device:
                fcntl.ioctl(device, rt.RETIRE)
                retired = rt.info(device.fileno())
            rt.require(retired == dict(state=2, modules=0, frames=0, writers=0), 'source retirement incomplete')
            record['retired'] = retired
            self.run('unload-observer', ['rmmod', 'kd_mmap1_identity'])
            record['observer_loaded'] = False
            self.run('unload-provider', ['rmmod', 'kdlock_km'])
            record['provider_loaded'] = False
            bench.idle()
            record.update(state='COMPLETE', passed=True, drained=True)
        except BaseException as error:
            record.update(state='FAILED', passed=False, error=repr(error), traceback=traceback.format_exc())
            try:
                record['retained_state'] = dict(source=rt.status(), parameters=rt.parameters(), registry=rt.registry())
            except BaseException as observation_error:
                record['retained_state_error'] = repr(observation_error)
            raise
        finally:
            summary = self.collector.finish()
            record['kernel_log_collection'] = summary
            rt.write_json(logdir / 'result.json', summary)
            if not self.collector.thread.is_alive():
                os.close(self.log_fd)
            self.log_fd = None
            self.collector = None
            if not summary['complete'] or summary['fault_detected']:
                record.update(state='FAILED', passed=False, log_error='lifecycle kernel collection incomplete/faulted')
            self.save()
        rt.require(record['passed'], 'diagnostic model did not complete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'source-state', 'source-manifest', 'sites'):
        parser.add_argument('--' + name, type=Path, required=True)
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--source-commit', required=True)
    bench.arguments(parser)
    args = parser.parse_args()
    rt.require(args.mode == 'kd' and args.kernel_variant == 'kdscope5-kd', 'explicit kdscope5 delegated mode required')
    bench.guest(args)
    rt.require(os.geteuid() == 0 and sys.executable == PYTHON and str(ROOT).startswith('/root/'),
               'guest root/pinned Python/private frozen input required')
    namespace = next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('NSpid:'))
    rt.require(len(namespace.split()) == 2 and os.stat('/proc/self/ns/time').st_ino == os.stat('/proc/1/ns/time').st_ino,
               'initial PID/time namespaces required')
    args.output = args.output.resolve()
    for key in ('inputs', 'source_state', 'source_manifest', 'sites'):
        setattr(args, key, getattr(args, key).resolve(strict=True))
    rt.require(not args.output.exists() and args.output.is_relative_to(Path('/mnt/kdlock-builds2')) and
               not args.output.is_relative_to(ROOT) and not ROOT.is_relative_to(args.output), 'fresh independent DATA2 output required')
    bench.idle()
    rt.require(shutil.disk_usage(args.output.parent).free > 3 * GIB + 2 * bench.kernel_log.MAX_BYTES,
               'provider build and bounded diagnostic collection headroom unavailable')
    rows = source_manifest(args)
    inputs = checked(args.inputs, args.inputs_sha256)
    inputs = bench.inputs_from(args.inputs)
    args.output.mkdir(parents=True)
    result = None
    controller = None
    try:
        admitted = bench.admit(args, args.output)
        audit = site_audit(args, admitted['kernel_binding'])
        source, files = copy_source(args.output, rows)
        for key in ('inputs', 'source_state', 'source_manifest', 'sites'):
            path = getattr(args, key)
            files[str(path)] = rt.digest(path)
            shutil.copyfile(path, args.output / (key.replace('_', '-') + '.json'))
        files.update(inputs['files'])
        files[str(args.inputs.parent / 'result.json')] = rt.digest(args.inputs.parent / 'result.json')
        controller = Controller(args, args.output, files, source, audit, {})
        result = controller.result
        result.update(admitted, inputs=reference(args.inputs), source_state=reference(args.source_state),
                      source_manifest=reference(args.source_manifest), sites=reference(args.sites), controller=reference(Path(__file__)))
        controller.save()
        controller.prepare()
        for model in bench.MODELS:
            controller.model_run(model, inputs)
            controller.model = None
        source_manifest(args)
        controller.verify()
        bench.idle()
        rt.write_json(args.output / 'immutable-files.json', controller.files)
        result.update(state='COMPLETE', passed=True, drained=True, final_idle=True,
                      files=reference(args.output / 'immutable-files.json'))
    except BaseException as error:
        if result is None:
            result = dict(schema=1, passed=False, drained=False, accepted=False, scored=False)
        result.update(state='FAILED', passed=False, error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        if result is not None:
            rt.write_json(args.output / 'result.json', result)


if __name__ == '__main__':
    main()
