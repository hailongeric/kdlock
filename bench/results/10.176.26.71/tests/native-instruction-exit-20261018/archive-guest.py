"""Archive the exact completed VM attempts; no module or source mutation."""
import argparse, hashlib, json, pathlib, shutil, subprocess
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--final", action="store_true")
args = parser.parse_args()
root = pathlib.Path('/mnt/kdlock-builds')
out = root/('native-escape-archives-final-20261018' if args.final else 'native-escape-archives-20261018')
out.mkdir(exist_ok=True)
names = ['native-escape-units-20261018-01','native-escape-units-20261018-02',
         'native-escape-live-20261018-01','native-escape-live-20261018-02',
         'native-escape-rwsem-20261018-01']
if args.final:
    names = ['native-escape-units-20261018-03', 'native-escape-live-20261018-03',
             'native-escape-rwsem-20261018-02']
modules = pathlib.Path('/proc/modules').read_text()
project = [line for line in modules.splitlines() if line.split()[0] in
           ('kdlock_km','jit_escape_test','rwlock_bench','tc_allocator_guard')]
tasks = []
for path in pathlib.Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
    try:
        name = path.read_text().strip()
        if name in ('daemon','ke_worker','rb_worker','kd_test','sc_worker'):
            tasks.append(dict(path=str(path), name=name))
    except FileNotFoundError:
        pass
assert not project and not tasks, (project, tasks)
health = dict(idle=True, modules=project, tasks=tasks,
              boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              cmdline=pathlib.Path('/proc/cmdline').read_text(),
              cpus=pathlib.Path('/sys/devices/system/cpu/online').read_text().strip())
(out/'health-after.json').write_text(json.dumps(health,indent=2)+'\n')
(out/'modules-after.txt').write_text(modules)
with (out/'dmesg-after.log').open('w') as log:
    subprocess.run(['dmesg'],stdout=log,check=True,timeout=10)
for file in ('arch/x86/lib/retpoline.S','arch/x86/include/asm/nospec-branch.h'):
    shutil.copyfile(pathlib.Path('/root/linux-6.1.159-kdclobber2')/file,out/pathlib.Path(file).name)
records = []
for name in names:
    archive = out/(name+'.tar.gz')
    assert not archive.exists(), archive
    subprocess.run(['tar','-czf',str(archive),'-C',str(root),name],check=True,timeout=180)
    digest=hashlib.sha256()
    with archive.open('rb') as incoming:
        for chunk in iter(lambda: incoming.read(1024*1024),b''):
            digest.update(chunk)
    records.append(dict(guest_run=str(root/name), archive=archive.name,
                        bytes=archive.stat().st_size, sha256=digest.hexdigest()))
    print(json.dumps(records[-1]),flush=True)
(out/'archives.json').write_text(json.dumps(records,indent=2)+'\n')
