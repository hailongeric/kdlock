#!/usr/bin/env python3
"""Serial guest build of the separate anonymous write-fault installation experiment; never boot."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import runpy
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
OUT = Path('/root/kdlock-kernel-work/mm-fault-body-20261022/candidate-1')
HERE = Path(__file__).resolve().parent
BASELINE = Path('/root/kdlock-kernel-baselines/mmap-kdmm3-20261022')
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def command(args, log, timeout=5400, cwd=None):
    record = dict(argv=list(map(str, args)), cwd=str(cwd) if cwd else None,
                  state='STARTING', started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    receipt = log.with_suffix(log.suffix + '.command.json')
    save(receipt, record)
    with log.open('w') as output:
        child = subprocess.Popen(record['argv'], cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        record.update(state='RUNNING', pid=child.pid); save(receipt, record)
        try:
            code = child.wait(timeout)
        except subprocess.TimeoutExpired:
            record.update(state='UNKNOWN_DRAIN'); save(receipt, record)
            raise RuntimeError('deadline without termination: ' + str(log))
    record.update(state='EXITED', returncode=code,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(receipt, record)
    if code:
        raise RuntimeError(f'exit {code}: {log}')


def main():
    assert os.geteuid() == 0 and os.uname().nodename != '380G10'
    assert os.uname().release == '6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == 'd4980f92-14c5-4bed-9749-beac916e76d3'
    assert os.environ['KDLOCK_SNAPSHOT_TAG'] == 'before-mutex-kdonly-20261017T140354Z'
    assert os.environ['KDLOCK_RECOVERY_CONFIRMED'] == '1'
    rt.idle()
    for module in Path('/sys/module').iterdir():
        assert not module.name.startswith(('kd_', 'tclock_', 'tc_', 'jit_'))
    inputs = json.loads((HERE / 'source-inputs.json').read_text())
    targets = json.loads((HERE / 'module-targets.json').read_text())
    assert len(targets) == 73 and 'drivers/input/serio/serio_raw.ko' in targets

    def verify():
        for name, digest in inputs['files'].items():
            assert sha(ROOT / name) == digest, name

    verify()
    assert not OUT.exists() and not BASELINE.exists()
    original = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json')
    assert sha(original) == '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a'
    host_check = runpy.run_path(str(ROOT / 'bench/basic/run.py'))['functional_host'](
        json.loads(original.read_text()), json.loads((HERE / 'host.json').read_text()),
        datetime.datetime.now(datetime.timezone.utc))
    save(HERE / 'host-functional-check.json', host_check)
    state = dict(passed=False, state='PREPARATION', installed=False, booted=False,
                 source_commit=inputs['commit'], script_sha256=sha(Path(__file__)),
                 source_inputs_sha256=sha(HERE / 'source-inputs.json'), stages=[])
    save(HERE / 'build-result.json', state)
    try:
        recovery = HERE / 'recovery'
        recovery.mkdir()
        boot_paths = [Path('/boot') / (kind + '-6.1.159-kdclobber2')
                      for kind in ('vmlinuz', 'initrd.img', 'config', 'System.map')]
        boot_paths += [Path('/boot') / (kind + '-' + release)
                      for release in ('6.1.159-kdmm1', '6.1.159-kdmm2')
                      for kind in ('vmlinuz', 'initrd.img', 'config', 'System.map')]
        boot_paths += [Path('/boot/grub/grub.cfg'), Path('/etc/default/grub')]
        boot_paths += [p for folder in ('/etc/default/grub.d', '/etc/grub.d')
                       for p in Path(folder).glob('*') if p.is_file()]
        for path in boot_paths:
            target = recovery / 'files' / path.relative_to('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            assert sha(target) == sha(path)
        save(recovery / 'boot-sha256.json', {str(p): sha(p) for p in boot_paths})
        save(recovery / 'modules-sha256.json', {str(p): sha(p)
             for p in Path('/lib/modules/6.1.159-kdclobber2').rglob('*')
             if p.is_file() and not p.is_symlink()})
        command([sys.executable, '-m', 'pip', 'check'], HERE / 'dependencies.log', 60)
        command(['make', '-C', ROOT / 'tests/unit', 'run', 'PYTHON=' + sys.executable, 'PY_TESTS='],
                HERE / 'basic.log', 180)
        command([sys.executable, ROOT / 'tests/kernel/mmap_lock/body/test_receipts.py'],
                HERE / 'receipts.log', 60)
        state['stages'].append('basic-2-and-body-receipts-4'); save(HERE / 'build-result.json', state)
        command([sys.executable, ROOT / 'kernel_integration/mmap_lock/prepare.py',
                 '--archive', '/root/kdlock-kernel-work/mmap-20261021/linux-6.1.159.tar.xz',
                 '--output', OUT, '--release=-kdmm3'], HERE / 'prepare.log', 600)
        tree = OUT / 'linux'
        prepared = json.loads((OUT / 'prepare.json').read_text())
        assert prepared['passed']
        # This new tree stays entirely on root ext4. The prior advice tree
        # and its bind mounts remain unchanged; no shared build outputs exist.
        for name, digest in prepared['outputs'].items():
            assert sha(tree / name) == digest
        verify()
        state.update(state='IMAGE_BUILD', prepared=str(OUT), storage_layout='root-ext4')
        save(HERE / 'build-result.json', state)
        command(['make', '-j16', 'bzImage'], OUT / 'build-1.log', cwd=tree)
        for name, digest in prepared['outputs'].items():
            assert sha(tree / name) == digest
        assert sha(tree / '.config') == prepared['config_sha256']
        save(OUT / 'build-1.json', dict(state='COMPLETE', passed=True, jobs=16, target='bzImage',
             release='6.1.159-kdmm3', prepare_sha256=sha(OUT / 'prepare.json'),
             image_sha256=sha(tree / 'arch/x86/boot/bzImage'), installed=False, booted=False))
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
            for name, digest in json.loads((recovery / receipt).read_text()).items():
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
