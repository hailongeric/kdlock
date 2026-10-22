#!/usr/bin/env python3
"""Read-only offline validation of copied campaign archives; never extract."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import stat
import tarfile

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archives',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();base=a.archives
    receipt=json.loads((base/'archives.json').read_text())
    assert receipt['completed'] and receipt['guest_idle']
    assert sha(base/'input-inventory.json')==receipt['input_inventory_sha256']
    expected=json.loads((base/'input-inventory.json').read_text())
    prefix=receipt['archive_prefix']+'/'
    seen=set();regular=0;groups=[]
    for group in receipt['groups']:
        path=base/group['file']
        assert path.stat().st_size==group['bytes'] and sha(path)==group['sha256'],path
        count=0
        with tarfile.open(path,'r:gz') as archive:
            for item in archive:
                assert item.name.startswith(prefix),item.name
                name=item.name[len(prefix):]
                assert name in expected and name not in seen,name
                seen.add(name);row=expected[name]
                assert item.mode==stat.S_IMODE(row['mode']),name
                assert (item.uid,item.gid)==(row['uid'],row['gid']),name
                if stat.S_ISDIR(row['mode']):assert item.isdir(),name
                elif stat.S_ISLNK(row['mode']):
                    assert item.issym() and item.linkname==row['link'],name
                else:
                    assert stat.S_ISREG(row['mode']) and item.isfile(),name
                    assert item.size==row['bytes'],name
                    regular+=1;count+=1
        groups.append(dict(file=group['file'],sha256=group['sha256'],regular_files=count))
    assert seen==set(expected),'missing paths'
    result=dict(completed=True,host=socket.gethostname(),inventory_paths=len(seen),
        regular_files=regular,verified_archives=groups,
        scope='Compressed hashes and complete archive path/type/size/mode/owner/link inventory. Read-only; no extraction.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(completed=True,inventory_paths=len(seen),regular_files=regular,archives=len(groups))))

if __name__=='__main__':main()
