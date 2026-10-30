#!/usr/bin/env python3
"""Read-only functional kernel artifact correspondence for stage/install r2.

This standalone helper never imports the historical preinstall controller.
Signing remains ordinary Kbuild work; no signing/certificate audit runs here.
"""
import hashlib
import json
import mmap
import os
from pathlib import Path, PurePosixPath
import struct

SCHEMA = 2
COMMIT = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
RELEASE = '7.0.0-38-kdscope1'
SOURCE = Path('/mnt/kdlock-builds/linux-' + RELEASE + '/source')
BUILD = SOURCE.parent / 'build'
BACKING = Path('/root/kdlock-build-output/linux-' + RELEASE)
BUILD_RUN = Path('/root/kdlock-evidence/10.176.26.71/tests/kernel-scope-build-20261030')
PREPARATION = Path('/root/kdlock-evidence/10.176.26.71/tests/kernel-scope-prepare-r2-20261030/result.json')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    # Do not read or capture a private signing key.
    require(path.name != 'signing_key.pem', 'refusing private signing-key capture')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def relative(name):
    require(isinstance(name, str) and bool(name), 'invalid relative path')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name,
            'unsafe/noncanonical relative path: ' + name)
    return p


def file_record(path, mode=False):
    require(path.is_file() and not path.is_symlink(), 'not a regular input: ' + str(path))
    row = dict(bytes=path.stat().st_size, sha256=sha(path))
    if mode:
        row['mode'] = path.stat().st_mode
    return row


def source_inventory():
    rows = {}
    def fail(error):
        raise error
    for directory, dirs, files in os.walk(SOURCE, followlinks=False, onerror=fail):
        for name in sorted(dirs + files):
            p = Path(directory) / name
            rel = str(p.relative_to(SOURCE))
            if p.is_symlink():
                rows[rel] = dict(link=os.readlink(p))
            elif p.is_file():
                rows[rel] = file_record(p, mode=True)
    return rows


def group_members(group):
    rows = []
    if group is None:
        return rows
    for p in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = p.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group and fields[0] != 'Z':
                rows.append(dict(pid=int(p.parent.name), start_ticks=int(fields[19])))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def idle():
    prefixes = ('kdlock', 'kd_', 'tclock', 'tc_', 'jit_', 'sc_', 'rb_', 'mmap_',
                'real_api', 'mutex_cacheline', 'spin_cacheline', 'rwlock_bench')
    require(not any(line.split()[0].startswith(prefixes)
                    for line in Path('/proc/modules').read_text().splitlines()),
            'project module remains loaded')
    blocked = {'make', 'gmake', 'cc1', 'cc1plus', 'rustc', 'ld', 'ld.bfd', 'ld.lld',
               'daemon', 'client', 'split-client', 'pipe_client', 'setfd_client'}
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = p.read_bytes().split(b'\0')
            if args and args[0] and int(p.parent.name) != os.getpid():
                require(Path(os.fsdecode(args[0])).name not in blocked,
                        'compiler/client/translator active: ' + str(p.parent.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    for p in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = p.read_text().strip()
            require(not name.startswith(('rb_worker', 'sc_worker', 'kd_mtask_', 'kd-local/',
                                          'kd_rwsem_', 'kd_proxy/', 'kd-cancel')),
                    'project worker remains active: ' + str(p))
        except (FileNotFoundError, ProcessLookupError):
            pass


class ELF:
    """Read the fixed ELF64 little-endian formats used by this x86 build."""
    def __init__(self, path):
        self.path = path
        self.stream = path.open('rb')
        self.data = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_READ)
        d = self.data
        require(d[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', d, 18)[0] == 62,
                'not x86-64 little-endian ELF')
        self.elf_type = struct.unpack_from('<H', d, 16)[0]
        shoff = struct.unpack_from('<Q', d, 40)[0]
        entsize, count, names_index = struct.unpack_from('<HHH', d, 58)
        require(entsize == 64 and count > 0 and names_index < count and
                shoff + count * entsize <= len(d), 'unsupported ELF section headers')
        self.sections = []
        for i in range(count):
            fields = struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * 64)
            self.sections.append(dict(zip(('name_index', 'type', 'flags', 'address', 'offset',
                'size', 'link', 'info', 'align', 'entsize'), fields)))
        strings = self.contents(self.sections[names_index])
        for section in self.sections:
            section['name'] = self.cstring(strings, section['name_index'])
        self.symbols = {}
        symtab = self.section('.symtab')
        require(symtab['entsize'] == 24 and symtab['size'] % 24 == 0, 'invalid symbol table')
        strings = self.contents(self.sections[symtab['link']])
        for offset in range(symtab['offset'], symtab['offset'] + symtab['size'], 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', d, offset)
            name = self.cstring(strings, name)
            if name:
                self.symbols.setdefault(name, []).append(dict(name=name, info=info, other=other,
                    index=index, value=value, size=size))

    @staticmethod
    def cstring(data, offset):
        require(0 <= offset < len(data), 'string offset outside table')
        end = data.find(b'\0', offset)
        require(end >= 0, 'unterminated ELF string')
        return data[offset:end].decode('utf-8')

    def contents(self, section):
        require(section['type'] != 8 and section['offset'] + section['size'] <= len(self.data),
                'missing/outside ELF section data')
        return self.data[section['offset']:section['offset'] + section['size']]

    def section(self, name):
        rows = [s for s in self.sections if s.get('name') == name]
        require(len(rows) == 1, 'missing/duplicate ELF section: ' + name)
        return rows[0]

    def close(self):
        self.data.close()
        self.stream.close()


def kernel_inputs(args):
    require(sha(BUILD_RUN / 'result.json') == args.build_result_sha256,
            'reviewed build result SHA changed')
    built = json.loads((BUILD_RUN / 'result.json').read_text())
    require(built.get('passed') is True and built.get('state') == 'COMPLETE' and
            built.get('returncode') == 0 and built.get('installed') is False and
            built.get('rebooted') is False and not built.get('drain_unknown'), 'full build did not complete')
    require(built['release'] == RELEASE and built['source'] == str(SOURCE) and
            built['build'] == str(BUILD) and built['boot_id'] == args.boot_id,
            'build roots/release/boot differ')
    require(all(built.get(key) is True for key in
                ('source_unchanged', 'config_unchanged', 'boot_unchanged')), 'build freeze failed')
    require(SOURCE.resolve() == SOURCE and BUILD.resolve() == BUILD and os.path.ismount(BUILD)
            and (BUILD.stat().st_dev, BUILD.stat().st_ino) ==
            (BACKING.stat().st_dev, BACKING.stat().st_ino), 'canonical bind mount absent/different')
    require(sha(PREPARATION) == built['preparation_sha256'], 'preparation receipt changed')
    require(sha(BUILD_RUN / 'source-inputs.json') == built['source_manifest_sha256'],
            'source manifest changed')
    require(sha(BUILD_RUN / 'input.config') == built['config_sha256'] == sha(BUILD / '.config'),
            'complete configuration changed')
    expected_outputs = {'vmlinux', 'arch/x86/boot/bzImage', 'System.map', 'Module.symvers',
        '.config', 'modules.order', 'include/config/kernel.release', 'include/generated/utsrelease.h',
        'include/generated/uapi/linux/version.h'}
    require(set(built['outputs']) == expected_outputs, 'build output manifest scope differs')
    for name, row in built['outputs'].items():
        relative(name)
        require(file_record(BUILD / name) == row, 'frozen output changed: ' + name)
    frozen = json.loads((BUILD_RUN / 'source-inputs.json').read_text())
    require(source_inventory() == frozen, 'complete kernel source/mode manifest differs')
    require((BUILD / 'include/config/kernel.release').read_text().strip() == RELEASE and
            (BUILD / 'include/generated/utsrelease.h').read_text().strip() ==
            '#define UTS_RELEASE "' + RELEASE + '"' and
            '#define LINUX_VERSION_CODE 458766' in
            (BUILD / 'include/generated/uapi/linux/version.h').read_text(), 'generated versions differ')
    config = {}
    for line in (BUILD / '.config').read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            k, v = line.split('=', 1)
            config[k] = v
    for key in ('CONFIG_KD_API_LOCKS', 'CONFIG_KDLOCK_MMAP', 'CONFIG_FRAME_POINTER',
                'CONFIG_SMP', 'CONFIG_MODULES', 'CONFIG_MODVERSIONS'):
        require(config.get(key) == 'y', 'required configuration absent: ' + key)
    for key in ('CONFIG_PREEMPT_RT', 'CONFIG_DEBUG_MUTEXES', 'CONFIG_DEBUG_LOCK_ALLOC',
                'CONFIG_LOCKDEP', 'CONFIG_DEBUG_SPINLOCK', 'CONFIG_X86_KERNEL_IBT',
                'CONFIG_MODULE_COMPRESS_ALL'):
        require(config.get(key, 'n') == 'n', 'unsupported configuration: ' + key)
    ordered = (BUILD / 'modules.order').read_text().splitlines()
    paths = []
    for name in ordered:
        name = name.removeprefix('./')
        relative(name)
        require(name.endswith('.o'), 'unexpected modules.order format')
        paths.append(name[:-2] + '.ko')
    require(paths and len(paths) == len(set(paths)) == built['module_count'],
            'ordered module count/uniqueness differs')
    actual = {str(p.relative_to(BUILD)) for p in BUILD.rglob('*.ko')}
    require(actual == set(paths), 'unexpected/missing build .ko files')
    modules = {name: file_record(BUILD / name, mode=True) for name in sorted(paths)}
    return built, modules
