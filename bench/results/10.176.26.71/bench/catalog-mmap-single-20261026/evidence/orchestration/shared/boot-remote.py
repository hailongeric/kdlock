import hashlib, json, os, runpy, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
request = json.load(sys.stdin)
root = Path('/root/host_fs/kdlock')
sys.path.insert(0, str(root / 'bench/spin_cacheline'))
import bench_runtime as rt

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def command(argv):
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
    row = dict(argv=argv, pid=child.pid, completion_unconfirmed=True)
    print(json.dumps(row), flush=True)
    out, err = child.communicate(timeout=30)
    row.update(returncode=child.returncode, completion_unconfirmed=False,
               stdout=out.decode(), stderr=err.decode())
    print(json.dumps(row), flush=True)
    assert child.returncode == 0, row
    return out.decode()

assert os.uname().release == request['previous_release']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == request['previous_boot']
assert sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines()) == sorted(request['previous_modules'])
runpy.run_path(str(root / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
art = request['artifacts']['artifact']
for group in ('candidate_boot_hashes', 'recovery_boot_hashes'):
    for name, digest in art[group].items():
        if name != '/boot/grub/grubenv':
            assert sha(name) == digest, name
assert 'set default="' + art['recovery_default'] + '"' in Path('/boot/grub/grub.cfg').read_text()
entry = request['entry']
assert entry in list(art['boot_entries'].values()) + [art['recovery_default']]
assert command(['grub-editenv', '/boot/grub/grubenv', 'list']).strip() == 'next_entry='
build = json.loads(Path(request['build']).read_text())
assert build['passed'] and build['client_only'] and build['reused_payload']
for name, digest in build['files'].items():
    assert sha(name) == digest, name
print(json.dumps(dict(preflight_passed=True, binary_hashes_verified=build['binaries'],
                     next_entry=entry, previous_boot=request['previous_boot'])), flush=True)
command(['grub-reboot', entry])
assert command(['grub-editenv', '/boot/grub/grubenv', 'list']).strip() == 'next_entry=' + entry
command(['systemctl', 'reboot'])
