from pathlib import Path
import hashlib,io,json,os,stat,subprocess,tarfile
root=Path('/home/eric/vm/vm-shared/kdlock-main')
prior=Path('/tmp/kdlock-kernel8-fixture-source-5c14b483-01')
out=Path('/tmp/kdlock-kernel8-fixture-source-0798c1ab-01')
head='0798c1abf422017cfc93647a2649be0e5a73c75a'
core_head='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
sha=lambda b:hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
def document(path,value):
    data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    return data
assert git('rev-parse','HEAD')==head and git('status','--short')==''
old_bytes=(prior/'source-sha256.json').read_bytes()
assert sha(old_bytes)=='6a14d26236343e37ae43a30c6e441783f979299b426c0a7b9fbbca9154f09645'
old=json.loads(old_bytes);assert len(old)==143
package_path=Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json')
package_bytes=package_path.read_bytes();package=json.loads(package_bytes)
assert sha(package_bytes)=='c7d1afa19ab56c0fa8bf21f0232bf1c8199751407a44e918a4b8c5c133966da9'
assert package['core_git_head']==core_head and package['code_file_count']==len(package['files'])==78
files={};data={};identities={};changed=[]
for name in sorted(old):
    p=root/name;s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
    before=(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    b=p.read_bytes();a=p.lstat();after=(a.st_dev,a.st_ino,a.st_mode,a.st_nlink,a.st_size,a.st_mtime_ns,a.st_ctime_ns)
    assert before==after and len(b)==s.st_size
    files[name]={'bytes':len(b),'sha256':sha(b)};data[name]=b;identities[name]=before
    if files[name]!=old[name]:changed.append(name)
expected=sorted(set(git('diff','--name-only','5c14b483ca16b3bba8f3dd40a00f16a6efefc12c',head).splitlines()) & set(old))
assert changed==expected
assert all(files[name]['sha256']==value for name,value in package['files'].items())
assert git('rev-parse','HEAD')==head and git('status','--short')=='' and not out.exists()
out.mkdir(mode=0o700)
archive=out/'source.tar'
with tarfile.open(archive,'x',format=tarfile.USTAR_FORMAT) as t:
    for name in sorted(files):
        s=(root/name).stat();item=tarfile.TarInfo(name);item.size=len(data[name]);item.mode=stat.S_IMODE(s.st_mode)
        item.uid=item.gid=0;item.uname=item.gname='';item.mtime=int(s.st_mtime);t.addfile(item,io.BytesIO(data[name]))
with archive.open('rb') as f:os.fsync(f.fileno())
manifest=document(out/'source-sha256.json',files)
state=document(out/'source-state.json',{'files':143,'git_status':'','source_git_head':head,'transfer_bytes':sum(x['bytes'] for x in files.values())})
with tarfile.open(archive,'r:') as t:
    members=t.getmembers();assert len(members)==143 and len({m.name for m in members})==143 and {m.name for m in members}==set(files)
    for m in members:
        assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
        b=t.extractfile(m).read();assert len(b)==files[m.name]['bytes'] and sha(b)==files[m.name]['sha256']
for name,b in data.items():
    s=(root/name).lstat();assert identities[name]==(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert (root/name).read_bytes()==b
assert git('rev-parse','HEAD')==head and git('status','--short')==''
transport={name:{'bytes':(out/name).stat().st_size,'sha256':sha((out/name).read_bytes())} for name in ('source.tar','source-sha256.json','source-state.json')}
receipt={'format':'kdlock.regular-only-host-export.v1','source_git_head':head,'git_status':'','prior_source_git_head':'5c14b483ca16b3bba8f3dd40a00f16a6efefc12c','prior_manifest_sha256':sha(old_bytes),'changed_from_5c14b483':changed,'new_members':[],'files':143,'transfer_bytes':sum(x['bytes'] for x in files.values()),'kernel_core_git_head':core_head,'kernel_package_files':78,'kernel_package_sha256':sha(package_bytes),'transport':transport,'scope':'Source-only cold ioctl request backing and maintained evidence wording. Same regular member set; no test, module build, runtime or MM result is claimed.'}
document(out/'export-receipt.json',receipt)
fd=os.open(out,os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
print(json.dumps({'status':'SOURCE_EXPORT_CLOSED','path':str(out),**receipt},sort_keys=True))
