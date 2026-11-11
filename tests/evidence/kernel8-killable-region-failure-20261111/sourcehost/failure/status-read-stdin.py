from pathlib import Path
import base64,hashlib,json,os,struct
name='kd_rwsem_killable_fixture';result={}
fd=os.open('/dev/'+name+'_ctl',os.O_RDONLY|os.O_CLOEXEC)
try:raw=os.pread(fd,8192,0)
finally:os.close(fd)
result['status_bytes']=base64.b64encode(raw).decode();result['status_sha256']=hashlib.sha256(raw).hexdigest();result['status']=json.loads(raw)
fd=os.open('/dev/'+name+'_events',os.O_RDONLY|os.O_CLOEXEC)
try:raw=os.pread(fd,40,0)
finally:os.close(fd)
assert len(raw)==40;result['header_hex']=raw.hex();result['header_words']=struct.unpack('<5Q',raw)
symbols={'fixture_killable_body','fixture_writer_body','fixture_source_step'};matched=[]
with Path('/proc/kallsyms').open() as stream:
 for index,line in enumerate(stream):
  assert index<2000000
  words=line.split()
  if len(words)==4 and words[2] in symbols and words[3]=='['+name+']':matched.append(line)
assert len(matched)==3;result['kallsyms_raw']=''.join(matched);result['kallsyms_sha256']=hashlib.sha256(result['kallsyms_raw'].encode()).hexdigest()
result['actors']=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  comm=(p/'comm').read_text().strip();argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if int(p.name)==5412 or 'tests/kernel/rwsem_killable/runner.py' in argv or comm.startswith('kd-kill'):
   result['actors'].append({'pid':int(p.name),'comm':comm,'argv':argv,'status':(p/'status').read_text(),'wchan':(p/'wchan').read_text(),'fd_targets':{x.name:os.readlink(x) for x in (p/'fd').iterdir()}})
 except (FileNotFoundError,ProcessLookupError):continue
result['boot']=Path('/proc/sys/kernel/random/boot_id').read_text().strip();result['release']=os.uname().release;result['taint']=Path('/proc/sys/kernel/tainted').read_text().strip();result['modules']=Path('/proc/modules').read_text()
print(json.dumps(result))
