#!/usr/bin/env python3
"""Reconstruct a separate approved guest kernel; never edit the recovery tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt

ARCHIVE_SHA256 = '1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def rename(text):
    # Prefix every KD identifier, including internal tags and guards, so the
    # builtin cannot satisfy or collide with the loadable provider's ABI.
    return text.replace('kd_', 'kd_mmap_').replace('KD_', 'KD_MMAP_')


def replace_once(text, old, new):
    rt.require(text.count(old) == 1, 'source boundary changed: ' + old[:100])
    return text.replace(old, new)


def generated_sources(target):
    inputs, outputs = {}, {}
    private = target / 'kernel/locking/kd_mmap'
    for name in ('include/kd_config.h', 'include/kd_mutex_types.h', 'include/kd_rwsem_types.h',
                 'include/kd_wait_queue.h', 'kernel_module/kd_wait_queue.c',
                 'include/kd_admission.h', 'kernel_module/kd_admission.c',
                 'include/kd_mutex.h', 'include/kd_rwsem.h', 'include/kd_regs.h',
                 'include/kd_lock.h', 'kernel_module/kd_mutex_local.h',
                 'kernel_module/kd_mutex_local.c', 'kernel_module/kd_mutex_osq.c',
                 'kernel_module/kd_rwsem.c'):
        source = ROOT / name
        text = source.read_text()
        inputs[name] = digest(source)
        if name.endswith('kd_mutex_local.c'):
            start = text.index('static int (*kd_io_prepare)(void);')
            end = text.index('\nvoid kd_mutex_local_runtime_exit(void)', start)
            # Builtins call scheduler helpers directly. The module's resolver
            # remains unchanged and is never needed during early mm creation.
            text = text[:start] + ('int kd_mutex_local_runtime_init(void)\n'
                                  '{\n\treturn 0;\n}\n') + text[end:]
            text = replace_once(text, 'int old = kd_io_prepare();', 'int old = io_schedule_prepare();')
            text = replace_once(text, 'kd_io_finish(old);', 'io_schedule_finish(old);')
        if name.endswith('kd_rwsem.c'):
            # The builtin retains the same selected-phase C writer algorithm,
            # with physical local release for both up_write and downgrade.
            # It has no loadable API router or continuation capture entry.
            old = 'kd_mutex_api_unlock(&sem->gate);'
            rt.require(text.count(old) == 2, 'local rwsem release boundaries changed')
            text = text.replace(old, 'kd_mutex_local_unlock(&sem->gate);')
        if name.endswith('kd_admission.c'):
            # C writers share canonical admission/cleanup. Their builtin gate
            # has no scheduling-service ownership or loadable unlock router.
            text = replace_once(text, 'kd_mutex_api_unlock(a->gate);',
                                'kd_mutex_local_unlock(a->gate);')
        if name in ('include/kd_mutex.h', 'include/kd_rwsem.h'):
            text = re.sub(r'#include "(kd_(?:mutex|rwsem)_types.h)"',
                          r'#include <linux/\1>', text)
        text = text.replace('#include "kd_wait_queue.h"', '#include <linux/kd_wait_queue.h>')
        filename = rename(Path(name).name)
        public_header = name.endswith('_types.h') or name in (
            'include/kd_config.h', 'include/kd_wait_queue.h')
        dest = (target / 'include/linux' if public_header else private) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        rt.require(not dest.exists(), 'generated source already exists: ' + str(dest))
        dest.write_text(rename(text))
        outputs[str(dest.relative_to(target))] = digest(dest)
    for source in (HERE / 'overlay').rglob('*'):
        if not source.is_file():
            continue
        dest = target / source.relative_to(HERE / 'overlay')
        dest.parent.mkdir(parents=True, exist_ok=True)
        rt.require(not dest.exists(), 'overlay source already exists: ' + str(dest))
        shutil.copyfile(source, dest)
        inputs[str(source.relative_to(ROOT))] = digest(source)
        outputs[str(dest.relative_to(target))] = digest(dest)
    return inputs, outputs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--recovery', type=Path, default=Path('/root/linux-6.1.159-kdclobber2'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--release', default='-kdmm1')
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release == '6.1.159-kdclobber2', 'existing recovery guest required')
    rt.require(re.fullmatch(r'-kdmm[0-9]+', a.release), 'distinct experimental release required')
    rt.require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'verified recovery snapshot required')
    rt.idle()
    for module in Path('/sys/module').iterdir():
        rt.require(not module.name.startswith(('kd_', 'tclock_', 'tc_', 'jit_')) and
                   module.name != 'rwsem_probe', 'project module remains: ' + module.name)
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(a.recovery.resolve()) and
               not out.is_relative_to(ROOT), 'new independent directory required')
    rt.require(digest(a.archive) == ARCHIVE_SHA256, 'original archive checksum differs')
    config_before = digest(a.recovery / '.config')
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, recovery=str(a.recovery.resolve()),
                  recovery_config_sha256=config_before, archive_sha256=ARCHIVE_SHA256,
                  release='6.1.159' + a.release, installed=False, booted=False,
                  script_sha256=digest(Path(__file__)))
    rt.write_json(out / 'prepare.json', result)
    try:
        tree = out / 'linux'
        tree.mkdir()
        # The archive is authenticated by the preserved version checksum; still
        # reject traversal and extract only into the freshly created directory.
        with tarfile.open(a.archive, 'r:xz') as archive:
            for member in archive:
                path = Path(member.name)
                rt.require(path.parts[0] == 'linux-6.1.159' and not path.is_absolute()
                           and '..' not in path.parts, 'unsafe archive member')
        rt.command(['tar', '-xJf', a.archive, '--strip-components=1', '--no-same-owner',
                    '-C', tree], out / 'extract.log', timeout=300)
        for number, patch in enumerate(('kernel_baseline/linux-6.1.159-guest.patch',
                'kernel_baseline/experiments/spin_static/guest-kernel.patch',
                'kernel_baseline/experiments/spin_clobber/guest-kernel.patch',
                'kernel_baseline/experiments/mutex_clobber/guest-kernel.patch')):
            rt.command(['patch', '--batch', '--fuzz=0', '-p1', '-i', ROOT / patch],
                       out / f'ancestor-{number}.log', timeout=60, cwd=tree)
        expected = json.loads((HERE / 'base-sha256.json').read_text())
        for name, h in expected.items():
            rt.require(digest(tree / name) == digest(a.recovery / name) == h,
                       'captured kernel input differs: ' + name)
        shutil.copyfile(a.recovery / '.config', tree / '.config')
        rt.command(['patch', '--batch', '--fuzz=0', '-p1', '-i', HERE / 'guest-kernel.patch'],
                   out / 'integration-patch.log', timeout=60, cwd=tree)
        inputs, outputs = generated_sources(tree)
        for name in expected:
            outputs[name] = digest(tree / name)
        result.update(inputs=inputs, outputs=outputs,
                      patch_sha256=digest(HERE / 'guest-kernel.patch'),
                      base_manifest_sha256=digest(HERE / 'base-sha256.json'))
        rt.command([tree / 'scripts/config', '--file', tree / '.config', '--set-str',
                    'LOCALVERSION', a.release, '--enable', 'KD_MMAP_LOCK'],
                   out / 'config-selection.log', timeout=30, cwd=tree)
        rt.command(['make', 'olddefconfig'], out / 'olddefconfig.log', timeout=120, cwd=tree)
        before = set((a.recovery / '.config').read_text().splitlines())
        after = set((tree / '.config').read_text().splitlines())
        removed, added = sorted(before - after), sorted(after - before)
        rt.require(removed == ['CONFIG_LOCALVERSION="-kdclobber2"'] and
                   set(added) == {'CONFIG_LOCALVERSION="' + a.release + '"', 'CONFIG_KD_MMAP_LOCK=y'},
                   'unapproved configuration difference: ' + repr((removed, added)))
        rt.require(digest(a.recovery / '.config') == config_before, 'recovery config changed')
        result.update(state='COMPLETE', passed=True, config_removed=removed, config_added=added,
                      config_sha256=digest(tree / '.config'), source_tree=str(tree))
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        rt.write_json(out / 'prepare.json', result)
    print(json.dumps({k: result[k] for k in ('state', 'passed', 'release', 'source_tree')}))


if __name__ == '__main__':
    main()
