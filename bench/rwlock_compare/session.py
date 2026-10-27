"""Snapshot/rwlock preparation, complete-body evidence and strict source/queue drain."""
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
from bench_runtime import Failure, children, parameters, registry, require, status
from bench_session import Session
from summarize import write_json
from protocol import DEVICE, PREPARE, DRAIN, snapshot
from oracle import check_snapshot, jit_evidence, validate

KD_PARAMS = Path('/sys/module/kdlock_km/parameters')


class RWSession(Session):
    def __init__(self, out, spec, binaries):
        super().__init__(out, spec, workload_module=binaries['workloads'][spec['variant']])
        self.binaries = binaries
        self.loaded_tc = False
        self.daemon_paused = False
        self.tc_module = binaries.get('tclock', Path('tclock_rwlock_backend_km.ko')).stem
        self.tc_params = Path('/sys/module') / self.tc_module / 'parameters'

    def has_entry(self):
        if self.record['lock_kind'] in ('rwsem', 'mutex'):
            return self.record['delegate'] and bool(self.record['write_percent'])
        return self.record['write_percent'] < 100 if self.record['lock_kind'] == 'spin' else bool(self.record['write_percent'])

    def counts(self, label):
        row = snapshot()
        write_json(self.path / (label + '.counts.json'), row)
        check_snapshot(row, self.record)
        return row

    def tc_idle(self):
        kind = self.record['lock_kind']
        if kind == 'rwsem' or (kind == 'mutex' and self.loaded_source):
            # Client process has returned; retain refs until PID retirement too.
            for attempt in range(100):
                try:
                    if kind == 'rwsem':
                        (self.tc_params / 'drain').write_text('1')
                    else:
                        with open(DEVICE, 'rb', buffering=0) as device:
                            fcntl.ioctl(device, DRAIN)
                    break
                except OSError as error:
                    if error.errno != errno.EBUSY or attempt == 99:
                        raise
                    time.sleep(0.01)
        row = {p.name: int(p.read_text()) for p in self.tc_params.iterdir()
               if p.name != 'drain'}
        require(row['quiescent'] == 1, 'TCLock contexts/queue remain active', 'UNDRAINED')
        return row

    def start_daemon(self):
        workspace = self.path / 'workspace'
        (workspace / 'daemon').mkdir(parents=True)
        for directory in ('disassem', 'include'):
            (workspace / directory).symlink_to(self.path.parent / 'source' / directory,
                                               target_is_directory=True)
        self.daemon_log = (self.path / 'daemon.log').open('w')
        env = dict(os.environ, KD_JIT_BODY_WITNESS='1')
        env.pop('KD_DEVICE_FD', None)
        self.daemon = subprocess.Popen([self.binaries['daemon'], '--quiet', '--metrics', '--mode', 'per-tgid'],
            cwd=workspace / 'daemon', env=env, stdout=self.daemon_log, stderr=subprocess.STDOUT,
            start_new_session=True)
        self.record['daemon_pid'] = self.daemon.pid
        self.save()

    def await_publication(self):
        deadline = time.monotonic() + 90
        while True:
            self.faults()
            require(self.daemon.poll() is None, 'daemon exited during preparation')
            text = (self.path / 'daemon.log').read_text()
            require(not re.search(r'\[KD_JIT\]\[ERROR\]|Traceback|command failed', text),
                    'translator failed; see daemon.log')
            metrics = [json.loads(line.split(' ', 1)[1]) for line in text.splitlines()
                       if line.startswith('KD_TRANSLATION_METRICS ')]
            require(all(m['result'] == m['status'] == 0 for m in metrics), 'translation refused')
            rows = registry()
            require(len(rows) == 1 and rows[0]['entry'] == self.record['layout']['entry'] and
                    rows[0]['status'] in (-1, 0, 1, 2), 'unexpected delegated-entry registry')
            if rows[0]['status'] == 0 and metrics and not children(self.daemon.pid):
                self.record['translation'] = metrics
                publication = self.publication()
                self.record['publication'] = publication
                # The translator overwrites its asm directory on the next
                # helper miss. Preserve every admitted image before learning.
                history = self.record.setdefault('publications', [])
                archive = self.path / 'publications' / f'{len(history):02d}'
                archive.mkdir(parents=True)
                entry = publication['entry']
                folder = self.path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
                for name in publication['images']:
                    shutil.copyfile(folder / name, archive / name)
                history.append(dict(path=str(archive.relative_to(self.path)), **publication))
                self.save()
                return
            if time.monotonic() >= deadline:
                raise Failure('TIMEOUT', 'delegated-entry publication timed out', unsafe=True)
            time.sleep(0.1)

    def pause_daemon(self):
        require(not children(self.daemon.pid), 'translator active before learning wave', 'UNDRAINED')
        os.kill(self.daemon.pid, signal.SIGSTOP)
        self.daemon_paused = True
        deadline = time.monotonic() + 5
        while not re.search(r'^State:\s+T', Path(f'/proc/{self.daemon.pid}/status').read_text(), re.M):
            require(time.monotonic() < deadline, 'daemon did not stop')
            time.sleep(.01)
        require(not children(self.daemon.pid), 'translator raced daemon pause', 'UNDRAINED')

    def stop_daemon(self):
        if self.daemon is not None and self.daemon_paused:
            require(status()['frames'] == 0, 'learning callers still active', 'UNDRAINED')
            os.kill(self.daemon.pid, signal.SIGCONT)
            self.daemon_paused = False
        super().stop_daemon()

    def learn_helpers(self):
        # Same drain-separated learning protocol as bench/real_api: an old
        # spin image is never replaced while workers are executing it.
        # A separate recorded cohort learns the same body even for one-worker
        # timing. It cannot change the measured CPUs or relax entry policy.
        learning_spec = dict(self.record, threads=len(self.record['helper_cpus']),
            cpus=self.record['helper_cpus'], cpu_nodes=self.record.get('helper_cpu_nodes', []),
            iterations=self.record['helper_iterations_per_worker'], duration_ms=0)
        self.record['learning_waves'] = []
        for wave in range(self.record['helper_waves']):
            self.pause_daemon()
            before = int((KD_PARAMS / 'bench_jit_bodies').read_text())
            complete_before = int((KD_PARAMS / 'bench_jit_completions').read_text())
            measured = self.phase(f'learning-{wave}', learning_spec)
            evidence = jit_evidence(before, int((KD_PARAMS / 'bench_jit_bodies').read_text()),
                measured['reads'], backend='kdlock', delegate=True, operation='snapshot',
                completed=int((KD_PARAMS / 'bench_jit_completions').read_text()) - complete_before)
            state = status()
            require(state['frames'] == 0 and state['writers'] == 1,
                    'learning wave did not drain to paused daemon lease', 'UNDRAINED')
            rows = registry()
            self.record['learning_waves'].append(dict(registry=rows, **evidence))
            self.save()
            os.kill(self.daemon.pid, signal.SIGCONT)
            self.daemon_paused = False
            if len(rows) == 1 and rows[0]['status'] == 0:
                # A cold wave can leave the initial CALL-miss image NORMAL
                # simply because it never ran. It has not learned the body.
                if evidence['jit_completions']:
                    return
            else:
                self.await_publication()
        raise Failure('PREPARATION_FAILED',
                      'helper learning did not establish complete delegation within configured waves')

    def prepare(self):
        self.run(['insmod', self.binaries['guard']], 'load-allocator-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-allocator-guard.log')
        if self.record['arm'] == 'kdlock':
            self.run(['insmod', self.binaries['kdlock'], 'bench_quiet=1', 'bench_complete_probe=1', 'jit_timing=0',
                      'hotlock_stats=1', 'target_process=rb_worker', 'spin_prefetch=2',
                      f'spin_entry_ratio_limit={self.record["spin_entry_ratio_limit"]}',
                      f'spin_delegate={int(self.record["delegate"])}'], 'load-kdlock.log')
            self.loaded_kd = True
        elif self.record['arm'] == 'tclock':
            self.run(['insmod', self.binaries['tclock'], 'komb_batch_size=1024'], 'load-tclock.log')
            self.loaded_tc = True
        self.run(['insmod', self.workload_module], 'load-source.log')
        self.loaded_source = True
        layout = self.counts('initial')
        require(layout['values'] == [0] * 16, 'workload not reset')
        self.record['layout'] = layout
        if self.loaded_tc:
            (self.tc_params / 'target_lock').write_text(str(layout['lock_addr']))
            self.record['parameters'] = self.tc_idle()
            require(self.record['parameters']['target_lock'] == layout['lock_addr'] and
                    self.record['parameters']['komb_batch_size'] == 1024, 'TCLock binding differs')
        if self.loaded_kd:
            (KD_PARAMS / 'bench_lock_addr').write_text(str(layout['gate_addr']))
            self.record['parameters'] = params = parameters()
            expected = dict(bench_lock_addr=layout['gate_addr'], bench_quiet=1, bench_complete_probe=1, jit_timing=0,
                            spin_entry_ratio_limit=self.record['spin_entry_ratio_limit'],
                            spin_delegate=int(self.record['delegate']), spin_prefetch=2, hotlock_stats=1)
            def number(value):
                return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value, 0)
            require(all(number(params[k]) == v for k, v in expected.items()) and
                    params['target_process'] == 'rb_worker', 'KD parameters differ')
            self.record.update(entry_range=[layout['entry'], layout['entry'] + 1])
            # Rwsem/rwlock readers have no delegated entry. Explicit rwsem
            # writer shells publish ABI2; spin snapshots delegate their reads.
            if self.has_entry():
                with open(DEVICE, 'rb', buffering=0) as device:
                    fcntl.ioctl(device, PREPARE)
                self.start_daemon()
                self.await_publication()
                if self.record['helper_waves']:
                    self.learn_helpers()
                self.stop_daemon()
                require(status()['writers'] == 0, 'translator writer still open', 'UNDRAINED')
        self.phase('warmup', dict(self.record, iterations=48000, duration_ms=0))
        self.save()

    def phase(self, label, spec):
        path = self.path / (label + '.spec.json')
        write_json(path, spec)
        raw = self.run([sys.executable, self.path.parent / 'source/bench/rwlock_compare/client.py',
                        '--spec', path], label + '.json', timeout=120)
        self.faults()
        m = json.loads(raw)
        require(m.get('data_ok') is True, 'client data validation failed', 'DATA_ERROR')
        peak = validate(m, spec)
        if peak:
            m['peak'] = peak
        self.counts(label)
        if self.loaded_tc and self.record['lock_kind'] in ('rwsem', 'mutex'):
            self.tc_idle()
        return m

    def measure(self):
        count_path = KD_PARAMS / 'bench_jit_bodies'
        complete_path = KD_PARAMS / 'bench_jit_completions'
        address_guard_path = KD_PARAMS / 'address_guard_count'
        before = int(count_path.read_text()) if self.loaded_kd else 0
        complete_before = int(complete_path.read_text()) if self.loaded_kd else 0
        self.record['address_guards_before'] = (int(address_guard_path.read_text())
            if self.loaded_kd and address_guard_path.exists() else None)
        publication = self.publication() if self.loaded_kd and self.has_entry() else None
        if publication:
            require(publication['source']['writers'] == 0,
                    'translator writer before measurement', 'UNDRAINED')
            self.record['published_before'] = publication
        if self.loaded_tc:
            self.record['tclock_before'] = self.tc_idle()
        self.record.update(execution_status='MEASURING', jit_before=before, jit_complete_before=complete_before)
        self.save()
        m = self.phase('measure', self.record)
        self.record['measurement'] = m
        after = int(count_path.read_text()) if self.loaded_kd else 0
        complete_after = int(complete_path.read_text()) if self.loaded_kd else 0
        self.record['jit_after'] = after
        self.record['jit_complete_after'] = complete_after
        guard_before = self.record['address_guards_before']
        guard_after = int(address_guard_path.read_text()) if guard_before is not None else None
        self.record.update(address_guards_after=guard_after,
                           address_guard_exits=guard_after - guard_before
                           if guard_before is not None else None)
        snapshot_entry = self.record['lock_kind'] == 'spin'
        self.record.update(jit_evidence(before, after, m['reads'] if snapshot_entry else m['writes'],
                                        backend=self.record['arm'], delegate=self.record['delegate'],
                                        operation='snapshot' if snapshot_entry else 'writer',
                                        completed=complete_after - complete_before))
        if publication:
            after_publication = self.publication()
            self.record['published_after'] = after_publication
            require(publication == after_publication,
                    'delegated-entry publication changed during measurement')
        if self.loaded_tc:
            self.record['tclock_after'] = self.tc_idle()
        self.record['tclock_delegation_status'] = 'UNMEASURED' if self.loaded_tc else 'NOT_APPLICABLE'
        self.save()
        require(not self.record['require_jit'] or self.record['jit_completions'] > 0,
                'required complete KD body did not execute', 'NO_JIT')

    def cleanup(self):
        if self.loaded_tc:
            self.faults()
            if self.loaded_source:
                self.counts('tclock-drain')
            self.record['tclock_drained'] = self.tc_idle()
            (self.tc_params / 'target_lock').write_text('0')
        super().cleanup()
        if self.loaded_tc:
            self.record['drained'] = False
            self.save()
            self.run(['rmmod', self.tc_module], 'unload-tclock.log')
            self.loaded_tc = False
            self.faults()
            self.record['drained'] = True
