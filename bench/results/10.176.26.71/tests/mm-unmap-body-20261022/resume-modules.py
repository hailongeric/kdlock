#!/usr/bin/env python3
"""Complete only the failed module stage; preserve the frozen image and failure."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-unmap-body-20261022')
OUT=Path('/root/kdlock-kernel-work/mm-unmap-body-20261022/candidate-1')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm4-20261022')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='11968a2a-23e4-4474-95b8-a636a9858fbd'
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
    prior=BASE/'build-control-1';here=Path(__file__).parent;tree=OUT/'linux'
    load=lambda path:json.loads(path.read_text())
    inputs=load(prior/'source-inputs.json');prepared=load(OUT/'prepare.json')
    first=load(prior/'build-result.json');image=load(OUT/'build-1.json')
    assert first['state']=='FAILED' and first['stages'][-1]=='image' and image['passed']
    assert load(OUT/'modules-serio.log.command.json')['state']=='EXITED'
    assert load(OUT/'modules-serio.log.command.json')['returncode']==2
    command=runpy.run_path(str(prior/'build.py'))['command']
    def verify():
        for name,digest in inputs['files'].items():assert rt.digest(ROOT/name)==digest,name
        for name,digest in prepared['outputs'].items():assert rt.digest(tree/name)==digest,name
        assert rt.digest(tree/'.config')==prepared['config_sha256']
        assert rt.digest(tree/'arch/x86/boot/bzImage')==image['image_sha256']
    verify()
    old=OUT/'failed-module-1';old.mkdir()
    hashes={}
    for path in (tree/'drivers/input/serio').iterdir():
        if path.is_file() and ('serio_raw' in path.name or path.name=='Module.symvers'):
            if path.suffix not in ('.c','.h') or path.name.endswith('.mod.c'):
                shutil.copyfile(path,old/path.name)
                hashes[path.name]=rt.digest(path)
                assert rt.digest(old/path.name)==hashes[path.name]
    rt.write_json(old/'sha256.json',hashes)
    state=dict(passed=False,state='MODULE_RETRY',installed=False,booted=False,
               source_commit=inputs['commit'],source_inputs_sha256=rt.digest(prior/'source-inputs.json'),
               preserved_image_sha256=image['image_sha256'],script_sha256=rt.digest(Path(__file__)))
    rt.write_json(here/'build-result.json',state)
    try:
        command(['make','-j1','M=drivers/input/serio','modules'],OUT/'modules-serio-directory-2.log',300,cwd=tree)
        shutil.copyfile(tree/'drivers/input/serio/Module.symvers',OUT/'serio-Module.symvers')
        symbols={}
        for path in (tree/'vmlinux.symvers',OUT/'runtime-Module.symvers',OUT/'serio-Module.symvers'):
            for line in path.read_text().splitlines():
                fields=line.split()
                if not fields:continue
                assert fields[1] not in symbols or symbols[fields[1]]==line
                symbols[fields[1]]=line
        (tree/'Module.symvers').write_text('\n'.join(symbols[n] for n in sorted(symbols))+'\n')
        targets=load(prior/'module-targets.json')
        assert len(targets)==73
        rt.write_json(OUT/'modules-build-2.json',dict(passed=True,count=73,
            modules={name:rt.digest(tree/name) for name in targets},
            merged_symvers_sha256=rt.digest(tree/'Module.symvers'),
            scope='same 73 runtime modules; isolated serio directory retry, image unchanged'))
        verify()
        command([sys.executable,ROOT/'kernel_integration/mmap_lock/capture.py','--prepared',OUT,
                 '--output',BUNDLE],OUT/'capture-2.log',300)
        verify()
        for receipt in ('boot-sha256.json','modules-sha256.json'):
            for name,digest in load(prior/'recovery'/receipt).items():assert rt.digest(Path(name))==digest,name
        state.update(passed=True,state='COMPLETE',baseline=str(BUNDLE),
                     baseline_manifest_sha256=rt.digest(BUNDLE/'manifest.json'),recovery_unchanged=True,
                     stages=['basic-2-advice-receipts-5-fault-receipts-5','image','runtime-modules-73'])
    except BaseException as error:
        state.update(state='FAILED',error=repr(error));raise
    finally:rt.write_json(here/'build-result.json',state)
    print(json.dumps(state))


if __name__=='__main__':main()
