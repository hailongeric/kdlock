#!/usr/bin/env python3
"""VM-only remaining basic checks; preserve every original build and failure."""
import hashlib,json,os,runpy,time
from pathlib import Path
BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel7-fixtures-e01a89d9-02')
OLD=BASE/'build-02/receipts'
OUT=BASE/'basic-continue-01'
NEW=BASE/'continuation-input-01/mmap-runner-fixed.py'
HELPER=BASE/'transport/build.py'
HELPER_SHA='cbeca599151d06306919c9fb9172670716b121d1851b45a1e0cb97194cea1ad2'
FAILED_SHA='2820a2952f5da8815e130d6d0fb62a5a7f912b48cf815ad4b533fd6b62e93432'
FIXED_SHA='c20114507195b4dbccdd2fbca504230400a8cc9be3c51182d76ea30eff3dfb31'
FIXED_COMMIT='e9365fdfffb625f47766aeef935cbcfb8f875eea'
record=None
def require(value,message):
 if not value:raise RuntimeError(message)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
require(os.geteuid()==0 and sha(HELPER)==HELPER_SHA,'guest/root reviewed helper required')
ns=runpy.run_path(str(HELPER));g=ns['atomic_json'].__globals__
ns['environment']()
require(not any(name in os.environ for name in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')),'unreviewed compiler/Python environment override')
old_path,old=ns['checked_json'](OLD/'result.json',FAILED_SHA)
require(old['status']=='FAILED_OR_INCOMPLETE' and old['error']=="RuntimeError('new-runner-syntax failed; original output retained')",'original failed syntax result differs')
commands=old['commands'];require(len(commands)==37 and all(x['returncode']==0 for x in commands[:36]) and commands[-1]['label']=='new-runner-syntax' and commands[-1]['returncode']==1,'passing builds/client or original syntax failure differs')
for row in commands:
 require(not Path('/proc',str(row['pid'])).exists(),'original child still present')
 require(sha(OLD/(row['label']+'.log'))==row['log_sha256'],'original command log changed')
require(sha(NEW)==FIXED_SHA and NEW.resolve(strict=True)==NEW,'exact new standalone runner required')
config_path,config=ns['checked_json'](old['config'],old['config_sha256']);bounds=config['bounds']
built_path,built=ns['checked_json'](old['build_receipt'],old['build_receipt_sha256']);require(built['status']=='BUILT_AND_LINKED_IDENTITY_VERIFIED','successful linked build required')
identity_path,identity=ns['checked_json'](built_path.parent/'final-identity.json',built['final_identity_sha256'])
focus_path,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256'])
source,build=ns['canonical'](built['source']),ns['canonical'](built['build']);inp=ns['canonical'](old['source_input'])
manifest_path,files=ns['checked_json'](config['manifest'],config['manifest_sha256']);state_path,state=ns['checked_json'](config['state'],config['state_sha256'])
require(state['source_git_head']==old['source_git_head']=='e01a89d95aec9e2efa0937d88f66a92b95b71e08' and old['kernel_core_git_head']==g['CORE'] and len(files)==139,'compiled snapshot/core scope differs')
ns['source_files'](inp,files)
require(set(old['modules'])=={'native-api','mmap','killable','rwsem','mutex'},'all five original signed modules required')
artifact_pins={}
for label,row in old['modules'].items():
 for kind in ('unsigned','signed'):
  facts=row[kind];require(sha(facts['path'])==facts['sha256'] and Path(facts['path']).stat().st_size==facts['bytes'],'original module changed');artifact_pins[facts['path']]=facts['sha256']
require(sha(old['client']['path'])==old['client']['sha256'],'original passed client changed');artifact_pins[old['client']['path']]=old['client']['sha256']
outputs={name:row['sha256'] for name,row in identity['files'].items()};require(len(outputs)==16,'exact16 core outputs required')
ns['pins'](build,outputs)
require(ns['protected'](focused)==old['protected_before'] and ns['source_pins'](focused,source)==old['kernel_source_before'] and ns['boot_files']()==old['boot_before'],'source/normal/kernel6/boot changed since passing builds')
require(not os.path.lexists(OUT) and OUT.parent.resolve(strict=True)==BASE,'fresh continuation receipt required');OUT.mkdir(mode=0o700);g['out']=OUT
tools={name:Path(row['path']) for name,row in config['tools'].items()}
for name,row in config['tools'].items():require(tools[name].resolve(strict=True)==Path(row['resolved_path']) and sha(row['resolved_path'])==row['sha256'],'actual pinned tool changed')
record={'status':'PREPARED_BASIC_CONTINUATION','prior_result':str(old_path),'prior_result_sha256':FAILED_SHA,'prior_error':old['error'],'compiled_source_git_head':old['source_git_head'],'kernel_core_git_head':g['CORE'],'corrected_runner_git_head':FIXED_COMMIT,'corrected_runner':str(NEW),'corrected_runner_sha256':FIXED_SHA,'build_receipt':str(built_path),'build_receipt_sha256':old['build_receipt_sha256'],'modules':old['modules'],'client':old['client'],'artifact_pins':artifact_pins,'core_pins_before':outputs,'commands':[],'scope':'No rebuild/sign/load/boot: only corrected AST2, previously unrun four boundary tests and one unselected2x8 syscall baseline. Original failures and frozen e01 input remain immutable.'};g['record']=record;ns['atomic_json']('result.json',record)
try:
 record['identity_before']=ns['idle'](focused['identity_after'])
 deadline=time.monotonic()+300
 syntax='import ast,pathlib,sys; files=sys.argv[1:]; assert len(files)==2; [ast.parse(pathlib.Path(p).read_bytes(),filename=p) for p in files]; print("AST_COMPLETE 2")'
 syntax_log=ns['dispatch']('corrected-runner-syntax',[str(tools['python']),'-c',syntax,str(NEW),str(inp/'tests/kernel/rwsem_killable/runner.py')],deadline,60,BASE,bounds,cwd=inp)
 require(syntax_log.read_text().strip()=='AST_COMPLETE 2','both corrected/current runner syntax checks required')
 tests='import pathlib,sys,unittest; root=pathlib.Path(sys.argv[1]); suite=unittest.defaultTestLoader.discover(str(root/"tests"),pattern="test_source_boundaries.py"); assert suite.countTestCases()==4; result=unittest.TextTestRunner(verbosity=2).run(suite); assert result.testsRun==4 and not result.skipped and result.wasSuccessful(); print("SOURCE_BOUNDARIES_COMPLETE 4")'
 test_log=ns['dispatch']('source-boundary-four',[str(tools['python']),'-c',tests,str(inp)],deadline,60,BASE,bounds,cwd=inp,python_path=inp)
 require(test_log.read_text().splitlines()[-1]=='SOURCE_BOUNDARIES_COMPLETE 4','actual four tests/no skips required')
 baseline_log=ns['dispatch']('unselected-syscalls',[old['client']['path'],'--threads','2','--iterations','8','--deadline-ms','60000'],deadline,60,BASE,bounds,cwd=BASE)
 record['unselected_syscall_baseline']=ns['baseline_result'](baseline_log)
 ns['source_files'](inp,files);record['core_pins_after']=ns['pins'](build,outputs)
 for path,digest in artifact_pins.items():require(sha(path)==digest,'passing module/client changed')
 require(sha(NEW)==FIXED_SHA and sha(old_path)==FAILED_SHA and sha(HELPER)==HELPER_SHA and sha(config_path)==old['config_sha256'],'old receipt/input/new runner changed')
 require(ns['protected'](focused)==old['protected_before'] and ns['source_pins'](focused,source)==old['kernel_source_before'] and ns['boot_files']()==old['boot_before'],'final source/normal/kernel6/boot changed')
 record['identity_after']=ns['idle'](focused['identity_after']);record['checks']={'new_runner_ast':2,'source_boundary_tests':4,'source_boundary_skips':0,'unselected_threads':2,'unselected_iterations_per_thread':8};record['status']='AFFECTED_MODULE_BUILDS_AND_BASIC_CHECKS_COMPLETE';ns['atomic_json']('result.json',record);print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json'),'sha256':sha(OUT/'result.json')}))
except Exception as error:
 if record.get('status')!='INCOMPLETE_CHILD_RETAINED':record['status']='FAILED_BASIC_CONTINUATION'
 record['error']=repr(error);ns['atomic_json']('result.json',record);raise
