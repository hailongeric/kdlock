#!/usr/bin/env python3
"""One-off kernel4 repeat boot preflight/arm/postproof. Never reboots or loads.

Caller exclusively holds the idle VM window. Review inputs bind the actual db7
two-module build and the completed ordinary recovery of the earlier spin run.
Host recovery and headroom are read separately from guest free space.
No phase retries or cleans up a prior partial receipt directory.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
OLD = BASE / 'receipts/install-kdrebuild4-spin-01'
NEW = BASE / 'receipts/repeat-kdrebuild4-db7-20261111-01'
POSTOUT = BASE / 'receipts/postboot-kdrebuild4-db7-20261111-01'
POST = BASE / 'receipts/kernel4-install-helpers-spin-01/kdlock-kdrebuild4-postboot.py'
INPUTS = BASE / 'receipts/overlay-kdrebuild4-spin-01/build-inputs.json'
WORK = Path('/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-0a07f678-01a1bc4f')
RECOVERY = WORK / 'recovery-spin-approved-01'
RECOVERY_OBSERVER = WORK / 'recovery-spin-controller-01/result.json'
BOOT = '84e4ba94-b616-4b65-9efe-820921f36c16'
RELEASE = '7.0.0-38-kdrebuild4'
CORE = '2d0ad60b0bc46929f3070aefa364e710c0a81115'
FIXTURE = 'db7d7d6e38e1341e24b643553bd83633616d4ea7'
BID = 'f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053'
UUID = 'aa0bde06-47f6-4049-aaaf-13d052e53961'
ENTRY = 'gnulinux-advanced-' + UUID + '>gnulinux-' + RELEASE + '-advanced-' + UUID
DEFAULT = 'gnulinux-advanced-' + UUID + '>gnulinux-7.0.0-38-kdlock1-advanced-' + UUID
CFG = '9797117f0ac48ebd8122a39b38716c3f7dd5c86c59ced0ead048389ae086f9a1'
PINS = {'vmlinux': '310df27ab801ecb0cb291d510a77d491030b6c85388a3930df2f54306bc27dd5',
        '.config': '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483',
        'arch/x86/boot/bzImage': 'd89fead1a6d3a7ad573e530eb29b460754655c67b05c49780a43dc88d653afbf',
        'System.map': '5832a5f64db2100543972a9f97e1d7b969f746a4bafed04ec04f04c8f5484c78',
        'Module.symvers': 'e4b9faad85933d5f3ffbcb70313fc6416135df4587fdd63cc363e1d6a620192b',
        'include/config/kernel.release': 'a79fd7078936815525022ebb9ff4607c380f6d6259c92d23e3431108dc2f7a87',
        'include/generated/utsrelease.h': 'efa16a86f679dbb4adc76f66059d248cd0981646c7f4bea5e19194474d6b00e0'}
BOOT_FILES = [{'path': '/boot/vmlinuz-7.0.0-38-kdrebuild4', 'sha256': 'd89fead1a6d3a7ad573e530eb29b460754655c67b05c49780a43dc88d653afbf', 'size': 17191424}, {'path': '/boot/System.map-7.0.0-38-kdrebuild4', 'sha256': '5832a5f64db2100543972a9f97e1d7b969f746a4bafed04ec04f04c8f5484c78', 'size': 10567738}, {'path': '/boot/config-7.0.0-38-kdrebuild4', 'sha256': '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483', 'size': 308548}, {'path': '/boot/initrd.img-7.0.0-38-kdrebuild4', 'sha256': '9b356a73d19bb9861fa05a7a77e6bad4ed875462b7cd9fe780f9a8554c34c31d', 'size': 30886382}]
POSTSHA = '80b6eb9d68d2d1bcf1650c9bcdb315b63867665efaff08eda311d4d96c2790eb'
MANIFESTSHA = '1a626dfb99d2098c7e0a2aef199c5c0f33ca1ffe00078f1cdae63ac184dac9e0'
RECOVERY_SHA = 'd5b188ce454de29a730dd8871d1926c121bca8d79c1be04a7fa099726b116524'
OBSERVER_SHA = '172eedfe8c6d4ac131f1e6a63467b90c3851fdd94b3d50a67e101bd94e937262'
ARCHIVE_SHA = '21328862c8fb47dd8ad4b7842c5b766e169c6a027aee964a458d9b78b66a678d'
LIMITED_SHA = '67d487e3c830b9231f882bde5f8e8f3b9e36a063b76f314a059f3041c9ee76de'
PREVIOUS_POST = BASE / 'receipts/postboot-kdrebuild4-spin-01'
PROTECTED_BOOT = {'normal-recovery-boot-unchanged.json':
                  ('e7ebcfb8468ac3965cddfad5563554c1881589ed49474018a5df6e850d1cf332',8),
                  'prior-candidate-boot-unchanged.json':
                  ('6f0f114959a2f0c9fe6c8b29b575b037f748723c018615146dd91bd1401a7a21',12)}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'not regular: ' + str(path))
    with path.open('rb') as f:
        h = hashlib.sha256()
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    after = path.lstat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), 'changed hash input')
    return h.hexdigest()


def save(name, value):
    data = value if isinstance(value, bytes) else (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    with (NEW/name).open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    fd = os.open(NEW,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_pinned(path, expected):
    require(digest(path)==expected, 'reviewed receipt hash differs: '+str(path))
    require(Path(path).stat().st_size<=4*1024*1024,'review receipt too large')
    return json.loads(Path(path).read_text())


def run(label, argv, timeout, byte_limit):
    path=NEW/(label+'.log'); started=time.monotonic()
    def limit():
        resource.setrlimit(resource.RLIMIT_FSIZE,(byte_limit,byte_limit))
    with path.open('xb') as f:
        p=subprocess.Popen(list(map(str,argv)),stdout=f,stderr=subprocess.STDOUT,
             start_new_session=True,preexec_fn=limit,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'})
        timed=False
        try:
            rc=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed=True
            try:
                os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                rc=p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                save(label+'-result.json',dict(argv=list(map(str,argv)),pid=p.pid,timed_out=True,drain_established=False,outstanding=True))
                raise RuntimeError('unreaped command; retain output and process')
        f.flush(); os.fsync(f.fileno())
    save(label+'-result.json',dict(argv=list(map(str,argv)),returncode=rc,timed_out=timed,
         elapsed_seconds=time.monotonic()-started,sha256=digest(path)))
    require(not timed and rc==0,'command failed: '+label)
    return path.read_text()


def idle(label, post=False):
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    taint=Path('/proc/sys/kernel/tainted').read_text().strip()
    require(os.uname().release==RELEASE,'wrong running kernel')
    require((boot!=BOOT and taint=='0') if post else (boot==BOOT and taint=='12288'),'unexpected boot/taint')
    modules=Path('/proc/modules').read_text()
    require(not any(any(x in l.split()[0].lower() for x in ('kdlock','kd_','komb','tclock')) for l in modules.splitlines()),'KD module still present')
    require(not list(Path('/dev').glob('kd*')),'fixture device remains')
    bad=[]; rows=[]
    names={'make','gmake','ninja','gcc','clang','cc1','cc1plus','ld','ld.bfd','ld.lld','as','objcopy','insmod','rmmod','modprobe','fio','perf'}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():
            continue
        try:
            comm=(p/'comm').read_text().strip(); cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        except (OSError,ProcessLookupError):
            continue
        rows.append(dict(pid=int(p.name),comm=comm,command=cmd))
        if comm in names or any(x in comm for x in ('gcc','clang','cc1','kd-fixture','kd_fixture','kd-scene/')) or any(x in cmd for x in ('pytest','unittest','run_runtime_fixture.py','run_spin_runtime_fixture.py','will-it-scale','kernel4-spin-recover')):
            bad.append(rows[-1])
    save(label+'.json',dict(boot_id=boot,taint=taint,release=RELEASE,modules=modules,processes=rows,unexpected=bad,unix_time=time.time()))
    require(not bad,'build/test/fixture/recovery activity')
    return boot


def grub(label, armed, byte_limit):
    require(digest('/boot/grub/grub.cfg')==CFG,'GRUB cfg changed')
    text=Path('/boot/grub/grub.cfg').read_text()
    require('set default="'+DEFAULT+'"' in text,'normal default changed')
    run(label+'-syntax',['grub-script-check','/boot/grub/grub.cfg'],30,byte_limit)
    raw=run(label+'-environment',['grub-editenv','/boot/grub/grubenv','list'],30,byte_limit)
    env=dict(x.split('=',1) for x in raw.splitlines() if '=' in x)
    require(env.get('next_entry','')==(ENTRY if armed else '') and not env.get('prev_saved_entry'),'unexpected one-shot state')
    d=dict(grub_cfg_sha256=CFG,normal_default=DEFAULT,environment=env,candidate_entry=ENTRY)
    save(label+'.json',d); return d


def installed():
    for row in BOOT_FILES:
        path=Path(row['path'])
        require(path.stat().st_size==row['size'] and digest(path)==row['sha256'],
                'installed kernel4 boot bytes differ')
    limited=load_pinned(OLD/'limited-stage.json',LIMITED_SHA)
    root=Path('/lib/modules')/RELEASE
    names=set()
    for row in limited['namespace']:
        path=root/row['name']; meta=path.lstat()
        require(stat.S_ISREG(meta.st_mode) and stat.S_IMODE(meta.st_mode)==row['mode'] and
                meta.st_size==row['size'] and digest(path)==row['sha256'],
                'installed limited namespace differs: '+row['name'])
        names.add(row['name'])
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual==names,'installed limited namespace membership differs')
    for name,(expected,count) in PROTECTED_BOOT.items():
        receipt=load_pinned(PREVIOUS_POST/name,expected)
        require(len(receipt['files'])==count and
                len({row['path'] for row in receipt['files']})==count,
                'protected boot snapshot membership differs')
        for row in receipt['files']:
            path=Path(row['path']); metadata=path.lstat()
            require(stat.S_ISREG(metadata.st_mode) and
                    stat.S_IMODE(metadata.st_mode)==row['mode'] and
                    metadata.st_size==row['size'] and digest(path)==row['sha256'],
                    'protected normal/recovery/prior-candidate boot file differs')


def module_build(review):
    result=load_pinned(review['module_build_result'],review['module_build_result_sha256'])
    require(result['mode']=='build' and result['status']=='COMPLETE' and result['returncode']==0 and
            result['verified_inputs']['source_commit']==FIXTURE and
            result['verified_inputs']['core_commit']==CORE and
            result['verified_inputs']['package_file_count']==67 and
            all(result['verified_inputs']['kernel_pins'][name]==PINS[name]
                for name in ('vmlinux','.config','System.map','Module.symvers',
                             'include/config/kernel.release','include/generated/utsrelease.h')),
            'actual completed db7 fixture build differs')
    require(set(result['module_builds'])=={'spin','mutex'},'both module build results required')
    for name,row in result['module_builds'].items():
        path=Path(row['module'])
        require(row['returncode']==0 and row['observer_stop'] is None and row['runner_ast']=='PASS' and
                path.resolve(strict=True)==path and path.stat().st_size==row['module_bytes'] and
                digest(path)==row['module_sha256'],'actual db7 module differs: '+name)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('preflight','arm','postproof'))
    p.add_argument('--review-inputs',type=Path,required=True)
    p.add_argument('--review-sha256',required=True)
    a=p.parse_args(); require(os.geteuid()==0,'VM root controller required')
    review=load_pinned(a.review_inputs,a.review_sha256)
    for k in ('minimum_root_free_bytes','minimum_build_free_bytes','minimum_host_free_bytes','max_command_bytes'):
        require(type(review[k]) is int and review[k]>0,'invalid explicit bound: '+k)
    age=review['max_proof_age_seconds']; require(type(age) in (int,float) and math.isfinite(age) and age>0,'invalid age bound')
    if a.phase=='preflight':
        NEW.mkdir(mode=0o700,exist_ok=False)
    else:
        require(NEW.is_dir(),'missing preflight directory')
    save(a.phase+'-started.json',dict(unix_time=time.time(),review_path=str(a.review_inputs),review_sha256=a.review_sha256))
    try:
        if a.phase=='preflight':
            recovery=load_pinned(RECOVERY/'result.json',RECOVERY_SHA)
            observer=load_pinned(RECOVERY_OBSERVER,OBSERVER_SHA)
            require(recovery['status']=='EXACT_ORDINARY_RECOVERY_COMPLETE' and
                    observer['returncode']==0 and observer['observer_expired'] is False and
                    [(x['operation'],x['sequence'],x['status']) for x in recovery['exchanges']]==
                    [(9,22,0),(10,23,0),(11,24,0),(6,25,0)] and
                    recovery['settled_rows']==len(recovery['archive']['keys'])==5 and
                    recovery['archive']['sha256']==ARCHIVE_SHA and
                    digest(RECOVERY/'shutdown-raw-archive.json')==ARCHIVE_SHA,
                    'actual ordinary failed-run recovery is incomplete')
            save('prior-recovery-result.json',(RECOVERY/'result.json').read_bytes())
            save('prior-recovery-observer.json',RECOVERY_OBSERVER.read_bytes())
            built=module_build(review)
            save('module-build-input.json',Path(review['module_build_result']).read_bytes())
            hmp=load_pinned(review['hmp_result'],review['hmp_result_sha256'])
            stamp=hmp['unix']
            require(0<=time.time()-stamp<=age and
                    stamp>=max(recovery['finished_unix'],datetime.datetime.fromisoformat(built['end_utc']).timestamp()),
                    'post-recovery/module HMP proof is not fresh')
            commands={row['command']:row['output'] for row in hmp['commands']}
            require('VM status: running' in commands['info status'],'VM is not running')
            snapshots=commands['info snapshots'].split('List of partial',1)[0]
            require('List of snapshots present on all disks:' in snapshots and
                    'kdlock-builddisk-clean-20261031' in snapshots,'missing real recovery snapshot')
            require(all(name+' (' in commands['info block'] for name in
                        ('drive_system','drive_data1','drive_kdlock_builds2')),'incomplete disk identity')
            require(hmp['host_free_bytes']>=review['minimum_host_free_bytes'],'reviewed host headroom consumed')
            idle('preflight-idle')
            installed()
            require({n:digest(BASE/'build'/n) for n in PINS}==PINS,'ELF/config/bzImage/System.map changed')
            manifest=load_pinned(INPUTS,MANIFESTSHA)
            require(manifest['build_input_count']==67 and len(manifest['files'])==67 and manifest['core_git_head']==CORE,'kernel input identity changed')
            actual={n:digest(BASE/'source/kernel/kdlock'/n) for n in manifest['files']}
            require(actual==manifest['files'],'kernel source67 changed')
            save('kernel-source67.json',actual)
            notes=run('elf-build-id',['readelf','-n',BASE/'build/vmlinux'],30,review['max_command_bytes'])
            require(re.findall(r'Build ID: ([0-9a-f]+)',notes)==[BID],'ELF BuildID differs')
            for path,k in [('/', 'minimum_root_free_bytes'),(BASE,'minimum_build_free_bytes')]:
                s=os.statvfs(path); require(s.f_bavail*s.f_frsize>=review[k],'reviewed guest headroom consumed')
            run('preflight-df',['df','-B1','/','/boot',BASE],30,review['max_command_bytes'])
            grub('preflight-grub',False,review['max_command_bytes'])
        elif a.phase=='arm':
            prior=json.loads((NEW/'preflight-complete.json').read_text())
            require(prior['review_sha256']==a.review_sha256 and 0<=time.time()-prior['unix_time']<=age,'preflight stale/different review')
            idle('arm-idle'); installed(); module_build(review)
            before=grub('arm-before',False,review['max_command_bytes'])
            run('arm-one-shot',['grub-reboot',ENTRY],30,review['max_command_bytes'])
            after=grub('arm-after',True,review['max_command_bytes'])
            require({k:v for k,v in before['environment'].items() if k!='next_entry'}=={k:v for k,v in after['environment'].items() if k!='next_entry'},'other GRUB state changed')
            run('arm-sync',['sync'],30,review['max_command_bytes'])
        else:
            arm=json.loads((NEW/'arm-complete.json').read_text())
            require(arm['review_sha256']==a.review_sha256,'different arm review')
            boot=idle('postproof-idle',True)
            require(digest(POST)==POSTSHA,'postboot helper changed')
            run('postproof-helper',[sys.executable,POST,'--output',POSTOUT,'--timeout','30','--max-command-bytes',str(review['max_command_bytes']),'--max-notes-bytes','65536'],180,review['max_command_bytes'])
            result=json.loads((POSTOUT/'result.json').read_text())
            require(result['phase']=='POSTBOOT_IDENTITY_VERIFIED' and result['boot_id']==boot and boot!=BOOT,'new boot proof incomplete')
            old=json.loads((NEW/'arm-after.json').read_text()); now=result['grub']
            require(now['configuration_sha256']==old['grub_cfg_sha256'] and now['normal_default']==old['normal_default'] and not now['environment'].get('next_entry'),'repeat one-shot not consumed')
            require({k:v for k,v in old['environment'].items() if k!='next_entry'}=={k:v for k,v in now['environment'].items() if k!='next_entry'},'other GRUB state changed across boot')
            save('repeat-postboot-binding.json',dict(old_boot_id=BOOT,new_boot_id=boot,repeat_arm=arm,repeat_armed_grub=old,postboot_result=str(POSTOUT/'result.json'),postboot_helper_sha256=POSTSHA))
        save(a.phase+'-complete.json',dict(status='COMPLETE',phase=a.phase,unix_time=time.time(),review_sha256=a.review_sha256,reboot_performed=False,module_load_performed=False))
    except BaseException as e:
        save(a.phase+'-failure.json',dict(status='FAILED_NO_AUTOMATIC_RETRY',error=repr(e),one_shot_may_be_set=a.phase=='arm'))
        raise


if __name__=='__main__':
    main()
