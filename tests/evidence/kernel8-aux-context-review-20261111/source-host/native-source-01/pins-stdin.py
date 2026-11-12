from pathlib import Path
import hashlib,json,os,runpy,stat,time
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');helper=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/transport/build.py')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
assert digest(helper)=='56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb'
ns=runpy.run_path(str(helper));bp,built=ns['checked_json'](root/'receipts/full-01/result.json','024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5');fp,focused=ns['checked_json'](built['focused_receipt'],built['focused_sha256']);ip,linked=ns['checked_json'](bp.parent/'final-identity.json',built['final_identity_sha256'])
pins={n:r['sha256'] for n,r in linked['files'].items()};actual=ns['pins'](root/'build',pins);source_pins=ns['source_pins'](focused,root/'source');protected=ns['protected'](focused)
assert len(actual)==16 and source_pins==built['source_after'] and protected==built['protected_after']
source_package=focused['package_after'];assert len(source_package)==78
rows={};total=0
for name in ['arch/x86/kernel/irq_64.c', 'arch/x86/kernel/stacktrace.c', 'arch/x86/kernel/unwind_orc.c', 'arch/x86/kernel/process_64.c', 'arch/x86/include/asm/irq_stack.h', 'arch/x86/include/asm/switch_to.h', 'arch/x86/include/asm/processor.h', 'arch/x86/include/asm/stacktrace.h', 'kernel/sched/core.c', 'kernel/entry/common.c']+['build/.config']:
 p=(root/'source'/name) if name!='build/.config' else root/'build/.config';before=p.lstat();assert stat.S_ISREG(before.st_mode) and p.resolve(strict=True)==p and before.st_size<=2*1024**2
 sha=digest(p);after=p.lstat();identity=lambda s:[s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
 assert identity(before)==identity(after);total+=before.st_size;rows['source/'+name if name!='build/.config' else name]={'path':str(p),'bytes':before.st_size,'sha256':sha,'identity':identity(before)}
assert total<=4*1024**2
print(json.dumps({'status':'AUX_SOURCE_PINS_VERIFIED','captured_unix':time.time(),'kernel_source':str(root/'source'),'kernel_build':str(root/'build'),'kernel_core_git_head':ns['CORE'],'full_receipt_sha256':digest(bp),'focused_receipt_sha256':digest(fp),'final_identity_sha256':digest(ip),'build_pins':actual,'source_pins':source_pins,'protected':protected,'package78':source_package,'selected':rows,'selected_bytes':total,'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':int(Path('/proc/sys/kernel/tainted').read_text())},sort_keys=True))
