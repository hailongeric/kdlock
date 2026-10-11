"""Rwlock preparation, returned-writer evidence and strict source/queue drain."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
from bench_runtime import Failure, children, parameters, registry, require, status
from bench_session import Session
from summarize import write_json
from protocol import DEVICE, PREPARE, snapshot
from oracle import check_snapshot, jit_evidence, validate

TC_PARAMS = Path('/sys/module/tclock_rwlock_backend_km/parameters')
KD_PARAMS = Path('/sys/module/kdlock_km/parameters')


class RWSession(Session):
    def __init__(self, out, spec, binaries):
        super().__init__(out, spec, workload_module=binaries['workloads'][spec['variant']])
        self.binaries = binaries
        self.loaded_tc = False

    def counts(self, label):
        row = snapshot()
        write_json(self.path / (label + '.counts.json'), row)
        check_snapshot(row, self.record)
        return row

    def tc_idle(self):
        row = {p.name: int(p.read_text()) for p in TC_PARAMS.iterdir()}
        require(row['quiescent'] == 1, 'TCLock rwlock contexts/queue remain active', 'UNDRAINED')
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

    def prepare(self):
        self.run(['insmod', self.binaries['guard']], 'load-allocator-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-allocator-guard.log')
        if self.record['arm'] == 'kdlock':
            self.run(['insmod', self.binaries['kdlock'], 'bench_quiet=1', 'jit_timing=0',
                      'hotlock_stats=1', 'target_process=rb_worker', 'spin_prefetch=2',
                      'mutex_blocking=' + str(int(self.record.get('mutex_wait_mode') == 'blocking')),
                      'mutex_spin_limit=' + str(self.record.get('mutex_spin_limit', 1024)),
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
            (TC_PARAMS / 'target_lock').write_text(str(layout['lock_addr']))
            self.record['parameters'] = self.tc_idle()
            require(self.record['parameters']['target_lock'] == layout['lock_addr'] and
                    self.record['parameters']['komb_batch_size'] == 1024, 'TCLock binding differs')
        if self.loaded_kd:
            (KD_PARAMS / 'bench_lock_addr').write_text(str(layout['gate_addr']))
            self.record['parameters'] = params = parameters()
            expected = dict(bench_lock_addr=layout['gate_addr'], bench_quiet=1, jit_timing=0,
                            mutex_blocking=int(self.record.get('mutex_wait_mode') == 'blocking'),
                            mutex_spin_limit=self.record.get('mutex_spin_limit', 1024),
                            spin_entry_ratio_limit=self.record['spin_entry_ratio_limit'],
                            spin_delegate=int(self.record['delegate']), spin_prefetch=2, hotlock_stats=1)
            def number(value):
                return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value, 0)
            require(all(number(params[k]) == v for k, v in expected.items()) and
                    params['target_process'] == 'rb_worker', 'KD parameters differ')
            self.record.update(entry_range=[layout['entry'], layout['entry'] + 1], caller_abi='clobber', entry_abi=3)
            # Read-only sessions have no writer continuation to execute. Keep
            # them as explicit native-reader controls, without a fake JIT pass.
            if self.record['write_percent']:
                with open(DEVICE, 'rb', buffering=0) as device:
                    fcntl.ioctl(device, PREPARE)
                self.start_daemon()
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
                    require(len(rows) == 1 and rows[0]['entry'] == layout['entry'] and
                            rows[0]['status'] in (-1, 0), 'unexpected writer registry')
                    if rows[0]['status'] == 0 and metrics and not children(self.daemon.pid):
                        self.record['translation'] = metrics
                        self.record['publication'] = self.publication()
                        break
                    if time.monotonic() >= deadline:
                        raise Failure('TIMEOUT', 'writer publication timed out', unsafe=True)
                    time.sleep(0.1)
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
        return m

    def measure(self):
        count_path = KD_PARAMS / 'bench_jit_bodies'
        before = int(count_path.read_text()) if self.loaded_kd else 0
        publication = self.publication() if self.loaded_kd and self.record['write_percent'] else None
        if self.loaded_tc:
            self.record['tclock_before'] = self.tc_idle()
        self.record.update(execution_status='MEASURING', jit_before=before)
        self.save()
        m = self.phase('measure', self.record)
        self.record['measurement'] = m
        after = int(count_path.read_text()) if self.loaded_kd else 0
        self.record['jit_after'] = after
        self.record.update(jit_evidence(before, after, m['writes'], backend=self.record['arm'],
                                        delegate=self.record['delegate']))
        if publication:
            require(publication == self.publication(), 'writer publication changed during measurement')
        if self.loaded_tc:
            self.record['tclock_after'] = self.tc_idle()
        self.record['tclock_delegation_status'] = 'UNMEASURED' if self.loaded_tc else 'NOT_APPLICABLE'
        self.save()
        require(not self.record['require_jit'] or self.record['jit_bodies'] > 0,
                'required KD writer JIT did not execute', 'NO_JIT')

    def cleanup(self):
        if self.loaded_tc:
            self.faults()
            if self.loaded_source:
                self.counts('tclock-drain')
            self.record['tclock_drained'] = self.tc_idle()
            (TC_PARAMS / 'target_lock').write_text('0')
        super().cleanup()
        if self.loaded_tc:
            self.record['drained'] = False
            self.save()
            self.run(['rmmod', 'tclock_rwlock_backend_km'], 'unload-tclock.log')
            self.loaded_tc = False
            self.faults()
            self.record['drained'] = True
