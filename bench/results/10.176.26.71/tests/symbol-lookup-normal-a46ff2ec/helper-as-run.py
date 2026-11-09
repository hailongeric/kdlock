"""Guest-only metadata lookup comparison; no translator execution or module load."""
import ast
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode = True
request = json.loads(sys.stdin.buffer.read())
root, out = Path(request['root']), Path(request['output'])
assert os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == request['boot_id']
assert sys.executable == '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
sys.path.insert(0, str(root / 'bench/spin_cacheline'))
import bench_runtime as rt
rt.idle()
assert not Path('/sys/module/kdlock_km').exists()
for path in Path('/sys/module').iterdir():
    assert not path.name.startswith(('kd_', 'jit_', 'tclock_', 'tc_')), path.name
for name, wanted in request['files'].items():
    assert rt.digest(root / name) == wanted, name
out.mkdir(parents=True, exist_ok=False)
os.sched_setaffinity(0, {63})
sys.path.insert(0, str(root / 'disassem'))
import native_terminals, context_symbols, hostcall

source_path = root / 'disassem/disassem.py'
source = source_path.read_text()
tree = ast.parse(source, filename=str(source_path))
lookup_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'get_kernel_symbol')
percpu_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'get_percpu_symbol_offset')
scope = {}
exec(compile(ast.Module(body=[lookup_node], type_ignores=[]), str(source_path), 'exec'), scope)
original = scope['get_kernel_symbol']
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'dis_assem')
assign_names = ('raw_spin_lock', 'raw_spin_unlock', 'mutex_lock', 'mutex_unlock',
    'clobber_lock', 'clobber_unlock', 'pinned_spin_lock', 'cold_spin_unlock',
    'clobber_mutex_lock', 'clobber_mutex_unlock', 'direct_mutex_lock', 'direct_mutex_unlock',
    'contended_mutex_lock', 'outer_mutex_lock', 'service_acquire_names', 'service_release_names',
    'service_continue_names', 'service_symbols', 'rwsem_clobber_lock', 'rwsem_clobber_unlock',
    'api_unlock_name', 'api_unlock')
assignments = [node for node in function.body if isinstance(node, ast.Assign) and
    any(isinstance(target, ast.Name) and target.id in assign_names for target in node.targets)]
assert {target.id for node in assignments for target in node.targets if isinstance(target, ast.Name)} == set(assign_names)
alias_code = compile(ast.Module(body=assignments, type_ignores=[]), str(source_path), 'exec')
assert len(native_terminals.load_specs()) == 98
real_open = builtins.open
active = None

def counted_open(path, *args, **kwargs):
    if active is not None and os.fspath(path) == '/proc/kallsyms':
        active['opens'] += 1
    return real_open(path, *args, **kwargs)

scope['open'] = counted_open

class Snapshot:
    """First raw token wins; conversion/defaults remain lookup-local."""
    def __init__(self, opener=counted_open):
        self.tokens, self.failed, self.opener = None, False, opener

    def load(self):
        tokens = {}
        read_failed = False
        try:
            with self.opener('/proc/kallsyms', 'r', encoding='utf-8', errors='ignore') as stream:
                try:
                    for line in stream:
                        parts = line.split()
                        if len(parts) >= 3:
                            tokens.setdefault(parts[2], parts[0])
                except OSError:
                    read_failed = True
        except OSError:
            self.failed = True
            # Entry or close failures make the original resolver return the
            # call's default, even if it had already found a matching line.
            return {}
        if read_failed:
            self.failed = True
            # A prefix match would have returned before the iterator failed.
            # Retry the table on the next call rather than caching a failure.
            return tokens
        self.failed = False
        self.tokens = tokens
        return tokens

    def lookup(self, name, default=0):
        tokens = self.load() if self.tokens is None else self.tokens
        token = tokens.get(name)
        return int(token, 16) if token is not None else default

def semantic_checks():
    text = '0000 t zero\n0010 T duplicate [one]\n0020 t duplicate [two]\n0030 t valid\nwrong t malformed\nshort line\n'
    fake = lambda *args, **kwargs: io.StringIO(text)
    old = scope['open']
    try:
        scope['open'] = fake
        snapshot = Snapshot(fake)
        for name, default in (('zero', 99), ('duplicate', 99), ('valid', 0), ('missing', 71), ('missing', 83)):
            assert original(name, default) == snapshot.lookup(name, default)
        for lookup in (original, snapshot.lookup):
            try:
                lookup('malformed', 99)
            except ValueError:
                pass
            else:
                raise AssertionError('matching malformed token did not raise')
        class Partial:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                yield '0030 t valid\n'
                raise OSError('fixture partial read failure')
        partial = lambda *args, **kwargs: Partial()
        scope['open'] = partial
        snapshot = Snapshot(partial)
        for name, default in (('valid', 99), ('missing', 71), ('missing', 83)):
            assert original(name, default) == snapshot.lookup(name, default)
        assert snapshot.failed and snapshot.tokens is None
        class CloseFailure(io.StringIO):
            def __exit__(self, *args):
                self.close()
                raise OSError('fixture close failure')
        close_failure = lambda *args, **kwargs: CloseFailure(text)
        scope['open'] = close_failure
        snapshot = Snapshot(close_failure)
        for name, default in (('valid', 99), ('missing', 71), ('missing', 83)):
            assert original(name, default) == snapshot.lookup(name, default) == default
        assert snapshot.failed and snapshot.tokens is None
        attempts = []
        def recovery(*args, **kwargs):
            attempts.append(1)
            if len(attempts) <= 2:
                raise OSError('fixture read failure')
            return io.StringIO(text)
        snapshot = Snapshot(recovery)
        assert snapshot.lookup('missing', 71) == 71 and snapshot.lookup('missing', 83) == 83
        assert snapshot.lookup('valid', 99) == 0x30 and len(attempts) == 3
    finally:
        scope['open'] = old
    return dict(passed=True, first_match=True, zero_distinct_from_missing=True,
        caller_defaults=True, lazy_conversion=True, matching_malformed_raises=True,
        unrelated_malformed_ignored=True, partial_prefix_preserved=True, close_failure_default=True,
        read_failure_retries=True)

def state():
    data = Path('/proc/kallsyms').read_bytes()
    modules = Path('/proc/modules').read_bytes()
    return dict(at_ns=time.monotonic_ns(), table_sha256=hashlib.sha256(data).hexdigest(),
        table_bytes=len(data), table_lines=data.count(b'\n'), modules_sha256=hashlib.sha256(modules).hexdigest(),
        modules=modules.decode(), affinity=sorted(os.sched_getaffinity(0)))

def sequence(lookup, records):
    def traced(name, default=0):
        address = lookup(name, default)
        records.append(dict(name=name, default=default, address=address))
        return address
    controls = context_symbols.resolve_control_symbols(traced)
    hostcall.resolve_hostcalls(traced)
    native_terminals.resolve(traced)
    namespace = dict(get_kernel_symbol=traced, control_symbols=controls, abi=2)
    exec(alias_code, namespace, namespace)
    exec(compile(ast.Module(body=[percpu_node], type_ignores=[]), str(source_path), 'exec'), namespace, namespace)
    namespace['get_percpu_symbol_offset']('current_task')

def measure(kind):
    global active
    active = dict(opens=0)
    records = []
    before = resource.getrusage(resource.RUSAGE_SELF)
    start = time.perf_counter_ns()
    snapshot = Snapshot() if kind == 'snapshot' else None
    sequence(snapshot.lookup if snapshot else original, records)
    elapsed = time.perf_counter_ns() - start
    after = resource.getrusage(resource.RUSAGE_SELF)
    counts, active = active, None
    measured = dict(kind=kind, wall_ns=elapsed, user_ns=round((after.ru_utime-before.ru_utime)*1e9),
        system_ns=round((after.ru_stime-before.ru_stime)*1e9), lookup_count=len(records), open_attempts=counts['opens'],
        minor_faults=after.ru_minflt-before.ru_minflt, major_faults=after.ru_majflt-before.ru_majflt,
        voluntary_switches=after.ru_nvcsw-before.ru_nvcsw, involuntary_switches=after.ru_nivcsw-before.ru_nivcsw,
        maxrss_kib_before=before.ru_maxrss, maxrss_kib_after=after.ru_maxrss,
        snapshot_symbols=len(snapshot.tokens or {}) if snapshot else None,
        snapshot_failed=snapshot.failed if snapshot else None, requests=records)
    if snapshot and snapshot.tokens is not None:
        measured['requested_name_presence'] = {
            name: dict(present=name in snapshot.tokens,
                zero=name in snapshot.tokens and int(snapshot.tokens[name], 16) == 0)
            for name in {record['name'] for record in records}}
    return measured

result = dict(schema=1, passed=False, production_changed=False, modules_loaded=False, images_published=False,
    workload_run=False, repetitions=1, kernel_release=os.uname().release, build_id=request['build_id'],
    build_id_provenance='previous running verification receipt, bound to the same boot UUID and release',
    verification_receipt_sha256=request['verification_receipt_sha256'],
    boot_id=request['boot_id'], source_commit=request['source_commit'], source_root=str(root), files=request['files'],
    helper_sha256=request['helper_sha256'], python=sys.executable, python_version=sys.version,
    resolver_source=ast.get_source_segment(source, lookup_node),
    scope='normal-kernel resolver reproduction; not retrospective full-compiler attribution',
    lookup_scope='actual control, scalar hostcall, 98 manifest terminal, ABI2 alias assignments and current_task/percpu_start lookup; no device-dependent controls or source-dependent preempt lookup',
    instrumentation='one Python counter per symbol-file open and one record per lookup; no per-line or profiler hook',
    startup_scope='constructed lookup sequence only; missing-control and device-dependent startup checks are not run',
    memory_scope='ru_maxrss is cumulative for this process; the second arm inherits the first arm high-water mark',
    warmup='table/module identity reads precede measurement; original first; no cache flush',
    clock=dict(resolution=time.get_clock_info('perf_counter').resolution, monotonic=time.get_clock_info('perf_counter').monotonic))
try:
    result['semantics'] = semantic_checks()
    result['before'] = state()
    result['original'] = measure('original')
    result['between'] = state()
    result['snapshot'] = measure('snapshot')
    result['after'] = state()
    presence = result['snapshot']['requested_name_presence']
    for kind in ('original', 'snapshot'):
        records = result[kind]['requests']
        names = {record['name'] for record in records}
        result[kind]['requested_counts'] = dict(total=len(records), unique=len(names),
            present=sum(presence[record['name']]['present'] for record in records),
            missing=sum(not presence[record['name']]['present'] for record in records),
            zero=sum(presence[record['name']]['zero'] for record in records),
            unique_present=sum(presence[name]['present'] for name in names),
            unique_missing=sum(not presence[name]['present'] for name in names),
            unique_zero=sum(presence[name]['zero'] for name in names))
    result['identical_requests'] = result['original']['requests'] == result['snapshot']['requests']
    result['observed_table_stable'] = len({result[name]['table_sha256'] for name in ('before','between','after')}) == 1
    result['observed_modules_stable'] = len({result[name]['modules_sha256'] for name in ('before','between','after')}) == 1
    assert result['identical_requests'] and result['observed_table_stable'] and result['observed_modules_stable']
    assert result['original']['open_attempts'] == result['original']['lookup_count']
    assert result['snapshot']['open_attempts'] == 1 and not result['snapshot']['snapshot_failed']
    rt.idle();assert not Path('/sys/module/kdlock_km').exists()
    result.update(passed=True, final_idle=True)
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
