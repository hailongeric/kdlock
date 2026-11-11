#!/usr/bin/env python3
"""VM-only metadata finalization; no make, source writes or old-receipt edits."""
import hashlib,json,os,runpy,time
from pathlib import Path
BASE=Path('/mnt/kdlock-builds2/kdlock-main-kernel7-0c97cd34-01')
INPUT=Path('/mnt/kdlock-builds2/kdlock-main-kernel7-input-0c97cd34-01')
OLD=BASE/'receipts/full-01'
OUT=BASE/'receipts/full-finalize-01'
HELPER_SHA='d6a198768592788a6a3ad4807fd4977e3efef97435e2f0e390c85a8094d79ee2'
PREVIOUS_SHA='7f07914093c65d58462e6d44290fbc204bfabf177f0a58d0726660c7b9caf878'
IDENTITY_SHA='9743ae092f2a8dc9bcd4e81f86b2dacd59eade79ed5d55a721ddff11cc6b85bc'
GS_SHA='534faa61ea608f4c6a1699c6777a0e1e535adf2be941c643ac799a55cd448669'
FOCUS_SHA='63db511cef8095f010e7d6117314f69d6b7c2480076c7fcb22c1d4fb12e83839'

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def require(value,message):
 if not value:raise RuntimeError(message)

require(os.geteuid()==0,'guest root required')
helper=INPUT/'full-build.py';require(sha(helper)==HELPER_SHA,'reviewed helper changed')
ns=runpy.run_path(str(helper));g=ns['atomic_json'].__globals__
previous_path,previous=ns['checked_json'](OLD/'result.json',PREVIOUS_SHA)
require(previous['status']=='FAILED_OR_INCOMPLETE' and previous['error'].startswith('build/workload or blocked task remains: '),'original failure differs')
trigger=json.loads(previous['error'].split(': ',1)[1])
require(trigger['busy']==[] and trigger['blocked']==[{'pid':458,'tid':458}],'original final-idle trigger differs')
labels=['kernel','nls','module-vermagic','module-dependencies','elf-notes','elf-symbols','gs-disassembly']
require([row['label'] for row in previous['commands']]==labels and all(row['returncode']==0 for row in previous['commands']),'all original commands must have completed0')
for row in previous['commands']:
 require(not Path('/proc',str(row['pid'])).exists(),'original command PID still present')
 require(sha(OLD/(row['label']+'.log'))==row['log_sha256'],'original command log changed')
focus_path,focused=ns['checked_json'](BASE/'receipts/focused-02/result.json',FOCUS_SHA)
require(focused['status']=='FOCUSED_COMPILE_COMPLETE' and focused['target_units']=={'core':33,'native':8} and focused['core_git_head']==g['CORE'],'focused provenance differs')
identity_path,identity=ns['checked_json'](OLD/'final-identity.json',IDENTITY_SHA)
require(previous['final_identity_sha256']==IDENTITY_SHA and sha(OLD/'gs-config.json')==GS_SHA,'actual linked metadata changed')
require(identity['kernelrelease']==g['RELEASE'] and identity['build_id']=='6195c94ad20aa3548344f27416b350cfde14ad6e' and set(identity['files'])==set(g['FILE_NAMES']),'actual linked identity differs')
require(previous['protected_before']==previous['protected_after'] and previous['source_before']==previous['source_after'] and previous['boot_before']==previous['boot_after'],'original protection failed')
require(not any(previous['missing_export_diagnostics'].values()),'original missing-export diagnostics present')
require(OUT.parent.resolve(strict=True)==BASE/'receipts' and not os.path.lexists(OUT),'fresh finalization receipt required')
OUT.mkdir(mode=0o700)
g['out']=OUT
record=dict(previous)
record.update(status='PREPARED_METADATA_FINALIZATION',prior_result=str(previous_path),prior_result_sha256=PREVIOUS_SHA,prior_status=previous['status'],prior_error=previous['error'],finalization_started_unix=time.time(),scope='Both original makes and linked readers completed0; only metadata/preservation and two unchanged current strict-idle checks are repeated. No compilation/install/load/boot/test.')
record.pop('error',None);g['record']=record
ns['atomic_json']('result.json',record)
try:
 record['finalization_identity_before']=ns['idle'](focused['identity_after'])
 source,build=ns['canonical'](focused['source']),ns['canonical'](focused['build'])
 before=ns['pins'](build,{name:row['sha256'] for name,row in identity['files'].items()})
 record['protected_after']=ns['protected'](focused)
 record['source_after']=ns['source_pins'](focused,source)
 record['boot_after']=ns['boot_files']()
 require(record['protected_after']==previous['protected_before'] and record['source_after']==previous['source_before'] and record['boot_after']==previous['boot_before'],'current protected/source/boot pins changed')
 require((build/'modules.order').read_bytes()==g['ORDER'] and ns['export_rows'](build/'Module.symvers')==ns['export_rows'](build/'vmlinux.symvers'),'limited order/fresh export rows changed')
 require(sha(build/'.config')==focused['config_sha256'] and (build/'include/config/kernel.release').read_text().strip()==g['RELEASE'],'configuration/release changed')
 for name,digest in (('final-identity.json',IDENTITY_SHA),('gs-config.json',GS_SHA)):
  raw=(OLD/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'copied metadata changed')
  with (OUT/name).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 for name,row in identity['return_symbols'].items():
  raw=(OLD/(name+'.bin')).read_bytes();require(hashlib.sha256(raw).hexdigest()==row['sha256'],'actual thunk bytes changed')
  with (OUT/(name+'.bin')).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 time.sleep(10)
 record['identity_after']=ns['idle'](focused['identity_after'])
 record['linked_files_after']=ns['pins'](build,before)
 require(sha(previous_path)==PREVIOUS_SHA and sha(helper)==HELPER_SHA,'original receipt/helper changed')
 record['headroom_after']={'root':ns['available']('/'),'output':ns['available'](build)}
 record['status']='BUILT_AND_LINKED_IDENTITY_VERIFIED'
 record['finalization_elapsed_seconds']=time.time()-record['finalization_started_unix']
 ns['atomic_json']('result.json',record)
 print(json.dumps({'status':record['status'],'receipt':str(OUT/'result.json'),'sha256':sha(OUT/'result.json')}))
except Exception as error:
 record['status']='FAILED_METADATA_FINALIZATION';record['error']=repr(error)
 ns['atomic_json']('result.json',record)
 raise
