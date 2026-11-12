from pathlib import Path
import base64,hashlib,json,os,runpy,stat,time
kernel=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01');started=time.monotonic()
def need(v,m):
 if not v:raise RuntimeError(m)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def facts(p,limit):
 before=p.lstat();need(p.resolve(strict=True)==p and stat.S_ISREG(before.st_mode) and before.st_size<=limit,'strict regular/canonical extent differs: '+str(p));sha=digest(p);after=p.lstat();ident=lambda s:[s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns];need(ident(before)==ident(after),'input changed during hash');return {'path':str(p),'bytes':before.st_size,'sha256':sha,'identity':ident(before)}
def checked(p,expected):
 need(digest(p)==expected,'pinned receipt differs: '+str(p));return json.loads(p.read_bytes())
old=base/'transport/build.py';native_path=base/'native-api-input-01/controller.py';ctl_path=base/'mm-provider-ioctl-input-0798c1ab-01/controller.py'
need(digest(old)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb' and digest(native_path)=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074' and digest(ctl_path)=='6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136','reviewed metadata helpers differ')
ns=runpy.run_path(str(old));native=runpy.run_path(str(native_path));ctl=runpy.run_path(str(ctl_path));recipe=checked(base/'mm-provider-ioctl-input-0798c1ab-01/recipe.json','ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7');provider=checked(base/'mm-provider-ioctl-build-0798c1ab-01/receipts/result.json','73f57b2690b98c442160b576b757429a0090674f75f6eeafb60d7499ac473052');before_idle=ctl['idle'](native,recipe);need(native['running_notes']()[1]==recipe['build_id'],'running BID differs')
built=checked(kernel/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5');focused=checked(Path(built['focused_receipt']),built['focused_sha256']);linked=checked(kernel/'receipts/full-01/final-identity.json',built['final_identity_sha256']);pins={n:r['sha256'] for n,r in linked['files'].items()}
def preserved():
 rows={'linked16':ns['pins'](kernel/'build',pins),'source':ns['source_pins'](focused,kernel/'source'),'protected':ns['protected'](focused),'boot':ns['boot_files']()};need(len(rows['linked16'])==16 and len(focused['package_after'])==78 and rows['source']==built['source_after'] and rows['protected']==built['protected_after'] and rows['boot']==provider['boot_before'],'kernel/source/boot/protected pins differ');return rows
before_pins=preserved();source_names=['kernel/sched/Makefile','kernel/sched/build_policy.c','kernel/sched/build_utility.c'];before_sources={};data={};total=0
for name in source_names:
 path=kernel/'source'/name
 if not os.path.lexists(path):before_sources[name]={'exists':False,'path':str(path)};continue
 row=facts(path,65536);raw=path.read_bytes();need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'source changed during read');total+=len(raw);before_sources[name]={'exists':True,**row};data[name]=base64.b64encode(raw).decode()
need(total<=256*1024,'source total exceeds256KiB')
folder=kernel/'build/kernel/sched';need(folder.resolve(strict=True)==folder and stat.S_ISDIR(folder.lstat().st_mode),'scheduler build directory differs')
def objects():
 paths=sorted(p for p in folder.iterdir() if p.suffix=='.o');need(len(paths)<=128,'regular object count exceeds128');rows={};total=0
 for path in paths:
  row=facts(path,32*1024**2);total+=row['bytes'];need(total<=256*1024**2,'object hash input exceeds256MiB');rows[path.name]=row
 return rows
before_objects=objects();after_sources={}
for name in source_names:
 path=kernel/'source'/name
 after_sources[name]={'exists':True,**facts(path,65536)} if os.path.lexists(path) else {'exists':False,'path':str(path)}
after_objects=objects();after_pins=preserved();after_idle=ctl['idle'](native,recipe);need(before_sources==after_sources and before_objects==after_objects and before_pins==after_pins and before_idle==after_idle,'discovery input/pin/idle changed');need(time.monotonic()-started<=60,'discovery elapsed bound exceeded')
print(json.dumps({'status':'SCHEDULER_BUILD_DISCOVERY_COMPLETE','sources_before':before_sources,'sources_after':after_sources,'source_data_base64':data,'source_bytes':total,'objects_before':before_objects,'objects_after':after_objects,'pins_before':before_pins,'pins_after':after_pins,'package78':focused['package_after'],'identity_before':before_idle,'identity_after':after_idle,'build_id':native['running_notes']()[1],'elapsed_seconds':time.monotonic()-started,'scope':'Read-only exact scheduler source and actual existing regular object filenames; no alias chosen or object built.'},sort_keys=True))
