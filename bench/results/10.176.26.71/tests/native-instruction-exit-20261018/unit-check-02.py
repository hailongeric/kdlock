import hashlib, json, os, pathlib, shutil, subprocess, time
root = pathlib.Path('/root/host_fs/kdlock')
out = pathlib.Path('/mnt/kdlock-builds/native-escape-units-20261018-02')
out.mkdir()
source = out / 'source'
for directory in ('include', 'kernel_module', 'daemon', 'disassem', 'tests', 'bench/spin_cacheline', 'kernel_baseline'):
    shutil.copytree(root / directory, source / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'results'))
def hashes():
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and (p.suffix in ('.c','.h','.inc','.S','.def','.py') or p.name in ('Makefile','requirements.txt')) and not p.name.endswith('.mod.c')}
before = hashes()
(out/'source-sha256.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
records = []
env = dict(os.environ, PATH='/root/kdlock-evidence/clobber-20260918/venv/bin:'+os.environ['PATH'], LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
tests = ['admission/test_native_escape.py','admission/test_instruction_policy.py','admission/test_text_regions.py','admission/test_clobber_entry.py','admission/test_context_policy.py','codegen/test_native_escape_codegen.py','codegen/test_jit_body_witness.py','codegen/test_jit_diagnostics.py','codegen/test_clobber_abi.py','execution/test_native_escape_restore.py','execution/test_mutex_images.py','execution/test_exe_registry.py','execution/test_jit_entry_scope.py','execution/test_exec_capacity.py','infrastructure/test_source_lifetime.py','execution/test_native_registers.py','mutex/test_mutex_wait_clobber.py']
commands = [('basic', ['make','-C','tests/unit','run'])] + [(t.replace('/','-'), ['python3','tests/unit/run.py',t]) for t in tests]
for name, command in commands:
    start = time.monotonic()
    with (out/(name+'.log')).open('w') as log:
        try:
            r = subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            code = r.returncode
        except subprocess.TimeoutExpired:
            code = 124
    row = dict(name=name, command=command, returncode=code, seconds=time.monotonic()-start)
    records.append(row)
    (out/'results.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(row),flush=True)
assert hashes() == before, 'frozen source changed'
print('SOURCE_UNCHANGED',flush=True)
raise SystemExit(any(r['returncode'] for r in records))
