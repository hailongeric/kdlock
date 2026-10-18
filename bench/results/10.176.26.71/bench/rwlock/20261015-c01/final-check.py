import datetime
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path('/root/host_fs/kdlock')
out = Path('/root/kdlock-evidence/10.176.26.71/bench/rwlock-c01-grid-20261015')
sys.path.insert(0, str(root / 'bench/rwlock_compare'))
import run

assert (out.parent / (out.name + '.exit')).read_text().strip() == '0'
run.idle()
env = json.loads((out / 'environment.json').read_text())
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == env['boot_policy']['boot_id']
source = json.loads((out / 'source-sha256.json').read_text())
assert run.sources() == source
assert all(run.digest(out / 'source' / p) == v for p, v in source.items())
binary = json.loads((out / 'binary-sha256.json').read_text())
assert all(run.digest(Path(p)) == v for p, v in binary.items())
final = out / 'final'
final.mkdir()
policy = run.boot_policy.capture(Path('/root/linux-6.1.159-kdclobber2'), final, run.command)
assert policy == env['boot_policy']
assert Path('/sys/devices/system/cpu/online').read_text().strip() == '0-63'
assert '(voluntary)' in Path('/sys/kernel/debug/sched/preempt').read_text()
modules = [s for s in Path('/proc/modules').read_text().splitlines()
           if any(x in s.split()[0] for x in ('kdlock', 'tclock', 'rwlock_bench', 'tc_allocator'))]
assert not modules
receipt = dict(checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    idle=True, boot_policy=policy, source_unchanged=True, frozen_source_unchanged=True,
    binaries_unchanged=True, source_files=len(source), binaries=len(binary),
    online_cpus='0-63', project_modules=modules,
    cmdline=Path('/proc/cmdline').read_text().strip(),
    preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip())
(final / 'idle.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
