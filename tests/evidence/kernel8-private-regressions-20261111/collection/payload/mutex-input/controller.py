#!/usr/bin/env python3
"""VM-only sequential private rwsem QUERY/mutex checks on exact signed inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
KERNEL=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
HOST=BASE/'host-checks-a99186a5-01'
SOURCE='a99186a53568514da850bae6495f0542de7650b7'
record=None
ns=None


def need(value,message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def main():
    global ns,record
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family',choices=('rwsem','mutex'),required=True)
    parser.add_argument('--predecessor-sha256',required=True)
    parser.add_argument('--recovery-sha256',required=True)
    args=parser.parse_args();family=args.family
    inp=BASE/('private-'+family+'-input-01')
    out=BASE/('private-'+family+'-receipts-01')
    need(os.geteuid()==0,'designated VM root required')
    old=BASE/'transport/build.py';native_path=BASE/'native-api-input-01/controller.py'
    need(digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and
         digest(native_path)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074',
         'reviewed metadata/identity helper differs')
    ns=runpy.run_path(str(old));g=ns['main'].__globals__;native=runpy.run_path(str(native_path));ns['environment']()
    need(not any(k in os.environ for k in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE','LD_PRELOAD',
              'LD_LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')),
         'inherited execution override refused')
    predecessor=BASE/('recovery-killable-cycle-01' if family=='rwsem' else 'private-rwsem-receipts-01')/'result.json'
    pp,prior=ns['checked_json'](predecessor,args.predecessor_sha256)
    need(prior['status']==('ORDINARY_CLEANUP_COMPLETE' if family=='rwsem' else 'PRIVATE_RWSEM_COMPLETE'),
         'prior exact family has not completed/drained/unloaded')
    if family=='rwsem':
        need(args.predecessor_sha256=='285c6d6954e164db5f968118e6814d6c2a2e97787bb2eb014a38afc014b9dd6c' and
             prior['original_failure_preserved'] is True,'exact ordinary K cleanup proof differs')
        np,native_prior=ns['checked_json'](BASE/'native-api-mm-live-01/result.json',
             '5b1397d4b8832228ae3d95d3d0105884a98a084260fe1d5a5e464ce1fcece89e')
        need(native_prior['status']=='NATIVE_API_AND_MM_COMPLETE','actual completed native predecessor required')
    prior_identity=prior['identity_after'] if family=='rwsem' else prior['identity_after']['identity']
    before=native['idle']()
    need(before['identity']==prior_identity==
         {'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096},
         'exact same-boot predecessor identity differs; no fresh-boot claim')
    need(native['running_notes']()[1]=='a33dd4d11d0f0c6649107507e685b6e86e716c1a','running Build ID differs')
    config_path=inp/'arguments.json'
    expected={'rwsem':'fc808b241bf9669ef28e9c54f0c57247d9645aaee3dc2a11562fa37e6a4b04d4',
              'mutex':'4201d70c74c531f3d0a0de51eaa85be70ed8abf48c4e5cd06d7e0e3e05f45ee4'}[family]
    cp,config=ns['checked_json'](config_path,expected)
    argv=config['argv'];live=Path(argv[argv.index('--output')+1]);module=Path(config['compiled_module']['path'])
    need(config['host_source_git_head']==SOURCE and config['observer_seconds']==660 and
         config['host_source_manifest_sha256']=='94d35052c09b1688293191c74ff54f8017f97dfa4fe176c54417c687ff66f4a0' and
         live==BASE/('private-rwsem-query-01' if family=='rwsem' else 'private-mutex-01') and
         module==BASE/'build-01/signed'/('kd_rwsem_runtime_fixture.ko' if family=='rwsem' else 'kd_runtime_fixture.ko'),
         'exact reviewed family/caller arguments differ')
    need(module.stat().st_size==config['compiled_module']['bytes'] and digest(module)==config['compiled_module']['sha256'],
         'actual signed module differs')
    python=Path(argv[0]);need(argv[1]=='-B' and python==Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3') and
         python.resolve(strict=True)==Path('/usr/bin/python3.14') and digest(python.resolve())==
         '52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41','translation interpreter differs')
    for alias in ('/usr/sbin/insmod','/usr/sbin/rmmod'):
        need(digest(Path(alias).resolve(strict=True))=='6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7',
             'actual module-tool differs: '+alias)
    manifest=BASE/'host-support-a99186a5-input-01/source-sha256.json'
    state=BASE/'host-support-a99186a5-input-01/source-state.json'
    need(digest(manifest)=='94d35052c09b1688293191c74ff54f8017f97dfa4fe176c54417c687ff66f4a0' and
         digest(state)=='e3dcd9f8edd023b32a22d1e7bd6478aa26a958e461f5eeb89bf7765797814489','immutable143 manifest/state differ')
    files=json.loads(manifest.read_text());need(len(files)==143,'exact143 source membership required');ns['source_files'](HOST/'input',files)
    hp,hc=ns['checked_json'](HOST/'receipts/result.json','e4f76bb7ba3f50a4fcb8da57c1a3c478cb3c4dae748dd3bb546a48f05a674f6a')
    need(hc['status']=='HOST_CONTEXT_BOUNDARY_CHECKS_COMPLETE' and hc['source_git_head']==SOURCE,'actual changed host checks incomplete')
    bp,built=ns['checked_json'](KERNEL/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
    ip,linked=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
    build=Path(built['build']);source=Path(built['source']);pins={n:r['sha256'] for n,r in linked['files'].items()}
    need(len(pins)==16 and ns['pins'](build,pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'],'linked/source/protected identities differ')
    need(digest(KERNEL/'receipts/postboot-kdrebuild8-api-01/gs-proof.json')==
         '7b3480c16ac39def469c84d1a9cc349bcb15a591b655e752eb221c93e2b5a803' and
         digest(KERNEL/'receipts/postboot-kdrebuild8-api-01/result.json')==
         '878c80315ed3f5ee9fd96388987a64cb7f0776ea01bc4eae044eca63ff2bb919','actual postboot/GS proof differs')
    recovery=native['recovery']({'path':str(inp/'recovery.json'),'sha256':args.recovery_sha256},4*1024**3)
    need(not os.path.lexists(out) and not os.path.lexists(live) and out.parent.resolve(strict=True)==BASE,'fresh output leaves required')
    need(ns['available']('/')>=1024**3 and ns['available'](BASE)>=4*1024**3,'root/data floors')
    out.mkdir(mode=0o700);g['out']=out
    record={'status':'PREPARED','family':family,'source_git_head':SOURCE,
            'compiled_module_source_git_head':'140aecc4f83a6b6ae6f20245234e8a63504f9210',
            'kernel_core_git_head':'0d42063ead37dc8fc1631fa56c8348890ede9c5f',
            'predecessor':str(pp),'predecessor_sha256':args.predecessor_sha256,'configuration':config,
            'arguments_sha256':expected,'identity_before':before,'recovery':recovery,'core_pins_before':pins,
            'boot_before':ns['boot_files'](),'commands':[],
            'scope':'Private directly affected 4x8 mechanism checks, including RWS QUERY; no real MM JIT or performance claim.'}
    g['record']=record;ns['atomic_json']('result.json',record)
    row={'label':'private-'+family,'argv':argv,'started_unix':time.time()};record['commands'].append(row);ns['atomic_json']('result.json',record)
    log=out/('private-'+family+'.log');env=dict(os.environ,PATH='/usr/sbin:/usr/bin:/sbin:/bin',**config['environment'])
    with log.open('xb') as output:
        child=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,cwd=HOST/'input',env=env,
                               stdin=subprocess.DEVNULL,start_new_session=True)
        row['pid']=child.pid;ns['atomic_json']('result.json',record);end=time.monotonic()+660
        while child.poll() is None:
            if time.monotonic()>=end or ns['available']('/')<1024**3 or ns['available'](BASE)<4*1024**3 or log.stat().st_size>32*1024**2:
                row.update(status='CHILD_RETAINED',elapsed_seconds=time.time()-row['started_unix'])
                record['status']='INCOMPLETE_CHILD_RETAINED';ns['atomic_json']('result.json',record)
                raise RuntimeError('deadline/space/log observer; original child and controls retained')
            time.sleep(0.25)
        row.update(returncode=child.returncode,elapsed_seconds=time.time()-row['started_unix'])
    row['log_sha256']=digest(log);ns['atomic_json']('result.json',record)
    need(child.returncode==0 and log.stat().st_size<=32*1024**2,'runner failed or incomplete; no cleanup inferred')
    value=json.loads((live/'result.json').read_text())
    need(value['status']==('protected_rwsem_jit_reader_mechanism_pass' if family=='rwsem' else 'protected_jit_recursive_mechanism_pass') and
         value['module_sha256']==config['compiled_module']['sha256'] and value['warm_claim_no_new_facts'] is True and
         value['returned_full_jit_body']=='protected_episode_completed' and
         value['full_c_function_jit_return']=='outside_protected_episode_scope','actual protected family completion incomplete')
    for name in ('result.json','observations-final.bin','observations-final.json','shutdown-archive.json'):
        need((live/name).is_file() and (live/name).stat().st_size>0,'actual final record absent: '+name)
    after=native['idle']()
    need(after['identity']==before['identity'],'same boot/release/taint changed after signed module')
    for name in ('kd_rwsem_runtime_fixture','kd_runtime_fixture'):
        need(not (Path('/sys/module')/name).exists(),'fixture module remains: '+name)
        for suffix in ('','_ctl','_events'):
            need(not (Path('/dev')/(name+suffix)).exists(),'fixture control remains: '+name+suffix)
    ns['source_files'](HOST/'input',files)
    need(digest(module)==config['compiled_module']['sha256'] and digest(config_path)==expected and
         digest(pp)==args.predecessor_sha256 and ns['pins'](build,pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'] and ns['boot_files']()==record['boot_before'],
         'immutable runtime input/protected output changed')
    record.update(status='PRIVATE_'+family.upper()+'_COMPLETE',identity_after=after,runner_result=str(live/'result.json'),
                  runner_result_sha256=digest(live/'result.json'),event_sha256=digest(live/'observations-final.bin'),
                  event_bytes=(live/'observations-final.bin').stat().st_size,archive_sha256=digest(live/'shutdown-archive.json'))
    ns['atomic_json']('result.json',record);print(json.dumps({'status':record['status'],'receipt':str(out/'result.json')}))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if record is not None:
            record['status']='INCOMPLETE_CHILD_RETAINED' if record['status']=='INCOMPLETE_CHILD_RETAINED' else 'FAILED_OR_INCOMPLETE'
            record['error']=repr(error);ns['atomic_json']('result.json',record)
        raise
