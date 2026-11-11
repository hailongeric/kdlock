from pathlib import Path
import base64,hashlib,json,os,stat,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');source=base/'source';elf=base/'build/vmlinux';symbols={'__rcu_read_lock': {'start': 18446744071584509744, 'bytes': 42}, '__rcu_read_unlock': {'start': 18446744071584546496, 'bytes': 60}, 'vm_mmap_pgoff': {'start': 18446744071587165008, 'bytes': 804}, 'unmap_page_range': {'start': 18446744071587356768, 'bytes': 7090}, 'unmap_vmas': {'start': 18446744071587364176, 'bytes': 373}, 'do_mmap': {'start': 18446744071587439040, 'bytes': 1656}, '__pte_offset_map': {'start': 18446744071587500576, 'bytes': 295}, 'pte_offset_map_lock': {'start': 18446744071587501296, 'bytes': 284}, 'unmap_region': {'start': 18446744071587586176, 'bytes': 269}, '__vm_munmap': {'start': 18446744071587606064, 'bytes': 746}, '_raw_spin_lock': {'start': 18446744071603408112, 'bytes': 92}, '_raw_spin_unlock': {'start': 18446744071603408544, 'bytes': 61}};files=['include/linux/pgtable.h', 'include/linux/spinlock_api_smp.h', 'include/linux/spinlock.h', 'include/linux/preempt.h', 'include/linux/rcupdate.h', 'arch/x86/include/asm/pgtable.h', 'arch/x86/include/asm/tlbflush.h', 'mm/pgtable-generic.c'];tool={'alias': '/usr/bin/objdump', 'resolved': '/usr/bin/x86_64-linux-gnu-objdump', 'bytes': 415760, 'sha256': '44f07f8da860b15bd4dec909f229dec536595fb170a616fe3ab29c7b21c9736f'}
assert os.uname().release=='7.0.0-38-kdrebuild8' and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0'
def sha(q):
 h=hashlib.sha256()
 with q.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def signature(s):return [s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
a=elf.stat();assert sha(elf)=='4441e45c27f9300a4cd19739c917458308581472604c3b75d8ffba9fec493be1'
exe=Path(tool['alias']);assert str(exe.resolve(strict=True))==tool['resolved'] and sha(exe.resolve())==tool['sha256']
v={'source':str(source),'elf':str(elf),'elf_sha256':sha(elf),'build_id':'a33dd4d11d0f0c6649107507e685b6e86e716c1a','source_files':{},'disassembly':{},'tool':tool,'scope':'Read-only retained source and linked ELF disassembly; no runtime instruction execution, admission or context equivalence proof.'}
total=0
for n in files:
 q=source/n;before=q.lstat();assert q.resolve(strict=True)==q and stat.S_ISREG(before.st_mode) and before.st_size<=1048576
 raw=q.read_bytes();after=q.lstat();assert signature(before)==signature(after);total+=len(raw);assert total<=4194304
 v['source_files'][n]={'path':str(q),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity_before':signature(before),'identity_after':signature(after),'data':base64.b64encode(raw).decode()}
for n,row in symbols.items():
 assert 0<row['bytes']<=8192
 args=[str(exe),'-d','-Mintel','--start-address='+hex(row['start']),'--stop-address='+hex(row['start']+row['bytes']),str(elf)]
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10);assert r.returncode==0 and len(r.stdout)<=262144 and len(r.stderr)<=262144
 total+=len(r.stdout)+len(r.stderr);assert total<=6291456
 v['disassembly'][n]={'argv':args,'returncode':r.returncode,'start':hex(row['start']),'bytes':row['bytes'],'stdout_bytes':len(r.stdout),'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stdout':base64.b64encode(r.stdout).decode(),'stderr':base64.b64encode(r.stderr).decode()}
assert signature(elf.stat())==signature(a) and sha(elf)==v['elf_sha256'];v['elf_identity_before']=signature(a);v['elf_identity_after']=signature(elf.stat());v['source_file_count']=len(files);v['symbol_count']=len(symbols);v['payload_bytes']=total;print(json.dumps(v))
