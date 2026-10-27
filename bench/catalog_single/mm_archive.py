"""Read-only complete evidence inventory, including empty attempt directories."""
import hashlib
import os
from pathlib import Path
import stat


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def inventory(base):
    rows = {}
    for path in sorted(Path(base).rglob('*')):
        info = path.lstat()
        name = str(path.relative_to(base))
        if stat.S_ISREG(info.st_mode):
            rows[name] = dict(kind='file', sha256=digest(path), bytes=info.st_size,
                              mode=info.st_mode, mtime_ns=info.st_mtime_ns)
        elif stat.S_ISLNK(info.st_mode):
            rows[name] = dict(kind='link', target=os.readlink(path), mode=info.st_mode)
        elif stat.S_ISDIR(info.st_mode):
            rows[name] = dict(kind='directory', mode=info.st_mode)
        else:
            raise ValueError('special evidence member: ' + name)
    if not rows:
        raise ValueError('empty evidence tree')
    return rows
