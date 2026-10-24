#!/usr/bin/env python3
"""Guest-only lock adapter source/compile checks; never build or boot a kernel."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

WRAPPERS={'include/linux/mm_types.h','include/linux/mmap_lock.h','include/linux/sched/mm.h',
    'kernel/bpf/mmap_unlock_work.h','kernel/bpf/task_iter.c','kernel/fork.c',
    'kernel/locking/Makefile','mm/Kconfig','mm/mmap_lock.c'}
NATIVE_BODIES=('mm/mmap.c','mm/memory.c','mm/madvise.c','mm/rmap.c','lib/maple_tree.c')
OBJECTS=('adapter.o','pool.o','kd_mmap_mutex_local.o','kd_mmap_mutex_osq.o','kd_mmap_rwsem.o')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    kernel_identity.arguments(p);a=p.parse_args()
    assert os.geteuid()==0 and str(ROOT).startswith('/root/') and os.uname().release=='6.1.159-kdclobber2'
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
    assert not a.output.exists() and not a.output.resolve().is_relative_to(ROOT)
    a.output.mkdir(parents=True)
    out=a.output;integration=ROOT/'kernel_integration/mmap_lock';result=dict(passed=False,booted=False,installed=False,live_mm_tests=0)
    try:
        result['kernel_identity']=kernel_identity.capture(a,out,rt.command)
        body_hashes={n:rt.digest(a.kernel_source/n) for n in NATIVE_BODIES}
        expected=json.loads((integration/'base-sha256.json').read_text())
        patch=(integration/'guest-kernel.patch').read_text()
        paths=re.findall(r'^\+\+\+ b/(.+)$',patch,re.M)
        assert set(paths)==WRAPPERS==set(expected) and len(paths)==len(WRAPPERS)
        assert not any(n in patch for n in ('split_vma_prepared','do_mas_align_munmap_prepared','kd_mmap_mas_preallocate','kd_anon_vma_clone_prepared','kd_mmap_madvise','kd_mmap_fault_submit','kd_mmap_munmap'))
        adapter=(integration/'overlay/kernel/locking/kd_mmap/adapter.c').read_text()
        for name in ('kd_mmap_read_lock','kd_mmap_read_lock_killable','kd_mmap_read_trylock','kd_mmap_read_unlock','kd_mmap_read_unlock_non_owner',
                     'kd_mmap_write_lock','kd_mmap_write_lock_nested','kd_mmap_write_lock_killable','kd_mmap_write_trylock','kd_mmap_write_unlock','kd_mmap_write_downgrade'):
            assert 'EXPORT_SYMBOL_GPL('+name+');' in adapter and name in patch,name
        assert 'kd_mmap_body_write_owned' not in adapter and 'kd_mmap_fault_init' not in adapter and 'kd_mmap_unmap_init' not in adapter
        assert not list((integration/'overlay/mm').glob('*.inc'))
        old=Path('/root/kdlock-kernel-work/mm-populated-unmap-20261022/candidate-1/linux/kernel/locking/kd_mmap')
        observed=sum((old/n).stat().st_size for n in OBJECTS)
        source_bytes=sum((a.kernel_source/n).stat().st_size for n in expected)
        budget=source_bytes+4*observed
        assert shutil.disk_usage(out).free>budget
        result['space']=dict(free=shutil.disk_usage(out).free,measured_old_object_bytes=observed,native_wrapper_bytes=source_bytes,budget=budget)
        wrappers=out/'native-wrapper-copy';wrappers.mkdir()
        for name,h in expected.items():
            assert rt.digest(a.kernel_source/name)==h,name
            dest=wrappers/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a.kernel_source/name,dest)
        rt.command(['patch','--batch','--fuzz=0','-p1','-i',integration/'guest-kernel.patch'],out/'wrapper-patch.log',timeout=30,cwd=wrappers)
        generated=out/'generated';generated.mkdir()
        inputs,outputs=runpy.run_path(str(integration/'prepare.py'))['generated_sources'](generated)
        rt.write_json(out/'source-sha256.json',inputs)
        private=generated/'kernel/locking/kd_mmap'
        assert not any((private/n).exists() for n in ('body.c','fault.c','unmap.c','body_internal.h'))
        assert not any(name.startswith('mm/') for name in outputs)
        # Compile the five builtin lock objects only. This produces no module,
        # kernel image, boot entry or installed output and changes no native MM body.
        rt.command(['make','-C',a.kernel_source,'M='+str(private),'W=1','UBSAN_SANITIZE=n',
                    'KCFLAGS=-I'+str(generated/'include'),*OBJECTS],out/'lock-objects.log',timeout=180)
        symbols=subprocess.check_output(['nm','--defined-only',*[str(private/n) for n in OBJECTS]],text=True,timeout=30)
        assert all(name in symbols for name in ('kd_mmap_down_read','kd_mmap_down_write','kd_mmap_read_unlock_non_owner','kd_mmap_mutex_osq_node_put'))
        assert not re.search(r'\bkd_mmap_(?:madvise|fault_submit|unmap_submit|rwsem_body_lock)\b',symbols)
        rt.command(['make','-C',ROOT/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS=mutex/test_mutex_api.py'],out/'basic-lock-api.log',timeout=180)
        assert {n:rt.digest(a.kernel_source/n) for n in NATIVE_BODIES}==body_hashes
        for n,h in inputs.items():assert rt.digest(ROOT/n)==h,n
        runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
        result.update(passed=True,idle=True,wrapper_files=len(WRAPPERS),native_body_sha256=body_hashes,
            generated_sources=len(outputs),object_sha256={n:rt.digest(private/n) for n in OBJECTS},
            basic_programs=2,lock_api_drivers=1,kernel_image_built=False,recovery_unchanged=True,
            limitation='Compile and API checks only; actual-mm wrapper runtime needs a separately verified lock-only kernel.')
    except BaseException as error:result['error']=repr(error);raise
    finally:rt.write_json(out/'result.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
