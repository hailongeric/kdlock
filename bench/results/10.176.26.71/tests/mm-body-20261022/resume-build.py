#!/usr/bin/env python3
"""Resume only the exited, uninstalled candidate; preserve failed build inputs."""
import datetime
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('build-control-1')
B = runpy.run_path(str(OLD / 'build.py'))
ROOT, OUT, DATA, BASELINE = (B[n] for n in ('ROOT', 'OUT', 'DATA', 'BASELINE'))
sha, save, command, rt = (B[n] for n in ('sha', 'save', 'command', 'rt'))


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '97c45a77-3ce3-4d3f-87b4-4ef3e880af64'
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    assert os.environ['KDLOCK_SNAPSHOT_TAG'] == 'before-mutex-kdonly-20261017T140354Z'
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    previous = json.loads((OLD / 'build-result.json').read_text())
    assert previous['state'] == 'FAILED' and not previous['installed'] and not previous['booted']
    receipt = json.loads((OUT / 'build-1.log.command.json').read_text())
    assert receipt['state'] == 'EXITED' and receipt['returncode'] == 2
    assert not Path('/proc', str(receipt['pid'])).exists()
    assert not BASELINE.exists() and not Path('/lib/modules/6.1.159-kdmm2').exists()
    original = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json')
    assert sha(original) == '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    host = runpy.run_path(str(ROOT / 'bench/basic/run.py'))['functional_host'](
        json.loads(original.read_text()), json.loads((HERE / 'host.json').read_text()),
        datetime.datetime.now(datetime.timezone.utc))
    save(HERE / 'host-functional-check.json', host)
    inputs = json.loads((HERE / 'source-inputs.json').read_text())
    targets = json.loads((OLD / 'module-targets.json').read_text())
    assert len(targets) == 73

    def verify():
        for name, digest in inputs['files'].items():
            assert sha(ROOT / name) == digest, name

    verify()
    state = dict(passed=False, installed=False, booted=False, state='PREPARATION',
                 source_commit=inputs['commit'], source_inputs_sha256=sha(HERE / 'source-inputs.json'),
                 script_sha256=sha(Path(__file__)), previous_result_sha256=sha(OLD / 'build-result.json'),
                 stages=[])
    save(HERE / 'build-result.json', state)
    try:
        tree = OUT / 'linux'
        prepared = json.loads((OUT / 'prepare.json').read_text())
        failed = OUT / 'failed-attempt-1'
        failed.mkdir()
        shutil.copyfile(OUT / 'prepare.json', failed / 'prepare.json')
        for name, digest in prepared['outputs'].items():
            assert sha(tree / name) == digest, name
            target = failed / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / name, target)
            assert sha(target) == digest
        assert sha(tree / '.config') == prepared['config_sha256']
        shutil.copyfile(tree / '.config', failed / 'guest.config')
        # Only these reviewed overlay edits differ from the failed kernel.
        changed = []
        for name in ('adapter.c', 'body_internal.h', 'pool.c'):
            relative = 'kernel/locking/kd_mmap/' + name
            source = ROOT / 'kernel_integration/mmap_lock/overlay' / relative
            before = sha(tree / relative)
            shutil.copyfile(source, tree / relative)
            digest = sha(source)
            prepared['outputs'][relative] = digest
            prepared['inputs'][str(source.relative_to(ROOT))] = digest
            changed.append(dict(path=relative, before=before, after=digest))
        # Mirror the candidate's root view. Relative includes which traverse a
        # moved directory now find the same sibling bytes on either filesystem.
        view = {}
        for child in tree.iterdir():
            if child.name in ('arch', 'drivers', 'fs'):
                assert child.resolve() == DATA / child.name
                continue
            alias = DATA / child.name
            assert not alias.exists() and not alias.is_symlink()
            alias.symlink_to(child, target_is_directory=child.is_dir())
            view[child.name] = str(child)
        save(OUT / 'storage-view-2.json', view)
        prepared['revision'] = dict(attempt=2, previous_prepare_sha256=sha(failed / 'prepare.json'),
                                    source_commit=inputs['commit'], changed=changed)
        save(OUT / 'prepare.json', prepared)
        command([sys.executable, '-m', 'pip', 'check'], HERE / 'dependencies.log', 60)
        command(['make', '-C', ROOT / 'tests/unit', 'run', 'PYTHON=' + sys.executable, 'PY_TESTS='],
                HERE / 'basic.log', 180)
        command([sys.executable, ROOT / 'tests/kernel/mmap_lock/body/test_receipts.py'], HERE / 'receipts.log', 60)
        state['stages'].append('basic-2-and-body-receipts-4')
        state['state'] = 'IMAGE_BUILD'; save(HERE / 'build-result.json', state)
        command(['make', '-j16', 'bzImage'], OUT / 'build-2.log', cwd=tree)
        for name, digest in prepared['outputs'].items():
            assert sha(tree / name) == digest
        assert sha(tree / '.config') == prepared['config_sha256']
        save(OUT / 'build-2.json', dict(passed=True, release='6.1.159-kdmm2',
             prepare_sha256=sha(OUT / 'prepare.json'), image_sha256=sha(tree / 'arch/x86/boot/bzImage'),
             installed=False, booted=False))
        state['stages'].append('image'); state['state'] = 'MODULE_BUILD'; save(HERE / 'build-result.json', state)
        serio = 'drivers/input/serio/serio_raw.ko'
        command(['make', '-j16', *[n for n in targets if n != serio]], OUT / 'modules-runtime.log', cwd=tree)
        shutil.copyfile(tree / 'Module.symvers', OUT / 'runtime-Module.symvers')
        command(['make', '-j16', serio], OUT / 'modules-serio.log', cwd=tree)
        shutil.copyfile(tree / 'Module.symvers', OUT / 'serio-Module.symvers')
        symbols = {}
        for path in (tree / 'vmlinux.symvers', OUT / 'runtime-Module.symvers', OUT / 'serio-Module.symvers'):
            for line in path.read_text().splitlines():
                fields = line.split()
                if not fields:
                    continue
                name = fields[1]
                assert name not in symbols or symbols[name] == line, 'different symbol records: ' + name
                symbols[name] = line
        (tree / 'Module.symvers').write_text('\n'.join(symbols[n] for n in sorted(symbols)) + '\n')
        save(OUT / 'modules-build-2.json', dict(passed=True, count=len(targets),
             modules={name: sha(tree / name) for name in targets},
             merged_symvers_sha256=sha(tree / 'Module.symvers'),
             scope='same 73 recovery-loaded modules and dependency closure; all-configured modules unvalidated'))
        state['stages'].append('runtime-modules-73'); state['state'] = 'CAPTURE'; save(HERE / 'build-result.json', state)
        command([sys.executable, ROOT / 'kernel_integration/mmap_lock/capture.py', '--prepared', OUT,
                 '--output', BASELINE], OUT / 'capture.log', 300)
        verify()
        for receipt in ('boot-sha256.json', 'modules-sha256.json'):
            for name, digest in json.loads((OLD / 'recovery' / receipt).read_text()).items():
                assert sha(Path(name)) == digest, 'recovery changed: ' + name
        state.update(state='COMPLETE', passed=True, baseline=str(BASELINE),
                     baseline_manifest_sha256=sha(BASELINE / 'manifest.json'))
    except BaseException as error:
        state.update(state='FAILED', error=repr(error))
        raise
    finally:
        save(HERE / 'build-result.json', state)
    print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
