"""VM-only live5 controller; requires actual kernel3 postboot proof before load.

The observer never kills a timed-out child or treats a timeout as source drain.
Authoring/reviewing this file performs no VM command or project import.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

base = Path('/mnt/kdlock-builds/kdlock-main-work')
source_leaf = base / 'module4-69ba6b03-01a1bc4f'
repo = source_leaf / 'input'
module = source_leaf / 'module-build/kd_runtime_fixture.ko'
kernel_root = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
proof_root = kernel_root / 'receipts/postboot-kdrebuild3-20261110-UTC-01'
output = base / 'live5-runtime-69ba6b03-20261110-UTC-01'
receipts = base / 'live5-controller-69ba6b03-20261110-UTC-01'
release = '7.0.0-38-kdrebuild3'
source_commit = '69ba6b030c1eb7e5f1c3f9461b70f5fef6791309'
core_commit = '1b50e37382d2c739b16953027c47d7e2388562f0'
module_sha = '2be5cd04f9b7e5aa570c56dd1e940619e03696b33ef8d14bbc4262d2ac11a2a3'
manifest_sha = 'f0284c0318f4712524bd0274e887c5454b947cbcdbef578c1dfb8646273d5ff1'
pins_sha = 'c3ff591b1a60d2f4a094d41d4c2241d72691c04d6ed67720a2a0e91e65037f0e'
elf_sha = 'c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d'
config_sha = '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483'
build_id = '264a4ef8e55952e5d9ceccf93f65f25f05a50c1f'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


if output.exists() or receipts.exists():
    raise SystemExit('fresh live output and controller receipt required')
if os.geteuid() != 0 or os.uname().machine != 'x86_64':
    raise SystemExit('designated VM root context required')
proof = json.loads((proof_root / 'result.json').read_text())
if proof['phase'] != 'POSTBOOT_IDENTITY_VERIFIED':
    raise SystemExit('successful actual postboot proof required')
if os.uname().release != release:
    raise SystemExit('wrong running release')
if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != proof['boot_id']:
    raise SystemExit('running boot differs from proof')
if Path('/proc/sys/kernel/tainted').read_text().strip() != '0':
    raise SystemExit('expected the fresh untainted boot')
if any(line.startswith('kd_runtime_fixture ') for line in Path('/proc/modules').read_text().splitlines()) or any(Path('/dev').glob('kd_runtime_fixture*')):
    raise SystemExit('fixture module/devices already active')
if digest(module) != module_sha:
    raise SystemExit('module differs from its retained actual build')
manifest_path = source_leaf / 'kdlock-main-69ba6b03-manifest.json'
if digest(manifest_path) != manifest_sha:
    raise SystemExit('retained source manifest differs')
manifest = json.loads(manifest_path.read_text())
actual = {}
for path in repo.rglob('*'):
    if path.is_symlink():
        raise SystemExit('frozen source contains a symlink')
    if path.is_file():
        actual[path.relative_to(repo).as_posix()] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
if len(actual) != 109 or actual != manifest:
    raise SystemExit('frozen source differs from reviewed109-file manifest')
pins_path = source_leaf / 'kernel3-six-pins.json'
if digest(pins_path) != pins_sha:
    raise SystemExit('kernel3 six-output pins differ')
pins = json.loads(pins_path.read_text())
if {name: digest(kernel_root / 'build' / name) for name in pins} != pins:
    raise SystemExit('actual completed kernel3 outputs differ')
tracer_path = Path('/sys/kernel/tracing/current_tracer')
tracer = tracer_path.read_text().strip() if tracer_path.exists() else None
if tracer is not None and tracer != 'nop':
    raise SystemExit('source immutability context differs from the admitted run')
gs = json.loads((proof_root / 'gs-proof.json').read_text())
if (gs['verified_for_running_kernel'] is not True or gs['kernel_release'] != release
        or gs['boot_id'] != proof['boot_id'] or gs['build_id'] != build_id
        or gs['kernel_elf_sha256'] != elf_sha or gs['kernel_config_sha256'] != config_sha
        or gs['gs_symbol'] != 'current_task'
        or int(str(gs['current_task_gs_offset']), 0) != 0xffffffff8440f018
        or int(str(gs['const_current_task']), 0) != 0xffffffff8440f018
        or not gs['kaslr_disabled']):
    raise SystemExit('actual kernel3 full-VMA GS proof differs')
args = [
    '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3',
    str(repo / 'tests/kernel/run_runtime_fixture.py'),
    '--repo', str(repo), '--module', str(module), '--output', str(output),
    '--expected-release', release,
    '--kernel-elf', str(kernel_root / 'build/vmlinux'),
    '--kernel-config', str(kernel_root / 'build/.config'),
    '--gs-proof-json', str(proof_root / 'gs-proof.json'),
    '--gs-offset', str(gs['current_task_gs_offset']),
    '--dependency-page-limit', '4', '--total-source-byte-limit', '262144',
    '--wire-log-byte-limit', '134217728', '--event-capacity', '65536',
    '--immutable-text-contract', '--auxiliary-stack-contract',
    '--workers', '4', '--iterations', '8', '--deadline', '120',
]
env = dict(os.environ)
overrides = dict(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
                 LC_ALL='C', LANG='C', KDLOCK_RECOVERY_CONFIRMED='1',
                 KDLOCK_SNAPSHOT_TAG='kdlock-builddisk-clean-20261031')
env.update(overrides)
receipts.mkdir(mode=0o700)
record = dict(argv=list(args), environment_overrides=overrides,
              start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              tracer=tracer, kernel_code_commit=core_commit,
              host_source_commit=source_commit,
              common_compiler_commit='18c8f2e499d5fb74972e92bad5748489b921035d',
              source_snapshot=str(repo), source_manifest_sha256=manifest_sha,
              verified_source_files=len(actual), kernel_pins=pins,
              module_sha256=module_sha, boot_id=proof['boot_id'], observer_seconds=600,
              deadline_policy='Observer deadline retains the child and makes no drain claim.')
(receipts / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
start = time.monotonic()
with (receipts / 'stdout.log').open('x') as log:
    child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                             env=env, start_new_session=True)
    record['pid'] = child.pid
    (receipts / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
    while child.poll() is None and time.monotonic() - start < record['observer_seconds']:
        time.sleep(1)
    code = child.poll()
record.update(returncode=code, elapsed_seconds=time.monotonic() - start,
              end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              taint_after=Path('/proc/sys/kernel/tainted').read_text().strip(),
              status='RETURNED' if code is not None else 'RUNNING_AFTER_OBSERVER_DEADLINE')
(receipts / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
print((receipts / 'stdout.log').read_text()[-12000:])
raise SystemExit(code if code is not None else 124)
