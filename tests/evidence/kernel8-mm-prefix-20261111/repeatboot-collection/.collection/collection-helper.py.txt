#!/usr/bin/env python3
"""Read completed named guest receipts and retain exact source-host copies.

Adapted from tests/evidence/kernel-build4-20261111/collection-helper.py.
Run only after the controller closes the relevant immutable receipt window.
Every resource bound and selected guest path is supplied by the caller.
Example bounds: --max-files 10240 --max-paths 40960 --max-total-bytes 268435456
--max-file-bytes 50331648 --max-metadata-bytes 16777216. All output is retained
on failure. The remote program only opens and reads the selected files.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import time

SSH = ['ssh', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
       'root@10.176.26.71', 'python3 -']


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relative_name(name):
    parts = PurePosixPath(name).parts
    require(isinstance(name, str) and name and not name.startswith('/')
            and '\\' not in name and '\0' not in name
            and parts and all(part not in ('', '.', '..') for part in parts)
            and '/'.join(parts) == name, 'noncanonical relative member: ' + repr(name))
    return name


def absolute_name(name):
    value = PurePosixPath(name)
    require(value.is_absolute() and str(value) == name and '..' not in value.parts
            and '\0' not in name, 'canonical absolute guest path required')
    return name


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def document(path, value):
    write(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def json_unique(data):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate JSON member')
            value[key] = item
        return value
    return json.loads(data, object_pairs_hook=pairs)


# Guest paths and counts are JSON data in the encoded CONFIG. They never enter
# the SSH command text, which stays the fixed literal `python3 -`.
REMOTE = r'''import base64,hashlib,json,os,pathlib,signal,stat,sys,tarfile,io,time
C=json.loads(base64.b64decode(CONFIG))
signal.alarm(C['seconds'])
def need(value,message):
 if not value:raise RuntimeError(message)
def ident(s):
 return [s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def regular(name,expected=None):
 p=pathlib.Path(name);before=p.lstat()
 need(p.resolve(strict=True)==p and stat.S_ISREG(before.st_mode),'nonregular/canonical file: '+name)
 need(before.st_size<=C['max_file_bytes'],'per-file byte bound: '+name)
 if expected is not None:need(ident(before)==expected['identity'],'file identity before copy: '+name)
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 h=hashlib.sha256();data=bytearray();count=0
 with os.fdopen(fd,'rb') as f:
  need(ident(os.fstat(f.fileno()))==ident(before),'opened file identity: '+name)
  while True:
   block=f.read(min(1048576,C['max_file_bytes']+1-count))
   if not block:break
   count+=len(block);need(count<=C['max_file_bytes'],'growing file exceeds bound')
   h.update(block)
   if C['operation']=='copy':data.extend(block)
  need(ident(os.fstat(f.fileno()))==ident(before),'file changed during read: '+name)
 need(ident(p.lstat())==ident(before),'file changed after read: '+name)
 row=dict(path=name,bytes=count,sha256=h.hexdigest(),identity=ident(before))
 need(count==before.st_size,'file length changed: '+name)
 if expected is not None:need(row==expected,'file bytes differ from inventory: '+name)
 return row,bytes(data)
def directory(name):
 p=pathlib.Path(name);s=p.lstat()
 need(p.resolve(strict=True)==p and stat.S_ISDIR(s.st_mode),'noncanonical directory: '+name)
 return dict(path=name,identity=ident(s))
if C['operation']=='inventory':
 selected=dict(C['files']);dirs={};visited=0
 for label,root in C['trees'].items():
  stack=[(label,root)]
  while stack:
   prefix,name=stack.pop();dirs[name]=directory(name);visited+=1
   need(visited<=C['max_paths'],'visited-path bound')
   with os.scandir(name) as entries:
    for entry in entries:
     visited+=1;need(visited<=C['max_paths'],'visited-path bound')
     p=pathlib.Path(entry.path);s=p.lstat();member=prefix+'/'+entry.name
     if stat.S_ISDIR(s.st_mode):stack.append((member,str(p)))
     else:
      need(stat.S_ISREG(s.st_mode),'nonregular selected entry: '+str(p))
      need(member not in selected,'duplicate selected name: '+member)
      selected[member]=str(p);need(len(selected)<=C['max_files'],'file-count bound')
 need(len(selected)<=C['max_files'],'file-count bound')
 rows={};total=0
 for member,name in sorted(selected.items()):
  row,_=regular(name);total+=row['bytes'];need(total<=C['max_total_bytes'],'total byte bound')
  rows[member]=row
 for name,row in dirs.items():need(directory(name)==row,'directory changed during inventory')
 report=dict(files=rows,directories=dirs,count=len(rows),bytes=total,visited_paths=visited,collected_unix=time.time())
 encoded=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
 need(len(encoded)<=C['max_metadata_bytes'],'inventory metadata bound')
 sys.stdout.buffer.write(encoded)
else:
 index=C['inventory']
 for name,row in index['directories'].items():need(directory(name)==row,'directory changed before transport')
 with tarfile.open(fileobj=sys.stdout.buffer,mode='w|',format=tarfile.PAX_FORMAT) as archive:
  for member,row in sorted(index['files'].items()):
   actual,data=regular(row['path'],row)
   item=tarfile.TarInfo(member);item.size=len(data);item.mode=0o644
   archive.addfile(item,io.BytesIO(data))
 for name,row in index['directories'].items():need(directory(name)==row,'directory changed after transport')
'''


def remote(control, phase, config, seconds, limit):
    config = {**config, 'seconds': seconds}
    encoded = base64.b64encode(json.dumps(config).encode()).decode('ascii')
    code = REMOTE.replace('CONFIG', repr(encoded))
    source = control / (phase + '-input.py.txt')
    output = control / (phase + ('.tar' if config['operation'] == 'copy' else '.json'))
    error = control / (phase + '-stderr.log')
    write(source, code.encode())
    command = dict(argv=SSH, input=str(source.name), input_sha256=sha(code.encode()),
                   seconds=seconds, stdout_limit=limit,
                   stderr_limit=config['max_metadata_bytes'], started_unix=time.time())
    document(control / (phase + '-command.json'), command)
    child = None
    counts = {'stdout': 0, 'stderr': 0}
    stopped = None
    try:
        with source.open('rb') as supplied, output.open('xb') as out, error.open('xb') as err:
            child = subprocess.Popen(SSH, stdin=supplied, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
            selector = selectors.DefaultSelector()
            for stream, name, target, bound in ((child.stdout,'stdout',out,limit),
                    (child.stderr,'stderr',err,config['max_metadata_bytes'])):
                selector.register(stream, selectors.EVENT_READ, (name,target,bound))
            deadline = time.monotonic() + seconds + 15
            try:
                while selector.get_map() or child.poll() is None:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('bounded receipt command expired')
                    for key, _ in selector.select(min(0.2, max(0, deadline-time.monotonic()))):
                        name, target, bound = key.data
                        block = os.read(key.fd, 65536)
                        if not block:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        remaining = bound-counts[name]
                        if remaining > 0:
                            target.write(block[:remaining])
                            counts[name] += min(len(block), remaining)
                        require(len(block) <= remaining, phase+' '+name+' bound exceeded')
                code = child.wait(timeout=5)
            finally:
                selector.close()
                for stream in (out,err):stream.flush();os.fsync(stream.fileno())
        require(code == 0, phase+' SSH returned '+str(code))
    except BaseException as failure:
        stopped = repr(failure)
        if child is not None and child.poll() is None:
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
        raise
    finally:
        row = dict(command, finished_unix=time.time(), error=stopped,
                   returncode=None if child is None else child.poll(),
                   process_reaped=child is not None and child.poll() is not None,
                   remote_completed=stopped is None and child is not None and child.poll()==0)
        for name,path in (('stdout',output),('stderr',error)):
            if path.exists():row[name]=dict(bytes=path.stat().st_size,sha256=file_sha(path))
        document(control / (phase+'-result.json'),row)
    return output


def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def validate_index(index, config, output):
    require(type(index['count']) is int and 0<=index['count']<=config['max_files'], 'inventory file count')
    require(len(index['files'])==index['count'], 'inventory membership count')
    require(type(index['visited_paths']) is int and index['visited_paths']<=config['max_paths'], 'inventory path count')
    total=0
    names=sorted(index['files']); known=set(names)
    for name in names:
        relative_name(name)
        parts=PurePosixPath(name).parts
        require(not any('/'.join(parts[:i]) in known for i in range(1,len(parts))),
                'file/directory member collision')
        target=output/'payload'/name
        require(len(os.fsencode(target))<os.pathconf(output,'PC_PATH_MAX'), 'destination path too long')
        require(all(len(os.fsencode(part))<=os.pathconf(output,'PC_NAME_MAX') for part in PurePosixPath(name).parts), 'member component too long')
        row=index['files'][name];absolute_name(row['path'])
        matches = config['files'].get(name)==row['path']
        for label,root in config['trees'].items():
            if name.startswith(label+'/'):
                matches |= row['path']==root+'/'+name[len(label)+1:]
        require(matches,'inventory file outside the named selection')
        require(type(row['bytes']) is int and 0<=row['bytes']<=config['max_file_bytes'], 'inventory per-file extent')
        require(len(row['sha256'])==64 and all(c in '0123456789abcdef' for c in row['sha256']), 'inventory SHA256')
        require(isinstance(row['identity'],list) and len(row['identity'])==7, 'inventory identity')
        total+=row['bytes'];require(total<=config['max_total_bytes'],'inventory total extent')
    require(total==index['bytes'], 'inventory total bytes')


def archive_members(path, index):
    seen=set()
    with tarfile.open(path,mode='r:') as archive:
        for member in archive:
            relative_name(member.name)
            require(member.isfile() and not member.issparse() and member.name in index['files']
                    and member.name not in seen, 'unexpected or duplicate archive member')
            row=index['files'][member.name]
            require(member.size==row['bytes'], 'archive size differs from inventory')
            stream=archive.extractfile(member);h=hashlib.sha256();length=0
            for block in iter(lambda:stream.read(1048576),b''):h.update(block);length+=len(block)
            require(length==row['bytes'] and h.hexdigest()==row['sha256'],'archive hash differs from inventory')
            seen.add(member.name)
        end=archive.offset
    require(seen==set(index['files']),'archive membership differs from inventory')
    with path.open('rb') as stream:
        stream.seek(end)
        for block in iter(lambda:stream.read(1048576),b''):
            require(not any(block),'nonzero bytes after archive end')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tree',nargs=2,action='append',default=[],metavar=('LABEL','GUEST_PATH'))
    parser.add_argument('--file',nargs=2,action='append',default=[],metavar=('LABEL','GUEST_PATH'))
    for name in ('max-files','max-paths','max-file-bytes','max-total-bytes','max-metadata-bytes','inventory-seconds','copy-seconds'):
        parser.add_argument('--'+name,type=int,required=True)
    args=parser.parse_args()
    for name,value in vars(args).items():
        if name.startswith('max_') or name.endswith('_seconds'):
            require(value>0,'positive explicit bound required: '+name)
    require(args.inventory_seconds<2**31 and args.copy_seconds<2**31,'alarm extent')
    require(args.max_file_bytes<=args.max_total_bytes,'per-file bound exceeds total bound')
    trees={};files={}
    for source,destination in ((args.tree,trees),(args.file,files)):
        for label,name in source:
            relative_name(label);absolute_name(name)
            require(label not in trees and label not in files,'duplicate selection label')
            destination[label]=name
    require(trees or files,'at least one exact named guest selection required')
    output=args.output.absolute()
    require(output.parent.resolve(strict=True)==output.parent and not output.exists() and not output.is_symlink(), 'fresh output with canonical existing parent required')
    output.mkdir(mode=0o700)
    control=output/'.collection';control.mkdir(mode=0o700)
    fsync_directory(output.parent);fsync_directory(output)
    write(control/'collection-helper.py.txt',Path(__file__).read_bytes())
    config=dict(trees=trees,files=files,max_files=args.max_files,max_paths=args.max_paths,
                max_file_bytes=args.max_file_bytes,max_total_bytes=args.max_total_bytes,
                max_metadata_bytes=args.max_metadata_bytes)
    document(control/'selection.json',dict(config,argv=sys.argv))
    try:
        before_path=remote(control,'inventory-before',dict(config,operation='inventory'),args.inventory_seconds,args.max_metadata_bytes)
        before=json_unique(before_path.read_bytes());validate_index(before,config,output)
        # Per-member tar/PAX/name padding is bounded by the actual inventory
        # name lengths, rather than a fixed 512-file assumption.
        overhead=sum(4096+4*len(name.encode()) for name in before['files'])+20480
        payload=remote(control,'copy',dict(config,operation='copy',inventory=before),args.copy_seconds,args.max_total_bytes+overhead)
        archive_members(payload,before)
        archive_identity=(payload.stat().st_dev,payload.stat().st_ino,payload.stat().st_size,
                          payload.stat().st_mtime_ns,payload.stat().st_ctime_ns)
        archive_sha256=file_sha(payload)
        after_path=remote(control,'inventory-after',dict(config,operation='inventory'),args.inventory_seconds,args.max_metadata_bytes)
        after=json_unique(after_path.read_bytes());validate_index(after,config,output)
        require(all(before[k]==after[k] for k in ('files','directories','count','bytes','visited_paths')),'selected bytes, identity or membership changed across transport')
        # No member payload is written until the entire archive and final
        # independent inventory have passed exact membership and byte checks.
        current=payload.stat()
        require(archive_identity==(current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns)
                and file_sha(payload)==archive_sha256,'validated local archive changed')
        root=output/'payload';root.mkdir(mode=0o700);directories={output,root};copies=[];seen=set()
        with tarfile.open(payload,mode='r:') as archive:
            for member in archive:
                relative_name(member.name)
                require(member.isfile() and not member.issparse() and member.name in before['files']
                        and member.name not in seen and member.size==before['files'][member.name]['bytes'],
                        'validated member changed before write')
                seen.add(member.name)
                target=root/member.name
                target.parent.mkdir(parents=True,exist_ok=True)
                directories.update(target.parents)
                incoming=archive.extractfile(member);h=hashlib.sha256();length=0
                with target.open('xb') as stream:
                    for block in iter(lambda:incoming.read(1048576),b''):
                        stream.write(block);h.update(block);length+=len(block)
                    stream.flush();os.fsync(stream.fileno())
                row=before['files'][member.name]
                require(length==row['bytes'] and h.hexdigest()==row['sha256'] and file_sha(target)==row['sha256'],'written copy differs')
                fsync_directory(target.parent)
                copies.append(dict(name=member.name,path=str(target.relative_to(output)),guest_path=row['path'],bytes=length,sha256=row['sha256'],identity=row['identity']))
        require(seen==set(before['files']),'written membership differs')
        for directory in sorted((p for p in directories if p==output or output in p.parents),key=lambda p:len(p.parts),reverse=True):fsync_directory(directory)
        document(output/'copy-index.json',dict(files=copies,count=len(copies),bytes=before['bytes']))
        document(output/'collection.json',dict(status='COMPLETE',finished_unix=time.time(),files=len(copies),bytes=before['bytes'],archive_sha256=archive_sha256,scope='Exact named saved-file collection after the controller closed its receipt window.'))
        print(json.dumps(dict(status='COMPLETE',output=str(output),files=len(copies),bytes=before['bytes']),indent=2))
    except BaseException as failure:
        document(output/'collection-failure.json',dict(status='FAILED_RETAIN_OUTPUT',error=repr(failure),no_automatic_retry=True,unix=time.time()))
        raise


if __name__=='__main__':
    main()
