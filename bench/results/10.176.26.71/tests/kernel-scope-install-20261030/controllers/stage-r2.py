#!/usr/bin/env python3
"""VM-only functional module stage; leave live modules, boot and GRUB unchanged.

Bind the historical build/preinstall receipts using a standalone functional
input helper. Normal Kbuild signing is retained without separate signing audits.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
SCHEMA = 2
RELEASE = '7.0.0-38-kdscope1'
COMMIT = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
DATA = Path('/mnt/kdlock-builds')
SOURCE = DATA / ('linux-' + RELEASE) / 'source'
BUILD = SOURCE.parent / 'build'
STAGE = DATA / 'kdscope1-install-stage-r2-20261030' / 'modules'
MODLIB = STAGE / 'lib/modules' / RELEASE
OUT = DATA / 'kdlock-evidence/10.176.26.71/tests/kernel-scope-module-stage-r2-20261030'
ENV = dict(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           LANG='C', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(OUT / 'tmp'))


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    require(path.name != 'signing_key.pem', 'refusing private signing-key capture')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def regular(path):
    require(path.is_file() and not path.is_symlink(), 'not a regular file: ' + str(path))
    s = path.stat()
    return dict(bytes=s.st_size, sha256=sha(path), mode=s.st_mode,
                allocated_bytes=s.st_blocks * 512)


def inventory(root):
    """Do not follow directory links (notably module source/build links)."""
    rows = {}
    def visit(path):
        s = path.lstat()
        key = str(path.relative_to(root))
        if stat.S_ISLNK(s.st_mode):
            rows[key] = dict(link=os.readlink(path), mode=s.st_mode)
        elif stat.S_ISREG(s.st_mode):
            rows[key] = regular(path)
        elif stat.S_ISDIR(s.st_mode):
            rows[key] = dict(directory=True, mode=s.st_mode)
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            raise RuntimeError('unsupported inventory member: ' + str(path))
    if root.exists() or root.is_symlink():
        visit(root)
    else:
        rows['.'] = dict(absent=True)
    return rows


def protected():
    roots = [Path(name) for name in ('/boot', '/lib/modules', '/etc/default/grub',
             '/etc/default/grub.d', '/etc/grub.d')]
    roots.extend(sorted(Path('/').glob('vmlinuz*')))
    roots.extend(sorted(Path('/').glob('initrd.img*')))
    return {str(path): inventory(path) for path in roots}


def load_artifact_helper(args):
    path = args.artifact_helper
    require(path.is_absolute() and path.resolve() == path and path.is_file() and not path.is_symlink(),
            'artifact helper must have an exact canonical regular path')
    require(sha(path) == args.artifact_helper_sha256, 'artifact helper SHA differs')
    spec = importlib.util.spec_from_file_location('scope_functional_artifact_inputs_r2', path)
    require(spec is not None and spec.loader is not None, 'cannot load artifact helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.SCHEMA == SCHEMA and module.RELEASE == RELEASE and module.SOURCE == SOURCE
            and module.BUILD == BUILD and module.COMMIT == COMMIT,
            'artifact helper schema/generation/roots differ')
    return module


def loader_identity(helper, path):
    """Allocated bytes and loader relocations/symbols; ignores removable DWARF.

    The module loader consumes SHF_ALLOC sections, their relocations and symbol
    bindings. Strip-debug can renumber sections/symbols, so those references are
    normalized by section/name/value rather than comparing index numbers.
    This is artifact correspondence, not a universal runtime ABI proof.
    """
    elf = helper.ELF(path)
    try:
        require(elf.elf_type == 1, 'module is not relocatable ELF: ' + str(path))
        allocated = {i: s for i, s in enumerate(elf.sections) if s['flags'] & 2}
        require(allocated and len({s['name'] for s in allocated.values()}) == len(allocated),
                'missing/duplicate allocated section names')
        sections = []
        for s in allocated.values():
            row = {k: s[k] for k in ('name', 'type', 'flags', 'size', 'align', 'entsize')}
            row['sha256'] = None if s['type'] == 8 else hashlib.sha256(elf.contents(s)).hexdigest()
            sections.append(row)
        tab = elf.section('.symtab')
        strings = elf.contents(elf.sections[tab['link']])
        symbols = []
        for offset in range(tab['offset'], tab['offset'] + tab['size'], 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', elf.data, offset)
            require(index != 0xffff, 'extended symbol indexes need separate review')
            target = elf.sections[index]['name'] if 0 < index < len(elf.sections) else index
            symbols.append(dict(name=elf.cstring(strings, name), info=info, other=other,
                                section=target, value=value, size=size))
        # FILE/debug-only symbols may disappear. Keep every allocated/undefined
        # and non-FILE absolute/common symbol that can affect module linkage.
        names = {s['name'] for s in allocated.values()}
        relevant = [s for s in symbols if s['section'] in names or s['section'] == 0 or
                    (s['section'] in (0xfff1, 0xfff2) and s['info'] & 15 != 4)]
        relocations = []
        for s in elf.sections:
            if s['type'] not in (4, 9) or s['info'] not in allocated:
                continue
            require(elf.sections[s['link']] is tab, 'relocation uses an unexpected symbol table')
            size = 24 if s['type'] == 4 else 16
            require(s['entsize'] == size and s['size'] % size == 0, 'invalid module relocations')
            for offset in range(s['offset'], s['offset'] + s['size'], size):
                where, info = struct.unpack_from('<QQ', elf.data, offset)
                require(info >> 32 < len(symbols), 'relocation symbol outside table')
                relocations.append(dict(section=allocated[s['info']]['name'], offset=where,
                    type=info & 0xffffffff, symbol=symbols[info >> 32],
                    addend=struct.unpack_from('<q', elf.data, offset + 16)[0] if size == 24 else None))
        key = lambda row: json.dumps(row, sort_keys=True)
        return digest_json(dict(sections=sorted(sections, key=key),
                               symbols=sorted(relevant, key=key),
                               relocations=sorted(relocations, key=key)))
    finally:
        elf.close()


class Stage:
    def __init__(self, args, helper):
        self.args, self.helper = args, helper
        self.child = self.group = self.current = None
        self.deadline = time.monotonic() + 5400
        self.operations = 0
        self.journal = (OUT / 'operations.jsonl').open('x')
        self.result = dict(schema=SCHEMA, correctness_scope='kernel-artifact-installation',
            historical_kernel_project_commit=COMMIT, current_provider_validated=False, passed=False, state='PREFLIGHT', release=RELEASE,
            source_commit=COMMIT, source=str(SOURCE), build=str(BUILD), stage=str(STAGE),
            staged_module_root=str(MODLIB), boot_id=args.boot_id, started=time.time(),
            controller_sha256=sha(Path(__file__)), preinstall_result=str(args.preinstall_result),
            preinstall_result_sha256=args.preinstall_result_sha256,
            preinstall_controller_sha256=args.preinstall_controller_sha256,
            artifact_helper_sha256=args.artifact_helper_sha256,
            build_result_sha256=args.build_result_sha256, installed=False, loaded=False,
            rebooted=False, private_key_read_by_controller=False,
            private_key_captured=False, performance_accepted=False, live_abi_validated=False)

    def persist(self):
        save(OUT / 'result.json', self.result)

    def record(self, value):
        self.journal.write(json.dumps(value, sort_keys=True) + '\n')
        self.journal.flush()

    def command(self, label, argv, seconds=30, allowed=(0,), compact=True):
        require(time.monotonic() < self.deadline, 'total stage deadline reached')
        require(re.fullmatch('[a-z0-9-]+', label) is not None, 'unsafe command label')
        argv = list(map(str, argv))
        path = OUT / ('operation.stdout' if compact else label + '.log')
        row = dict(event='start', number=self.operations, label=label, argv=argv,
                   started=time.time(), timeout_seconds=seconds)
        self.current = row
        with path.open('wb' if compact else 'xb') as log:
            self.child = subprocess.Popen(argv, cwd=OUT, env=ENV, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self.group = self.child.pid
            row['pid'] = self.group
            self.record(row)
            if not compact or self.operations % 100 == 0:
                self.result.update(state=label.upper(), operation_count=self.operations,
                                   active_operation=row)
                self.persist()
            end = min(self.deadline, time.monotonic() + seconds)
            while self.child.poll() is None:
                require(time.monotonic() < end, label + ': deadline; child untouched, drain unknown')
                try:
                    self.child.wait(timeout=min(10, max(.01, end - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            remaining = self.helper.group_members(self.group)
            row = dict(row, event='end', finished=time.time(), returncode=self.child.returncode,
                       remaining_processes=remaining, stdout_sha256=sha(path))
            if compact:
                require(path.stat().st_size <= 65536, 'unexpectedly large compact command output')
                output = path.read_bytes()
                row['stdout'] = output.decode('utf-8', errors='replace')
            else:
                output = b''
                row['log'] = str(path)
            self.record(row)
            require(not remaining and self.child.returncode in allowed, label + ': failed or undrained')
            code = self.child.returncode
        self.child = self.group = self.current = None
        self.operations += 1
        return output, code

    def bind_preinstall(self):
        path = self.args.preinstall_result
        require(path.is_absolute() and path.resolve() == path and path.is_file() and not path.is_symlink(),
                'preinstall result must have an exact canonical regular path')
        require(sha(path) == self.args.preinstall_result_sha256, 'preinstall result SHA differs')
        p = json.loads(path.read_text())
        require(p.get('passed') is True and p.get('state') == 'PREINSTALL_ARTIFACTS_VERIFIED_NOT_INSTALLED',
                'historical preinstall did not complete')
        require(p['source_commit'] == COMMIT and p['release'] == RELEASE and
                p['source'] == str(SOURCE) and p['build'] == str(BUILD) and
                p['boot_id'] == self.args.boot_id and
                p['controller_sha256'] == self.args.preinstall_controller_sha256 and
                p['build_result_sha256'] == self.args.build_result_sha256,
                'historical source/controller/build/boot binding differs')
        require(p.get('kernel_source_build_unchanged') is True and
                p.get('current_project_inputs_unchanged') is True and
                all(p.get(k) is False for k in ('installed', 'loaded', 'rebooted')) and
                p.get('site_count') == 3 and p.get('static_bridge_count') == 4,
                'historical preinstall artifact scope/invariants differ')
        directory = path.parent
        # These old reports are immutable historical linked/source evidence.
        # No old controller code is imported or executed, and no old provider is
        # treated as the current provider generation.
        files = {'controller.py': 'controller_sha256',
                 'build-module-identities.json': 'module_manifest_sha256',
                 'linked-api-audit.json': 'linked_audit_sha256',
                 'provider-api-audit.json': 'provider_audit_sha256',
                 'project-inputs.json': 'project_manifest_sha256',
                 'provider/kernel_module/kdlock_km.ko': 'provider_sha256'}
        for name, field in files.items():
            require(sha(directory / name) == p[field], 'historical artifact changed: ' + name)
        self.build_result, self.build_modules = self.helper.kernel_inputs(self.args)
        require(self.build_modules == json.loads((directory / 'build-module-identities.json').read_text())
                and len(self.build_modules) == p['module_count'] == self.build_result['module_count']
                and p['source_manifest_sha256'] == self.build_result['source_manifest_sha256'],
                'frozen build/module identity differs')
        shutil.copyfile(path, OUT / 'preinstall-result.json')
        shutil.copyfile(self.helper.BUILD_RUN / 'result.json', OUT / 'fullbuild-result.json')
        save(OUT / 'build-module-identities.json', self.build_modules)
        shutil.copyfile(directory / 'linked-api-audit.json', OUT / 'linked-api-audit.json')
        shutil.copyfile(directory / 'provider-api-audit.json', OUT / 'provider-api-audit.json')
        self.result.update(source_manifest_sha256=self.build_result['source_manifest_sha256'],
            build_module_manifest_sha256=sha(OUT / 'build-module-identities.json'),
            linked_api_audit_sha256=p['linked_audit_sha256'], provider_audit_sha256=p['provider_audit_sha256'],
            historical_provider_sha256=p['provider_sha256'])
        self.preinstall = p

    def module_paths(self):
        require(MODLIB.is_dir() and not MODLIB.is_symlink(), 'staged module root missing/linked')
        expected = {'kernel/' + name for name in self.build_modules}
        entries = inventory(MODLIB / 'kernel')
        actual = set()
        for name, row in entries.items():
            if row.get('directory'):
                continue
            require(name.endswith('.ko') and 'sha256' in row, 'unexpected staged kernel member: ' + name)
            actual.add('kernel/' + name)
        require(actual == expected, 'staged module path set differs from modules.order')
        all_ko = {str(path.relative_to(MODLIB)) for path in MODLIB.rglob('*.ko')}
        require(all_ko == expected, 'extra staged module outside kernel subtree')
        require(not any(MODLIB.rglob('*.ko.gz')) and not any(MODLIB.rglob('*.ko.xz'))
                and not any(MODLIB.rglob('*.ko.zst')), 'unexpected compressed module')
        ordered = (MODLIB / 'modules.order').read_text().splitlines()
        ordered = [name.replace('kernel/./', 'kernel/', 1) for name in ordered]
        original = [(name.removeprefix('./')[:-2] + '.ko')
                    for name in (BUILD / 'modules.order').read_text().splitlines()]
        require(ordered == ['kernel/' + name for name in original], 'staged module order differs')
        for name in ('modules.dep', 'modules.dep.bin', 'modules.alias', 'modules.alias.bin',
                     'modules.builtin', 'modules.builtin.modinfo'):
            regular(MODLIB / name)
        for name in ('modules.builtin', 'modules.builtin.modinfo'):
            require(sha(MODLIB / name) == sha(BUILD / name), 'staged builtin metadata differs')
        for name, target in (('build', BUILD), ('source', SOURCE)):
            link = MODLIB / name
            if name == 'source' and not link.exists() and not link.is_symlink():
                link.symlink_to(target)
                self.result['created_staged_source_link'] = True
            require(link.is_symlink() and os.readlink(link) == str(target) and link.resolve() == target,
                    'staged ' + name + ' link differs')
        return [MODLIB / ('kernel/' + name) for name in original]

    def verify_modules(self, paths):
        records = {}
        for number, path in enumerate(paths):
            name = str(path.relative_to(MODLIB))
            row = dict(regular(path),
                       build_sha256=self.build_modules[name.removeprefix('kernel/')]['sha256'])
            source = BUILD / name.removeprefix('kernel/')
            identity = loader_identity(self.helper, source)
            require(identity == loader_identity(self.helper, path),
                    'loadable contents/linkage changed during modules_install: ' + name)
            row.update(loadable_identity_sha256=identity, loadable_identity_equal=True)
            records[name] = row
            if number % 100 == 0:
                self.result.update(modules_checked=number + 1, operation_count=self.operations)
                self.persist()
        require(records and len(records) == len(paths), 'empty/incomplete module verification')
        for offset in range(0, len(paths), 100):
            batch = paths[offset:offset + 100]
            raw, _ = self.command('vermagic-' + str(offset), ['modinfo', '-F', 'vermagic', *batch])
            lines = raw.decode().splitlines()
            require(len(lines) == len(batch) and all(line.split() and line.split()[0] == RELEASE for line in lines),
                    'module release metadata differs')
            for path in batch:
                records[str(path.relative_to(MODLIB))]['release_verified'] = True
        save(OUT / 'module-verification.json', records)
        self.result.update(module_count=len(paths), all_module_releases_verified=True,
            all_loadable_build_stage_identities_equal=True,
            module_verification_sha256=sha(OUT / 'module-verification.json'))

    def execute(self):
        self.persist()
        self.bind_preinstall()
        before = protected()
        save(OUT / 'protected-before.json', before)
        # A conservative worst-case unstripped copy bound, despite strip-debug
        # normally reducing the stage greatly. Never reclaim any old artifacts.
        bound = sum(row['bytes'] for row in self.build_modules.values()) + 1024**3
        require(shutil.disk_usage(DATA).free > bound, 'DATA free space below conservative staging bound')
        self.result['resources_before'] = dict(root_free=shutil.disk_usage('/').free,
            data_free=shutil.disk_usage(DATA).free, conservative_stage_bound=bound)
        for label, path in (('root', '/'), ('data', DATA), ('boot', '/boot'), ('modules', '/lib/modules'), ('build', BUILD)):
            self.command('mount-' + label, ['findmnt', '-T', path, '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'])
        for label, argv in (('make-version', ['make', '--version']),
                            ('strip-version', ['x86_64-linux-gnu-strip', '--version']),
                            ('modinfo-version', ['modinfo', '--version']),
                            ('depmod-version', ['depmod', '--version'])):
            self.command(label, argv)
        self.helper.idle()
        require(not STAGE.parent.exists() and not STAGE.parent.is_symlink(), 'fresh staging prefix required')
        require(STAGE.parent.resolve() == STAGE.parent, 'staging parent path is not canonical')
        STAGE.mkdir(parents=True)
        self.command('modules-install', ['make', '-C', SOURCE, 'O=' + str(BUILD), 'ARCH=x86',
            'CC=x86_64-linux-gnu-gcc', 'KERNELRELEASE=' + RELEASE, '-j16',
            'INSTALL_MOD_PATH=' + str(STAGE), 'INSTALL_MOD_STRIP=1', 'modules_install'],
            seconds=1800, compact=False)
        paths = self.module_paths()
        staged_before = inventory(MODLIB)
        self.verify_modules(paths)
        staged_after = inventory(MODLIB)
        require(staged_after == staged_before, 'staged tree changed while being verified')
        save(OUT / 'staged-release-manifest.json', staged_after)
        built, modules = self.helper.kernel_inputs(self.args)
        require(built == self.build_result and modules == self.build_modules,
                'frozen kernel source/build inputs changed')
        require(sha(self.args.preinstall_result) == self.args.preinstall_result_sha256 and
                sha(self.args.artifact_helper) == self.args.artifact_helper_sha256,
                'preinstall receipts/helper changed')
        after = protected()
        save(OUT / 'protected-after.json', after)
        require(before == after, 'protected live modules/boot/GRUB changed')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == self.args.boot_id,
                'boot changed')
        self.helper.idle()
        sizes = [row for row in staged_after.values() if 'sha256' in row]
        self.result.update(passed=True, state='DATA_MODULE_STAGE_VERIFIED_NOT_INSTALLED',
            kernel_source_build_unchanged=True,
            protected_live_paths_unchanged=True, staged_manifest_sha256=sha(OUT / 'staged-release-manifest.json'),
            protected_before_sha256=sha(OUT / 'protected-before.json'),
            protected_after_sha256=sha(OUT / 'protected-after.json'),
            staged_regular_bytes=sum(row['bytes'] for row in sizes),
            staged_allocated_bytes=sum(row['allocated_bytes'] for row in sizes),
            resources_after=dict(root_free=shutil.disk_usage('/').free, data_free=shutil.disk_usage(DATA).free),
            limits=['Modules exist only under the recorded new DATA prefix.',
                'No live installation, initramfs, boot selection, loading or performance acceptance.',
                'The kernel and old provider evidence retain their historical 8446 identity.',
                'Current provider functionality and performance require separate validation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--build-result-sha256', required=True)
    parser.add_argument('--preinstall-result', type=Path, required=True)
    parser.add_argument('--preinstall-result-sha256', required=True)
    parser.add_argument('--artifact-helper', type=Path, required=True)
    parser.add_argument('--artifact-helper-sha256', required=True)
    parser.add_argument('--preinstall-controller-sha256', required=True)
    parser.add_argument('--idle-confirmed', required=True, action='store_true')
    args = parser.parse_args()
    for value in (args.build_result_sha256, args.preinstall_result_sha256, args.preinstall_controller_sha256,
                  args.artifact_helper_sha256):
        require(re.fullmatch('[0-9a-f]{64}', value) is not None, 'invalid reviewed SHA256')
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1', 'designated guest/root only')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id, 'wrong current boot')
    require(DATA.resolve() == DATA and DATA.stat().st_dev != Path('/').stat().st_dev,
            'DATA staging must be on a separate canonical filesystem')
    require(not OUT.exists() and not OUT.is_symlink() and
            not STAGE.parent.exists() and not STAGE.parent.is_symlink(),
            'fresh evidence and stage required; no retry overwrite')
    require(OUT.parent.resolve() == OUT.parent and STAGE.parent.resolve() == STAGE.parent,
            'noncanonical output parent')
    require(not (Path('/lib/modules') / RELEASE).exists() and not (Path('/lib/modules') / RELEASE).is_symlink()
            and not any(Path('/boot').glob('*-' + RELEASE)), 'new release already installed')
    require(shutil.disk_usage('/').free > 2 * 1024**3, 'root reserve below 2 GiB')
    helper = load_artifact_helper(args)
    helper.idle()
    OUT.mkdir(parents=True)
    (OUT / 'tmp').mkdir()
    shutil.copyfile(__file__, OUT / 'controller.py')
    shutil.copyfile(args.artifact_helper, OUT / 'artifact-inputs.py')
    run = Stage(args, helper)
    def interrupted(signum, frame):
        raise InterruptedError('controller interrupted; child untouched')
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, interrupted)
    try:
        run.execute()
    except BaseException as error:
        members = helper.group_members(run.group)
        uncertain = bool(members) or bool(run.child and run.child.poll() is None)
        run.result.update(passed=False, state='UNKNOWN_DRAIN' if uncertain else 'FAILED',
            error=repr(error), active_operation=run.current, remaining_processes=members,
            child_may_still_be_running=uncertain,
            failure_policy='Preserve stage/evidence/processes; no signals, cleanup, retry or live installation.')
    finally:
        run.journal.flush()
        os.fsync(run.journal.fileno())
        run.journal.close()
        run.result.update(finished=time.time(), operation_count=run.operations,
                          operations_sha256=sha(OUT / 'operations.jsonl'))
        if run.result['passed']:
            run.result.pop('active_operation', None)
        run.persist()
    print(json.dumps(run.result, sort_keys=True), flush=True)
    return 0 if run.result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
