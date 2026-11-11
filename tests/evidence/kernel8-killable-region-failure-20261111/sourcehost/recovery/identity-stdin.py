from pathlib import Path
import json,os
p=Path('/proc/5412');a=(p/'stat').read_text();b=(p/'cmdline').read_bytes();fds={x.name:os.readlink(x) for x in (p/'fd').iterdir()};c=(p/'stat').read_text();assert a[a.rfind(')')+2:].split()[19]==c[c.rfind(')')+2:].split()[19]
print(json.dumps({'pid':5412,'proc_stat':a,'startticks':int(a[a.rfind(')')+2:].split()[19]),'argv':b.rstrip(b'\0').decode().split('\0'),'fd_targets':fds,'status':(p/'status').read_text(),'wchan':(p/'wchan').read_text()}))
