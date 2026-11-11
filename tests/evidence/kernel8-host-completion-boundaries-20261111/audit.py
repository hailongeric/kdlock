"""Offline standard-library receipt/archive audit; no project code executes."""
from pathlib import Path,PurePosixPath
import base64,gzip,hashlib,io,json,re,stat,sys,tarfile


def require(value,message):
 if not value:raise ValueError(message)


def digest(data):return hashlib.sha256(data).hexdigest()


def audit(root):
 root=Path(root);index=json.loads((root/'origin-index.json').read_bytes());rows=index['files'];by={r['logical_path']:r for r in rows}
 require(len(by)==len(rows)==index['count']==221,'origin count differs')
 for r in rows:
  name=PurePosixPath(r['logical_path']);stored=PurePosixPath(r['stored_path'])
  require(not name.is_absolute() and '..' not in name.parts and not stored.is_absolute() and '..' not in stored.parts,'unsafe copy path')
  p=root/r['stored_path'];require(stat.S_ISREG(p.lstat().st_mode),'nonregular stored member')
  data=p.read_bytes();require(len(data)==r['stored_bytes'] and digest(data)==r['stored_sha256'],'stored bytes differ')
  raw=gzip.decompress(data) if r['encoding']=='gzip' else data
  require(len(raw)==r['raw_bytes'] and digest(raw)==r['raw_sha256'],'raw readback differs')
 def read(name):
  r=by[name];data=(root/r['stored_path']).read_bytes();return gzip.decompress(data) if r['encoding']=='gzip' else data
 def load(name):return json.loads(read(name))
 def archive(name,expected):
  data=read(name)
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as source:
   members=source.getmembers();require(len(members)==len(expected) and len({m.name for m in members})==len(members),'archive membership differs')
   for member in members:
    pure=PurePosixPath(member.name)
    require(member.isfile() and not pure.is_absolute() and '..' not in pure.parts and str(pure)==member.name and member.name in expected,
            'unsafe, unexpected or nonregular tar member')
    raw=source.extractfile(member).read();wanted=expected[member.name]
    require(len(raw)==wanted['bytes'] and digest(raw)==wanted['sha256'],'tar member differs')
   end=max((m.offset_data+((m.size+511)//512)*512 for m in members),default=0)
   require(not any(data[end:]),'nonzero trailing tar data')
  return len(members)
 prefix='completion/collection/'
 guest=load(prefix+'copy-index.json');before=load(prefix+'.collection/inventory-before.json');after=load(prefix+'.collection/inventory-after.json')
 require(digest(read(prefix+'copy-index.json'))=='c22b6db9bc7fe7a7b10c9c52a08abab593976e82485f79e23eab8108edc52eb9','first collection index differs')
 require(guest['count']==len(guest['files'])==before['count']==after['count']==155 and guest['bytes']==before['bytes']==after['bytes']==3426990,
         'complete first guest collection extent differs')
 require(before['files']==after['files'] and before['directories']==after['directories'],'guest identities changed')
 expected={}
 for r in guest['files']:
  require(r['name'] not in expected and r['path']=='payload/'+r['name'],'guest path repeated or differs')
  require(len(read(prefix+r['path']))==r['bytes'] and digest(read(prefix+r['path']))==r['sha256'],'guest payload differs')
  require(before['files'][r['name']]=={'bytes':r['bytes'],'sha256':r['sha256'],'identity':r['identity'],'path':r['guest_path']},'guest copy identity differs')
  expected[r['name']]={'bytes':r['bytes'],'sha256':r['sha256']}
 complete=load(prefix+'collection.json')
 require(complete['status']=='COMPLETE' and digest(read(prefix+'.collection/copy.tar'))==complete['archive_sha256'],'raw first transport differs')
 archive(prefix+'.collection/copy.tar',expected)
 batches=[]
 spec=(('completion','completion/collection/payload/checks/receipts/',
        'completion/collection/payload/input/','b2ef338b1a3ee9de89f67e98392fbea9e275bbd9',142,
        'HOST_COMPLETION_CHECKS_COMPLETE',{'changed_mm_runner_ast':1,'completion_cases':12,'completion_skips':0}),
       ('context','context/sourcehost/completed/','context/source-export/',
        'a99186a53568514da850bae6495f0542de7650b7',143,
        'HOST_CONTEXT_BOUNDARY_CHECKS_COMPLETE',{'changed_killable_runner_ast':1,'source_boundary_cases':9,'source_boundary_skips':0}))
 reference=None
 for label,receipts,source,head,count,status,checks in spec:
  result=load(receipts+'result.json');state=load(source+'source-state.json');manifest=load(source+'source-sha256.json');export=load(source+'export-receipt.json')
  require(result['status']==status and result['source_git_head']==head and result['checks']==checks and len(result['commands'])==2,'check status/source/count differs')
  require(state['source_git_head']==head and state['files']==count==len(manifest) and state['git_status']=='' and
          state['transfer_bytes']==sum(r['bytes'] for r in manifest.values()),'snapshot state differs')
  require(export['source_git_head']==head and export['files']==count and export['kernel_package_files']==78,'export source/core extent differs')
  require(result['compiled_module_source_git_head']=='140aecc4f83a6b6ae6f20245234e8a63504f9210' and
          result['kernel_core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f' and len(result['core_pins_before'])==16,'compiled epoch/pins differ')
  for name,row in export['transport'].items():
   require(len(read(source+name))==row['bytes'] and digest(read(source+name))==row['sha256'],'export transport differs')
  archive(source+'source.tar',manifest)
  if label=='completion':
   for name,wanted in manifest.items():
    raw=read('completion/collection/payload/checks/input/'+name)
    require(len(raw)==wanted['bytes'] and digest(raw)==wanted['sha256'],'first retained input differs from archive/manifest')
  for command in result['commands']:
   log=read(receipts+command['label']+'.log')
   require(command['returncode']==0 and digest(log)==command['log_sha256'],'actual check command/log differs')
   if command['label'] in ('completion-checker-twelve','source-boundary-nine'):
    n=12 if label=='completion' else 9;text=log.decode('utf-8')
    require(len(re.findall(r'(?m)^Ran '+str(n)+r' tests in .+s$',text))==1 and '\nOK\n' in text and
            'skipped' not in text and 'FAILED (' not in text,'test count/skips/outcome differs')
  for name in ('identity_before','identity_after'):
   v=result[name];require(v['identity']=={'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096}
                         and not v['activity'] and [line.split()[0] for line in v['modules'].splitlines()]==['nls_iso8859_1'],'boot/module/idle check differs')
  require(reference is None or result['core_pins_before']==reference,'linked kernel pins differ across batches')
  reference=result['core_pins_before']
  batches.append({'batch':label,'status':status,'source_git_head':head,'source_files':count,'source_transfer_bytes':state['transfer_bytes'],
                  'source_archive_sha256':digest(read(source+'source.tar')),'manifest_sha256':digest(read(source+'source-sha256.json')),
                  'result_sha256':digest(read(receipts+'result.json')),'checks':checks,'commands':[(r['label'],r['returncode']) for r in result['commands']]})
 require(batches[0]['result_sha256']=='976c0acca562fe01f396cc6dbec006c6677f2bb3ae3cc0e4b81c100234011e22' and
         batches[1]['result_sha256']=='e4f76bb7ba3f50a4fcb8da57c1a3c478cb3c4dae748dd3bb546a48f05a674f6a','actual check receipt pins differ')
 context_index=load('context/sourcehost/read-index.json');pulled=load('context/sourcehost/read.stdout')
 require(set(context_index)==set(pulled)=={'result.json','source-boundary-nine.log','changed-killable-runner-ast.log'},'second copied guest subset differs')
 for name,row in context_index.items():
  raw=read('context/sourcehost/completed/'+name);require(len(raw)==row['bytes'] and digest(raw)==row['sha256'] and
    base64.b64decode(pulled[name]['data'],validate=True)==raw and pulled[name]['sha256']==row['sha256'],'second read envelope differs')
 refused=load('completion/collection/payload/input/export-receipt.json')['prior_host_export_refusal']
 require('omitted two reviewed README changes' in refused['reason'],'source export refusal metadata differs')
 require(read('completion/refused-export-01/source.tar')==read('completion/collection/payload/input/source.tar'),'refused tar differs from later retained source')
 return {'status':'OFFLINE_SAVED_RECEIPTS_VERIFIED','scope':'Synthetic checker and boundary unit outcomes plus syntax only. No live MM/JIT/context or performance proof.',
  'copies':{'count':index['count'],'raw_bytes':index['raw_bytes'],'stored_bytes':index['stored_bytes'],'gzip_files':sum(r['encoding']=='gzip' for r in rows)},
  'first_complete_guest_collection':{'files':155,'bytes':3426990,'raw_tar_members':155},
  'second_explicit_guest_reads':{'files':3,'bytes':sum(r['bytes'] for r in context_index.values()),'index':context_index},
  'batches':batches,'preserved_source_export_refusal':refused,
  'limits':['No second full guest collection is claimed; its three verified read copies and full source-host snapshot/controls are retained.',
            'The refusal reason is recorded by the accepted export receipt. Only the original refused source.tar remains in its source directory.',
            'Compiled modules remain fixture140; no kernel/module/workload build, load or live execution occurs in these check batches.']}


if __name__=='__main__':
 print(json.dumps(audit(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent),indent=2,sort_keys=True))
