"""Optional compiler evidence; observations never decide translation or upload.

The daemon creates a fresh attempt directory and its context before launching
one compiler. Local evidence IDs describe that lineage, not a kernel lease ID.
Input hooks retain bytes from their real reads. The final manifest is written
only after a complete build, under the existing frozen-workspace convention.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import sys


MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_BINARY_BYTES = 4 * 1024 * 1024
MAX_CONTEXT_BYTES = 64 * 1024
MAX_ERRORS = 32
_recorder = None
_directory = None


def enabled():
    return bool(os.environ.get('KD_PROVENANCE_ATTEMPT_DIR'))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read_bounded(path, limit):
    with open(path, 'rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('artifact exceeds its capture bound')
    return data


def _start_ticks(pid):
    text = _read_bounded(f'/proc/{pid}/stat', 16384).decode('ascii')
    # comm can contain spaces and parentheses; fields after its final ')' start
    # with state (field 3), so starttime (field 22) is the twentieth token.
    return int(text[text.rindex(')') + 1:].split()[19])


def _stat(value):
    return {name: getattr(value, name) for name in
            ('st_dev', 'st_ino', 'st_rdev', 'st_mode')}


def _interpreter():
    # Read the running executable, rather than trusting a pathname that may
    # have been replaced after exec. This is an optional bounded observation.
    digest = hashlib.sha256()
    remaining = 64 * 1024 * 1024
    with open('/proc/self/exe', 'rb') as stream:
        while remaining:
            piece = stream.read(min(1024 * 1024, remaining))
            if not piece:
                break
            digest.update(piece)
            remaining -= len(piece)
        if not remaining and stream.read(1):
            raise ValueError('interpreter exceeds its identity capture bound')
    return dict(path=sys.executable, resolved_path=str(Path(sys.executable).resolve()),
                proc_exe=os.readlink('/proc/self/exe'), sha256=digest.hexdigest(),
                version=sys.version)


class _Recorder:
    def __init__(self, directory):
        self.path = Path(directory)
        self.errors = []
        self.errors_truncated = False
        self.sealed = False
        self.assembly_bytes = None
        self.data = dict(schema=1, context=None, complete=False,
                         evidence_complete=False, kernel_durable_lease_id=None,
                         kernel_lease_identity='not_exposed', histories={})
        try:
            if not self.path.is_absolute() or not self.path.is_dir():
                raise ValueError('attempt directory must already exist and be absolute')
            if ((self.path / 'manifest.json').exists() or
                    (self.path / 'manifest.sha256').exists()):
                self.sealed = True
                raise ValueError('attempt already contains a manifest')
            raw = _read_bounded(self.path / 'context.json', MAX_CONTEXT_BYTES)
            context = json.loads(raw)
            self.data['context'] = context
            self.data['context_sha256'] = _digest(raw)
            if (not isinstance(context, dict) or context.get('schema') != 1 or
                    not isinstance(context.get('session_id'), str) or
                    type(context.get('compile_attempt_id')) is not int or
                    not context['session_id'] or
                    not 0 < context['compile_attempt_id'] < 1 << 64):
                raise ValueError('invalid compiler context identity')
            entry = context.get('entry')
            fields = ('pid', 'tgid', 'entry', 'lock_kind', 'entry_abi',
                      'base_generation', 'status', 'target', 'jump_from')
            if (not isinstance(entry, dict) or
                    any(type(entry.get(name)) is not int for name in fields)):
                raise ValueError('invalid compiler entry context')
            self.data['context_validated'] = True
        except Exception as error:
            self.error('context', error)

    def error(self, stage, error):
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(dict(stage=str(stage)[:64],
                                    detail=f'{type(error).__name__}: {error}'[:384]))
        else:
            self.errors_truncated = True

    def artifact(self, name, raw):
        if not isinstance(raw, bytes):
            raise ValueError('exact input bytes were not captured')
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError('artifact exceeds its capture bound')
        with (self.path / name).open('xb') as stream:
            stream.write(raw)
        return dict(path=name, sha256=_digest(raw), bytes=len(raw))

    def capture(self, event, values):
        if self.sealed:
            return
        if event == 'translation':
            # Preserve daemon PID key/TGID separately from compiler processes.
            self.data['translation'] = values
            context = self.data.get('context') or {}
            expected = context.get('entry', {}) if isinstance(context, dict) else {}
            for name, key in (('pid', 'pid'), ('entry', 'entry'),
                              ('lock_kind', 'lock_kind'), ('entry_abi', 'entry_abi')):
                actual = values[name]
                if name == 'lock_kind':
                    actual = {'spin': 1, 'mutex': 2}.get(actual, 0)
                if actual != expected.get(key):
                    raise ValueError('translation arguments differ from daemon context')
        elif event == 'descriptor':
            fd, inherited_fd = values['fd'], values['inherited_fd']
            result = dict(validated=True, fd=fd, inherited=values['inherited'],
                          inherited_fd=inherited_fd, opened=_stat(values['opened']),
                          named=_stat(values['named']), source_info=values['source_info'],
                          access_flags=fcntl.fcntl(fd, fcntl.F_GETFL),
                          descriptor_flags=fcntl.fcntl(fd, fcntl.F_GETFD))
            if inherited_fd is not None:
                result['inherited_stat'] = _stat(os.fstat(inherited_fd))
                result['inherited_descriptor_flags'] = fcntl.fcntl(
                    inherited_fd, fcntl.F_GETFD)
                result['relationship'] = 'inherited_description_then_dup'
            else:
                result['relationship'] = 'direct_open'
            self.data['descriptor'] = result
        elif event == 'capabilities':
            raw = values['raw']
            if not isinstance(raw, bytes) or len(raw) > 4096:
                raise ValueError('capability response exceeds its capture bound')
            result = dict(raw_hex=raw.hex(), response_bytes=len(raw),
                          fd=values.get('fd'),
                          result=values.get('result'), errno=values.get('errno'),
                          response_available=values.get('errno') is None,
                          validated=values['validated'], parsed=values.get('parsed'))
            if len(raw) == 16:
                result.update(zip(('version', 'features', 'mutex_stack_bytes',
                                   'percpu_module_bytes'), struct.unpack('<IIII', raw)))
            self.data['capabilities'] = result
        elif event == 'service_table':
            mode = values['mode']
            result = dict(mode=mode, validated=True, generation=values.get('generation'),
                          slots=values.get('slots'), active=values.get('active'))
            self.data['service_table'] = result
            if mode == 'not_read':
                result['reason'] = values['reason']
                return
            for name, key in (('state_before_hex', 'before'), ('state_after_hex', 'after')):
                raw = values.get(key) or b''
                if not isinstance(raw, bytes) or len(raw) > 4096:
                    raise ValueError('registry state exceeds its capture bound')
                result[name] = raw.hex()
            pages = values.get('pages', [])
            if (len(pages) > 8 or any(not isinstance(raw, bytes) for raw in pages) or
                    sum(len(raw) for raw in pages) > MAX_ARTIFACT_BYTES):
                raise ValueError('registry pages exceed their capture bound')
            result['pages'] = [self.artifact(f'service-page-{i}.txt', raw)
                               for i, raw in enumerate(pages)]
            raw = values.get('raw')
            if raw is None:
                raw = b''.join(pages)
            result['snapshot'] = self.artifact('service-table.txt', raw)
            result['parsed'] = values['parsed']
        elif event == 'controls':
            result = dict(mode=values['mode'])
            self.data['controls'] = result
            if values['mode'] == 'read':
                result['snapshot'] = self.artifact('rwsem-controls.txt', values['raw'])
                result['parsed'] = values['parsed']
        elif event == 'history':
            name = values['name']
            if name not in ('callee_table.txt', 'ij_table.txt'):
                raise ValueError('unknown history input')
            result = dict(state=values['state'], errno=values.get('errno'),
                          parser_sha256=_digest(values['text'].encode('ascii')))
            self.data['histories'][name] = result
            if values['state'] == 'read':
                result.update(self.artifact(name, values['raw']))
        else:
            raise ValueError('unknown compiler evidence event')

    def assembly(self, path):
        if self.sealed:
            return
        self.assembly_bytes = _read_bounded(path, MAX_ARTIFACT_BYTES)
        self.data['assembly'] = self.artifact('jit.S', self.assembly_bytes)

    def finish(self, binary_path, dependency_identity):
        if self.sealed:
            return
        self.data['complete'] = True
        self.data['compiler'] = dict(pid=os.getpid(), ppid=os.getppid(),
                                     dependency_identity=dependency_identity)
        for name, callback in (
                ('start_ticks', lambda: _start_ticks(os.getpid())),
                ('parent_start_ticks', lambda: _start_ticks(os.getppid())),
                ('interpreter', _interpreter)):
            try:
                self.data['compiler'][name] = callback()
            except Exception as error:
                self.error(name, error)
        try:
            after = _read_bounded(Path(binary_path).with_name('jit.S'), MAX_ARTIFACT_BYTES)
            unchanged = self.assembly_bytes is not None and after == self.assembly_bytes
            self.data.setdefault('assembly', {})['unchanged_after_build'] = unchanged
            if not unchanged:
                raise ValueError('assembly changed after its pre-compiler snapshot')
        except Exception as error:
            self.error('assembly_after_build', error)
        try:
            raw = _read_bounded(binary_path, MAX_BINARY_BYTES)
            self.data['binary'] = dict(sha256=_digest(raw), bytes=len(raw),
                                       header_hex=raw[:64].hex())
        except Exception as error:
            self.error('binary', error)
        required = ('translation', 'descriptor', 'capabilities', 'service_table',
                    'controls', 'assembly', 'binary')
        for name in required:
            if name not in self.data:
                self.error(name, ValueError('required observation is absent'))
        for name in ('callee_table.txt', 'ij_table.txt'):
            if name not in self.data['histories']:
                self.error(name, ValueError('required history observation is absent'))
        if not self.data.get('capabilities', {}).get('validated'):
            self.error('capabilities', ValueError('capability response was not validated'))
        self.data['errors'] = self.errors
        self.data['errors_truncated'] = self.errors_truncated
        self.data['evidence_complete'] = not self.errors
        raw = (json.dumps(self.data, sort_keys=True, indent=2) + '\n').encode('ascii')
        # Close both exclusive temporary files before exposing either final
        # name. The sidecar is published last, so failed writes/closes cannot
        # leave an apparently complete manifest/digest pair for the daemon.
        manifest_path = self.path / 'manifest.json'
        sidecar_path = self.path / 'manifest.sha256'
        manifest_partial = self.path / 'manifest.json.partial'
        sidecar_partial = self.path / 'manifest.sha256.partial'
        self.sealed = True
        sidecar_rename_started = False
        try:
            for path, contents in ((manifest_partial, raw),
                                   (sidecar_partial, (_digest(raw) + '\n').encode('ascii'))):
                with path.open('xb') as stream:
                    if stream.write(contents) != len(contents):
                        raise OSError('short compiler manifest write')
                    stream.flush()
                    os.fsync(stream.fileno())
            if manifest_path.exists() or sidecar_path.exists():
                raise FileExistsError('attempt manifest appeared before finalization')
            os.rename(manifest_partial, manifest_path)
            sidecar_rename_started = True
            os.rename(sidecar_partial, sidecar_path)
        except Exception:
            # These final names belong to this fresh, single-writer attempt.
            # Also handle an observation failure reported after rename took
            # effect: no usable final sidecar may survive failed finalization.
            if sidecar_rename_started:
                try:
                    sidecar_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise


def _get():
    global _recorder, _directory
    directory = os.environ.get('KD_PROVENANCE_ATTEMPT_DIR')
    if not directory:
        return None
    if _recorder is None or directory != _directory:
        _directory = directory
        _recorder = _Recorder(directory)
    return _recorder


def _observe(stage, action):
    recorder = None
    try:
        recorder = _get()
        if recorder is not None:
            action(recorder)
    except Exception as error:
        # Evidence failures have no authority over compiler or publication
        # results. Keep finite diagnostics in any manifest that can be emitted.
        if recorder is not None:
            try:
                recorder.error(stage, error)
            except Exception:
                pass


def capture(event, **values):
    _observe(event, lambda recorder: recorder.capture(event, values))


def capture_assembly(path):
    _observe('assembly', lambda recorder: recorder.assembly(path))


def complete(binary_path, dependency_identity):
    _observe('manifest', lambda recorder: recorder.finish(binary_path, dependency_identity))
