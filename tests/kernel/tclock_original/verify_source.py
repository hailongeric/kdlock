#!/usr/bin/env python3
"""Check pinned provenance and the upstream decisions restored by this port."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tclock_backend'))
from update_patches import expanded


def compact(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


def main():
    base = ROOT / 'tclock_backend'
    manifest = json.loads((base / 'UPSTREAM.json').read_text())
    for path, digest in manifest['sha256'].items():
        assert hashlib.sha256((base / 'upstream' / path).read_bytes()).hexdigest() == digest, path
    original = (base / 'upstream/locks/komb.c').read_text()
    current = expanded(base / 'komb.c')
    for source in (original, current):
        assert '#ifdef KERNEL_SYNCSTRESS' in source
    def batch(source):
        return compact(source.split('uint64_t counter = ptr->counter_val;')[1]
                       .split('incoming_rsp_ptr')[0])
    assert batch(original) == batch(current)
    def wait(source):
        return source.split('#ifdef KERNEL_SYNCSTRESS\n#define smp_cond_load_relaxed_sched')[1].split('#else')[0]
    assert compact(wait(original)) == compact(wait(current))
    original = (base / 'upstream/locks/komb_rwlock.c').read_text()
    current = (base / 'komb_rwlock.c').read_text()
    pattern = r'local_irq_(?:disable|enable)\(\)|retq'
    assert re.findall(pattern, original) == re.findall(pattern, current)
    assert (base / 'include/spinlock/aqs.h').read_bytes() == (base / 'upstream/include/spinlock/aqs.h').read_bytes()
    def aqs(source):
        return source[source.index('#define ENABLE_SHUFFLERS'):]
    assert aqs((base / 'aqs.c').read_text()) == aqs((base / 'upstream/locks/aqs.c').read_text())
    print(json.dumps(dict(upstream_files=len(manifest['sha256']), original_spin_batch=True,
                         original_spin_wait=True, original_rwlock_irq_return_sequence=True,
                         original_aqs_body_and_header=True)))


if __name__ == '__main__':
    main()
