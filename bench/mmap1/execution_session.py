"""Explicit prewarmed execution environment for an unchanged application run.

The controller owns load/prepare/activate/deactivate and normal retirement.
This verifier admits only its frozen module/daemon/registry, and does not prove
that an application invocation was delegated. Runtime trace joins do that.
"""
import json
import hashlib
from pathlib import Path

import bench_runtime as rt

PARAMETERS = Path('/sys/module/kdlock_km/parameters')
NOTE = Path('/sys/module/kdlock_km/notes/.note.gnu.build-id')


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


class ExecutionSession:
    """A hash-bound controller receipt, with no lifecycle side effects.

    Schema1 keys: boot_id; provider {path,sha256,note_sha256}; daemon
    {pid,start_ticks,executable,executable_sha256,cwd,argv}; parameters (exact
    selected values); registry (complete ready rt.registry rows); source
    {state,modules}; files (absolute immutable input file hashes).
    """
    def __init__(self, path, sha256):
        self.path = Path(path).resolve(strict=True)
        self.sha256 = sha256
        rt.require(rt.digest(self.path) == sha256, 'execution-session receipt bytes differ', 'DATA_ERROR')
        self.expected = json.loads(self.path.read_text())
        expected = self.expected
        rt.require(expected.get('schema') == 1 and expected.get('boot_id') and
                   expected.get('source', {}).get('state') == 0 and
                   set(expected['source']) == {'state', 'modules'} and
                   type(expected['source'].get('modules')) is int and expected['source']['modules'] >= 0,
                   'execution-session schema/source differs', 'DATA_ERROR')
        values = expected.get('parameters', {})
        rt.require(values.get('rwsem_provider_active') == 'Y' and
                   values.get('rwsem_provider_mode') == 'active' and
                   values.get('jit_timing') == 'N' and values.get('service_trace') in ('Y', 'N'),
                   'active provider and explicit instrumentation parameters required', 'DATA_ERROR')
        rows = expected.get('registry', [])
        rt.require(rows and len({(row['pid'], row['tgid'], row['entry']) for row in rows}) == len(rows) and
                   all(row['pid'] == row['tgid'] == row['status'] == 0 and row['entry_abi'] == 2 and
                       row['lock_kind'] == 2 and row['entry'] > 0 and row['code'] > 0 and row['generation'] > 0
                       for row in rows), 'complete ready ABI2 image registry required', 'DATA_ERROR')
        files = expected.get('files', {})
        provider, daemon = expected['provider'], expected['daemon']
        rt.require(files and files.get(provider['path']) == provider['sha256'] and
                   files.get(daemon['executable']) == daemon['executable_sha256'] and
                   daemon['pid'] > 0 and daemon['start_ticks'] > 0 and daemon['argv'],
                   'module/daemon must be bound by immutable input hashes', 'DATA_ERROR')

    def identity(self):
        return dict(path=str(self.path), sha256=self.sha256,
                    provider_sha256=self.expected['provider']['sha256'],
                    daemon_pid=self.expected['daemon']['pid'],
                    daemon_start_ticks=self.expected['daemon']['start_ticks'],
                    delegated_execution_proved=False)

    def verify(self, *, allow_identity_probe=False):
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
        actual = task_identity(daemon['pid'])
        rt.require(all(actual[key] == daemon[key] for key in
                       ('pid', 'start_ticks', 'executable', 'cwd', 'argv')) and
                   not rt.children(daemon['pid']),
                   'exact daemon lifetime/workspace changed or translator remains active', 'UNDRAINED')
        for name, wanted in expected['parameters'].items():
            rt.require((PARAMETERS / name).read_text().strip() == wanted,
                       'execution-session parameter changed: ' + name, 'DATA_ERROR')
        source = rt.status()
        rt.require(source == dict(expected['source'], frames=0, writers=0),
                   'source is not open with exact inactive frame/publisher state', 'UNDRAINED')
        rt.require(registry(rt.registry()) == registry(expected['registry']),
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
        bindings = int((PARAMETERS / 'rwsem_provider_bindings').read_text())
        rt.require(bindings >= 1, 'active factory has no source binding lease', 'UNDRAINED')
        return dict(source=source, bindings=bindings,
                    binding_drain_proved=False, application_delegation_proved=False)
