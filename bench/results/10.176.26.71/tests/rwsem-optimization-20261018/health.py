"""Guest-only final identity/drain receipt; no module or kernel mutation."""
import hashlib, json, re, runpy, subprocess
from pathlib import Path

root = Path('/root/host_fs/kdlock')
base = Path('/mnt/kdlock-builds/rwsem-opt-20261018')
probe = runpy.run_path(str(root / 'tests/kernel/rwsem/run.py'), run_name='health_preflight')
probe['idle']()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
checked = []
for name in ('xlong-probe', 'final-basic', 'final-functional', 'final-local', 'final-jit',
             'final-grid', 'final-reference', 'final-profile/rwsem'):
    out = base / name
    manifest = json.loads((out / 'source-sha256.json').read_text())
    for relative, expected in manifest.items():
        for where in (root, out / 'source'):
            assert sha(where / relative) == expected, str(where / relative)
    binaries = json.loads((out / 'binary-sha256.json').read_text()) if (out / 'binary-sha256.json').exists() else {}
    for path, expected in binaries.items():
        assert sha(Path(path)) == expected, path
    checked.append(dict(name=name, source_files=len(manifest), binary_files=len(binaries),
                        source_manifest_sha256=sha(out / 'source-sha256.json')))
    if name == 'final-basic':
        assert json.loads((out / 'result.json').read_text())['returncode'] == 0
    elif name.startswith('final-profile/'):
        result = json.loads((out.parent / 'result.json').read_text())
        assert result['completed'] and result['tracing_restored'] and result['guest_idle']
        assert all(row['returncode'] == 0 for row in result['commands'])
    else:
        assert json.loads(out.with_suffix('.command.json').read_text())['returncode'] == 0, name

binary = json.loads((base / 'final-grid/binary-sha256.json').read_text())
provider = next(Path(name) for name in binary if name.endswith('/kdlock_km.ko'))
imports = (base / 'final-grid' / (provider.parent.name + '-ubsan.txt')).read_text()
(base / 'provider-imports.txt').write_text(imports)
assert not re.search(r'\b(?:__)?mutex_(?:lock|unlock|trylock|is_locked|init|destroy)', imports)
faults, logs = [], []
for path in base.glob('**/kernel.log'):
    logs.append(str(path.relative_to(base)))
    if probe['rt'].FAULT.search(path.read_text()):
        faults.append(str(path.relative_to(base)))
assert logs and not faults, faults
tracing = Path('/sys/kernel/tracing')
trace = {key:(tracing / key).read_text() for key in
         ('current_tracer', 'function_profile_enabled', 'enabled_functions',
          'set_ftrace_filter', 'set_graph_function')}
assert trace['current_tracer'].strip() == 'nop'
assert trace['function_profile_enabled'].strip() == '0'
assert not trace['enabled_functions'].strip()
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot == 'b65f0205-c8f9-4385-8b13-039cbce243a6', boot
(base / 'dmesg-final.txt').write_text(subprocess.check_output(['dmesg'], text=True))
probe['idle']()
health = dict(idle=True, boot_id=boot, source_and_binary_checks=checked,
              no_linux_mutex_imports=True, per_session_kernel_logs=len(logs),
              per_session_kernel_faults=faults, tracing=trace,
              dmesg_scope='Final ring retained; fault checks cover each captured session kernel.log')
(base / 'health.json').write_text(json.dumps(health, indent=2)+'\n')
print(json.dumps(health, indent=2))
