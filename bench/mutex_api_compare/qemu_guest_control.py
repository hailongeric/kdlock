#!/usr/bin/env python3
"""Small serial I/O controls in the existing VM; stdout is the evidence stream.

No modules, cache dropping, tuning or benchmark acceptance. Only uniquely named
files created by this process may be removed. Commands arrive one at a time.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def emit(event, **values):
    print(json.dumps(dict(event=event, real_ns=time.time_ns(),
                         mono_ns=time.monotonic_ns(), **values)), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    a = p.parse_args()
    assert a.run.isascii() and a.run.replace('-', '').isalnum()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '88449cfc-cea9-4647-a294-bc601e372146'
    transition = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-recovery-followup-20261021/transition-1/result.json')
    assert hashlib.sha256(transition.read_bytes()).hexdigest() == '81280a1655854fead9e64c4ee752275a32eef3c3f30ce09d27b71a89621a1ca1'
    modules = sorted(row.split()[0] for row in Path('/proc/modules').read_text().splitlines())
    assert modules == json.loads(transition.read_text())['modules'] and len(modules) == 73
    paths = {
        'tmpfs': Path('/dev/shm')/('kdlock-qemu-workers-'+a.run),
        'disk': Path('/root/kdlock-evidence')/('qemu-workers-'+a.run+'.data'),
    }
    assert all(not path.exists() for path in paths.values())
    block = b'K'*(1024*1024)
    digest = hashlib.sha256(block*4).hexdigest()
    created = set()
    emit('ready', pid=os.getpid(), modules=modules, paths={k: str(v) for k, v in paths.items()},
         bytes_per_file=len(block)*4, expected_sha256=digest)
    for line in sys.stdin:
        message = json.loads(line)
        assert set(message) == {'action'}
        action = message['action']
        emit('begin', action=action)
        result = {}
        if action in ('clock', 'noop'):
            pass
        elif action.endswith('-write'):
            kind = action.removesuffix('-write')
            path = paths[kind]
            assert kind not in created
            with path.open('xb', buffering=0) as stream:
                created.add(kind)
                for _ in range(4):
                    assert stream.write(block) == len(block)
                os.fsync(stream.fileno())
            result = dict(path=str(path), bytes=path.stat().st_size, fsync=True)
            assert result['bytes'] == 4*len(block)
        elif action.endswith('-read'):
            kind = action.removesuffix('-read')
            assert kind in created
            result = dict(sha256=hashlib.sha256(paths[kind].read_bytes()).hexdigest())
            assert result['sha256'] == digest
        elif action == 'cleanup':
            for kind in sorted(created):
                assert paths[kind].stat().st_size == 4*len(block)
                paths[kind].unlink()
            created.clear()
        elif action == 'stop':
            assert not created
            emit('end', action=action, result=result)
            break
        else:
            raise ValueError(action)
        emit('end', action=action, result=result)
    assert not created, 'own control files remain; retain and report failure'
    emit('complete', removed_own_files=True)


if __name__ == '__main__':
    main()
