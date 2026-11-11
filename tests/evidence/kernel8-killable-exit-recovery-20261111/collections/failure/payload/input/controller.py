#!/usr/bin/env python3
"""VM-only pinned private managed-killable run; failures retain original actors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
KERNEL = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
INPUT = BASE/'managed-killable-input-02'
OUT = BASE/'managed-killable-receipts-02'
LIVE = BASE/'managed-killable-live-02'
HOST = BASE/'host-checks-de76da8a-01'
SOURCE = 'de76da8aa2031d73f185f5864071f316c1150c08'
COMPILED = '140aecc4f83a6b6ae6f20245234e8a63504f9210'
CORE = '0d42063ead37dc8fc1631fa56c8348890ede9c5f'
PYTHON = Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3')
MODULE = BASE/'build-01/signed/kd_rwsem_killable_fixture.ko'
MODULE_SHA = '74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8'
LIMITS_SHA = '23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8'
record = None
ns = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def idle(native):
    current = native['idle']()
    actors = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            comm = (entry/'comm').read_text().strip()
            argv = (entry/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            if 'tests/kernel/rwsem_killable/runner.py' in argv or comm.startswith('kd-kill'):
                actors.append({'pid':int(entry.name),'comm':comm,'argv':argv})
        except (FileNotFoundError, ProcessLookupError):
            continue
    need(not actors, 'prior killable actors remain: ' + repr(actors))
    for name in ('kd_rwsem_killable_fixture','kd_rwsem_runtime_fixture','kd_runtime_fixture'):
        need(not (Path('/sys/module')/name).exists(), 'fixture remains: ' + name)
        for suffix in ('', '_ctl', '_events'):
            need(not (Path('/dev')/(name+suffix)).exists(), 'fixture device remains: ' + name+suffix)
    return current


def main():
    global ns, record
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-checks-sha256', required=True)
    parser.add_argument('--recovery-sha256', required=True)
    args = parser.parse_args()
    need(os.geteuid()==0, 'designated VM root required')
    old = BASE/'transport/build.py'
    native_path = BASE/'native-api-input-01/controller.py'
    need(digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and
         digest(native_path)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074',
         'reviewed metadata/identity helper differs')
    ns=runpy.run_path(str(old));g=ns['main'].__globals__
    native=runpy.run_path(str(native_path));ns['environment']()
    need(not any(k in os.environ for k in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE',
              'LD_PRELOAD','LD_LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')),
         'inherited execution override refused')
    host_path,checked=ns['checked_json'](BASE/'host-source-continue-de76da8a-01/receipts/result.json',args.host_checks_sha256)
    need(checked['status']=='HOST_NAMED_SOURCE_CHECKS_COMPLETE' and checked['source_git_head']==SOURCE and
         checked['checks']=={'fixed_killable_runner_ast':1,'saved_source_named_spans':3} and
         all(row['returncode']==0 for row in checked['commands']) and len(checked['commands'])==1 and
         checked['prior_ast']['returncode']==0 and checked['prior_ast']['label']=='fixed-killable-runner-ast' and
         checked['prior_failed_check_sha256']=='96e3903dbb55ed34d6d2276bd1433a22e5898c3adb9f8824d24adce17864b7df',
         'actual changed host checks must complete first')
    old_check=Path(checked['prior_failed_check_receipt'])
    need(digest(old_check)==checked['prior_failed_check_sha256'] and
         checked['prior_ast']==json.loads(old_check.read_text())['commands'][0],
         'actual prior AST row/original failed receipt differs')
    cleanup_path,cleanup=ns['checked_json'](BASE/'recovery-killable-regions-01/result.json',
         '793484d3b32ef8b62759659f7704f0d3323e5090cc0815395d171636d15b0092')
    need(cleanup['status']=='ORDINARY_CLEANUP_COMPLETE' and cleanup['original_failure_preserved'] is True,
         'actual first-attempt cleanup must complete before fresh K')
    before=idle(native)
    need(before['identity']==cleanup['identity_after']==checked['identity_after']['identity']==
         {'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096},
         'same actual drained boot/taint differs; no fresh-boot claim')
    need(native['running_notes']()[1]=='a33dd4d11d0f0c6649107507e685b6e86e716c1a', 'running Build ID differs')
    need(PYTHON.resolve(strict=True)==Path('/usr/bin/python3.14') and digest(PYTHON.resolve())==
         '52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41', 'translation interpreter differs')
    for alias, expected in (('/usr/sbin/insmod','6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7'),
                            ('/usr/sbin/rmmod','6edf62330978627d75d8de7e903f243b6ba765f8b54baa914ec83e21cd85bdc7'),
                            ('/usr/bin/dmesg','889b3947799e06c354b611f2759364b92e65e6ad596166e05bf62525f72468ce')):
        need(digest(Path(alias).resolve(strict=True))==expected, 'actual tool differs: ' + alias)
    manifest=BASE/'host-support-de76da8a-input-01/source-sha256.json'
    state=BASE/'host-support-de76da8a-input-01/source-state.json'
    need(digest(manifest)=='71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60' and
         digest(state)=='3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f', 'clean143 identities differ')
    files=json.loads(manifest.read_text());ns['source_files'](HOST/'input',files)
    need(len(files)==143 and json.loads(state.read_text())=={'files':143,'git_status':'','source_git_head':SOURCE,'transfer_bytes':1594299},
         'exact143 source snapshot required')
    need(digest(MODULE)==MODULE_SHA and digest(INPUT/'limits.json')==LIMITS_SHA, 'actual module/caller limits differ')
    bounds=json.loads((INPUT/'limits.json').read_text())
    need(len(bounds)==39 and bounds['decode_window_bytes']==30720 and bounds['source_capacity']==bounds['decode_sites']==2048,
         'corrected explicit39 capacities required')
    bp,built=ns['checked_json'](KERNEL/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
    ip,linked=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
    build=Path(built['build']);source=Path(built['source']);pins={n:r['sha256'] for n,r in linked['files'].items()}
    need(len(pins)==16 and ns['pins'](build,pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'], 'linked/source/protected identities differ')
    proof=KERNEL/'receipts/postboot-kdrebuild8-api-01/gs-proof.json'
    need(digest(proof)=='7b3480c16ac39def469c84d1a9cc349bcb15a591b655e752eb221c93e2b5a803', 'actual GS proof differs')
    need(digest(KERNEL/'receipts/postboot-kdrebuild8-api-01/result.json')==
         '878c80315ed3f5ee9fd96388987a64cb7f0776ea01bc4eae044eca63ff2bb919', 'actual postboot proof differs')
    recovery=native['recovery']({'path':str(INPUT/'recovery.json'),'sha256':args.recovery_sha256},4*1024**3)
    need(not os.path.lexists(OUT) and not os.path.lexists(LIVE) and OUT.parent.resolve(strict=True)==BASE,
         'fresh output and runtime leaves required')
    need(ns['available']('/')>=1024**3 and ns['available'](BASE)>=4*1024**3, 'root/data floors')
    OUT.mkdir(mode=0o700);g['out']=OUT
    record={'status':'PREPARED','source_git_head':SOURCE,'compiled_module_source_git_head':COMPILED,'kernel_core_git_head':CORE,
            'cleanup_receipt':str(cleanup_path),'cleanup_sha256':'793484d3b32ef8b62759659f7704f0d3323e5090cc0815395d171636d15b0092',
            'identity_before':before,'host_checks_receipt':str(host_path),'host_checks_sha256':args.host_checks_sha256,
            'module_sha256':MODULE_SHA,'limits_sha256':LIMITS_SHA,'limits':bounds,'recovery':recovery,
            'core_pins_before':pins,'boot_before':ns['boot_files'](),'commands':[],
            'scope':'Private root managed-killable mechanism; no real MM JIT, general nested cancellation, performance or full C epilogue claim.'}
    g['record']=record;ns['atomic_json']('result.json',record)
    runner=HOST/'input/tests/kernel/rwsem_killable/runner.py'
    argv=[str(PYTHON),'-B',str(runner),'--repo',str(HOST/'input'),'--module',str(MODULE),'--output',str(LIVE),
          '--expected-release','7.0.0-38-kdrebuild8','--kernel-elf',str(build/'vmlinux'),'--kernel-config',str(build/'.config'),
          '--gs-proof-json',str(proof),'--limits-json',str(INPUT/'limits.json'),'--builtin-source-start','0xffffffff8276eee0',
          '--builtin-source-size','2','--deadline','60','--immutable-text-contract','--auxiliary-stack-contract']
    # Finite outer observation leaves the original runner, fd/channel and role
    # actors alive on any timeout, capacity stop or retained runner failure.
    limits={'root_floor_bytes':1024**3,'output_floor_bytes':4*1024**3,'log_bytes':32*1024**2}
    log=OUT/'managed-killable.log'
    row={'label':'managed-killable','argv':argv,'started_unix':time.time()};record['commands'].append(row)
    ns['atomic_json']('result.json',record)
    env=dict(os.environ,LC_ALL='C',PATH='/usr/sbin:/usr/bin:/sbin:/bin',PYTHONDONTWRITEBYTECODE='1')
    with log.open('xb') as output:
        child=subprocess.Popen(argv,stdout=output,stderr=subprocess.STDOUT,cwd=HOST/'input',
                               env=env,stdin=subprocess.DEVNULL,start_new_session=True)
        row['pid']=child.pid;ns['atomic_json']('result.json',record);end=time.monotonic()+1200
        while child.poll() is None:
            failed=False;result=LIVE/'result.json'
            if result.exists() and result.stat().st_size<=16*1024**2:
                try:failed=json.loads(result.read_text()).get('status')=='failed_retained'
                except json.JSONDecodeError:pass
            if failed or time.monotonic()>=end or ns['available']('/')<limits['root_floor_bytes'] or \
                    ns['available'](BASE)<limits['output_floor_bytes'] or log.stat().st_size>limits['log_bytes']:
                row.update(status='CHILD_RETAINED',elapsed_seconds=time.time()-row['started_unix'],
                           observed_runner_failed_retained=failed)
                record['status']='INCOMPLETE_CHILD_RETAINED';ns['atomic_json']('result.json',record)
                raise RuntimeError('runner failure/deadline/space/log observer; original child and controls retained')
            time.sleep(0.25)
        row.update(returncode=child.returncode,elapsed_seconds=time.time()-row['started_unix'])
    row['log_sha256']=digest(log);ns['atomic_json']('result.json',record)
    need(child.returncode==0 and log.stat().st_size<=limits['log_bytes'],'runner rc/output incomplete; no cleanup inferred')
    value=json.loads((LIVE/'result.json').read_text())
    required={'ready-before-fatal-cancel','reader-drain-cancel','queued-exit-before-holder-release',
              'origin-signal-wakes-foreign-c','candidate-cancel-drains-current-w'}
    names=[row['name'] for row in value['cases']]
    need(value['status']=='managed_killable_mechanism_pass' and value['module_sha256']==MODULE_SHA and
         value['bounds']==bounds and value['fixed_claim_no_new_facts'] is True and required<=set(names) and
         len(names)==len(set(names)) and 1<=sum(n.startswith('learning-') for n in names)<=bounds['learning_passes'] and
         value['final']['retired']==1 and value['final']['native_scopes']==0 and value['final']['pool_idle']==1,
         'actual bounded scene/retirement result incomplete')
    for path in ('result.json','observations-final.bin','observations-final.json','shutdown-archive.json','source-export.bin'):
        need((LIVE/path).is_file() and (LIVE/path).stat().st_size>0, 'missing actual record: '+path)
    after=idle(native)
    need(after['identity']['boot']==before['identity']['boot'] and after['identity']['release']==before['identity']['release'] and
         after['identity']['taint']==before['identity']['taint'], 'unexpected final boot/release/taint')
    ns['source_files'](HOST/'input',files)
    need(digest(MODULE)==MODULE_SHA and digest(INPUT/'limits.json')==LIMITS_SHA and
         digest(manifest)=='71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60' and
         digest(state)=='3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f' and
         ns['pins'](build,pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'] and ns['boot_files']()==record['boot_before'],
         'immutable runtime inputs or protected outputs changed')
    record.update(status='MANAGED_KILLABLE_COMPLETE',identity_after=after,runner_result=str(LIVE/'result.json'),
                  runner_result_sha256=digest(LIVE/'result.json'),case_names=names,
                  event_bytes=(LIVE/'observations-final.bin').stat().st_size,
                  event_sha256=digest(LIVE/'observations-final.bin'),archive_sha256=digest(LIVE/'shutdown-archive.json'))
    ns['atomic_json']('result.json',record);print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json')}))


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record['status']='INCOMPLETE_CHILD_RETAINED' if record['status']=='INCOMPLETE_CHILD_RETAINED' else 'FAILED_OR_INCOMPLETE'
            record['error']=repr(error);ns['atomic_json']('result.json',record)
        raise
