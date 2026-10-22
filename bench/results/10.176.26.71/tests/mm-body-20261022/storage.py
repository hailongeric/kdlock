#!/usr/bin/env python3
"""Mount only this candidate's split build directories at their original paths.

No persistent mount, boot policy or recovery path is changed. Run again after a
guest reboot before candidate source verification or external-module builds.
"""
import json
import os
from pathlib import Path
import subprocess

OUT = Path('/root/kdlock-kernel-work/mm-body-20261022/candidate-1')
DATA = Path('/mnt/kdlock-builds/mm-body-20261022/candidate-1')


def main():
    assert os.geteuid() == 0 and os.uname().nodename != '380G10'
    tree = OUT / 'linux'
    assert tree.is_dir() and DATA.is_dir()
    saved = OUT / 'storage-symlinks-attempt-2'
    rows = []
    for name in ('arch', 'drivers', 'fs'):
        source, target = DATA / name, tree / name
        assert source.is_dir() and not source.is_symlink()
        if target.is_symlink():
            assert target.resolve() == source
            saved.mkdir(exist_ok=True)
            assert not (saved / name).exists() and not (saved / name).is_symlink()
            target.rename(saved / name)
            target.mkdir()
        assert target.is_dir() and not target.is_symlink()
        before = target.stat()
        expected = source.stat()
        if (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino):
            assert not any(target.iterdir()), 'nonempty foreign build directory: ' + str(target)
            subprocess.run(['mount', '--bind', str(source), str(target)], check=True, timeout=30)
        after = target.stat()
        assert (after.st_dev, after.st_ino) == (expected.st_dev, expected.st_ino)
        assert target.resolve().is_relative_to(tree.resolve())
        rows.append(dict(source=str(source), target=str(target), device=after.st_dev, inode=after.st_ino))
    print(json.dumps(dict(passed=True, mounts=rows)))


if __name__ == '__main__':
    main()
