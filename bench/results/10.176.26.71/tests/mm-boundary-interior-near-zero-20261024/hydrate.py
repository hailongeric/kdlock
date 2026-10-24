#!/usr/bin/env python3
"""Expand only the new compressed ELF into RAM for unchanged identity checks."""
import lzma
import hashlib
import json
from pathlib import Path
import shutil

OUT=Path('/root/kdlock-kernel-work/mm-boundary-interior-near-zero-20261024')
TREE=Path('/dev/shm/kdmm26-identity')

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def hydrate():
    receipt=json.loads((OUT/'identity-store.json').read_text())
    if TREE.exists():
        assert (TREE/'vmlinux').is_file() and not (TREE/'vmlinux').is_symlink()
        assert digest(TREE/'vmlinux')==receipt['vmlinux_sha256']
        return
    source=OUT/'identity'
    compressed=Path(receipt['compressed_path'])
    assert compressed.stat().st_size==receipt['compressed_bytes'] and digest(compressed)==receipt['compressed_sha256']
    TREE.mkdir()
    for p in source.rglob('*'):
        if p.is_file():
            dst=TREE/p.relative_to(source);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
    with lzma.open(compressed,'rb') as inp,(TREE/'vmlinux').open('wb') as out:shutil.copyfileobj(inp,out,1<<20)
    assert digest(TREE/'vmlinux')==receipt['vmlinux_sha256']

if __name__=='__main__':hydrate()
