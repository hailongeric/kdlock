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
PROFILE_MODULE = ROOT / 'tests/kernel/mutex/profile/kd_mutex_profile.ko'


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


def parse_owned_preflight_profile(messages, record):
    """Separate optional diagnostic receipt; historical lock_profile is unchanged."""
    enabled = record.get('profile_owned_preflight', False)
    require(type(enabled) is bool, 'invalid owned preflight profile flag')
    rows = re.findall(r'kd_mutex_profile ownedpreflight: ([^\n]+)', messages)
    if not enabled:
        require(not rows, 'unexpected owned preflight profile receipt')
        return None
    require(record.get('profile_lock') and record.get('diagnostic') and
            record.get('arm') == 'kdlock' and record.get('mutex_implementation') == 'owned-v1' and
            record.get('owned_preflight_policy') == 'c_abi_v1',
            'owned preflight profile requires an unscored owned C-ABI gate')
    require(len(rows) == 1, 'missing or duplicate owned preflight profile receipt')
    fields = {'gate_self', 'gate_capture', 'optimistic_acquired', 'optimistic_busy',
              'optimistic_self', 'optimistic_other', 'missed'}
    tokens = rows[0].split()
    require(all(re.fullmatch(r'[a-z_]+=[0-9]+', token) for token in tokens),
            'malformed owned preflight profile counters')
    pairs = [token.split('=', 1) for token in tokens]
    require(len(pairs) == len(fields) and {key for key, _ in pairs} == fields,
            'incomplete owned preflight profile counters')
    result = {key: int(value) for key, value in pairs}
    require(result['missed'] == result['optimistic_other'] == 0,
            'owned preflight profile missed returns or saw an unknown enum')
    require(result['optimistic_acquired'] + result['optimistic_self'] <= result['gate_self'] and
            result['gate_capture'] <= result['optimistic_busy'] and
            result['optimistic_acquired'] + result['optimistic_busy'] + result['optimistic_self'] <=
            result['gate_self'] + result['gate_capture'],
            'owned preflight profile outcomes are inconsistent')
    return result


def check_kd_parameters(params, record, lock_addr):
    # Parameter identity rejects an old provider that can disable mutex JIT.
    # Returned-body evidence remains a separate execution requirement.
    require(params['bench_quiet'] == 'Y' and params['jit_timing'] == 'N' and
            int(params['bench_lock_addr']) == lock_addr and
            'hotlock_mode' not in params and 'mutex_jit' not in params and
            int(params['spin_entry_ratio_limit']) == record['spin_entry_ratio_limit'] and
            int(params['spin_prefetch']) == record['spin_prefetch'] and
            'spin_cold_fastpath' not in params and 'spin_hot_min_queue' not in params and
            'mutex_blocking' not in params and record['mutex_wait_mode'] == 'blocking' and
            params['spin_delegate'] == ('N' if record.get('spin_delegate') == 'off' else 'Y'),
            'kdlock observation parameters differ')
    if record.get('mutex_implementation', 'legacy') == 'owned-v1':
        require({'owned_mutex_spin_limit', 'owned_mutex_entry_ratio_limit',
                 'owned_mutex_self_route', 'owned_mutex_native_after_control'} <= set(params),
                'missing owned mutex provider parameters')
        require(record.get('mutex_routing', 'adaptive') in ('adaptive', 'self') and
                int(params['owned_mutex_spin_limit']) == record['mutex_spin_limit'] and
                int(params['owned_mutex_entry_ratio_limit']) == record['owned_mutex_entry_ratio_limit'] and
                params['owned_mutex_self_route'] == ('Y' if record.get('mutex_routing') == 'self' else 'N') and
                params['mutex_native_route'] == 'N' and
                int(params['owned_mutex_native_after_control']) ==
                int(record.get('owned_mutex_force_full', False)),
                'owned mutex observation parameters differ')
        # The initial finite-FIFO archive predates this opt-in control.
        require(('owned_mutex_refill' not in record or 'owned_mutex_refill' in params) and
                params.get('owned_mutex_refill', 'N') ==
                ('Y' if record.get('owned_mutex_refill', False) else 'N'),
                'owned FIFO refill parameter differs')
        policy = record.get('owned_preflight_policy')
        budget = record.get('owned_mutex_preflight_spins')
        enabled = record.get('owned_mutex_preflight')
        require('owned_mutex_preflight' not in record or (type(enabled) is bool and
                policy == ('c_abi_v1' if enabled else 'capture_first')),
                'owned preflight compile-time policy differs')
        require((policy is None and budget is None and
                 int(params.get('owned_mutex_preflight_spins', 0)) == 0) or
                (policy == 'capture_first' and enabled is False and type(budget) is int and budget == 0 and
                 'owned_mutex_preflight_spins' in params and int(params['owned_mutex_preflight_spins']) == 0) or
                (policy == 'c_abi_v1' and type(budget) is int and
                 budget in (0, 64, 256, 1024, 4096) and
                 'owned_mutex_preflight_spins' in params and
                 int(params['owned_mutex_preflight_spins']) == budget),
                'owned preflight policy or parameter differs')
        queued = record.get('owned_mutex_preflight_queue')
        require((queued is None and params.get('owned_mutex_preflight_queue', 'N') == 'N') or
                (type(queued) is bool and 'owned_mutex_preflight_queue' in params and
                 params['owned_mutex_preflight_queue'] == ('Y' if queued else 'N') and
                 (not queued or (policy == 'c_abi_v1' and budget > 0))),
                'owned queued preflight policy or parameter differs')
    else:
        require(int(params['mutex_spin_limit']) == record['mutex_spin_limit'] and
                int(params['mutex_entry_ratio_limit']) == record['mutex_entry_ratio_limit'] and
                params['mutex_native_route'] == ('Y' if record.get('mutex_routing') == 'native' else 'N'),
                'kdlock observation parameters differ')


def check_jit_evidence(record):
    # A policy may select self-execution. Keep NO_JIT explicit and retain all
    # publication/body counters; contended protocol positives still fail
    # without a returned body. Valid throughput is not JIT acceptance.
    record['execution_class'] = ('NATIVE' if record['arm'] == 'native' else
                                 'JIT' if record.get('jit_bodies', 0) > 0 else 'NO_JIT')
    if record['arm'] == 'kdlock' and record.get('lock_kind') == 'mutex':
        owned = record.get('mutex_implementation', 'legacy') == 'owned-v1'
        if owned:
            require(record.get('mutex_routing', 'adaptive') != 'native',
                    'owned mutex cannot use a Linux native route')
            record['execution_class'] = 'JIT' if record.get('jit_bodies', 0) > 0 else 'KD_SELF'
        if record.get('mutex_routing') == 'self':
            require(owned and record.get('jit_bodies', 0) == 0, 'self routing control executed JIT or is not owned')
            require(not record.get('functional', False), 'self control is not a functional JIT check')
            record.update(jit_acceptance='SELF_ROUTING_CONTROL', execution_class='KD_SELF', diagnostic=True)
            return
        if record.get('mutex_routing', 'adaptive') == 'native':
            require(record.get('jit_bodies', 0) == 0, 'native routing control executed JIT')
            require(not record.get('functional', False), 'native control is not a functional JIT check')
            record.update(jit_acceptance='NATIVE_ROUTING_CONTROL',
                          execution_class='NATIVE_ROUTING_CONTROL', diagnostic=True)
            return
        if record.get('mutex_acceptance', 'jit-required') == 'adaptive-performance':
            require(not record.get('functional', False), 'adaptive performance is not a functional JIT check')
            record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0 else
                                        'ADAPTIVE_SELF' if owned else 'ADAPTIVE_NATIVE')
            record['execution_class'] = ('JIT' if record.get('jit_bodies', 0) > 0 else
                                         'KD_SELF' if owned else 'ADAPTIVE_NATIVE')
            return
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
    def mutex_wait_stats(self):
        if self.record.get('mutex_implementation', 'legacy') != 'owned-v1':
            return super().mutex_wait_stats()
        values = list(map(int, Path('/sys/module/kdlock_km/parameters/owned_mutex_wait_stats').read_text().split()))
        require(len(values) == 3 and all(v >= 0 for v in values), 'invalid owned mutex wait observations')
        return dict(zip(('result_schedule_calls', 'result_wakes', 'gate_wait_calls'), values))

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
                    '-e', 'cycles,instructions,cache-misses,task-clock,context-switches,cpu-migrations',
                    '--', *args]
        if args[0] == HERE/'client' and log == 'measure.json' and self.record.get('perf_record'):
            # Flat kernel PC samples avoid interpreting borrowed stack frames.
            # Resolve symbols while modules are still loaded, retain raw data
            # and the exact symbol map, and never score an instrumented run.
            for name in ('kallsyms', 'modules'):
                (self.path/name).write_text(Path('/proc', name).read_text())
            result = super().run(['perf', 'record', '--quiet', '--sample-cpu',
                '-e', 'cycles:k', '-F', '199',
                '-o', self.path/'perf.data', '--', *args], log, **kwargs)
            super().run(['perf', 'report', '--stdio', '--no-children',
                '--sort', 'comm,dso,symbol', '--percent-limit', '0.2',
                '--kallsyms', self.path/'kallsyms', '-i', self.path/'perf.data'],
                'perf-report.txt', timeout=60)
            super().run(['perf', 'script', '--show-lost-events',
                '--kallsyms', self.path/'kallsyms', '-i', self.path/'perf.data',
                '-F', 'comm,pid,tid,cpu,time,event,ip,sym,dso,period'],
                'perf-samples.txt', timeout=60)
            return result
        return super().run(args, log, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loaded_tc = False
        self.loaded_profile = False
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
            if self.record.get('mutex_implementation', 'legacy') == 'owned-v1':
                mutex_params = [
                    'owned_mutex_spin_limit=' + str(self.record['mutex_spin_limit']),
                    'owned_mutex_entry_ratio_limit=' + str(self.record['owned_mutex_entry_ratio_limit']),
                    'owned_mutex_refill=' + str(int(self.record.get('owned_mutex_refill', False))),
                    'owned_mutex_preflight_spins=' + str(self.record['owned_mutex_preflight_spins']),
                    'owned_mutex_preflight_queue=' + str(int(self.record.get('owned_mutex_preflight_queue', False))),
                    'owned_mutex_self_route=' + ('1' if self.record.get('mutex_routing') == 'self' else '0')]
            else:
                mutex_params = [
                    'mutex_spin_limit=' + str(self.record.get('mutex_spin_limit', 4096)),
                    'mutex_entry_ratio_limit=' + str(self.record['mutex_entry_ratio_limit']),
                    'mutex_native_route=' + ('1' if self.record.get('mutex_routing') == 'native' else '0')]
            if self.record.get('owned_mutex_force_full'):
                mutex_params.append('owned_mutex_native_after_control=1')
            self.run(['insmod', PROVIDER, 'bench_quiet=1', 'jit_timing=0', 'hotlock_stats=1',
                      'target_process=sc_worker', *mutex_params,
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
        if self.record.get('mutex_implementation', 'legacy') == 'owned-v1':
            require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                    layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0,
                    'owned c01 lock/payload layout differs from the 32-byte aligned contract')
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
        if self.record.get('profile_lock'):
            counter = 0
            owned = self.record.get('mutex_implementation') == 'owned-v1'
            if self.loaded_kd:
                counter_symbol = 'kd_owned_mutex_bodies' if owned else 'kd_mutex_jit_success_count'
                symbols = [int(s[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
                           if len(s := line.split()) == 4 and
                           s[2:] == [counter_symbol, '[kdlock_km]']]
                require(len(symbols) == 1 and symbols[0], 'missing batch completion counter')
                counter = symbols[0]
            preflight = self.record.get('profile_owned_preflight', False)
            require(not preflight or (owned and
                    self.record.get('owned_preflight_policy') == 'c_abi_v1' and
                    self.record.get('diagnostic')),
                    'owned preflight probes require an unscored C-ABI gate')
            extra_profile = ['preflight=1'] if preflight else []
            self.run(['taskset', '-c', str(self.record['collector_cpu']), 'insmod', PROFILE_MODULE,
                      'target_lock=' + str(self.record['layout']['lock_addr']),
                      'success_counter=' + str(counter), 'kd=' + str(int(self.loaded_kd)),
                      'owned=' + str(int(owned)),
                      'spin=' + str(int(self.lock_kind == 'spin')), *extra_profile], 'load-profile.log')
            self.loaded_profile = True
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
        if getattr(self, 'loaded_profile', False):
            self.faults()
            require(self.counts('profile-drain')['active'] == 0, 'profiler workers active', 'UNDRAINED')
            self.run(['rmmod', PROFILE_MODULE.stem], 'unload-profile.log')
            self.loaded_profile = False
            self.faults()
            rows = re.findall(r'kd_mutex_profile: ([^\n]+)', self.messages)
            require(len(rows) == 1, 'missing profiler receipt')
            observed = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', rows[0])}
            observed['batch_histogram'] = {int(k): int(v) for k, v in re.findall(
                r'kd_mutex_profile histogram: bucket=(\d+) batches=(\d+)', self.messages)}
            self.record['lock_profile'] = observed
            preflight = parse_owned_preflight_profile(self.messages, self.record)
            if preflight is not None:
                self.record['owned_preflight_profile'] = preflight
            if self.record.get('mutex_implementation') == 'owned-v1':
                owned_rows = re.findall(r'kd_mutex_profile owned: ([^\n]+)', self.messages)
                require(len(owned_rows) == 1, 'missing owned profiler receipt')
                detail = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', owned_rows[0])}
                observed['owned'] = detail
                require(observed['native_calls'] == observed['native_slow'] ==
                        detail['linux_target_unlocks'] == detail['missed'] == 0,
                        'owned target reached Linux mutex API or profile was incomplete')
            self.save()
            require(observed['missed'] == 0 and len(observed['batch_histogram']) == 12,
                    'incomplete lock profile')
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
        if self.record.get('mutex_implementation') == 'owned-v1':
            rows = re.findall(r'kd_owned_mutex: bodies=(\d+) batches=(\d+) refusals=(\d+) early_releases=(\d+)',
                              self.messages)
            require(len(rows) == 1, 'missing owned provider drain observations')
            self.record['owned_observations'] = dict(zip(
                ('bodies', 'batches', 'refusals', 'early_releases'), map(int, rows[0])))
            if self.record.get('scenario') == 'early':
                require(self.record['owned_observations']['early_releases'] > 0,
                        'early-release scenario never released a delegated outer mutex')
            if self.record.get('owned_mutex_force_full'):
                require('reason=OWNED_CONTROL_NATIVE ' in self.messages,
                        'checked post-control continuation was not exercised')
                acks = re.findall(r'kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)',
                                  self.messages)
                require(len(acks) == 1, 'missing FULL owner-ACK observations')
                started, completed, unlocks = map(int, acks[0])
                self.record['owned_full_ack'] = dict(started=started, completed=completed, unlocks=unlocks)
                require(started == completed and started > 0 and unlocks >= 2,
                        'forced FULL continuation did not drain both owner acknowledgments')
        if self.loaded_tc:
            self.record['drained'] = False
            self.save()
            self.run(['rmmod', self.tc_module.stem], 'unload-tclock.log')
            self.loaded_tc = False
            self.faults()
            self.record['drained'] = True
