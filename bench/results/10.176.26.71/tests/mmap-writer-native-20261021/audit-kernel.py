#!/usr/bin/env python3
"""Read inert kernel source and inventory mmap-lock tokens; execute no kernel input."""
import collections
import hashlib
import json
from pathlib import Path
import re
import tarfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mmap-writer-native-20261021/kernel-capture-1'
read=lambda p:json.loads(p.read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=read(RAW/'source-sha256.json');capture=read(RAW/'capture.json')
assert sha((RAW/'kernel-inputs.tar.gz').read_bytes())==capture['archive_sha256']
assert sha((RAW/'source-sha256.json').read_bytes())==capture['manifest_sha256']
pattern=re.compile(rb'\b(?:mmap_(?:read|write|init|assert|lock)[A-Za-z0-9_]*|MMAP_LOCK_INITIALIZER)\b')
selected=('include/linux/mmap_lock.h','include/linux/mm_types.h','include/linux/rwsem.h',
          'mm/mmap_lock.c','mm/util.c','mm/mmap.c','mm/mprotect.c','mm/mremap.c','mm/memory.c',
          'mm/gup.c','mm/filemap.c','kernel/fork.c','kernel/exit.c','fs/proc/task_mmu.c',
          'fs/proc/base.c','mm/userfaultfd.c','fs/userfaultfd.c','mm/hugetlb.c','kernel/locking/rwsem.c')
rows=[];seen=set();contents={};apis=collections.Counter();families=collections.Counter()
with tarfile.open(RAW/'kernel-inputs.tar.gz') as archive:
    for member in archive:
        assert member.isfile() and member.name.startswith('kernel/')
        path=member.name[len('kernel/'):]
        assert path in manifest and path not in seen and '..' not in Path(path).parts
        data=archive.extractfile(member).read();assert sha(data)==manifest[path];seen.add(path)
        if path=='.config' or path in selected:contents[path]=data.decode(errors='replace')
        if pattern.search(data):
            content=data.decode(errors='replace');contents[path]=content
            for number,line in enumerate(content.splitlines(),1):
                tokens=sorted(set(match.group().decode() for match in pattern.finditer(line.encode())))
                if not tokens:continue
                calls=sorted(set(re.findall(r'\b(mmap_(?:read|write|init|assert|lock)\w*)\s*\(',line)))
                apis.update(calls);families[path.split('/')[0]]+=1
                rows.append(dict(path=path,line=number,tokens=tokens,calls=calls,text=line.strip(),file_sha256=manifest[path]))
assert seen==set(manifest) and len(seen)==capture['files']
# Keep selected source text for concrete API/mode/lifetime review; all other
# participants remain recoverable from the independently hashed full archive.
selected_dir=RAW/'kernel-review';selected_dir.mkdir(exist_ok=True)
for name in selected:
    assert name in contents
    dest=selected_dir/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(contents[name])
configuration={key:('y' if key+'=y\n' in contents['.config'] else 'n') for key in
 ('CONFIG_LOCKDEP','CONFIG_USERFAULTFD','CONFIG_TRANSPARENT_HUGEPAGE','CONFIG_HUGETLBFS','CONFIG_DAX','CONFIG_EXT4_FS','CONFIG_FS_IOMAP','CONFIG_PREEMPT_RT')}
result=dict(schema=1,verified_files=len(seen),source_bytes=capture['bytes'],archive_sha256=capture['archive_sha256'],
    manifest_sha256=capture['manifest_sha256'],inventory_rows=len(rows),participant_files=len({r['path'] for r in rows}),
    families=dict(sorted(families.items())),api_occurrences=dict(sorted(apis.items())),configuration=configuration,
    selected_source_hashes={p:manifest[p] for p in selected},script_sha256=sha(Path(__file__).read_bytes()),
    limits='Lexical inventory includes definitions, comments and disabled architectures/configurations. It is not a build reachability or full transitive callback proof; indirect aliases require review.',
    kernel_modified=False,kd_integration=False,accepted=False)
(HERE/'participant-inventory.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
(HERE/'kernel-audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:result[k] for k in ('verified_files','inventory_rows','participant_files','families','api_occurrences','configuration')}))
