"""Read QEMU task lifetimes and activity without changing host state."""
import datetime
import json
import os
import time
from pathlib import Path

base = Path('/proc/257489')
args = (base / 'cmdline').read_bytes().split(b'\0')
assert Path(os.fsdecode(args[0])).name == 'qemu-system-x86_64'
rows = []
for task in sorted((base / 'task').iterdir(), key=lambda p: int(p.name)):
    try:
        fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
        rows.append(dict(tid=int(task.name), comm=(task / 'comm').read_text().strip(),
            affinity=sorted(os.sched_getaffinity(int(task.name))), state=fields[0],
            start_ticks=int(fields[19]), user_ticks=int(fields[11]), system_ticks=int(fields[12]),
            wchan=(task / 'wchan').read_text().strip(),
            io={k: int(v) for k, v in (line.split(':', 1) for line in (task / 'io').read_text().splitlines())}))
    except (FileNotFoundError, ProcessLookupError):
        rows.append(dict(tid=int(task.name), exited_during_read=True))
print(json.dumps(dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    monotonic_ns=time.monotonic_ns(), uptime=Path('/proc/uptime').read_text().strip(),
    clock_ticks=os.sysconf('SC_CLK_TCK'), qemu_pid=257489, tasks=rows), indent=2))
