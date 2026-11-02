#!/usr/bin/env python3
"""Guest-only returned rwsem proxy body, downgraded read tail and fresh writer."""
import argparse
import ctypes
import fcntl
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
from bench_session import Session
import kernel_identity
from provider.prepare import prepare as prepare_provider

DEVICE, MODULE = '/dev/kd_rwsem_proxy', 'kd_rwsem_proxy_test'
HOLDER, EXECUTOR, WRITER, READER, PREDECESSOR = range(5)
COMM = ('krp_writer', 'krp_writer', 'krp_writer', 'krp_reader', 'krp_previous')
FIELDS = ('sem', 'gate', 'entry', 'active', 'errors', 'started', 'ready', 'done',
          'armed', 'predecessor_release', 'predecessor_done', 'holder_release',
          'reader_held', 'reader_release', 'prefix', 'tail_done', 'own_bodies', 'warm_ops',
          'warm_eligible', 'entry_checked', 'entry_eligible', 'g_task', 'c_task', 'w_task', 't_task',
          'owner', 'gate_state', 'tail', 'waiters', 'readers', 'admission',
          'generation', 'write_generation', 'own_generation')
RUN, WARMUP = 0xC0185201, 0xC0185207
SNAPSHOT = (2 << 30) | (len(FIELDS) * 8 << 16) | (ord('R') << 8) | 2
PREPARE, PREDECESSOR_RELEASE, HOLDER_RELEASE, READER_RELEASE, ARM, DRAIN = (
    (ord('R') << 8) | number for number in (3, 4, 5, 6, 8, 9))
PARAMETERS = Path('/sys/module/kdlock_km/parameters')
REQUIRED = (1 << HOLDER) | (1 << EXECUTOR) | (1 << WRITER)


def control(command):
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, command)


def snapshot():
    data = bytearray(len(FIELDS) * 8)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, data, True)
    return dict(zip(FIELDS, struct.unpack('=' + str(len(FIELDS)) + 'Q', data)))


def publish(path, value):
    temporary = path.with_suffix('.tmp')
    rt.write_json(temporary, value)
    temporary.replace(path)


def worker(arguments):
    role, cpu, iterations = map(int, arguments[:3])
    warm, receipt, go = arguments[3] == 'warm', Path(arguments[4]), Path(arguments[5])
    rt.require(0 <= role < 5 and arguments[3] in ('warm', 'test'), 'invalid worker role')
    comm = 'krp_writer' if warm else COMM[role]
    libc = ctypes.CDLL(None, use_errno=True)
    rt.require(libc.prctl(15, ctypes.c_char_p(comm.encode()), 0, 0, 0) == 0, 'worker comm failed')
    os.sched_setaffinity(0, {cpu})
    rt.require(os.sched_getaffinity(0) == {cpu}, 'worker affinity differs')
    data = bytearray(struct.pack('=2I2Q', role, iterations, 0, 0))
    with open(DEVICE, 'rb', buffering=0) as device:
        publish(receipt, dict(pid=os.getpid(), role=role, cpu=cpu, comm=comm))
        deadline = time.monotonic() + 360
        while not go.exists():
            rt.require(not (go.parent / 'abort-starts.json').exists(), 'unstarted worker canceled')
            rt.require(time.monotonic() < deadline, 'worker start barrier expired', 'TIMEOUT')
            time.sleep(.001)
        fcntl.ioctl(device, WARMUP if warm else RUN, data, True)
    returned_role, requested, returned, errors = struct.unpack('=2I2Q', data)
    print(json.dumps(dict(pid=os.getpid(), role=returned_role, cpu=cpu, comm=comm,
                          iterations=requested, returned=returned, errors=errors)))


def sources(root):
    hashes = {}
    for directory in ('include', 'kernel_module', 'daemon', 'disassem', 'kernel_baseline',
                      'kernel_integration/linux70', 'bench/spin_cacheline',
                      'bench/tclock_compare/allocator_guard', 'tests/protocols',
                      'tests/kernel/rwsem/proxy'):
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if (not path.is_file() or any(p.startswith('.') or p in ('__pycache__', 'results')
                                          for p in relative.parts) or path.name.endswith('.mod.c')):
                continue
            if (path.suffix in ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch', '.md') or
                    path.name in ('Makefile', 'requirements.txt', 'guest.config')):
                hashes[str(relative)] = rt.digest(path)
    return hashes


def idle():
    rt.idle()
    for name in (MODULE, 'rwsem_probe', 'kd_mutex_mixed_transfer', 'rwlock_bench', 'real_api',
                 'tc_allocator_guard', 'tclock_backend_km', 'tclock_mutex_backend_km',
                 'tclock_rwlock_backend_km', 'kd_mutex_local_probe', 'kd_spin_irq_api_test'):
        rt.require(not Path('/sys/module', name).exists(), 'existing module: ' + name)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            rt.require(path.read_text().strip() not in COMM, 'existing proxy fixture task: ' + str(path))
        except FileNotFoundError:
            pass


def trace_records(messages, prefix):
    result = []
    for line in messages.splitlines():
        if prefix in line:
            fields = line.split(prefix, 1)[1].strip().split()
            rt.require(all(field.count('=') == 1 for field in fields), 'malformed trace: ' + line)
            row = dict(field.split('=') for field in fields)
            rt.require(len(row) == len(fields), 'duplicate trace field: ' + line)
            result.append(row)
    return result


def observe_provider(provider):
    """Expose cached eligibility and existing diagnostic sinks in this build."""
    hotlock = provider / 'kernel_module/kd_hotlock.c'
    text = hotlock.read_text()
    anchor = ('bool kd_hotlock_query_mutex(unsigned long address) { '
              'return kd_hotlock_access(address, 1, false, false); }')
    export = 'EXPORT_SYMBOL_GPL(kd_hotlock_query_mutex);'
    rt.require(text.count(anchor) == 1 and export not in text, 'cached query overlay differs')
    records = [dict(path=str(hotlock.relative_to(provider)), before=rt.digest(hotlock))]
    hotlock.write_text(text.replace(anchor, anchor + '\n' + export))
    records[-1]['after'] = rt.digest(hotlock)
    for relative, addition in (
            ('include/kd_bench.h', '\nextern bool kd_rwsem_proxy_trace;\n'),
            ('kernel_module/kd_bench.c', '\nbool kd_rwsem_proxy_trace;\n'
             'module_param_named(rwsem_proxy_trace, kd_rwsem_proxy_trace, bool, 0644);\n')):
        path = provider / relative
        records.append(dict(path=relative, before=rt.digest(path)))
        path.write_text(path.read_text() + addition)
        records[-1]['after'] = rt.digest(path)
    # These are diagnostic-only sites in the runtime. Never change a branch,
    # request state, eligibility value or ownership update to obtain a trace.
    observed = 0
    for path in (provider / 'kernel_module').rglob('*'):
        if not path.is_file() or path.suffix not in ('.c', '.inc'):
            continue
        text = path.read_text()
        before = rt.digest(path)
        for prefix in ('kd_rwsem proxy:', 'kd_native begin:'):
            old = 'KD_PR_ROUTINE("' + prefix
            observed += text.count(old) if prefix == 'kd_rwsem proxy:' else 0
            replacement = ('if (READ_ONCE(kd_rwsem_proxy_trace)) pr_info("' + prefix
                           if prefix == 'kd_rwsem proxy:' else 'pr_info("' + prefix)
            text = text.replace(old, replacement)
        if text != path.read_text():
            path.write_text(text)
            records.append(dict(path=str(path.relative_to(provider)), before=before, after=rt.digest(path)))
    rt.require(observed > 0, 'runtime has no exact rwsem request diagnostic sites')
    return records


class ProxySession(Session):
    def __init__(self, out, spec, binaries, verify):
        super().__init__(out, spec, workload_module=binaries['payload'])
        self.binaries, self.verify = binaries, verify
        self.daemon_binary, self.translation_source = binaries['daemon'], out / 'source'
        self.callers, self.logs = [], []

    def counts(self, label):
        row = snapshot()
        rt.write_json(self.path / (label + '.counts.json'), row)
        rt.require(row['active'] == row['owner'] == row['gate_state'] == row['tail'] ==
                   row['waiters'] == row['readers'] == row['admission'] == 0,
                   'caller/lock records have not drained: ' + str(row), 'UNDRAINED')
        rt.require(not row['errors'], 'payload failed: ' + str(row), 'DATA_ERROR')
        if self.record.get('callers_joined'):
            control(DRAIN)
        return row

    def counters(self):
        return {name: int((PARAMETERS / name).read_text())
                for name in ('bench_jit_bodies', 'bench_jit_completions')}

    def prepare(self):
        self.verify()
        self.run(['insmod', self.binaries['guard']], 'load-guard.log')
        self.run(['rmmod', 'tc_allocator_guard'], 'unload-guard.log')
        self.run(['insmod', self.binaries['provider'], 'bench_quiet=1', 'bench_complete_probe=1',
                  'jit_timing=0', 'target_process=krp_writer'], 'load-provider.log')
        self.loaded_kd = True
        self.run(['insmod', self.workload_module], 'load-payload.log')
        self.loaded_source = True
        layout = self.counts('initial')
        rt.require(layout['sem'] and layout['gate'] and layout['entry'], 'missing entry/lock identity')
        self.record.update(layout=layout, entry_range=[layout['entry'], layout['entry'] + 1], caller_abi='clobber')
        (PARAMETERS / 'bench_lock_addr').write_text(str(layout['gate']))
        control(PREPARE)
        self.start_daemon()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.faults()
            rows = rt.registry()
            rt.require(self.daemon.poll() is None, 'daemon exited during publication')
            rt.require(len(rows) == 1 and rows[0]['entry'] == layout['entry'] and
                       rows[0]['status'] in (-1, 0), 'unexpected entry: ' + str(rows))
            if rows[0]['status'] == 0 and not rt.children(self.daemon.pid):
                self.record['publication'] = self.publication()
                self.save()
                return
            time.sleep(.1)
        raise rt.Failure('TIMEOUT', 'rwsem image did not publish', unsafe=True)

    def launch(self, role, warm=False, round_number=0):
        prefix = f'warm-{round_number}' if warm else 'test'
        name = prefix + '-' + str(role)
        receipt = self.path / (name + '-ready.json')
        go = self.path / (prefix + '-go.json' if warm else name + '-go.json')
        log = (self.path / (name + '.json')).open('w')
        self.logs.append(log)
        count = self.record['warmup_iterations'] if warm else 1
        argv = [sys.executable, self.translation_source / 'tests/kernel/rwsem/proxy/run.py', '--worker',
                role, self.record['cpus'][role], count, 'warm' if warm else 'test', receipt, go]
        process = subprocess.Popen(list(map(str, argv)), stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        row = dict(pid=process.pid, role=role, cpu=self.record['cpus'][role], warm=warm,
                   iterations=count, argv=list(map(str, argv)), receipt=str(receipt), output=name + '.json')
        self.callers.append((process, row))
        self.record['callers'] = [row for _, row in self.callers]
        self.save()
        return process, row

    def ready(self, processes):
        deadline = time.monotonic() + 10
        while not all(Path(row['receipt']).exists() for _, row in processes):
            rt.require(time.monotonic() < deadline and all(p.poll() is None for p, _ in processes),
                       'worker readiness failed', 'TIMEOUT')
            time.sleep(.005)

    def join(self, processes, timeout=60):
        deadline = time.monotonic() + timeout
        rows = []
        for process, metadata in processes:
            process.wait(timeout=max(.01, deadline - time.monotonic()))
            rt.require(process.returncode == 0, 'worker failed: ' + str(metadata), 'DATA_ERROR')
            row = json.loads((self.path / metadata['output']).read_text())
            comm = 'krp_writer' if metadata['warm'] else COMM[metadata['role']]
            rt.require(row == dict(pid=process.pid, role=metadata['role'], cpu=metadata['cpu'], comm=comm,
                                   iterations=metadata['iterations'], returned=metadata['iterations'], errors=0),
                       'worker effects/context differ: ' + str(row), 'DATA_ERROR')
            rows.append(row)
        return rows

    def wait(self, label, predicate, processes, timeout=4):
        deadline = time.monotonic() + timeout
        row = None
        try:
            while time.monotonic() < deadline:
                self.faults()
                row = snapshot()
                rt.require(not row['errors'], 'payload failed during ' + label + ': ' + str(row), 'DATA_ERROR')
                if predicate(row):
                    rt.write_json(self.path / (label + '.counts.json'), row)
                    return row
                rt.require(all(p.poll() is None for p, _ in processes), 'worker exited before ' + label)
                time.sleep(.002)
            raise rt.Failure('TIMEOUT', 'retain workers: ' + label, unsafe=True)
        except Exception as error:
            rt.write_json(self.path / (label + '.failed.json'), dict(error=str(error), last_snapshot=row,
                observed_ns=time.monotonic_ns(), callers=[dict(meta, returncode=p.poll()) for p, meta in processes]))
            raise

    def start(self, role):
        publish(self.path / f'test-{role}-go.json', dict(start=True))

    def warm(self):
        self.record['warm_rounds'] = []
        for number in range(1, self.record['warmup_rounds'] + 1):
            workers = [self.launch(role, True, number) for role in range(5)]
            self.ready(workers)
            publish(self.path / f'warm-{number}-go.json', dict(start=True))
            returned = self.join(workers)
            row = self.counts(f'warm-{number}-drain')
            rt.require(row['warm_ops'] == number * 5 * self.record['warmup_iterations'] and
                       row['prefix'] == row['tail_done'] == row['own_bodies'] == row['started'] == 0,
                       'warmup/probe isolation differs', 'DATA_ERROR')
            self.record['warm_rounds'].append(dict(workers=returned, after=row))
            self.save()
            if row['warm_eligible'] & REQUIRED == REQUIRED:
                return
        raise rt.Failure('DATA_ERROR', 'real warmup did not make all writer CPUs eligible')

    def measure(self):
        self.verify()
        workers = [self.launch(role) for role in range(5)]
        self.ready(workers)
        self.warm()
        counters = self.counters()
        rt.require(counters['bench_jit_completions'] > 0, 'warmup has no returned JIT completion')
        control(ARM)
        (PARAMETERS / 'rwsem_proxy_trace').write_text('1')
        # Exclude warmup traces from the controlled event sequence, while
        # retaining every raw line in kernel.log and checking final totals.
        self.faults()
        trace_start = len(self.messages)
        self.start(PREDECESSOR)
        self.wait('predecessor-held', lambda r: r['ready'] & (1 << PREDECESSOR) and
                  r['owner'] == r['t_task'] != 0 and r['gate_state'] == 0, workers)
        self.start(HOLDER)
        self.wait('holder-acquiring', lambda r: r['owner'] == r['t_task'] != 0 and
                  r['gate_state'] == 2 and r['entry_eligible'] & (1 << HOLDER), workers)
        control(PREDECESSOR_RELEASE)
        queued = [item for item in workers if item[1]['role'] != PREDECESSOR]
        self.wait('holder-held', lambda r: r['owner'] == r['g_task'] != 0 and
                  r['gate_state'] == 1 and r['predecessor_done'], queued)
        self.start(EXECUTOR)
        first = self.wait('executor-queued', lambda r: r['waiters'] == 1 and r['tail'] and
                          r['entry_eligible'] & (1 << EXECUTOR), queued)
        self.start(WRITER)
        self.wait('writer-queued', lambda r: r['waiters'] == 2 and r['tail'] != first['tail'] and
                  r['entry_checked'] == r['entry_eligible'] == REQUIRED, queued)
        control(HOLDER_RELEASE)
        tail_users = [item for item in workers if item[1]['role'] in (EXECUTOR, WRITER, READER)]
        self.wait('delegated-read-tail', lambda r: r['prefix'] == 1 and r['readers'] == 1 and
                  r['admission'] == r['owner'] == 0 and not r['tail_done'], tail_users)
        self.start(READER)
        # W may return after its own read release. R and C remain live until
        # the controller observes a new exclusive phase blocked on R's share.
        live = [item for item in workers if item[1]['role'] in (EXECUTOR, READER)]
        held = self.wait('fresh-writer-drains-reader', lambda r: r['reader_held'] and
                         r['tail_done'] == 1 and r['readers'] == 1 and
                         r['admission'] == (1 << 64) - 1 and r['own_bodies'] == 0 and
                         r['generation'] > r['write_generation'] and
                         r['owner'] == r['c_task'] != 0, live)
        control(READER_RELEASE)
        self.record['workers'] = self.join(workers, 15)
        self.record['callers_joined'] = True
        (PARAMETERS / 'rwsem_proxy_trace').write_text('0')
        self.faults()
        after = self.counts('final')
        delta = {key: self.counters()[key] - counters[key] for key in counters}
        rt.require(delta == dict(bench_jit_bodies=1, bench_jit_completions=1),
                   'expected one fully returned delegated writer/read tail: ' + str(delta), 'DATA_ERROR')
        rt.require(after['prefix'] == after['tail_done'] == after['own_bodies'] == 1 and
                   after['started'] == after['ready'] == after['done'] == 31 and
                   after['own_generation'] >= held['generation'] > after['write_generation'],
                   'effects/generation differ: ' + str(after), 'DATA_ERROR')
        controlled = self.messages[trace_start:]
        rt.require(not trace_records(controlled, 'kd_native begin: '),
                   'controlled proxy body used original-task continuation', 'DATA_ERROR')
        self.record.update(after=after, jit_delta=delta, held_reader=held,
                           proxy_events=validate_proxy_events(controlled, self.record))
        rt.require(self.publication() == self.record['publication'], 'immutable image changed', 'DATA_ERROR')
        self.verify()
        self.save()

    def execute(self):
        try:
            self.prepare()
            self.measure()
            self.cleanup()
            stats = trace_records(self.messages, 'kd_native stats: ')
            rt.require(stats == [dict(started='0', completed='0', unlocks='0')],
                       'unexpected original-task continuation, including warmup: ' + str(stats), 'DATA_ERROR')
            self.record.update(execution_status='OK', native_stats=stats)
        except Exception as error:
            publish(self.path / 'abort-starts.json', dict(error=str(error),
                meaning='unstarted userspace barriers only; active ioctls untouched'))
            self.record.update(execution_status=getattr(error, 'status', 'RUN_FAILED'), error=str(error),
                               unsafe=True, retained_modules=[n for n in (MODULE, 'kdlock_km')
                                                              if Path('/sys/module', n).exists()])
            raise
        finally:
            self.record['finished_ns'] = time.monotonic_ns()
            self.save()
            for log in self.logs:
                log.close()
            os.close(self.kmsg)


def validate_proxy_events(messages, record):
    """Require exact same-request events, never infer proxying from API time."""
    rows = trace_records(messages, 'kd_rwsem proxy: ')
    pids = {row['role']: row['pid'] for row in record['workers']}
    events = [row for row in rows if row.get('origin') == str(pids[WRITER])]
    rt.require([row.get('stage') for row in events] == ['write', 'downgrade', 'read_release'],
               'missing/extraneous delegated request events: ' + str(events), 'DATA_ERROR')
    exact = ('sem', 'origin', 'executor', 'request', 'identity', 'sequence', 'generation')
    rt.require(all(set(row) == set(exact) | {'stage'} for row in events), 'event schema differs')
    reference = {key: events[0][key] for key in exact}
    rt.require(all(all(row[key] == reference[key] for key in exact) for row in events) and
               int(reference['sem'], 16) == record['layout']['sem'] and
               reference['executor'] == str(pids[EXECUTOR]) != reference['origin'] and
               int(reference['request'], 16) != 0 and int(reference['identity'], 16) != 0 and
               int(reference['sequence']) != 0 and
               int(reference['generation']) == record['after']['write_generation'],
               'exact origin/executor/request generation differs: ' + str(events), 'DATA_ERROR')
    reacquire = [row for row in rows if row.get('stage') == 'reacquire' and
                 row.get('origin') == str(pids[EXECUTOR])]
    rt.require(len(reacquire) == 1 and reacquire[0]['executor'] == str(pids[EXECUTOR]) and
               int(reacquire[0]['sem'], 16) == record['layout']['sem'] and
               int(reacquire[0]['generation']) == record['after']['own_generation'] >
               int(reference['generation']) and rows.index(reacquire[0]) > rows.index(events[-1]),
               'fresh executor writer reacquisition is not witnessed: ' + str(reacquire), 'DATA_ERROR')
    return rows


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpus', type=rt.cpu_list, default=rt.cpu_list('0-4'))
    parser.add_argument('--warmup-iterations', type=int, default=50000)
    parser.add_argument('--warmup-rounds', type=int, default=4)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    rt.require(os.geteuid() == 0 and ROOT == Path('/root/host_fs/kdlock') and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and os.environ.get('KDLOCK_SNAPSHOT_TAG'),
               'confirmed recovery guest and recorded snapshot required')
    rt.require(len(args.cpus) == len(set(args.cpus)) == 5 and set(args.cpus) <= os.sched_getaffinity(0),
               'select five distinct available CPUs')
    rt.require(5000 <= args.warmup_iterations <= 200000 and 1 <= args.warmup_rounds <= 4,
               'bounded real warmup required')
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new output outside source required')
    idle()
    out.mkdir(parents=True)
    try:
        identity = kernel_identity.capture(args, out, rt.command)
        rt.write_json(out / 'environment.json', dict(kernel_identity=identity, argv=sys.argv,
            python=sys.executable, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'], uname=list(os.uname()),
            topology=rt.capture_topology(args.cpus),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
        source, build = out / 'source', out / 'build'
        hashes = sources(ROOT)
        for relative in hashes:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        rt.write_json(out / 'source-sha256.json', hashes)
        rt.require(sources(ROOT) == sources(source) == hashes, 'source changed while freezing')
        prepare_provider(build / 'provider', source)
        rt.write_json(out / 'observation-overlay.json', observe_provider(build / 'provider'))
        provider = build / 'provider/kernel_module/kdlock_km.ko'
        rt.command(['make', '-C', provider.parent, f'KDIR={args.kernel_source}', 'W=1',
                    'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1', 'UBSAN_SANITIZE=n'], out / 'build-provider.log', timeout=180)
        guard = build / 'guard'
        shutil.copytree(source / 'bench/tclock_compare/allocator_guard', guard)
        rt.command(['make', '-C', guard, f'KDIR={args.kernel_source}'], out / 'build-guard.log', timeout=180)
        payload = source / 'tests/kernel/rwsem/proxy/payload/kd_rwsem_proxy_test.ko'
        rt.command(['make', '-C', payload.parent, f'KDIR={args.kernel_source}',
                    f'KDLOCK_INCLUDE={source / "include"}', f'KBUILD_EXTRA_SYMBOLS={provider.parent / "Module.symvers"}'],
                   out / 'build-payload.log', timeout=180)
        rt.command(['objdump', '-dr', payload], out / 'payload-disassembly.txt')
        rt.command(['make', '-C', source / 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'],
                   out / 'build-daemon.log', timeout=120)
        binaries = dict(provider=provider, payload=payload, daemon=source / 'daemon/daemon',
                        guard=guard / 'tc_allocator_guard.ko')
        binary_hashes = {str(path): rt.digest(path) for path in binaries.values()}
        prepared = {str(p.relative_to(build / 'provider')): rt.digest(p)
                    for p in (build / 'provider').rglob('*') if p.is_file() and
                    (p.suffix in ('.c', '.h', '.inc', '.S', '.def') or p.name == 'Makefile') and
                    not p.name.endswith('.mod.c')}
        rt.write_json(out / 'binary-sha256.json', binary_hashes)
        rt.write_json(out / 'prepared-source-sha256.json', prepared)

        def verify():
            rt.require(sources(ROOT) == sources(source) == hashes, 'live or frozen source changed')
            rt.require(all(rt.digest(Path(p)) == value for p, value in binary_hashes.items()), 'binary changed')
            rt.require(all(rt.digest(build / 'provider' / p) == value for p, value in prepared.items()),
                       'prepared provider changed')

        verify()
        session = ProxySession(out, dict(name='session', arm='kdlock', lock_kind='rwsem', entry_abi=2,
            delegate=True, cpus=args.cpus, warmup_iterations=args.warmup_iterations,
            warmup_rounds=args.warmup_rounds, kernel_identity=identity), binaries, verify)
        session.execute()
        verify()
        idle()
        rt.write_json(out / 'result.json', dict(passed=True, drained=True, after=session.record['after'],
            jit_delta=session.record['jit_delta'], proxy_events=session.record['proxy_events'],
            native_stats=session.record['native_stats'], source_retirement=session.record['retired'],
            kernel_identity=identity, snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG']))
        print('PASS: other-task writer/read tail, exact returned completion, fresh writer drain and retirement')
        return 0
    except Exception as error:
        rt.write_json(out / 'failure.json', dict(error=str(error), status=getattr(error, 'status', 'RUN_FAILED'),
                                               cleanup='not attempted on failure'))
        print('FAIL: ' + str(error) + '; retain workers and modules', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
