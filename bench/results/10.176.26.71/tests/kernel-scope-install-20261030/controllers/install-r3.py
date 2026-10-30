#!/usr/bin/env python3
"""VM-only continuation after completed r2 module copy and depmod; stop before GRUB/boot.

Root executes only after timing has finished and the DATA staging receipt has
passed review. This controller never builds, loads modules, modifies GRUB,
changes boot links, arms a boot or reboots. Failed partial installs are retained.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
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
LIVE = Path('/lib/modules') / RELEASE
PRIOR_OUT = DATA / 'kdlock-evidence/10.176.26.71/tests/kernel-scope-install-r2-20261030'
PRIOR_RESULT_SHA256 = '343b64688df8f055104c4262a28add64bc79800d515b04ce4e48ee984bb07293'
PRIOR_CONTROLLER_SHA256 = '23e0f656fbee0f36797555ab3e639736dc34522d45f40867cfbb6ef1028a1114'
PRIOR_PROTECTED_SHA256 = 'fb8ec836f5b907e364d0e5094704291fdc5753ef8a717a1b10f46a82bf26f11d'
PRIOR_INSTALLED_SHA256 = '053c7bf4efec8001d10a7860cb8060f42b3deb9df802ecd7de57910fc74d74f2'
OUT = DATA / 'kdlock-evidence/10.176.26.71/tests/kernel-scope-install-r3-20261030'
WORK = DATA / 'kdscope1-root-install-work-r3-20261030'
INITRD = Path('/boot') / ('initrd.img-' + RELEASE)
BOOT_INPUTS = {'arch/x86/boot/bzImage': 'vmlinuz-' + RELEASE,
               'System.map': 'System.map-' + RELEASE, '.config': 'config-' + RELEASE}
BOOT_NEW = set(BOOT_INPUTS.values()) | {INITRD.name}
INDEX_FILES = {'modules.dep', 'modules.dep.bin', 'modules.alias', 'modules.alias.bin',
               'modules.symbols', 'modules.symbols.bin', 'modules.softdep', 'modules.weakdep',
               'modules.devname', 'modules.builtin.bin', 'modules.builtin.alias.bin'}
ENV = dict(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           LANG='C', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(WORK / 'tmp'))
GIB = 1024**3
INITRD_BUDGET = 512 * 1024**2


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


def load_module(path, digest, name):
    require(path.is_absolute() and path.resolve() == path and path.is_file() and not path.is_symlink(),
            'reviewed helper path is not a canonical regular file')
    require(sha(path) == digest, 'reviewed helper SHA differs')
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'cannot read reviewed helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def byte_identity(inventory):
    # Filesystem allocation can differ across DATA and root. All regular bytes,
    # sizes, modes, directory modes and literal symlink targets remain exact.
    return {name: {k: v for k, v in row.items() if k != 'allocated_bytes'}
            for name, row in inventory.items()}


def old_only(protected):
    """Exclude only this operation's four boot leaves and new module subtree."""
    result = {}
    for root, entries in protected.items():
        result[root] = {name: row for name, row in entries.items()
            if not (root == '/boot' and name in BOOT_NEW) and
               not (root == '/lib/modules' and (name == RELEASE or name.startswith(RELEASE + '/')))}
    return result


def archive_path(name):
    require(not name.startswith('/'), 'absolute initramfs path: ' + name)
    name = name.removeprefix('./').removesuffix('/') or '.'
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and str(p) == name,
            'unsafe initramfs path: ' + name)
    return p.parts


def module_relative(parts):
    """Only actual lib/modules path components identify a kernel release.

    A modprobe blacklist filename mentioning an old kernel is not such a path.
    Return a module-root-relative member when a release component is present.
    """
    found = []
    for index in range(len(parts) - 2):
        if parts[index:index + 2] == ('lib', 'modules'):
            require(parts[index + 2] == RELEASE, 'foreign release directory in initramfs')
            found.append('/'.join(parts[index + 3:]))
    require(len(found) <= 1, 'ambiguous nested module root in initramfs')
    return found[0] if found else None


class Install:
    def __init__(self, args, stage_helper):
        self.args, self.stage_helper = args, stage_helper
        self.child = self.group = None
        self.deadline = time.monotonic() + 3600
        self.result = dict(schema=SCHEMA, correctness_scope='kernel-artifact-installation',
            historical_kernel_project_commit=COMMIT, current_provider_validated=False, passed=False, state='PREFLIGHT', started=time.time(),
            release=RELEASE, source_commit=COMMIT, source=str(SOURCE), build=str(BUILD),
            boot_id=args.boot_id, controller_sha256=sha(Path(__file__)),
            stage_result=str(args.stage_result), stage_result_sha256=args.stage_result_sha256,
            stage_controller_sha256=args.stage_controller_sha256,
            installed=False, module_tree_created=False, boot_files_installed=False,
            initramfs_created=False, grub_modified=False, boot_links_modified=False,
            boot_armed=False, rebooted=False, loaded=False, private_key_read=False,
            performance_accepted=False, live_kernel_validated=False, commands=[],
            module_tree_reused=True, module_copy_rerun=False, depmod_rerun=False)

    def persist(self):
        save(OUT / 'result.json', self.result)

    def command(self, label, argv, seconds=120):
        require(re.fullmatch('[a-z0-9-]+', label) is not None, 'unsafe log label')
        require(time.monotonic() < self.deadline, 'overall install deadline reached')
        path = OUT / (label + '.log')
        row = dict(label=label, argv=list(map(str, argv)), started=time.time(), timeout_seconds=seconds)
        self.result['commands'].append(row)
        self.result['state'] = label.upper()
        with path.open('xb') as log:
            self.child = subprocess.Popen(row['argv'], cwd=OUT, env=ENV, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self.group = self.child.pid
            row['pid'] = self.group
            self.persist()
            end = min(self.deadline, time.monotonic() + seconds)
            while self.child.poll() is None:
                require(time.monotonic() < end, label + ': deadline; child untouched, drain unknown')
                try:
                    self.child.wait(timeout=min(10, max(.01, end - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            remaining = self.artifact_helper.group_members(self.group)
            row.update(returncode=self.child.returncode, finished=time.time(),
                       remaining_processes=remaining, log_sha256=sha(path))
            self.persist()
            require(not remaining and self.child.returncode == 0, label + ': failure or live descendants')
        self.child = self.group = None
        return path

    def bind_prior_install(self):
        path = self.args.prior_install_result
        require(path == PRIOR_OUT / 'result.json' and path.resolve() == path and
                path.is_file() and not path.is_symlink(), 'wrong retained r2 install result')
        require(self.args.prior_install_result_sha256 == PRIOR_RESULT_SHA256 and
                sha(path) == PRIOR_RESULT_SHA256, 'retained r2 install failure SHA differs')
        prior = json.loads(path.read_text())
        require(prior.get('passed') is False and prior.get('state') == 'FAILED' and
                prior.get('child_may_still_be_running') is False and
                prior.get('remaining_processes') == [] and
                prior.get('error') == "RuntimeError('depmod removed/linked an index or changed an unexpected member')",
                'r2 install is not the recorded drained inventory failure')
        require(prior['schema'] == SCHEMA and prior['release'] == RELEASE and
                prior['source_commit'] == prior['historical_kernel_project_commit'] == COMMIT and
                prior['source'] == str(SOURCE) and prior['build'] == str(BUILD) and
                prior['boot_id'] == self.args.boot_id and
                prior['controller_sha256'] == PRIOR_CONTROLLER_SHA256 and
                prior['module_count'] == self.stage['module_count'] == 6901 and
                prior.get('module_tree_created') is True and
                prior.get('partial_new_module_tree_exists') is True and
                prior.get('partial_new_boot_files') == [] and
                all(prior.get(k) is False for k in ('installed', 'loaded', 'rebooted',
                    'boot_files_installed', 'initramfs_created', 'grub_modified',
                    'boot_links_modified', 'boot_armed', 'current_provider_validated',
                    'performance_accepted', 'live_kernel_validated')),
                'r2 install generation/partial-state differs')
        for field in ('stage_result_sha256', 'stage_controller_sha256'):
            require(prior[field] == getattr(self.args, field), 'r2 stage binding differs: ' + field)
        require(prior['stage_result'] == str(self.args.stage_result), 'r2 stage path differs')
        for field in ('artifact_helper_sha256', 'build_result_sha256', 'staged_manifest_sha256',
                      'preinstall_result_sha256', 'preinstall_controller_sha256',
                      'linked_api_audit_sha256', 'provider_audit_sha256', 'historical_provider_sha256'):
            require(prior[field] == self.stage[field], 'r2 build/artifact binding differs: ' + field)
        commands = prior['commands']
        labels = ['mount-root', 'mount-boot', 'mount-modules', 'mount-data',
                  'cp-version', 'depmod-version', 'copy-new-module-release', 'depmod-new-release']
        require([row.get('label') for row in commands] == labels and
                all(row.get('returncode') == 0 and row.get('remaining_processes') == []
                    for row in commands), 'r2 commands did not complete and drain exactly')
        require(commands[-2]['argv'] == ['cp', '-a', '--reflink=never', '--', str(self.stage_root), str(LIVE)]
                and commands[-1]['argv'] == ['depmod', '-a', RELEASE],
                'r2 completed copy/depmod argv differs')
        bindings = {'result.json': PRIOR_RESULT_SHA256, 'controller.py': PRIOR_CONTROLLER_SHA256,
            'protected-before.json': PRIOR_PROTECTED_SHA256,
            'installed-before-depmod.json': PRIOR_INSTALLED_SHA256,
            'reviewed-stage-controller.py': self.args.stage_controller_sha256,
            'stage-result.json': self.args.stage_result_sha256,
            'artifact-inputs.py': self.stage['artifact_helper_sha256'],
            'fullbuild-result.json': self.stage['build_result_sha256'],
            'staged-release-manifest.json': self.stage['staged_manifest_sha256'],
            'module-verification.json': self.stage['module_verification_sha256']}
        bindings.update({row['label'] + '.log': row['log_sha256'] for row in commands})
        retained = OUT / 'prior-install-r2'
        retained.mkdir()
        for name, expected in bindings.items():
            require(sha(PRIOR_OUT / name) == expected, 'retained r2 evidence changed: ' + name)
            shutil.copyfile(PRIOR_OUT / name, retained / name)
            require(sha(retained / name) == expected, 'r2 evidence copy differs: ' + name)
        self.prior_before = json.loads((PRIOR_OUT / 'protected-before.json').read_text())
        self.prior_installed = json.loads((PRIOR_OUT / 'installed-before-depmod.json').read_text())
        require(self.prior_before == json.loads((self.stage_dir / 'protected-after.json').read_text()),
                'r2 original protected baseline differs from verified stage')
        require(byte_identity(self.prior_installed) == byte_identity(self.staged),
                'r2 pre-depmod installed tree differs from verified stage')
        self.prior_bindings = bindings
        save(OUT / 'prior-install-r2-bindings.json', bindings)
        self.result.update(prior_install_result=str(path), prior_install_result_sha256=PRIOR_RESULT_SHA256,
            prior_install_state='FAILED', prior_install_controller_sha256=PRIOR_CONTROLLER_SHA256,
            prior_copy_returncode=0, prior_depmod_returncode=0, prior_copy_depmod_drained=True,
            prior_install_bindings_sha256=sha(OUT / 'prior-install-r2-bindings.json'))
        self.persist()

    def bind_stage(self):
        path = self.args.stage_result
        require(path.is_absolute() and path.resolve() == path and path.is_file() and not path.is_symlink(),
                'stage result must be a canonical regular file')
        require(sha(path) == self.args.stage_result_sha256, 'stage result SHA differs')
        stage = json.loads(path.read_text())
        require(stage.get('passed') is True and stage.get('schema') == SCHEMA and
                stage.get('correctness_scope') == 'kernel-artifact-installation' and
                stage.get('state') == 'DATA_MODULE_STAGE_VERIFIED_NOT_INSTALLED',
                'functional module staging did not complete')
        require(stage['release'] == RELEASE and stage['source_commit'] == COMMIT and
                stage.get('historical_kernel_project_commit') == COMMIT and
                stage.get('current_provider_validated') is False and
                stage['source'] == str(SOURCE) and stage['build'] == str(BUILD) and
                stage['boot_id'] == self.args.boot_id and
                stage['controller_sha256'] == self.args.stage_controller_sha256,
                'stage source/build/controller/boot binding differs')
        require(all(stage.get(k) is True for k in ('kernel_source_build_unchanged',
                    'protected_live_paths_unchanged', 'all_module_releases_verified',
                    'all_loadable_build_stage_identities_equal')) and
                all(stage.get(k) is False for k in ('installed', 'loaded', 'rebooted')),
                'staging verification is incomplete')
        self.stage_dir = path.parent
        self.stage_root = self.stage_helper.MODLIB
        require(stage['staged_module_root'] == str(self.stage_root) and
                stage['stage'] == str(self.stage_helper.STAGE), 'stage path differs')
        bindings = {'controller.py': 'controller_sha256',
            'preinstall-result.json': 'preinstall_result_sha256',
            'artifact-inputs.py': 'artifact_helper_sha256',
            'fullbuild-result.json': 'build_result_sha256',
            'build-module-identities.json': 'build_module_manifest_sha256',
            'staged-release-manifest.json': 'staged_manifest_sha256',
            'module-verification.json': 'module_verification_sha256',
            'protected-before.json': 'protected_before_sha256',
            'protected-after.json': 'protected_after_sha256',
            'linked-api-audit.json': 'linked_api_audit_sha256',
            'provider-api-audit.json': 'provider_audit_sha256',
            'operations.jsonl': 'operations_sha256'}
        for name, field in bindings.items():
            require(sha(self.stage_dir / name) == stage[field], 'staging receipt changed: ' + name)
        self.artifact_args = argparse.Namespace(boot_id=self.args.boot_id,
            build_result_sha256=stage['build_result_sha256'],
            artifact_helper=self.stage_dir / 'artifact-inputs.py',
            artifact_helper_sha256=stage['artifact_helper_sha256'])
        self.artifact_helper = self.stage_helper.load_artifact_helper(self.artifact_args)
        self.artifact_helper.idle()
        self.built, self.build_modules = self.artifact_helper.kernel_inputs(self.artifact_args)
        require(self.built == json.loads((self.stage_dir / 'fullbuild-result.json').read_text()) and
                self.build_modules == json.loads((self.stage_dir / 'build-module-identities.json').read_text()),
                'full build/source inputs differ from staging')
        pre = json.loads((self.stage_dir / 'preinstall-result.json').read_text())
        require(pre.get('passed') is True and pre.get('state') == 'PREINSTALL_ARTIFACTS_VERIFIED_NOT_INSTALLED'
                and pre['source_commit'] == COMMIT and pre['release'] == RELEASE
                and pre['build_result_sha256'] == stage['build_result_sha256']
                and pre['controller_sha256'] == stage['preinstall_controller_sha256']
                and pre['provider_sha256'] == stage['historical_provider_sha256']
                and pre['linked_audit_sha256'] == stage['linked_api_audit_sha256']
                and pre['provider_audit_sha256'] == stage['provider_audit_sha256']
                and pre['site_count'] == 3 and pre['static_bridge_count'] == 4,
                'historical preinstall proof is not bound to this stage')
        self.staged = json.loads((self.stage_dir / 'staged-release-manifest.json').read_text())
        require(byte_identity(self.stage_helper.inventory(self.stage_root)) == byte_identity(self.staged),
                'exact staged module tree changed')
        module_rows = {name: row for name, row in self.staged.items() if name.endswith('.ko')}
        self.verifications = json.loads((self.stage_dir / 'module-verification.json').read_text())
        require(set(module_rows) == set(self.verifications) ==
                {'kernel/' + name for name in self.build_modules} and
                len(module_rows) == stage['module_count'] == self.built['module_count'],
                'module verification coverage differs')
        for name, row in module_rows.items():
            check = self.verifications[name]
            require(row['sha256'] == check['sha256'] and row['bytes'] == check['bytes'] and
                    check['build_sha256'] == self.build_modules[name.removeprefix('kernel/')]['sha256'] and
                    check.get('loadable_identity_equal') is True and check.get('release_verified') is True,
                    'module build/stage identity or release differs: ' + name)
        config = (BUILD / '.config').read_text().splitlines()
        for key in ('CONFIG_SCSI', 'CONFIG_BLK_DEV_SD', 'CONFIG_SCSI_VIRTIO',
                    'CONFIG_VIRTIO', 'CONFIG_VIRTIO_PCI', 'CONFIG_EXT4_FS'):
            require(key + '=y' in config, 'required built-in root storage support absent: ' + key)
        for name in ('preinstall-result.json', 'fullbuild-result.json', 'module-verification.json',
                     'staged-release-manifest.json', 'linked-api-audit.json', 'provider-api-audit.json',
                     'artifact-inputs.py'):
            shutil.copyfile(self.stage_dir / name, OUT / name)
        shutil.copyfile(path, OUT / 'stage-result.json')
        self.result.update(build_result_sha256=stage['build_result_sha256'],
            preinstall_result_sha256=stage['preinstall_result_sha256'],
            preinstall_controller_sha256=stage['preinstall_controller_sha256'],
            artifact_helper_sha256=stage['artifact_helper_sha256'],
            source_manifest_sha256=stage['source_manifest_sha256'],
            linked_api_audit_sha256=stage['linked_api_audit_sha256'],
            provider_audit_sha256=stage['provider_audit_sha256'],
            staged_manifest_sha256=stage['staged_manifest_sha256'], module_count=len(module_rows),
            historical_provider_sha256=stage['historical_provider_sha256'])
        self.stage = stage

    def reserve_space(self):
        rows = [row for row in self.staged.values() if 'sha256' in row]
        regular_allocated = sum(row['allocated_bytes'] for row in rows)
        # Include directory/link blocks, without counting a hardlinked inode
        # twice. lstat never follows the canonical source/build symlinks.
        seen, allocated = set(), 0
        for name in self.staged:
            s = (self.stage_root / name).lstat()
            key = (s.st_dev, s.st_ino)
            if key not in seen:
                allocated += s.st_blocks * 512
                seen.add(key)
        block = os.statvfs('/boot').f_frsize
        boot = sum(((self.built['outputs'][name]['bytes'] + block - 1) // block) * block
                   for name in BOOT_INPUTS)
        available = shutil.disk_usage('/').free
        # The module tree already occupies root space; do not budget a second copy.
        need = boot + INITRD_BUDGET + 2 * GIB
        require(available >= need, 'root cannot preserve 2 GiB after module/boot/initrd budget')
        # Be conservative on a separately mounted /boot as well.
        require(shutil.disk_usage('/boot').free >= boot + INITRD_BUDGET + 64 * 1024**2,
                'boot filesystem reserve unavailable')
        require(shutil.disk_usage(DATA).free >= 2 * GIB, 'DATA initramfs work reserve unavailable')
        self.result['space_admission'] = dict(root_free=available,
            staged_regular_allocated_bytes=regular_allocated,
            staged_total_allocated_bytes=allocated, rounded_boot_bytes=boot,
            initramfs_budget_bytes=INITRD_BUDGET, required_root_reserve=2 * GIB,
            required_root_free=need, root_after_budget=available - boot - INITRD_BUDGET,
            module_copy_budget_bytes=0, existing_module_tree_reused=True,
            data_free=shutil.disk_usage(DATA).free, boot_free=shutil.disk_usage('/boot').free)
        self.persist()

    def copy_boot_file(self, name, target_name):
        source, target = BUILD / name, Path('/boot') / target_name
        require(not target.exists() and not target.is_symlink(), 'boot leaf already exists')
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
            dst.flush()
            os.fsync(dst.fileno())
        target.chmod(0o644)
        require(sha(target) == self.built['outputs'][name]['sha256'], 'new boot copy differs')

    def verify_initramfs(self, installed):
        require(INITRD.is_file() and not INITRD.is_symlink() and INITRD.stat().st_size > 0,
                'new initramfs absent/nonregular/empty')
        require(INITRD.stat().st_size <= INITRD_BUDGET, 'initramfs exceeds admitted 512 MiB budget')
        listing_path = self.command('initramfs-list', ['lsinitramfs', INITRD], 180)
        listing = listing_path.read_text().splitlines()
        require(listing, 'empty initramfs listing')
        names = []
        for name in listing:
            parts = archive_path(name)
            module_relative(parts)
            require(not name.endswith(('.ko.gz', '.ko.xz', '.ko.zst')), 'unsupported compressed module in initramfs')
            names.append('/'.join(parts))
        require('init' in names, 'initramfs root init member absent')
        extract = WORK / 'initramfs-extracted'
        require(not extract.exists() and not extract.is_symlink(), 'fresh initramfs extraction required')
        self.command('initramfs-extract', ['unmkinitramfs', INITRD, extract], 300)
        modules = {}
        for directory, dirs, files in os.walk(extract, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                relative = str(path.relative_to(extract))
                module_name = module_relative(archive_path(relative))
                require(not name.endswith(('.ko.gz', '.ko.xz', '.ko.zst')), 'compressed extracted module')
                if name.endswith('.ko'):
                    require(module_name and module_name in installed and path.is_file() and
                            not path.is_symlink(), 'module absent from exact installed tree: ' + relative)
                    require(sha(path) == installed[module_name]['sha256'],
                            'initramfs module differs from verified installation: ' + relative)
                    modules[relative] = dict(installed_path=module_name,
                        sha256=installed[module_name]['sha256'], bytes=path.stat().st_size)
        require(modules, 'no installed module bytes verified in initramfs')
        save(OUT / 'initramfs-module-identities.json', modules)
        self.result.update(initramfs_sha256=sha(INITRD), initramfs_bytes=INITRD.stat().st_size,
            initramfs_module_copies=len(modules),
            initramfs_unique_modules=len({row['installed_path'] for row in modules.values()}),
            initramfs_module_manifest_sha256=sha(OUT / 'initramfs-module-identities.json'))

    def execute(self):
        self.persist()
        self.bind_stage()
        self.bind_prior_install()
        self.artifact_helper.idle()
        before = self.prior_before
        current_protected = self.stage_helper.protected()
        require(old_only(current_protected) == before,
                'old installed modules/boot/GRUB changed since original r2 baseline')
        save(OUT / 'protected-before.json', before)
        save(OUT / 'protected-resume-before.json', current_protected)
        self.reserve_space()
        installed_before = self.prior_installed
        installed = self.stage_helper.inventory(LIVE)
        before_identity, installed_identity = byte_identity(installed_before), byte_identity(installed)
        require(installed_identity == before_identity == byte_identity(self.staged),
                'existing module bytes/modes/paths/links differ from verified copy and stage')
        # st_blocks can settle independently of contents after the original copy.
        # Compare artifact changes with the same byte_identity projection above.
        changes = {name: dict(before=before_identity.get(name), after=installed_identity.get(name))
                   for name in set(before_identity) | set(installed_identity)
                   if before_identity.get(name) != installed_identity.get(name)}
        allocation_changes = {name: dict(before=installed_before[name].get('allocated_bytes'),
                                        after=installed[name].get('allocated_bytes'))
                              for name in installed if installed_before[name].get('allocated_bytes') !=
                              installed[name].get('allocated_bytes')}
        for name in ('modules.dep', 'modules.dep.bin', 'modules.alias', 'modules.alias.bin',
                     'modules.builtin', 'modules.builtin.modinfo'):
            self.stage_helper.regular(LIVE / name)
        save(OUT / 'installed-before-depmod.json', installed_before)
        save(OUT / 'installed-resume-before.json', installed)
        save(OUT / 'depmod-index-changes.json', changes)
        save(OUT / 'allocation-observations.json', allocation_changes)
        self.result.update(module_tree_created=False, reused_module_tree_verified=True,
            semantic_depmod_changes=len(changes), allocation_observation_count=len(allocation_changes),
            allocation_observations_sha256=sha(OUT / 'allocation-observations.json'))
        self.persist()
        for name, target in BOOT_INPUTS.items():
            self.copy_boot_file(name, target)
        self.result['boot_files_installed'] = True
        require(not INITRD.exists() and not INITRD.is_symlink(), 'new initramfs already exists')
        self.command('make-new-initramfs', ['mkinitramfs', '-o', INITRD, RELEASE], 900)
        self.result['initramfs_created'] = True
        self.verify_initramfs(installed)
        installed_after = self.stage_helper.inventory(LIVE)
        require(byte_identity(installed_after) == byte_identity(installed),
                'installed module tree changed during initramfs creation')
        installed = installed_after
        require(byte_identity(self.stage_helper.inventory(self.stage_root)) == byte_identity(self.staged), 'DATA stage changed during installation')
        for name, target in BOOT_INPUTS.items():
            require(sha(Path('/boot') / target) == self.built['outputs'][name]['sha256'], 'new boot artifact changed')
        built, modules = self.artifact_helper.kernel_inputs(self.artifact_args)
        require(built == self.built and modules == self.build_modules,
                'full kernel source/build inputs changed')
        require(sha(self.args.stage_result) == self.args.stage_result_sha256 and
                sha(self.args.stage_controller) == self.args.stage_controller_sha256 and
                sha(self.artifact_args.artifact_helper) == self.stage['artifact_helper_sha256'],
                'staging receipt/helpers changed')
        for name, expected in self.prior_bindings.items():
            require(sha(PRIOR_OUT / name) == expected and
                    sha(OUT / 'prior-install-r2' / name) == expected,
                    'original or retained r2 evidence changed: ' + name)
        after = self.stage_helper.protected()
        save(OUT / 'protected-after.json', after)
        require(old_only(after) == before, 'old kernel/module/boot/GRUB/default/boot-link contents changed')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == self.args.boot_id and
                os.uname().release == '7.0.0-38-kdlock1', 'running kernel/boot changed')
        require(shutil.disk_usage('/').free >= 2 * GIB, 'final root reserve below 2 GiB')
        require(time.monotonic() < self.deadline, 'install verification exceeded overall deadline')
        self.artifact_helper.idle()
        save(OUT / 'installed-release-manifest.json', installed)
        boot = {name: self.stage_helper.regular(Path('/boot') / name) for name in sorted(BOOT_NEW)}
        save(OUT / 'installed-boot-manifest.json', boot)
        self.result.update(passed=True, state='NEW_KERNEL_INSTALLED_NOT_ARMED', installed=True,
            kernel_source_build_unchanged=True,
            staged_tree_unchanged=True, protected_old_paths_unchanged=True,
            installed_manifest_sha256=sha(OUT / 'installed-release-manifest.json'),
            boot_manifest_sha256=sha(OUT / 'installed-boot-manifest.json'),
            protected_before_sha256=sha(OUT / 'protected-before.json'),
            protected_after_sha256=sha(OUT / 'protected-after.json'),
            depmod_changes_sha256=sha(OUT / 'depmod-index-changes.json'),
            root_free=shutil.disk_usage('/').free, data_free=shutil.disk_usage(DATA).free,
            next_gate='Separate reviewed GRUB append and explicit Native-MM-off boot; not implemented here.',
            limits=['The original r2 install remains FAILED; its completed copy and depmod were reused.',
                    'No running-kernel/API/MM/performance validation is claimed.',
                    'Existing boot/default selection remains unchanged; this release is not armed.',
                    'The kernel remains the historical 8446 artifact; the current provider is separate.',
                    'Later functional and performance checks are required on explicit Native/KD modes.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--prior-install-result', type=Path, required=True)
    parser.add_argument('--prior-install-result-sha256', required=True)
    parser.add_argument('--stage-result', type=Path, required=True)
    parser.add_argument('--stage-result-sha256', required=True)
    parser.add_argument('--stage-controller', type=Path, required=True)
    parser.add_argument('--stage-controller-sha256', required=True)
    parser.add_argument('--idle-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    for digest in (args.stage_result_sha256, args.stage_controller_sha256, args.prior_install_result_sha256):
        require(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'invalid reviewed SHA256')
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1', 'designated guest/root only')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id, 'wrong current boot')
    require(DATA.resolve() == DATA and DATA.stat().st_dev != Path('/').stat().st_dev,
            'DATA workspace must be on a separate canonical filesystem')
    require(LIVE.is_dir() and not LIVE.is_symlink(), 'existing r2 module release required')
    for path in (OUT, WORK, *(Path('/boot') / name for name in BOOT_NEW)):
        require(not path.exists() and not path.is_symlink(), 'fresh output required: ' + str(path))
    require(OUT.parent.resolve() == OUT.parent and WORK.parent.resolve() == WORK.parent,
            'output parent is not canonical')
    helper = load_module(args.stage_controller, args.stage_controller_sha256, 'reviewed_scope_stage')
    require(helper.SCHEMA == SCHEMA and helper.RELEASE == RELEASE and helper.COMMIT == COMMIT and helper.BUILD == BUILD
            and helper.SOURCE == SOURCE, 'reviewed staging generation/roots differ')
    OUT.mkdir(parents=True)
    (WORK / 'tmp').mkdir(parents=True)
    shutil.copyfile(__file__, OUT / 'controller.py')
    shutil.copyfile(args.stage_controller, OUT / 'reviewed-stage-controller.py')
    run = Install(args, helper)
    def interrupted(signum, frame):
        raise InterruptedError('controller interrupted; child untouched')
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, interrupted)
    try:
        run.execute()
    except BaseException as error:
        members = run.artifact_helper.group_members(run.group) if hasattr(run, 'artifact_helper') else []
        uncertain = bool(members) or bool(run.child and run.child.poll() is None)
        run.result.update(passed=False, state='UNKNOWN_DRAIN' if uncertain else 'FAILED',
            error=repr(error), remaining_processes=members, child_may_still_be_running=uncertain,
            partial_new_module_tree_exists=LIVE.exists(), partial_new_boot_files=[name for name in sorted(BOOT_NEW)
                if (Path('/boot') / name).exists()],
            failure_policy='Retain partial new artifacts and processes; no removal, signal, retry, GRUB change or boot.')
    finally:
        run.result['finished'] = time.time()
        run.persist()
    print(json.dumps(run.result, sort_keys=True), flush=True)
    return 0 if run.result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
