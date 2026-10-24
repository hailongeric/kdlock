#!/usr/bin/env python3
"""Recorded one-shot use of the already installed, approved candidate image."""
import argparse
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mm-boundary-interior-near-empty-20261024')
SOURCE=Path('/dev/shm/kdmm27-identity')
BUNDLE=Path('/root/kdlock-kernel-baselines/mmap-kdmm27-20261024')
RELEASE='6.1.159-kdmm27'


def load(path):return json.loads(path.read_text())
def idle():
    spec=importlib.util.spec_from_file_location('transition_archive',ROOT/'bench/archive_run.py')
    archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
    archive.idle(Path('/root'),rt.idle)


def preserved():
    boot=load(BASE/'recovery/boot-sha256.json')
    modules=load(BASE/'recovery/modules-sha256.json')
    for name,digest in {**boot,**modules}.items():
        if name=='/boot/grub/grub.cfg':continue
        rt.require(rt.digest(Path(name))==digest,'recovery artifact changed: '+name)
    installed=load(BASE/'install/result.json')
    rt.require(installed['passed'] and installed['recovery_unchanged'] and
               rt.digest(BASE/'install/installed-sha256.json')==installed['installed_manifest_sha256'],
               'installed candidate receipt changed')
    for name,digest in load(BASE/'install/installed-sha256.json').items():
        rt.require(rt.digest(Path(name))==digest,'installed candidate changed: '+name)
    cfg=Path('/boot/grub/grub.cfg').read_text()
    rt.require('set default="'+installed['recovery_default']+'"' in cfg and
               all(entry in cfg for entry in installed['boot_entries'].values()),
               'recovery default or candidate entry changed')
    return dict(recovery_module_files=len(modules),recovery_preserved=True,
                grub_sha256=rt.digest(Path('/boot/grub/grub.cfg')),installed=installed)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('request','verify'))
    p.add_argument('--mode',choices=('native','kd','recovery'),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--host-state',type=Path)
    p.add_argument('--request',type=Path);a=p.parse_args()
    rt.require(os.geteuid()==0 and str(ROOT)=='/root/host_fs/kdlock' and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG')=='before-mutex-kdonly-20261017T140354Z',
               'confirmed original VM required')
    idle();rt.require(not a.output.exists(),'new transition evidence path required');a.output.mkdir()
    result=dict(passed=False,mode=a.mode,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    result['driver_sha256']=rt.digest(Path(__file__))
    try:
        result.update(preserved())
        expected=load(BASE/'control/expected-guest.json')['modules']
        build=load(BASE/'build-1/result.json')
        rt.require(build['passed'] and rt.digest(BUNDLE/'manifest.json')==
                   build['baseline_manifest_sha256'],'built candidate capture differs')
        build_id=load(BUNDLE/'manifest.json')['running']['build_id']
        if a.action=='request':
            rt.require(a.host_state is not None,'actual host recovery evidence required')
            host=load(a.host_state)
            import datetime
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
            rt.require(0<=age<=300 and host['snapshot_listed'] and host['pins_verified'] and
                       len(host['qemu'])==1 and host['qemu'][0]['pid']==257489 and
                       host['recovery_snapshot']==os.environ['KDLOCK_SNAPSHOT_TAG'],'fresh recovery snapshot/pins required')
            rt.require(sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())==expected,
                       'pre-transition module set differs')
            result['host_state_sha256']=rt.digest(a.host_state)
            entry=(result['installed']['recovery_default'] if a.mode=='recovery' else
                   result['installed']['boot_entries'][a.mode])
            result.update(entry=entry,release_before=os.uname().release,reboot_requested=False)
            idle()
            # Only a quick capacity check against the observed two-boot/test growth.
            rt.require(shutil.disk_usage('/').free > 15_000_000, 'insufficient remaining boot/test headroom')
            result['root_free_before_boot']=shutil.disk_usage('/').free
            # Complete idle/admission checks before arming. If a subsequent
            # administrative command fails, retain the exact armed/unknown
            # state rather than claiming that no one-shot selection remains.
            result['one_shot_state']='ARMING'
            rt.write_json(a.output/'result.json',result)
            rt.command(['grub-reboot',entry],a.output/'grub-reboot.log')
            result['one_shot_state']='ARMED'
            rt.write_json(a.output/'result.json',result)
            environment=rt.command(['grub-editenv','list'],a.output/'grub-environment.log')
            rt.require('next_entry='+entry in environment,'one-shot entry not set')
            result.update(passed=True,reboot_requested=True)
            rt.write_json(a.output/'result.json',result)
            # All workers were joined before this administrative reboot. A
            # disconnected SSH does not itself validate the subsequent boot.
            subprocess.run(['systemctl','reboot'],check=True,timeout=30)
        else:
            if a.mode != 'recovery':
                import runpy
                runpy.run_path(str(BASE/'control/hydrate.py'))['hydrate']()
            rt.require(a.request is not None,'recorded request required')
            prior=load(a.request)
            rt.require(prior['passed'] and prior['reboot_requested'] and prior['mode']==a.mode and
                       prior['boot_id']!=result['boot_id'],'different explicitly requested boot required')
            cmdline=Path('/proc/cmdline').read_text().split()
            release='6.1.159-kdclobber2' if a.mode=='recovery' else RELEASE
            rt.require(os.uname().release==release and {'nokaslr','nopvspin'}<=set(cmdline),
                       'requested image/boot policy differs')
            rt.require([s for s in cmdline if s.startswith('kd_mmap=')]==
                       ([] if a.mode=='recovery' else ['kd_mmap='+('on' if a.mode=='kd' else 'off')]),
                       'requested immutable mmap mode differs')
            current=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
            missing=set(expected)-set(current)
            rt.require(not(set(current)-set(expected)) and missing<=
                       {'intel_uncore_frequency_common','nfit','nfnetlink','skx_edac_common','tls'},
                       'unreviewed runtime module difference')
            for name in sorted(missing):rt.command(['modprobe',name],a.output/(name+'.log'))
            modules=sorted(s.split()[0] for s in Path('/proc/modules').read_text().splitlines())
            rt.require(modules==expected,'exact runtime module restoration failed')
            args=argparse.Namespace(kernel_source=Path('/root/linux-6.1.159-kdclobber2') if a.mode=='recovery' else SOURCE,
                kernel_baseline=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919') if a.mode=='recovery' else BUNDLE)
            identity=kernel_identity.capture(args,a.output,rt.command)
            rt.require(identity['running_build_id']==('5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' if a.mode=='recovery' else build_id),
                       'running Build ID differs')
            dmesg=rt.command(['dmesg'],a.output/'boot-dmesg.log')
            result['boot_io_errors']=[line for line in dmesg.splitlines() if 'I/O error' in line]
            result['boot_faults']=rt.FAULT.findall(dmesg)
            rt.require(not result['boot_faults'],'new boot contains a kernel fault')
            idle();result.update(passed=True,idle=True,release=release,build_id=identity['running_build_id'],
                kernel_identity=identity,modules=modules,restored_modules=sorted(missing),
                request_sha256=rt.digest(a.request),before_boot_id=prior['boot_id'],cmdline=' '.join(cmdline))
    except BaseException as error:
        result.update(passed=False,error=repr(error));raise
    finally:rt.write_json(a.output/'result.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
