from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01');kernel=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def facts(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
def need(v,m):
 if not v:raise RuntimeError(m)
def text(p,limit):
 with p.open('rb') as f:b=f.read(limit+1)
 need(len(b)<=limit,'read extent '+str(p));return b.decode()
old=base/'transport/build.py';native_path=base/'native-api-input-01/controller.py';ctl=base/'managed-killable-input-04/controller.py';receipt=base/'managed-killable-receipts-04/result.json'
need(digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and digest(native_path)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074','reviewed helpers differ')
need(digest(ctl)=='d760565b7ca37b1ed5cd3a8404ca8e4448e4203050e9007e467737bd1ee6789d' and digest(receipt)=='d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488','closed K04 differs')
ns=runpy.run_path(str(old));native=runpy.run_path(str(native_path));controller=runpy.run_path(str(ctl));saved=json.loads(receipt.read_text());before=controller['idle'](native)
need(before['identity']=={'boot':'2ae5991e-d024-48ac-9f86-24a0a8910172','release':'7.0.0-38-kdrebuild8','taint':4096},'current exact candidate identity differs')
need(native['running_notes']()[1]=='a33dd4d11d0f0c6649107507e685b6e86e716c1a','running Build ID differs')
bp,built=ns['checked_json'](kernel/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5');fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256']);ip,linked=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
pins={name:row['sha256'] for name,row in linked['files'].items()};need(len(pins)==16 and ns['pins'](kernel/'build',pins),'linked16 differ')
need(ns['protected'](focused)==built['protected_after'] and ns['source_pins'](focused,kernel/'source')==built['source_after'],'protected source/output differ')
boot=ns['boot_files']();need({k:v for k,v in boot.items() if k!='/boot/grub/grubenv'}=={k:v for k,v in saved['boot_before'].items() if k!='/boot/grub/grubenv'},'non-environment boot/GRUB namespaces differ from K04')
config=text(kernel/'build/.config',1024*1024).splitlines();config_selected=[line for line in config if any(t in line for t in ('CONFIG_KDLOCK','CONFIG_PREEMPT_RT','CONFIG_DEBUG_MUTEXES','CONFIG_DEBUG_LOCK_ALLOC','CONFIG_LOCKDEP','CONFIG_PREEMPT_DYNAMIC','CONFIG_MODULE_SIG_'))]
need('CONFIG_KDLOCK_REBUILD=y' in config and '# CONFIG_PREEMPT_RT is not set' in config and 'CONFIG_KDLOCK_MMAP=y' not in config and 'CONFIG_KDLOCK_MMAP=m' not in config,'rebuild/nonRT/legacy-MM config differs')
installed=[]
for prefix,name in [('vmlinuz-','arch/x86/boot/bzImage'),('System.map-','System.map'),('config-','.config')]:
 row=facts(Path('/boot')/(prefix+'7.0.0-38-kdrebuild8'));need(row['bytes']==linked['files'][name]['bytes'] and row['sha256']==pins[name],'installed candidate file differs');installed.append(row)
row=facts(Path('/boot/initrd.img-7.0.0-38-kdrebuild8'));need(row['sha256']=='188febc028a662326553252d4973dd3869250434c9e4202d55e543242c9e58a2','candidate initrd differs');installed.append(row)
menu=text(Path('/boot/grub/grub.cfg'),2*1024*1024);custom=text(Path('/boot/grub/custom.cfg'),2*1024*1024);default=text(Path('/etc/default/grub'),65536)
need("'kdlock-kdrebuild8-api-01'" in custom or 'kdlock-kdrebuild8-api-01' in custom,'candidate custom menu entry absent')
need(digest(Path('/boot/grub/grub.cfg'))=='4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be','actual generated menu differs')
r=subprocess.run(['/usr/bin/grub-editenv','/boot/grub/grubenv','list'],capture_output=True,text=True,timeout=10);need(r.returncode==0 and len(r.stdout)<65536 and not r.stderr,'bounded GRUB environment read failed')
need(not any(line.startswith('next_entry=') and line!='next_entry=' for line in r.stdout.splitlines()),'unconsumed one-shot entry remains')
pp,prior=ns['checked_json'](base/'build-01/receipts/result.json','223392b879bd1aaad6ffc3e40f322706be8bd94039abd0a50c16afe238ffa37c');client=prior['client'];need(facts(Path(client['path']))==client,'existing client bytes differ')
client_commands=[row for row in prior['commands'] if any('mmap-userspace' in str(v) or 'userspace.c' in str(v) for v in row.get('argv',[]))]
provider_path=base/'mm-provider-ioctl-build-0798c1ab-01/receipts/result.json';need(digest(provider_path)=='73f57b2690b98c442160b576b757429a0090674f75f6eeafb60d7499ac473052','closed provider receipt differs');provider=json.loads(provider_path.read_text());provider_module=provider['modules']['mmap'];need(facts(Path(provider_module['signed']['path']))==provider_module['signed'] and facts(Path(provider_module['unsigned']['path']))==provider_module['unsigned'],'built provider bytes differ')
source_files=json.loads((base/'transport/source-sha256.json').read_text());client_sources={name:row for name,row in source_files.items() if name.startswith('tests/kernel/mmap_api/') and (name.endswith('userspace.c') or name.endswith('abi.h'))}
exports={};wanted={'kd_linux_rwsem_bind','kd_linux_rwsem_unbind','kd_linux_rwsem_binding_init','kd_task_setup_managed_mm','kd_task_lifecycle_enter'}
for line in (kernel/'build/System.map').open():
 row=line.split()
 if len(row)==3 and (row[2] in wanted or (row[2].startswith('kd_linux_rwsem') and len(exports)<32)):exports[row[2]]=row[0]
need(not (Path('/sys/module/kd_mmap_api_provider')).exists(),'provider loaded')
frozen=base/'mm-provider-ioctl-build-0798c1ab-01/input'
frozen_manifest=base/'mm-provider-ioctl-input-0798c1ab-01/source-sha256.json'
need(digest(frozen_manifest)=='a29e77397367173e51ae091edec94f31798d50f5b9d3b6b90ce31dda0e3b823e','frozen0798 manifest differs')
fm=json.loads(frozen_manifest.read_text());need(len(fm)==143,'frozen0798 manifest membership differs')
for name,row in fm.items():
 need(facts(frozen/name)['bytes']==row['bytes'] and digest(frozen/name)==row['sha256'],'frozen0798 input differs: '+name)
need({str(q.relative_to(frozen)) for q in frozen.rglob('*') if q.is_file()}==set(fm),'frozen0798 extra/missing members')
after=controller['idle'](native);need(after==before,'idle identity/module state changed during capture')
print(json.dumps({'status':'MM_READ_ONLY_PREFLIGHT_COMPLETE','idle':after,'running_build_id':native['running_notes']()[1],'config_selected':config_selected,'kernel_core_git_head':ns['CORE'],'linked_outputs':len(pins),'kernel_source_files':len(focused['package_after']),'protected_source_output_unchanged':True,'boot_files':boot,'installed_candidate':installed,'grub':{'config':facts(Path('/boot/grub/grub.cfg')),'custom':facts(Path('/boot/grub/custom.cfg')),'default':default,'environment':r.stdout,'candidate_entry':'kdlock-kdrebuild8-api-01'},'prior_build':{'path':str(pp),'sha256':digest(pp),'status':prior['status'],'source_git_head':prior['source_git_head']},'client':client,'client_build_commands':client_commands,'client_sources':client_sources,'metadata_provider':{'receipt':str(provider_path),'sha256':digest(provider_path),'source_git_head':provider['source_git_head'],'status':provider['status'],'module':provider_module,'loaded':False},'generic_rwsem_symbols':exports,'k04_preserved':facts(receipt),'k03_failure_preserved':facts(base/'managed-killable-live-03/result.json'),'k03_cleanup_preserved':facts(base/'recovery-killable-final-01/result.json'),'free':{'root':ns['available']('/'),'builds2':ns['available'](base)},'captured_unix':time.time()},sort_keys=True))
