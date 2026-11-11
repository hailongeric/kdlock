import base64,datetime,hashlib,json,os,pathlib,stat,struct,subprocess,sys,time
P=pathlib.Path; BASE=P('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04'); OUT=BASE/'receipts/return-normal6-api-private-01'; WORK=P('/mnt/kdlock-builds/kdlock-main-work'); PRIV=WORK/'kernel6-private-fixtures-80c272e5-01'
MODE=sys.argv[1] if len(sys.argv)>1 else os.environ['RETURN_MODE']
def require(ok,msg):
 if not ok: raise RuntimeError(msg)
def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(name,value):
 b=value if isinstance(value,bytes) else (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
 with open(OUT/name,'xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def load(p):return json.loads(P(p).read_bytes())
def run(argv):
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 require(r.returncode==0,'command '+repr(argv)+': '+r.stderr.decode(errors='replace'))
 return r.stdout
def tree(root):
 rows=[]
 for p in sorted(root.rglob('*')):
  s=p.lstat();require(not stat.S_ISLNK(s.st_mode),'symlink '+str(p))
  if stat.S_ISDIR(s.st_mode):continue
  require(stat.S_ISREG(s.st_mode),'nonregular '+str(p))
  rows.append(dict(name=str(p.relative_to(root)),size=s.st_size,mode=stat.S_IMODE(s.st_mode),sha256=digest(p)))
 return rows
def table_file(p):
 s=P(p).stat();return dict(path=str(p),size=s.st_size,mode=stat.S_IMODE(s.st_mode),sha256=digest(p))
def bid(data):
 off=0;ids=[]
 while off<len(data):
  require(off+12<=len(data),'notes header');n,d,k=struct.unpack_from('<III',data,off);a=off+12;b=a+((n+3)&~3);end=b+((d+3)&~3);require(end<=len(data),'notes extent')
  if k==3 and data[a:a+n]==b'GNU\0':ids.append(data[b:b+d].hex())
  off=end
 require(len(ids)==1,'one GNU ID');return ids[0]
def activity():
 rows=[];bad=[]
 for x in P('/proc').iterdir():
  if not x.name.isdigit():continue
  try:
   comm=(x/'comm').read_text().strip();ss=(x/'stat').read_text();state=ss[ss.rfind(')')+2:].split()[0]
   cmd=(x/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace');w=(x/'wchan').read_text().strip()
  except FileNotFoundError:continue
  r=dict(pid=int(x.name),comm=comm,state=state,wchan=w,args=cmd);rows.append(r)
  if state=='D' or comm in {'make','gcc','gcc-15','cc1','cc1plus','as','ld','ld.bfd','objtool','insmod','rmmod','mmap-userspace'} or comm.startswith(('kd-fixture','kd-scene','kd-reader','kd-rwapi')):bad.append(r)
 require(not bad,'active actor '+json.dumps(bad));return rows
try:
 if MODE=='pre':OUT.mkdir(parents=False,exist_ok=False)
 else:require(OUT.is_dir(),'missing pre output')
 notes=P('/sys/kernel/notes').read_bytes();identity=dict(boot=P('/proc/sys/kernel/random/boot_id').read_text().strip(),release=os.uname().release,machine=os.uname().machine,taint=int(P('/proc/sys/kernel/tainted').read_text()),build_id=bid(notes))
 save(MODE+'-notes.bin',notes);save(MODE+'-dmesg.txt',run(['dmesg']))
 processes=activity();modules=P('/proc/modules').read_text();names=[r.split()[0] for r in modules.splitlines()]
 require(not any(n.startswith(('kd_','kdlock')) for n in names),'experimental module')
 devices=[str(p) for p in P('/dev').iterdir() if p.name.startswith(('kd_','kdlock','kd-'))];require(not devices,'devices '+repr(devices))
 require(identity['machine']=='x86_64','machine')
 if MODE=='pre':require(identity==dict(boot='4400eea1-c8fc-40e1-b6b7-f7a99ecc1364',release='7.0.0-38-kdrebuild6',machine='x86_64',taint=12288,build_id='5ed6cd8cffed6960ce901261dfab3bb019a0442d'),'candidate identity');require(names==['nls_iso8859_1'],'candidate modules')
 else:require(identity['boot']!='4400eea1-c8fc-40e1-b6b7-f7a99ecc1364' and identity['release']=='7.0.0-38-kdlock1' and identity['taint']==0 and identity['build_id']=='b61c7bef25d2068f2a05ca3c31a5714c20c4aa62','normal identity')
 grub={str(p):table_file(p) for p in [P('/boot/grub/grub.cfg'),P('/boot/grub/custom.cfg')]}
 require(grub['/boot/grub/grub.cfg']['sha256']=='4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be','grub cfg')
 require(grub['/boot/grub/custom.cfg']['sha256']=='10704ea47ac50dfef89b9a0f2a6870f668bbaf7bb4935254d14f4c2dea829255','custom cfg')
 env=run(['grub-editenv','/boot/grub/grubenv','list']).decode();ev=dict(line.split('=',1) for line in env.splitlines() if '=' in line);require(not ev.get('next_entry') and not ev.get('prev_saved_entry'),'one-shot fields')
 default='gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdlock1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961';require(default in P('/boot/grub/grub.cfg').read_text(),'normal persistent default')
 final=BASE/'receipts/full-metadata-01/final-identity.json';require(digest(final)=='995255c9c14c513a356a70ba4155beac0879d37f3abd07ab7afb1fc328c0353b','final identity pin')
 core={}
 for name,row in load(final)['files'].items():
  p=BASE/'build'/name;require(p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],'core '+name);core[name]=row
 boots=[]
 for source in [BASE/'receipts/install-kdrebuild6-api-01/installed-boot.json',BASE/'receipts/postboot-kdrebuild6-api-01/normal-recovery-boot-unchanged.json',BASE/'receipts/postboot-kdrebuild6-api-01/prior-candidate-boot-unchanged.json']:
  for row in load(source)['files']:
   actual=table_file(row['path']);require(all(actual[k]==v for k,v in row.items() if k in actual),'boot '+row['path']);boots.append(actual)
 namespace=tree(P('/lib/modules/7.0.0-38-kdrebuild6'));require(namespace==load(BASE/'receipts/install-kdrebuild6-api-01/limited-stage.json')['namespace'],'candidate namespace')
 prereqs={}
 for label,path,sha in [('native',WORK/'kernel6-native-api-mm-live-01/result.json','1c97c7fdbd5f9667bd81f23894109cd837121a952e7de31cfedbb00bb4888add'),('rwsem',PRIV/'live-rwsem-receipts-01/result.json','3fa71f817e7720e0f1611dbb72745955a86f01cbe7af98d68640e57c7264a9d9'),('mutex',PRIV/'live-mutex-receipts-01/result.json','d4d81fb46982f090500cc4713c2477f129c2b78cc05bd89cc26f73e2f9401d6c')]:
  require(digest(path)==sha,'predecessor '+label);r=load(path)
  if label=='native':require(r['status']=='NATIVE_API_AND_MM_COMPLETE' and r['client_returncode']==0 and r['compat_driver_returncode']==0,'native complete')
  else:
   require(r['status']=='COMPLETE' and r['returncode']==0 and r['unloaded'] is True,'private complete '+label);require([w['operation'] for w in r['wire_tail']]==[9,10,11,6] and all(w['completed_response'] and w['status']==0 for w in r['wire_tail']),'wire tail '+label)
  prereqs[label]=dict(path=str(path),sha256=sha,status=r['status'])
 free={str(p):os.statvfs(p).f_bavail*os.statvfs(p).f_frsize for p in [P('/'),P('/mnt/kdlock-builds'),P('/mnt/kdlock-builds2')]};require(free['/']>=1073741824 and free['/mnt/kdlock-builds2']>=1073741824,'headroom')
 result=dict(status='RETURN_PRECONDITIONS_VERIFIED' if MODE=='pre' else 'NORMAL_IDENTITY_VERIFIED',returncode=0,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),identity=identity,modules=modules,devices=devices,processes=processes,grub=grub,grub_environment=env,normal_default=default,core=core,boot_files=boots,candidate_namespace=namespace,prerequisites=prereqs,available_bytes=free)
 if MODE=='post':
  before=load(OUT/'pre.json')
  for key in ['grub','grub_environment','normal_default','core','boot_files','candidate_namespace','prerequisites']:require(result[key]==before[key],'changed preserved '+key)
  result['pre_sha256']=digest(OUT/'pre.json')
 save(MODE+'.json',result);print(json.dumps(dict(status=result['status'],returncode=0,identity=identity,output=str(OUT),result_sha256=digest(OUT/(MODE+'.json')),available_bytes=free)))
except BaseException as e:
 if OUT.is_dir():
  p=OUT/(MODE+'-error.json')
  if not p.exists():save(p.name,dict(error=repr(e),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 raise
