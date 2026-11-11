from pathlib import Path
import json,os
rows={}
for pid in (8108,8134,8135):
 p=Path('/proc')/str(pid);a=(p/'stat').read_text();argv=(p/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0');fds={x.name:os.readlink(x) for x in (p/'fd').iterdir()};b=(p/'stat').read_text();start=int(a[a.rfind(')')+2:].split()[19]);assert start==int(b[b.rfind(')')+2:].split()[19]);rows[str(pid)]={'stat':a,'startticks':start,'argv':argv,'fd_targets':fds,'status':(p/'status').read_text(),'wchan':(p/'wchan').read_text()}
print(json.dumps(rows))
