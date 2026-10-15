#!/usr/bin/env python3
"""Live origin GS results and returned-body evidence in the recovery guest."""
import argparse
import ctypes
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'disassem'), str(ROOT/'bench/spin_cacheline')]
import origin_policy
import bench_runtime as runtime
import kernel_identity


def worker(cpu, command, count, barrier, output):
    os.sched_setaffinity(0, {cpu})
    ctypes.CDLL(None).prctl(15, b'kd_origin', 0, 0, 0)
    fd = os.open('/dev/kd_origin_gs', os.O_RDWR)
    barrier.wait()
    start = time.process_time_ns()
    fcntl.ioctl(fd, command, count)
    output.put(dict(cpu=cpu, operations=count, cpu_ns=time.process_time_ns()-start))
    os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--numa', action='store_true')
    parser.add_argument('--operations', type=int, default=20000)
    kernel_identity.arguments(parser)
    args = parser.parse_args()
    runtime.require(os.geteuid()==0 and ROOT==Path('/root/host_fs/kdlock') and
        os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1', 'confirmed recovery guest required')
    runtime.idle()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    kernel_identity.capture(args,out,runtime.command)
    source=ROOT/'tests/kernel/mutex/origin_gs'
    runtime.command(['make','-C',ROOT/'kernel_module',f'KDIR={args.kernel_source}',
        'KDLOCK_SELFTEST=0','UBSAN_SANITIZE=n','W=1'],out/'build-provider.log',timeout=180)
    runtime.command(['make','-C',ROOT/'daemon','CFLAGS=-O2 -Wall -Wextra -Werror'],out/'build-daemon.log')
    runtime.command(['make','-C',source,f'KDIR={args.kernel_source}'],out/'build-workload.log',timeout=180)
    for directory in ('include','disassem','kernel_module','tests/kernel/mutex'):
        for path in (ROOT/directory).rglob('*'):
            if path.is_file() and (path.suffix in ('.c','.h','.S','.inc','.py','.json','.def') or path.name=='Makefile') and not path.name.endswith('.mod.c'):
                target=out/'source'/path.relative_to(ROOT)
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    run_dir=out/'source/daemon';run_dir.mkdir(parents=True)
    ko=source/'kd_origin_gs.ko'
    shutil.copyfile(ko,out/ko.name)
    shutil.copyfile(ROOT/'kernel_module/kdlock_km.ko',out/'kdlock_km.ko')
    runtime.command(['insmod',ROOT/'kernel_module/kdlock_km.ko','target_process=kd_origin',
        'owned_mutex_origin_spin=1',f'owned_mutex_numa={int(args.numa)}'],out/'load-provider.log')
    runtime.command(['insmod',ko],out/'load-workload.log')
    symbols={parts[2]:int(parts[0],16) for line in Path('/proc/kallsyms').read_text().splitlines()
             if len(parts:=line.split())>=3}
    identity,_,_=origin_policy.elf_symbol(ko,'kd_origin_test_counter')
    manifest=dict(schema=1,symbol='kd_origin_test_counter',module='kd_origin_gs',
        elf=str(ko),elf_sha256=runtime.digest(ko),build_id=identity,
        source_sha256=runtime.digest(source/'module.c'),offset=symbols['kd_origin_test_counter'])
    runtime.write_json(out/'gs-audit.json',manifest)
    log=(out/'daemon.log').open('w')
    env=dict(os.environ,KD_GS_AUDIT=str(out/'gs-audit.json'),KD_JIT_BODY_WITNESS='1')
    daemon=subprocess.Popen([ROOT/'daemon/daemon','--quiet'],cwd=run_dir,env=env,stdout=log,stderr=subprocess.STDOUT)
    (out/'daemon.pid').write_text(str(daemon.pid))
    fd=os.open('/dev/kd_origin_gs',os.O_RDWR)
    fcntl.ioctl(fd,0x4700,0)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        device=os.open('/dev/kd_dev',os.O_RDONLY)
        entries=os.read(device,64*511);os.close(device)
        statuses=[struct.unpack_from('<i',entries,i)[0] for i in range(0,len(entries),64)]
        if len(statuses)==2 and statuses==[0,0]:break
        if any(status==-3 for status in statuses):raise RuntimeError('GS admission refused; retain evidence')
        if daemon.poll() is not None:raise RuntimeError('translator exited')
        time.sleep(.1)
    else:raise RuntimeError('translation timeout; retain loaded source and evidence')
    cpus=[0,1,2,3,32,33,34,35]
    results=[]
    for command in (0x4701,0x4702):
        barrier=multiprocessing.Barrier(len(cpus)); queue=multiprocessing.Queue()
        workers=[multiprocessing.Process(target=worker,args=(cpu,command,args.operations,barrier,queue)) for cpu in cpus]
        before=Path('/sys/module/kdlock_km/parameters/owned_mutex_origin_stats').read_text()
        for process in workers:process.start()
        for process in workers:
            process.join(60)
            runtime.require(process.exitcode==0,'worker failed or did not drain; retain modules')
        progress=[queue.get(timeout=1) for _ in workers]
        stats=list(map(int,Path('/sys/module/kdlock_km/parameters/owned_mutex_origin_stats').read_text().split()))
        old=list(map(int,before.split()))
        runtime.require(stats[0]>old[0] and stats[4]>old[4], 'no completed claimed GS bodies')
        results.append(dict(command=command,workers=progress,origin_stats_before=old,origin_stats_after=stats))
    report=bytearray(32);fcntl.ioctl(fd,0x4703,report,True)
    operations,errors,counter,idle=struct.unpack('<QQQQ',report)
    runtime.require(errors==0 and idle==1 and operations==2*len(cpus)*args.operations and
        counter==len(cpus)*args.operations,'incorrect origin CPU/counter results or incomplete drain')
    os.close(fd)
    daemon.terminate();daemon.wait(timeout=15);log.close()
    runtime.command([sys.executable,ROOT/'disassem/device_session.py','retire'],out/'retire.log')
    runtime.command(['rmmod','kd_origin_gs'],out/'unload-workload.log')
    runtime.command(['rmmod','kdlock_km'],out/'unload-provider.log')
    kernel=runtime.command(['dmesg'],out/'kernel.log')
    runtime.require('JIT body witness:' in kernel,'no returned JIT witness')
    runtime.idle()
    runtime.write_json(out/'result.json',dict(passed=True,drained=True,operations=operations,
        counter=counter,errors=errors,numa=args.numa,results=results))
    print('PASS origin CPU reads and task-only counter with claimed returned JIT bodies; drained')


if __name__=='__main__':main()
