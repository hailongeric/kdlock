"""Reuse the cacheline data oracle with a real TCLock native-delegation arm.

Each session owns a freshly loaded source and backend. No JIT classification is
assigned to TCLock; its unlock/completion counters must agree after worker join.
"""
import json
from pathlib import Path
import time

from bench_runtime import ROOT, HERE, require
from bench_session import Session

TC_MODULE = ROOT / 'tclock_backend/tclock_backend_km.ko'
GUARD_MODULE = ROOT / 'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'


def tc_parameters():
    return {p.name: int(p.read_text()) for p in
            Path('/sys/module/tclock_backend_km/parameters').iterdir()}


class BackendSession(Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loaded_tc = False
        self.record['preparation_cpus'] = [self.record['cpus'][0]]

    def phase(self, label, iterations):
        if label in ('warmup', 'promotion'):
            # Steady-state comparison: finish discovery/publication before
            # introducing contention, identically for all three backends.
            # Keep the failed concurrent-promotion run as separate evidence;
            # this preparation policy does not fix that kdlock cold-path bug.
            spec = dict(self.record, threads=1, cpus=self.record['preparation_cpus'],
                        cpu_nodes=self.record['cpu_nodes'][:1])
            return super().phase(label, iterations, spec=spec)
        return super().phase(label, iterations)

    def prepare(self):
        # Equal, unmeasured preparation in every arm. Linux 6.1's reserved
        # allocator can retain a stale cross-page hint after TCLock unload.
        # Normal page allocation/free refreshes it without kernel changes.
        self.run(['insmod', GUARD_MODULE], 'load-allocator-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-allocator-guard.log')
        if self.record['arm'] != 'tclock':
            return super().prepare()
        self.run(['insmod', self.workload_module], 'load-source.log')
        self.loaded_source = True
        layout = json.loads(self.run([HERE/'client', '--layout'], 'layout.json'))
        self.record['layout'] = layout
        require(self.counts('initial')['values'] == [0]*16, 'source was not reset')
        self.run(['insmod', TC_MODULE, f'target_lock={layout["lock_addr"]}',
                  'komb_batch_size=1024'], 'load-tclock.log')
        self.loaded_tc = True
        params = tc_parameters()
        require(params['target_lock'] == layout['lock_addr'] and
                params['komb_batch_size'] == 1024 and params['quiescent'] == 1,
                'TCLock identity/initial state differs')
        self.record['parameters'] = params
        self.phase('warmup', 1)
        time.sleep(1)
        self.phase('promotion', 12000)
        time.sleep(2)
        self.record['prepared_ns'] = time.monotonic_ns()
        self.save()

    def measure(self):
        if self.record['arm'] != 'tclock':
            super().measure()
            require(self.record['arm'] != 'kdlock' or self.record['threads'] == 1 or
                    self.record['jit_bodies'] > 0, 'contended kdlock arm had no actual JIT', 'NO_JIT')
            self.record.update(delegated_bodies=self.record['jit_bodies'],
                               delegation_share=self.record['jit_share'],
                               delegation_status=self.record['jit_status'])
            self.save()
            return
        before = tc_parameters()
        require(before['quiescent'] == 1 and before['delegated'] == before['completed'],
                'TCLock preparation did not drain', 'UNDRAINED')
        self.record.update(execution_status='MEASURING', tclock_before=before)
        self.save()
        measurement = self.phase('measure', self.record['iterations'])
        self.record['measurement'] = measurement
        after = tc_parameters()
        count = after['completed'] - before['completed']
        require(after['quiescent'] == 1 and after['delegated'] == after['completed'],
                'TCLock completion mismatch', 'UNDRAINED')
        require(0 <= count <= measurement['completed'], 'invalid delegation count')
        require(self.record['threads'] == 1 or count > 0,
                'contended TCLock arm did not execute any delegated body', 'NO_DELEGATION')
        self.record.update(tclock_after=after, delegated_bodies=count,
                           delegation_share=count/measurement['completed'],
                           delegation_status='TCLOCK' if count else 'NO_DELEGATION',
                           jit_bodies=0, jit_share=0, jit_status='NOT_APPLICABLE')
        self.save()

    def cleanup(self):
        if self.loaded_tc:
            self.faults()
            require(self.counts('tclock-drain')['active'] == 0, 'active TCLock workers', 'UNDRAINED')
            params = tc_parameters()
            require(params['quiescent'] == 1 and params['delegated'] == params['completed'],
                    'active TCLock stack/queue', 'UNDRAINED')
            self.record['tclock_drained'] = params
            # Restore the hook while its target source is still loaded.
            self.run(['rmmod', 'tclock_backend_km'], 'unload-tclock.log')
            self.loaded_tc = False
        super().cleanup()
