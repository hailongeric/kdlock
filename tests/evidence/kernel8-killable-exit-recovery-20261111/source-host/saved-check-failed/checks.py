#!/usr/bin/env python3
"""VM-only fixed K-runner AST1 plus saved SOURCE named-span check.

No kernel/module/syscall/image operation or previously passed check is invoked.
"""
from pathlib import Path
import hashlib
import json
import os
import runpy
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
TRANSPORT = BASE/'host-support-de76da8a-input-01'
OUT = BASE/'host-checks-de76da8a-01'
OLD_HELPER = BASE/'transport/build.py'
NATIVE_HELPER = BASE/'native-api-input-01/controller.py'
NATIVE_RESULT = BASE/'native-api-mm-live-01/result.json'
PYTHON = Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3')
SOURCE = 'de76da8aa2031d73f185f5864071f316c1150c08'
record = None
ns = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for b in iter(lambda: source.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def objdump_identity():
    alias=Path('/usr/bin/objdump');resolved=alias.resolve(strict=True)
    value={'alias':str(alias),'resolved':str(resolved),'bytes':resolved.stat().st_size,'sha256':digest(resolved)}
    need(value=={'alias':'/usr/bin/objdump','resolved':'/usr/bin/x86_64-linux-gnu-objdump',
                 'bytes':415760,'sha256':'44f07f8da860b15bd4dec909f229dec536595fb170a616fe3ab29c7b21c9736f'},
         'actual GNU data-decoding tool differs')
    return value


def main():
    global ns, record
    need(os.geteuid()==0, 'designated VM only')
    need(digest(OLD_HELPER)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and
         digest(NATIVE_HELPER)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074',
         'reviewed shared metadata/check helpers differ')
    ns=runpy.run_path(str(OLD_HELPER));g=ns['main'].__globals__
    native=runpy.run_path(str(NATIVE_HELPER))
    ns['environment']()
    need(not any(k in os.environ for k in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE','LD_PRELOAD','LD_LIBRARY_PATH',
              'GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')), 'inherited override refused')
    need(digest(NATIVE_RESULT)=='5b1397d4b8832228ae3d95d3d0105884a98a084260fe1d5a5e464ce1fcece89e',
         'actual completed native predecessor differs')
    prior=json.loads(NATIVE_RESULT.read_text());need(prior['status']=='NATIVE_API_AND_MM_COMPLETE','native predecessor not complete')
    cleanup_path=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/recovery-killable-regions-01/result.json')
    need(digest(cleanup_path)=='793484d3b32ef8b62759659f7704f0d3323e5090cc0815395d171636d15b0092' and
         json.loads(cleanup_path.read_text())['status']=='ORDINARY_CLEANUP_COMPLETE','actual checked cleanup must precede new host input')
    tool_before=objdump_identity()
    before=native['idle']()
    need(before['identity']==prior['identity_after']['identity'] and before['identity']['release']=='7.0.0-38-kdrebuild8',
         'actual drained same-boot identity differs; no fresh-boot claim')
    need(PYTHON.resolve(strict=True)==Path('/usr/bin/python3.14') and
         digest(PYTHON.resolve())=='52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41',
         'exact translation-venv invocation/interpreter required')
    archive=TRANSPORT/'source.tar';manifest=TRANSPORT/'source-sha256.json';state=TRANSPORT/'source-state.json'
    need(archive.stat().st_size==1710080 and digest(archive)=='ac7e533e1b3cefef7a78d9cdcbe48dbc53fc759bb577d36f7b1335f4ba0863c9' and
         digest(manifest)=='71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60' and
         digest(state)=='3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f', 'frozen143 transport differs')
    files=json.loads(manifest.read_text());need(len(files)==143 and json.loads(state.read_text())==
         {'files':143,'git_status':'','source_git_head':SOURCE,'transfer_bytes':1594299},'exact clean143 source membership differs')
    old_manifest=BASE/'transport/source-sha256.json';need(digest(old_manifest)=='412247ad7422c1c1ee36c15ff4bff6e41a1cda1a9e5c6f88ebbe1754f6b2a4d1','compiled fixture source manifest changed')
    old=json.loads(old_manifest.read_text())
    need(set(files)-set(old)=={'tests/kernel/mmap_api/completion.py','tests/test_mmap_completion.py',
                                  'tests/kernel/payload/native_context_boundaries.inc'} and
         set(old)<=set(files) and {n for n in old if old[n]!=files[n]}==
         {'tests/test_source_boundaries.py','tests/kernel/mmap_api/runner.py','tests/kernel/mmap_api/README.md',
          'tests/kernel/rwsem_killable/README.md','tests/kernel/mmap_api/payload/mmap_jit_profile.inc',
          'tests/kernel/run_runtime_fixture.py','tests/kernel/rwsem_killable/runner.py','kernel/integration/RWSEM.md'},
         'unexpected source delta from compiled140')
    package=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/package.json')
    need(digest(package)=='c7d1afa19ab56c0fa8bf21f0232bf1c8199751407a44e918a4b8c5c133966da9','kernel78 manifest changed')
    core=json.loads(package.read_text())['files'];need(len(core)==78 and all(files[n]['sha256']==h for n,h in core.items()),'host/kernel78 source bytes differ')
    built_path=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/full-01/result.json')
    bp,built=ns['checked_json'](built_path,'024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
    ip,identity=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
    build=Path(built['build']);source=Path(built['source']);pins={n:x['sha256'] for n,x in identity['files'].items()}
    need(len(pins)==16 and ns['pins'](build,pins) and ns['protected'](focused)==built['protected_after'] and
         ns['source_pins'](focused,source)==built['source_after'],
         'protected linked kernel/source differs')
    need(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True)==BASE,'fresh isolated output required')
    need(ns['available']('/')>=1024**3 and ns['available'](BASE)>=4*1024**3,'explicit root/data floors')
    OUT.mkdir(mode=0o700);inp=OUT/'input';receipt=OUT/'receipts';receipt.mkdir(mode=0o700)
    g['out']=receipt
    record={'status':'PREPARED','source_git_head':SOURCE,'compiled_module_source_git_head':'140aecc4f83a6b6ae6f20245234e8a63504f9210',
            'kernel_core_git_head':'0d42063ead37dc8fc1631fa56c8348890ede9c5f','native_predecessor_sha256':digest(NATIVE_RESULT),
            'identity_before':before,'objdump_before':tool_before,'commands':[],'core_pins_before':pins,'boot_before':ns['boot_files'](),
            'scope':'Fixed K-runner syntax1 and saved-source named3 mapping only; no kernel/JIT/syscall/image work or current source authority.'}
    g['record']=record;ns['atomic_json']('result.json',record)
    ns['unpack'](archive,files,inp,2*1024**2)
    bounds={'root_floor_bytes':1024**3,'output_floor_bytes':4*1024**3,'log_bytes':16*1024**2}
    deadline=time.monotonic()+120
    syntax='import ast,pathlib,sys; ast.parse(pathlib.Path(sys.argv[1]).read_bytes(),filename=sys.argv[1]); print("KILLABLE_RUNNER_AST_COMPLETE 1")'
    log=ns['dispatch']('fixed-killable-runner-ast',[str(PYTHON),'-B','-c',syntax,str(inp/'tests/kernel/rwsem_killable/runner.py')],deadline,60,OUT,bounds,cwd=inp)
    need(log.read_text().strip()=='KILLABLE_RUNNER_AST_COMPLETE 1','fixed K runner syntax did not complete')
    check=TRANSPORT/'saved-source-check.py'
    need(digest(check)=='2cc061130b003f6d0e90dadf8eb753863700609757762a816580669c9b9bd9e6','reviewed saved-source check differs')
    log=ns['dispatch']('saved-source-named-spans',[str(PYTHON),'-B',str(check),str(inp),str(OUT/'saved-source')],deadline,60,OUT,bounds,cwd=inp)
    need(log.read_text().strip()=='SAVED_SOURCE_NAMED_SPANS_COMPLETE 3','saved-source named3/actual CALL check did not complete')
    ns['source_files'](inp,files)
    need(digest(NATIVE_RESULT)==record['native_predecessor_sha256'] and ns['pins'](build,pins) and
         ns['protected'](focused)==built['protected_after'] and ns['source_pins'](focused,source)==built['source_after'] and
         ns['boot_files']()==record['boot_before'] and digest(archive)=='ac7e533e1b3cefef7a78d9cdcbe48dbc53fc759bb577d36f7b1335f4ba0863c9' and
         digest(manifest)=='71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60' and
         digest(state)=='3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f','immutable prerequisites changed')
    record['identity_after']=native['idle']();need(record['identity_after']['identity']==before['identity'],'kernel identity/taint changed')
    record['objdump_after']=objdump_identity();need(record['objdump_after']==tool_before,'GNU tool changed')
    record['checks']={'fixed_killable_runner_ast':1,'saved_source_named_spans':3}
    record['status']='HOST_NAMED_SOURCE_CHECKS_COMPLETE';ns['atomic_json']('result.json',record)
    print(json.dumps({'status':record['status'],'receipt':str(receipt/'result.json')}))


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if record is not None:
            record['status']='INCOMPLETE_CHILD_RETAINED' if record['status']=='INCOMPLETE_CHILD_RETAINED' else 'FAILED_OR_INCOMPLETE'
            record['error']=repr(error);ns['atomic_json']('result.json',record)
        raise
