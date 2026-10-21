#!/usr/bin/env python3
"""Serial VM-only basic and directly affected diagnostic checks."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-receipt-io-20261021')


def main():
    sys.dont_write_bytecode = True
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    idle = runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle']
    idle(BASE, rt.idle)
    manifest = json.loads(Path(sys.argv[1]).read_text())
    out = BASE/'checks-1'
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), out/'run-checks.py')
    (out/'committed-source.json').write_text(json.dumps(manifest, indent=2)+'\n')
    hashes = manifest['files']
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    for relative, digest in hashes.items():
        assert sha(ROOT/relative) == digest, relative
        target = out/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
        assert sha(target) == digest
    (out/'sources.json').write_text(json.dumps(hashes, indent=2)+'\n')
    commands = [('basic', ['make', '-B', '-C', str(out/'source/tests/unit'), 'run'])]
    commands += [(name, [sys.executable, str(out/'source/bench/mutex_api_compare'/file), '-v'])
        for name, file in [('receipt-trace', 'test_receipt_trace.py'),
                           ('phase-accounting', 'test_phase_accounting.py'),
                           ('boundary-trigger', 'test_boundary_trigger.py'),
                           ('boundary-protocol', 'test_boundary_protocol.py'),
                           ('prewarmup-control', 'test_prewarmup_control.py'),
                           ('recovery-gate', 'test_recovery_replay.py')]]
    result = dict(passed=False, commands=[], started_ns=time.time_ns(), source_revision=manifest['commit'],
                  final_idle=False, source_unchanged=False)
    def save():
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    save()
    try:
        for name, argv in commands:
            idle(BASE, rt.idle)
            row = dict(name=name, argv=argv, started_ns=time.time_ns())
            result['commands'].append(row)
            with (out/(name+'.log')).open('x') as log:
                process = subprocess.Popen(argv, cwd=out/'source', stdout=log, stderr=subprocess.STDOUT)
                row['pid'] = process.pid
                save()
                # A timeout leaves the process alone and records uncertainty.
                row['exit_code'] = process.wait(timeout=180)
            row['finished_ns'] = time.time_ns()
            save()
            print(name, row['exit_code'], flush=True)
            assert row['exit_code'] == 0, name
        for relative, digest in hashes.items():
            assert sha(ROOT/relative) == sha(out/'source'/relative) == digest, relative
        idle(BASE, rt.idle)
        result.update(passed=True, final_idle=True, source_unchanged=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        result['finished_ns'] = time.time_ns()
        save()
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
