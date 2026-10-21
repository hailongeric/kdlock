#!/usr/bin/env python3
"""Validate shared physical types on the unchanged recovery kernel, serially."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    kernel_identity.arguments(p)
    a = p.parse_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               os.uname().release == '6.1.159-kdclobber2', 'existing recovery VM required')
    rt.idle()
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new evidence directory required')
    out.mkdir(parents=True)
    result = dict(state='PREPARATION', passed=False, drained=False, kernel_modified=False,
                  full_suite=False, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    rt.write_json(out / 'result.json', result)
    try:
        result['kernel_identity'] = kernel_identity.capture(a, out, rt.command)
        source = out / 'source'
        hashes = {}
        for directory in ('include', 'kernel_module', 'daemon', 'tests/unit'):
            for path in (ROOT / directory).rglob('*'):
                rel = path.relative_to(ROOT)
                if (not path.is_file() or any(s.startswith('.') or s == '__pycache__' for s in rel.parts)
                        or path.name.endswith('.mod.c') or
                        (path.suffix not in ('.c', '.h', '.inc', '.S', '.py', '.def') and
                         path.name != 'Makefile')):
                    continue
                hashes[str(rel)] = rt.digest(path)
                target = source / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        rt.write_json(out / 'source-sha256.json', hashes)
        shutil.copyfile(__file__, out / 'runner.py')
        result.update(state='RUNNING', source_files=len(hashes))
        rt.write_json(out / 'result.json', result)
        rt.command([sys.executable, '-m', 'pip', 'check'], out / 'dependencies.log', timeout=60)
        rt.command(['make', '-C', source / 'kernel_module', 'KDIR=' + str(a.kernel_source),
                    'W=1', 'UBSAN_SANITIZE=n'], out / 'provider-build.log', timeout=240)
        rt.command(['make', '-C', source / 'daemon', 'CFLAGS=-O2 -Wall -Wextra -Werror'],
                   out / 'daemon-build.log', timeout=120)
        drivers = ('count', 'state', 'resources', 'osq', 'wait_clobber', 'outer_progress')
        selected = ' '.join('mutex/test_mutex_' + name + '.py' for name in drivers)
        rt.command(['make', '-C', source / 'tests/unit', 'run', 'PYTHON=' + sys.executable,
                    'PY_TESTS=' + selected], out / 'basic-affected.log', timeout=600)
        for name, digest in hashes.items():
            rt.require(rt.digest(ROOT / name) == rt.digest(source / name) == digest,
                       'frozen input changed: ' + name)
        rt.idle()
        result.update(state='COMPLETE', passed=True, drained=True, basic_programs=2,
                      affected_drivers=list(drivers), source_unchanged=True)
    except BaseException as error:
        result.update(state='FAILED', error=repr(error))
        raise
    finally:
        rt.write_json(out / 'result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
