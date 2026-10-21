#!/usr/bin/env python3
"""Compile the unchanged default provider profiles in isolated recovery copies."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021')


def main():
    rt.require(os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2','recovery VM required')
    idle=runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle']
    idle(Path('/root'),rt.idle)
    out=BASE/'compatibility-1';out.mkdir()
    manifest=json.loads((BASE/'source-7c517e1.json').read_text())['files']
    result=dict(passed=False,modules_loaded=0,builds=[],driver_sha256=rt.digest(Path(__file__)))
    files={}
    try:
        for profile,run,relative in (('kd','live-1','build/provider/kernel_module/Module.symvers'),
                                     ('tc','live-2','source/tclock_backend/Module.symvers')):
            source=out/profile
            for name,digest in manifest.items():
                if not name.startswith(('include/','tclock_backend/include/','workload_modules/mmap_fault/')):continue
                rt.require(rt.digest(ROOT/name)==digest,'default-profile source changed')
                target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
                files[str(ROOT/name)]=files[str(target)]=digest
            symbols=Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-fault-split-20261021')/run/relative
            target=source/'provider.symvers';shutil.copyfile(symbols,target)
            files[str(symbols)]=files[str(target)]=rt.digest(symbols)
            payload=source/'workload_modules/mmap_fault/kd_mmap_fault.ko'
            rt.command(['make','-C',payload.parent,'KDIR=/root/linux-6.1.159-kdclobber2','W=1',
                'KDLOCK_INCLUDE='+str(source/'include'),'TCLOCK_INCLUDE='+str(source/'tclock_backend/include'),
                'MF_TC_BUILD='+str(int(profile=='tc')),'KBUILD_EXTRA_SYMBOLS='+str(target)],
                out/(profile+'-build.log'),timeout=180)
            provider=rt.command(['modinfo','-F','mmap_provider',payload],out/(profile+'-provider.log')).strip()
            rt.require(provider==('kdlock' if profile=='kd' else 'tclock'),'default profile changed')
            rt.command(['nm','-u',payload],out/(profile+'-imports.txt'))
            result['builds'].append(dict(profile=profile,passed=True,payload_sha256=rt.digest(payload),provider=provider))
            rt.write_json(out/'result.json',result)
        rt.require(all(rt.digest(Path(name))==digest for name,digest in files.items()),'compatibility input changed')
        rt.write_json(out/'source-sha256.json',files)
        idle(Path('/root'),rt.idle);result.update(passed=True,final_idle=True)
    except BaseException as error:result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
