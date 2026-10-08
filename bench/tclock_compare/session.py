"""Reuse the cacheline data oracle with a real TCLock native-delegation arm.

Each session owns a freshly loaded source and backend. TCLock spin keeps its
uninstrumented protocol. The separate mutex port counts returned batches to
prove that its native stack delegation executes; neither uses the KD runtime.
"""
import json
import re
from pathlib import Path
import time

from bench_runtime import (ROOT, HERE, PROVIDER, require, parameters, registry,
                           children, status, Failure)
from bench_session import Session

TC_MODULE = ROOT / 'tclock_backend/tclock_backend_km.ko'
TC_MUTEX_MODULE = ROOT / 'tclock_backend/tclock_mutex_backend_km.ko'
GUARD_MODULE = ROOT / 'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'


def tc_parameters(lock_kind='spin'):
    return {p.name: int(p.read_text()) for p in
            Path('/sys/module/' + ('tclock_mutex_backend_km' if lock_kind == 'mutex' else 'tclock_backend_km') + '/parameters').iterdir()}


def tc_quiescent(params, lock_kind='spin'):
    # Exact parameter identity also rejects accidentally loading the previous
    # instrumented module. Protocol node/count state remains part of the oracle.
    expected = {'target_lock', 'komb_batch_size', 'quiescent'}
    if lock_kind == 'mutex':
        expected |= {'delegated', 'batches', 'parks'}
    require(set(params) == expected,
            'unexpected TCLock module parameters')
    require(params['quiescent'] == 1, 'active TCLock stack/queue', 'UNDRAINED')


def hash_layout(layout):
    # Reject an old module that still inserts per-operation scheduling points.
    require((layout['workload'], layout['buckets'], layout['entries'],
             layout['key_range'], layout['resched']) ==
            ('rcuht', 1024, 4096, 8192, 0), 'hash payload configuration differs')


def check_kd_parameters(params, record, lock_addr):
    # Parameter identity rejects an old provider that can disable mutex JIT.
    # Returned-body evidence remains a separate execution requirement.
    require(params['bench_quiet'] == 'Y' and params['jit_timing'] == 'N' and
            int(params['bench_lock_addr']) == lock_addr and
            'hotlock_mode' not in params and 'mutex_jit' not in params and
            int(params['spin_entry_ratio_limit']) == record['spin_entry_ratio_limit'] and
            int(params['spin_prefetch']) == record['spin_prefetch'] and
            'spin_cold_fastpath' not in params and 'spin_hot_min_queue' not in params and
            params['spin_delegate'] == ('N' if record.get('spin_delegate') == 'off' else 'Y'),
            'kdlock observation parameters differ')


def check_jit_evidence(record):
    # A policy may select self-execution. Keep NO_JIT explicit and retain all
    # publication/body counters; contended protocol positives still fail
    # without a returned body. Valid throughput is not JIT acceptance.
    if (record['arm'] == 'kdlock' and record.get('lock_kind', 'spin') == 'spin' and
            record.get('spin_delegate', 'on') == 'off'):
        require(record.get('jit_bodies', 0) == 0, 'disabled control executed JIT')
        record['jit_acceptance'] = 'DISABLED_CONTROL'
        return
    # Adaptive admission samples actual MCS entries. Small cohorts can become
    # hot; do not infer native-only execution from their thread count.
    if (record['arm'] == 'kdlock' and record['threads'] in (2, 3) and
            record.get('scenario', 'plain') == 'plain' and
            not record.get('functional', False)):
        # Fast/pending acquisitions and native MCS queue heads can complete
        # without a serviceable follower. Preserve small-group performance data
        # while keeping zero returned bodies distinct from a JIT positive.
        record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0
                                    else 'NO_JIT_LOW_CONTENTION')
        return
    required = (record['arm'] == 'kdlock' and record['threads'] > 1 and
                (record.get('functional', False) or record['threads'] >= 20 or
                 (record.get('lock_kind') == 'mutex' and record['threads'] >= 4) or
                 record.get('scenario', 'plain') in ('nested', 'early')))
    record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0 else 'NO_JIT')
    require(not required or record['jit_bodies'] > 0,
            'contended kdlock arm had no actual JIT', 'NO_JIT')


class BackendSession(Session):
    def run(self, args, log, **kwargs):
        # Every client command, including prepare and drain, checks the loaded
        # payload identity. A hash module must never satisfy a cacheline run.
        if args[0] == HERE/'client' and self.lock_kind == 'mutex':
            args = [*args, '--lock-kind', 'mutex']
        if args[0] == HERE/'client' and self.record.get('workload') == 'rcuht':
            args = [*args, '--workload', 'rcuht']
        if args[0] == HERE/'client' and log == 'measure.json' and self.record.get('pmu'):
            # Count the measured client and its pinned workers, excluding module
            # load, translation and warmup. PMU output stays separate from data.
            args = ['perf', 'stat', '-x', ';', '-o', self.path/'pmu.csv',
                    '-e', 'cycles,instructions,task-clock,context-switches,cpu-migrations',
                    '--', *args]
        return super().run(args, log, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loaded_tc = False
        self.lock_kind = self.record.get('lock_kind', 'spin')
        self.tc_module = TC_MUTEX_MODULE if self.lock_kind == 'mutex' else TC_MODULE
        self.tc_params = Path('/sys/module') / self.tc_module.stem / 'parameters'

    def prepare(self):
        # Equal, unmeasured preparation in every arm. Linux 6.1's reserved
        # allocator can retain a stale cross-page hint after TCLock unload.
        # Normal page allocation/free refreshes it without kernel changes.
        self.run(['insmod', GUARD_MODULE], 'load-allocator-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-allocator-guard.log')
        if self.record['arm'] == 'kdlock':
            self.run(['insmod', PROVIDER, 'bench_quiet=1', 'jit_timing=0', 'hotlock_stats=1',
                      'target_process=sc_worker',
                      'spin_entry_ratio_limit=' + str(self.record['spin_entry_ratio_limit']),
                      'spin_prefetch=' + str(self.record['spin_prefetch']),
                      'spin_delegate=' + ('0' if self.record.get('spin_delegate') == 'off' else '1')],
                     'load-kdlock.log')
            self.loaded_kd = True
        elif self.record['arm'] == 'tclock':
            self.run(['insmod', self.tc_module, 'komb_batch_size=1024'], 'load-tclock.log')
            self.loaded_tc = True
        # The module's direct references pin its backend. Source loading must
        # follow backend loading; retirement releases the reverse source pin.
        self.run(['insmod', self.workload_module], 'load-source.log')
        self.loaded_source = True
        layout = json.loads(self.run([HERE/'client', '--layout'], 'layout.json'))
        self.record['layout'] = layout
        if self.record.get('workload') == 'rcuht':
            hash_layout(layout)
        require(self.counts('initial')['values'] == [0]*16, 'source was not reset')
        if self.loaded_tc:
            (self.tc_params/'target_lock').write_text(
                str(layout['lock_addr']))
            params = tc_parameters(self.lock_kind)
            tc_quiescent(params, self.lock_kind)
            require(params['target_lock'] == layout['lock_addr'] and
                    params['komb_batch_size'] == 1024 and params['quiescent'] == 1,
                    'TCLock identity/initial state differs')
            self.record['parameters'] = params
        if self.loaded_kd:
            Path('/sys/module/kdlock_km/parameters/bench_lock_addr').write_text(
                str(layout['lock_addr']))
            params = parameters()
            check_kd_parameters(params, self.record, layout['lock_addr'])
            self.record['parameters'] = params
            prefix = 'mc' if self.lock_kind == 'mutex' else 'sc'
            source_tag = f'[{self.workload_module.stem}]'
            symbol = f'{prefix}_body_{self.record["cachelines"]}'
            found = [int(s[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
                     if len(s := line.split()) == 4 and s[2:] == [symbol, source_tag]]
            nm = self.run(['nm', '-S', self.workload_module], 'symbols.txt')
            sizes = [int(s[1], 16) for line in nm.splitlines()
                     if len(s := line.split()) == 4 and s[3] == symbol]
            require(len(found) == len(sizes) == 1 and found[0], 'unknown CS symbol')
            self.record['entry_range'] = [found[0], found[0] + sizes[0]]
            if self.record.get('scenario', 'plain') != 'plain':
                entry_name = f'{prefix}_entry_{self.record["cachelines"]}'
                roots = [int(s[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
                         if len(s := line.split()) == 4 and s[2:] == [entry_name, source_tag]]
                require(len(roots) == 1, 'ambiguous direct root continuation')
                self.record['root_entry'] = roots[0]
        self.record['prepare'] = json.loads(self.run(
            [HERE/'client', '--prepare', '--cachelines', self.record['cachelines']],
            'prepare.json'))
        if self.loaded_kd:
            self.start_daemon()
            deadline = time.monotonic() + 90
            while True:
                self.faults()
                require(self.daemon.poll() is None, 'daemon exited during preparation')
                log = (self.path/'daemon.log').read_text()
                require(not re.search(r'\[KD_JIT\]\[ERROR\]|Traceback|command failed', log),
                        'translator failed; see daemon.log')
                metrics = [json.loads(line.split(' ', 1)[1]) for line in log.splitlines()
                           if line.startswith('KD_TRANSLATION_METRICS ')]
                require(all(m['result'] == 0 and m['status'] == 0 for m in metrics),
                        'translation failed or refused')
                r = registry()
                require(len(r) == 1 and r[0]['status'] in (-1, 0),
                        'explicit preparation did not register one valid entry')
                if r[0]['status'] == 0 and metrics and not children(self.daemon.pid):
                    self.record['translation'] = metrics
                    self.publication()
                    break
                if time.monotonic() >= deadline:
                    raise Failure('TIMEOUT', 'explicit publication timed out', unsafe=True)
                time.sleep(0.1)
            self.stop_daemon()
            require(status()['writers'] == 0, 'translator writer still open', 'UNDRAINED')
        # Warm every measured CPU with the same worker cohort geometry. The
        # client joins and validates all workers before measurement snapshots
        # its counters; an added idle delay would age the warmed lock state.
        self.phase('warmup', self.record['warmup_iterations_per_worker'])
        self.record['prepared_ns'] = time.monotonic_ns()
        self.save()

    def measure(self):
        if self.record['arm'] != 'tclock':
            super().measure()
            check_jit_evidence(self.record)
            self.record.update(delegated_bodies=self.record['jit_bodies'],
                               delegation_share=self.record['jit_share'],
                               delegation_status=self.record['jit_status'])
            self.save()
            return
        before = tc_parameters(self.lock_kind)
        tc_quiescent(before, self.lock_kind)
        self.record.update(execution_status='MEASURING', tclock_before=before)
        self.save()
        measurement = self.phase('measure', self.record['iterations'])
        self.record['measurement'] = measurement
        after = tc_parameters(self.lock_kind)
        tc_quiescent(after, self.lock_kind)
        self.record.update(tclock_after=after, delegated_bodies=None,
                           delegation_share=None, delegation_status='UNMEASURED',
                           jit_bodies=0, jit_share=0, jit_status='NOT_APPLICABLE')
        if self.lock_kind == 'mutex':
            delegated = after['delegated'] - before['delegated']
            require(0 <= delegated <= measurement['completed'], 'invalid TCLock delegation count')
            require(self.record['threads'] < 4 or delegated > 0,
                    'contended TCLock mutex never delegated', 'NO_DELEGATION')
            self.record.update(delegated_bodies=delegated,
                delegation_share=delegated / measurement['completed'],
                delegation_status='PASS' if delegated else 'NO_DELEGATION_UNCONTENDED')
        self.save()

    def cleanup(self):
        if self.loaded_tc:
            self.faults()
            if self.loaded_source:
                require(self.counts('tclock-drain')['active'] == 0, 'active TCLock workers', 'UNDRAINED')
            params = tc_parameters(self.lock_kind)
            tc_quiescent(params, self.lock_kind)
            self.record['tclock_drained'] = params
            # Clear the diagnostic pointer before its lock storage disappears.
            (self.tc_params/'target_lock').write_text('0')
        super().cleanup()
        if self.loaded_tc:
            self.record['drained'] = False
            self.save()
            self.run(['rmmod', self.tc_module.stem], 'unload-tclock.log')
            self.loaded_tc = False
            self.faults()
            self.record['drained'] = True
