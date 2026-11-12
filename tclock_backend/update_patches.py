#!/usr/bin/env python3
"""Regenerate review diffs against immutable pinned source; run on source host."""
from pathlib import Path
import difflib
import re

BASE = Path(__file__).resolve().parent


def expanded(path):
    text = path.read_text()
    return re.sub(r'^#include "([^"\n]+\.inc)"\n',
                  lambda m: expanded(path.parent / m[1]), text, flags=re.M)


def render(pairs):
    return ''.join(''.join(difflib.unified_diff(
        (BASE / 'upstream' / original).read_text().splitlines(True),
        expanded(BASE / port).splitlines(True),
        fromfile='upstream/' + original, tofile=port))
        for original, port in pairs)


if __name__ == '__main__':
    common = [('locks/komb.c', 'komb.c'), ('lib/combiner.c', 'combiner.c'),
              ('include/lib/combiner.h', 'include/lib/combiner.h'),
              ('include/spinlock/komb.h', 'include/spinlock/komb.h'),
              ('locks/komb_mutex.c', 'komb_mutex.c'),
              ('include/mutex/komb_mutex.h', 'include/mutex/komb_mutex.h')]
    rwlock = [('locks/komb_rwlock.c', 'komb_rwlock.c'),
              ('include/rwlock/komb_rwlock.h', 'include/rwlock/komb_rwlock.h')]
    rwsem = [('locks/komb_rwsem.c', 'komb_rwsem.c'),
             ('include/rwsem/komb_rwsem.h', 'include/rwsem/komb_rwsem.h'),
             ('locks/aqs.c', 'aqs.c'), ('include/spinlock/aqs.h', 'include/spinlock/aqs.h')]
    for name, pairs in [('port.patch', common), ('rwlock-port.patch', rwlock),
                        ('rwsem-port.patch', rwsem)]:
        (BASE / name).write_text(render(pairs))
