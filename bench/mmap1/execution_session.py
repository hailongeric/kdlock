"""Explicit execution environment for an unchanged application run.

The controller owns load/prepare/activate/deactivate and normal retirement.
This verifier admits only its frozen module/daemon/registry, and does not prove
that an application invocation was delegated. Runtime trace joins do that.
"""
import json
import hashlib
import os
from pathlib import Path
import stat
import sys

import bench_runtime as rt

PARAMETERS = Path('/sys/module/kdlock_km/parameters')
NOTE = Path('/sys/module/kdlock_km/notes/.note.gnu.build-id')
PROC = Path('/proc')
DEVICE = Path('/dev/kd_dev')
SYSCALL_SHAPE_PARAMETERS = ('rwsem_provider_syscall_shape', 'rwsem_provider_syscall_shape_version')


def reached_observations():
    directory = Path(__file__).resolve().parents[2] / 'tests/kernel/jit_continuation'
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    from reached_mode import parse_stats
    return parse_stats((PARAMETERS / 'reached_stats').read_text())


def module_note_sha256(path):
    from elftools.elf.elffile import ELFFile
    with Path(path).open('rb') as stream:
        note = ELFFile(stream).get_section_by_name('.note.gnu.build-id')
        rt.require(note is not None, 'provider artifact has no GNU Build ID note', 'DATA_ERROR')
        return hashlib.sha256(note.data()).hexdigest()


def task_identity(pid):
    base = Path('/proc') / str(pid)
    fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]),
                executable=str((base / 'exe').resolve(strict=True)),
                cwd=str((base / 'cwd').resolve(strict=True)),
                argv=[word.decode() for word in (base / 'cmdline').read_bytes().split(b'\0') if word])


def registry(rows):
    return sorted(rows, key=lambda row: (row['pid'], row['tgid'], row['entry']))


def selected_writer_entries(values, sites):
    """An empty immutable entry list retains unrestricted root capture."""
    rt.require(type(values) is list and len(values) <= 64 and
               all(type(value) is int and 0 < value < 1 << 64 for value in values) and
               len(set(values)) == len(values) and set(values) <= set(sites),
               'writer entry selection differs from the builtin site table', 'DATA_ERROR')
    return set(values) if values else set(sites)


def parse_writer_entries(value):
    rt.require(type(value) is str, 'missing writer entry parameter', 'DATA_ERROR')
    try:
        return [int(word, 0) for word in value.strip().split(',')] if value.strip() else []
    except ValueError as error:
        raise rt.Failure('DATA_ERROR', 'invalid writer entry parameter') from error


def syscall_shape_contract(parameters, enabled):
    """Bind optional argument selection without inferring worker or pair proof."""
    rt.require(type(enabled) is bool, 'syscall argument selection must be explicit', 'DATA_ERROR')
    setting, version = SYSCALL_SHAPE_PARAMETERS
    if setting not in parameters:
        rt.require(version not in parameters and not enabled,
                   'provider lacks the configured syscall argument contract', 'DATA_ERROR')
        return None
    rt.require(parameters.get(setting) in ('Y', 'N') and parameters.get(version) == '1' and
               (parameters[setting] == 'Y') == enabled,
               'loaded syscall argument policy or version differs', 'DATA_ERROR')
    return dict(version=1, enabled=enabled)


def ready_writer_entries(rows, entries):
    if entries:
        rt.require(len(rows) == len(entries) and {row['entry'] for row in rows} == set(entries) and
                   all(row['status'] == 0 and row['code'] > 0 and row['generation'] > 0 for row in rows),
                   'selected writer images are not all ready for scoring', 'NO_JIT')


def demand_registry(rows, sites, *, settled=True):
    """Kernel entry identity is independent of its first registrar's task."""
    keys = {(row['pid'], row['entry']) for row in rows}
    rt.require(len(keys) == len(rows), 'duplicate demand registry entry', 'DATA_ERROR')
    for row in rows:
        rt.require(row['pid'] == 0 and row['entry'] in sites and
                   type(row['tgid']) is int and row['tgid'] > 0 and
                   row['entry_abi'] == row['lock_kind'] == 2,
                   'demand entry/site/ABI identity differs', 'DATA_ERROR')
        normal = row['status'] == 0 and row['code'] > 0 and row['generation'] > 0
        paired = (row['code'] == row['generation'] == 0 or
                  row['code'] > 0 and row['generation'] > 0)
        local = row['status'] == -3 and paired
        pending = not settled and row['status'] in (-1, 1, 2, 3, 4) and paired
        rt.require(normal or local or pending, 'demand publication is not in a valid state', 'UNDRAINED')
    return registry(rows)


def demand_transition(before, after, sites):
    demand_registry(before, sites, settled=False)
    demand_registry(after, sites, settled=False)
    current = {(row['pid'], row['entry']): row for row in after}
    for old in before:
        new = current.get((old['pid'], old['entry']))
        rt.require(new is not None and all(new[key] == old[key] for key in
                   ('pid', 'entry', 'tgid', 'entry_abi', 'lock_kind')) and
                   new['generation'] >= old['generation'] and
                   (new == old if old['status'] == -3 else
                    new['generation'] > old['generation'] or all(new[key] == old[key]
                        for key in ('code', 'requirements'))),
                   'demand entry lifetime or generation moved backwards', 'DATA_ERROR')
    return registry(before) != registry(after)


def device_writers():
    """Observe every writable descriptor for this exact live device.

    One daemon description is expected and the maintained daemon keeps only
    one descriptor for it. Refusing extra duplicate descriptors avoids treating
    descriptor counts as proof of distinct open descriptions.
    """
    device = DEVICE.stat()
    rt.require(stat.S_ISCHR(device.st_mode), 'execution device is not a character device', 'DATA_ERROR')
    rows = []
    for process in PROC.glob('[0-9]*'):
        for descriptor in (process / 'fd').glob('[0-9]*'):
            try:
                current = descriptor.stat()
                if not stat.S_ISCHR(current.st_mode) or current.st_rdev != device.st_rdev:
                    continue
                lines = (process / 'fdinfo' / descriptor.name).read_text().splitlines()
                flags = int(next(line.split()[1] for line in lines if line.startswith('flags:')), 8)
                if flags & os.O_ACCMODE == os.O_RDONLY:
                    continue
                fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
                rows.append(dict(pid=int(process.name), start_ticks=int(fields[19]), fd=int(descriptor.name),
                                 flags=flags, device=current.st_dev, inode=current.st_ino, rdev=current.st_rdev))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return sorted(rows, key=lambda row: (row['pid'], row['fd']))


class ExecutionSession:
    """A hash-bound controller receipt, with no lifecycle side effects.

    Schema1 keys: boot_id; provider {path,sha256,note_sha256}; daemon
    {pid,start_ticks,executable,executable_sha256,cwd,argv,device_writer}; preparer
    {pid,start_ticks,executable,executable_sha256,cwd,argv}; parameters (exact
    selected values); registry (complete ready rt.registry rows); source
    {state,modules,writers:1}; files (absolute immutable input file hashes).
    """
    def __init__(self, path, sha256):
        self.path = Path(path).resolve(strict=True)
        self.sha256 = sha256
        rt.require(rt.digest(self.path) == sha256, 'execution-session receipt bytes differ', 'DATA_ERROR')
        self.expected = json.loads(self.path.read_text())
        expected = self.expected
        self.demand = expected.get('demand', False)
        self.execution_mode = expected.get('execution_mode', 'image')
        if self.execution_mode == 'reached':
            self._init_reached()
            return
        rt.require(self.execution_mode == 'image', 'unknown execution-session mode', 'DATA_ERROR')
        rt.require(expected.get('schema') == (3 if self.demand else 1) and expected.get('boot_id') and
                   expected.get('source', {}).get('state') == 0 and
                   set(expected['source']) == {'state', 'modules', 'writers'} and
                   type(expected['source'].get('writers')) is int and expected['source']['writers'] == 1 and
                   type(expected['source'].get('modules')) is int and expected['source']['modules'] >= 0,
                   'execution-session schema/source differs', 'DATA_ERROR')
        values = expected.get('parameters', {})
        rt.require(values.get('rwsem_provider_active') == 'Y' and
                   values.get('rwsem_provider_mode') == 'active' and
                   values.get('jit_timing') == 'N' and values.get('service_trace') in ('Y', 'N'),
                   'active provider and explicit instrumentation parameters required', 'DATA_ERROR')
        preparer = expected.get('preparer', {})
        rt.require(type(preparer.get('pid')) is int and preparer['pid'] > 0 and
                   type(preparer.get('start_ticks')) is int and preparer['start_ticks'] > 0 and
                   preparer.get('argv'), 'exact live preparation controller required', 'DATA_ERROR')
        rows = expected.get('registry', [])
        scope = expected.get('writer_entries', [])
        shape = expected.get('syscall_shape')
        enabled = shape.get('enabled') if isinstance(shape, dict) else False
        rt.require(syscall_shape_contract(values, enabled) == shape and
                   (not enabled or (self.demand and scope)),
                   'syscall argument selection receipt differs', 'DATA_ERROR')
        rt.require(('writer_entries' in expected) == ('rwsem_provider_entries' in values),
                   'writer entry selection is missing from the receipt', 'DATA_ERROR')
        if 'writer_entries' in expected:
            rt.require(parse_writer_entries(values['rwsem_provider_entries']) == scope,
                       'writer entry parameter differs', 'DATA_ERROR')
            if scope:
                table = expected['writer_sites']
                rt.require(rt.digest(Path(table['path'])) == table['sha256'] and
                           expected['files'].get(table['path']) == table['sha256'],
                           'writer entry site-table identity differs', 'DATA_ERROR')
                selected_writer_entries(scope,
                    {row['entry'] for row in json.loads(Path(table['path']).read_text())['records']})
        if self.demand:
            table = expected['writer_sites']
            rt.require(values.get('rwsem_provider_demand') == 'Y' and
                       rt.digest(Path(table['path'])) == table['sha256'] and
                       expected['files'].get(table['path']) == table['sha256'],
                       'demand provider or site-table identity differs', 'DATA_ERROR')
            entries = {row['entry'] for row in json.loads(Path(table['path']).read_text())['records']}
            self.site_entries = selected_writer_entries(scope, entries)
            rt.require(self.site_entries, 'empty demand site table', 'DATA_ERROR')
            demand_registry(rows, self.site_entries)
        else:
            rt.require(rows and len({(row['pid'], row['tgid'], row['entry']) for row in rows}) == len(rows) and
                   (not scope or {row['entry'] for row in rows} == set(scope)) and
                   all(row['pid'] == row['status'] == 0 and row['tgid'] == preparer['pid'] and row['entry_abi'] == 2 and
                       row['lock_kind'] == 2 and row['entry'] > 0 and row['code'] > 0 and row['generation'] > 0
                       for row in rows), 'complete ready ABI2 image registry required', 'DATA_ERROR')
        files = expected.get('files', {})
        provider, daemon = expected['provider'], expected['daemon']
        rt.require(files and files.get(provider['path']) == provider['sha256'] and
                   files.get(daemon['executable']) == daemon['executable_sha256'] and
                   files.get(preparer['executable']) == preparer['executable_sha256'] and
                   daemon['pid'] > 0 and daemon['pid'] != preparer['pid'] and daemon['start_ticks'] > 0 and daemon['argv'],
                   'module/daemon must be bound by immutable input hashes', 'DATA_ERROR')
        writer = daemon.get('device_writer', {})
        rt.require(set(writer) == {'pid', 'start_ticks', 'fd', 'flags', 'device', 'inode', 'rdev'} and
                   all(type(value) is int and value >= 0 for value in writer.values()) and
                   writer['pid'] == daemon['pid'] and writer['start_ticks'] == daemon['start_ticks'] and
                   writer['flags'] & os.O_ACCMODE == os.O_RDWR and writer['inode'] > 0 and writer['rdev'] > 0,
                   'exact daemon writable-device descriptor required', 'DATA_ERROR')

    def identity(self):
        if self.execution_mode == 'reached':
            return dict(path=str(self.path), sha256=self.sha256, execution_mode='reached',
                        provider_sha256=self.expected['provider']['sha256'],
                        preparer_pid=self.expected['preparer']['pid'], daemon_pid=None,
                        device_writers=[], delegated_execution_proved=False)
        value = dict(path=str(self.path), sha256=self.sha256,
                    provider_sha256=self.expected['provider']['sha256'],
                    daemon_pid=self.expected['daemon']['pid'],
                    daemon_start_ticks=self.expected['daemon']['start_ticks'],
                    preparer_pid=self.expected['preparer']['pid'],
                    daemon_device_writer=self.expected['daemon']['device_writer'],
                    delegated_execution_proved=False)
        if 'syscall_shape' in self.expected:
            value['syscall_shape'] = self.expected['syscall_shape']
        return value

    def verify(self, *, allow_identity_probe=False):
        if self.execution_mode == 'reached':
            return self._verify_reached(allow_identity_probe=allow_identity_probe)
        expected = self.expected
        rt.require(rt.digest(self.path) == self.sha256 and json.loads(self.path.read_text()) == expected and
                   Path('/proc/sys/kernel/random/boot_id').read_text().strip() == expected['boot_id'],
                   'execution-session receipt or boot changed', 'DATA_ERROR')
        for name, wanted in expected['files'].items():
            path = Path(name)
            rt.require(path.is_absolute() and path.is_file() and rt.digest(path) == wanted,
                       'execution-session input changed: ' + name, 'DATA_ERROR')
        rt.require(NOTE.is_file() and rt.digest(NOTE) == expected['provider']['note_sha256'] and
                   module_note_sha256(expected['provider']['path']) == expected['provider']['note_sha256'],
                   'loaded provider Build ID note differs', 'DATA_ERROR')
        daemon = expected['daemon']
        preparer = expected['preparer']
        preparing_task = task_identity(preparer['pid'])
        rt.require(all(preparing_task[key] == preparer[key] for key in
                       ('pid', 'start_ticks', 'executable', 'cwd', 'argv')),
                   'exact preparation controller lifetime/workspace changed', 'UNDRAINED')
        actual = task_identity(daemon['pid'])
        rt.require(all(actual[key] == daemon[key] for key in
                       ('pid', 'start_ticks', 'executable', 'cwd', 'argv')),
                   'exact daemon lifetime/workspace changed', 'UNDRAINED')
        children = rt.children(daemon['pid'])
        if self.demand and children:
            demand_transition(expected['registry'], rt.registry(), self.site_entries)
            raise rt.Failure('LEARNING_ADVANCED', 'image learning continues beyond the timing receipt')
        rt.require(not children, 'translator remains active', 'UNDRAINED')
        rt.require(all((name in expected['parameters']) == (PARAMETERS / name).is_file()
                       for name in SYSCALL_SHAPE_PARAMETERS),
                   'syscall argument policy is missing from the receipt', 'DATA_ERROR')
        for name, wanted in expected['parameters'].items():
            rt.require((PARAMETERS / name).read_text().strip() == wanted,
                       'execution-session parameter changed: ' + name, 'DATA_ERROR')
        source = rt.status()
        rt.require(source == dict(expected['source'], frames=0) and
                   device_writers() == [daemon['device_writer']],
                   'source must have zero frames and only its exact live daemon writer', 'UNDRAINED')
        actual_registry = rt.registry()
        if self.demand and demand_transition(expected['registry'], actual_registry, self.site_entries):
            raise rt.Failure('LEARNING_ADVANCED', 'image learning advanced beyond the timing receipt')
        rt.require(registry(actual_registry) == registry(expected['registry']),
                   'immutable image registry changed', 'DATA_ERROR')
        allowed = {'kdlock_km'} | ({'kd_mmap1_identity'} if allow_identity_probe else set())
        other_modules = {'real_api', 'rwlock_bench', 'rwlock_test', 'rwsem_probe',
                         'spin_cacheline', 'mutex_cacheline', 'klock_module'}
        for module in Path('/sys/module').iterdir():
            rt.require(module.name in allowed or
                       (module.name not in other_modules and
                        not module.name.startswith(('kd_', 'jit_', 'tclock_', 'tc_'))),
                       'another experimental module remains: ' + module.name, 'UNDRAINED')
        forbidden_tasks = {'mmap1_threads', 'mmap1_processes', 'sc_worker', 'rb_worker',
                           'klock_test', 'kd_test'}
        for task in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
            try:
                name = task.read_text().strip()
                rt.require(name not in forbidden_tasks and
                           (name != 'daemon' or int(task.parent.name) == daemon['pid']),
                           'another workload/daemon remains: ' + str(task), 'UNDRAINED')
            except (FileNotFoundError, ProcessLookupError):
                continue
        rt.require(task_identity(daemon['pid']) == actual,
                   'daemon identity changed across session observation', 'UNDRAINED')
        rt.require(task_identity(preparer['pid']) == preparing_task and rt.status() == source and
                   device_writers() == [daemon['device_writer']],
                   'preparer or exact daemon-writer ledger changed across observation', 'UNDRAINED')
        bindings = int((PARAMETERS / 'rwsem_provider_bindings').read_text())
        rt.require(bindings >= 1, 'active factory has no source binding lease', 'UNDRAINED')
        return dict(source=source, bindings=bindings,
                    binding_drain_proved=False, application_delegation_proved=False)

    def _init_reached(self):
        expected = self.expected
        source, values = expected.get('source', {}), expected.get('parameters', {})
        rt.require(expected.get('schema') == 2 and expected.get('boot_id') and
                   set(source) == {'state', 'modules', 'writers'} and source.get('state') == 0 and
                   type(source.get('modules')) is int and source['modules'] >= 0 and
                   type(source.get('writers')) is int and source['writers'] == 0 and
                   expected.get('registry') == [] and expected.get('device_writers') == [] and
                   'daemon' not in expected,
                   'image-free execution-session source/writer/image contract differs', 'DATA_ERROR')
        rt.require(values.get('service_reached') == 'Y' and values.get('rwsem_provider_active') == 'Y' and
                   values.get('rwsem_provider_mode') == 'active' and values.get('jit_timing') == 'N' and
                   values.get('service_trace') in ('Y', 'N'),
                   'explicit active reached provider required', 'DATA_ERROR')
        preparer, provider, files = expected.get('preparer', {}), expected.get('provider', {}), expected.get('files', {})
        rt.require(type(preparer.get('pid')) is int and preparer['pid'] > 0 and
                   type(preparer.get('start_ticks')) is int and preparer['start_ticks'] > 0 and preparer.get('argv') and
                   files and files.get(provider.get('path')) == provider.get('sha256') and
                   files.get(preparer.get('executable')) == preparer.get('executable_sha256'),
                   'exact reached controller/module input identity required', 'DATA_ERROR')
        audit = expected.get('writer_sites', {})
        rt.require(set(audit) == {'path', 'sha256', 'entries'} and files.get(audit['path']) == audit['sha256'] and
                   audit['entries'] and all(type(value) is int and value > 0 for value in audit['entries']) and
                   audit['entries'] == sorted(set(audit['entries'])),
                   'exact builtin writer-site audit required', 'DATA_ERROR')
        rt.require(rt.digest(Path(audit['path'])) == audit['sha256'] and
                   sorted(row['entry'] for row in json.loads(Path(audit['path']).read_text())['records']) == audit['entries'],
                   'writer-site metadata differs from its bound audit', 'DATA_ERROR')
        self._last_reached_modules = source['modules']
        self._last_reached_stats = None

    def _verify_reached(self, *, allow_identity_probe=False):
        expected = self.expected
        rt.require(rt.digest(self.path) == self.sha256 and json.loads(self.path.read_text()) == expected and
                   Path('/proc/sys/kernel/random/boot_id').read_text().strip() == expected['boot_id'],
                   'reached execution-session receipt or boot changed', 'DATA_ERROR')
        for name, wanted in expected['files'].items():
            path = Path(name)
            rt.require(path.is_absolute() and path.is_file() and rt.digest(path) == wanted,
                       'reached execution-session input changed: ' + name, 'DATA_ERROR')
        rt.require(NOTE.is_file() and rt.digest(NOTE) == expected['provider']['note_sha256'] and
                   module_note_sha256(expected['provider']['path']) == expected['provider']['note_sha256'],
                   'loaded reached provider Build ID note differs', 'DATA_ERROR')
        preparer = expected['preparer']
        preparing_task = task_identity(preparer['pid'])
        rt.require(all(preparing_task[key] == preparer[key] for key in
                       ('pid', 'start_ticks', 'executable', 'cwd', 'argv')) and not device_writers(),
                   'reached controller changed or an unrecorded device writer remains', 'UNDRAINED')
        for name, wanted in expected['parameters'].items():
            rt.require((PARAMETERS / name).read_text().strip() == wanted,
                       'reached execution-session parameter changed: ' + name, 'DATA_ERROR')
        source, observations = rt.status(), reached_observations()
        rt.require(source['state'] == source['frames'] == source['writers'] == 0 and
                   source['modules'] >= self._last_reached_modules and
                   observations['active'] == observations['unsupported'] == 0 and
                   observations['roots'] == observations['completions'] and not rt.registry(),
                   'reached source/family/registry state is not drained', 'UNDRAINED')
        if self._last_reached_stats is not None:
            rt.require(all(observations[key] >= self._last_reached_stats[key] for key in observations if key != 'active'),
                       'reached execution observations moved backwards', 'DATA_ERROR')
        allowed = {'kdlock_km'} | ({'kd_mmap1_identity'} if allow_identity_probe else set())
        other_modules = {'real_api', 'rwlock_bench', 'rwlock_test', 'rwsem_probe',
                         'spin_cacheline', 'mutex_cacheline', 'klock_module'}
        for module in Path('/sys/module').iterdir():
            rt.require(module.name in allowed or
                       (module.name not in other_modules and
                        not module.name.startswith(('kd_', 'jit_', 'tclock_', 'tc_'))),
                       'another experimental module remains: ' + module.name, 'UNDRAINED')
        forbidden = {'mmap1_threads', 'mmap1_processes', 'sc_worker', 'rb_worker', 'klock_test', 'kd_test', 'daemon'}
        for task in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
            try:
                rt.require(task.read_text().strip() not in forbidden,
                           'another workload/translator remains: ' + str(task), 'UNDRAINED')
            except (FileNotFoundError, ProcessLookupError):
                continue
        rt.require(task_identity(preparer['pid']) == preparing_task and rt.status() == source and
                   not device_writers(), 'reached source/controller/writer ledger changed across observation', 'UNDRAINED')
        bindings = int((PARAMETERS / 'rwsem_provider_bindings').read_text())
        rt.require(bindings >= 1, 'active reached factory has no source binding lease', 'UNDRAINED')
        self._last_reached_modules, self._last_reached_stats = source['modules'], observations
        return dict(source=source, bindings=bindings, reached=observations,
                    binding_drain_proved=False, application_delegation_proved=False)
