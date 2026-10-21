#!/usr/bin/env python3
"""Capture inert C/assembly/header inputs; perform source analysis on 380G10."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path('/root/linux-6.1.159-kdclobber2').resolve()
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='b65f0205-c8f9-4385-8b13-039cbce243a6'
    assert not a.output.exists();a.output.mkdir(parents=True)
    manifest={};total=0
    with tarfile.open(a.output/'kernel-inputs.tar.gz','w:gz',compresslevel=1) as out:
        for directory,dirs,files in os.walk(root):
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not Path(directory,d).is_symlink())
            for name in sorted(files):
                source=Path(directory,name)
                if source.is_symlink() or not source.is_file():continue
                if not (source.suffix in ('.c','.h','.S') or name in ('.config','Makefile','Kbuild') or name.startswith('Kconfig')):continue
                if name.endswith('.mod.c'):continue
                before=source.stat();content=source.read_bytes();after=source.stat()
                assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
                relative=str(source.relative_to(root));manifest[relative]=hashlib.sha256(content).hexdigest();total+=len(content)
                out.add(source,arcname='kernel/'+relative,recursive=False)
                assert source.stat().st_mtime_ns==after.st_mtime_ns
    (a.output/'source-sha256.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    result=dict(captured=True,source_root=str(root),files=len(manifest),bytes=total,finished_ns=time.time_ns(),
        kernel_release=os.uname().release,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        archive_sha256=hashlib.sha256((a.output/'kernel-inputs.tar.gz').read_bytes()).hexdigest(),
        manifest_sha256=hashlib.sha256((a.output/'source-sha256.json').read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='C, headers, assembly, Kbuild/Makefile/Kconfig and .config; source analysis is not performed by this capture')
    (a.output/'capture.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
