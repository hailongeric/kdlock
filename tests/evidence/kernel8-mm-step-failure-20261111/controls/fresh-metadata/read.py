from pathlib import Path
import hashlib
import json
import os
import runpy
import stat
import sys
import time

KERNEL = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
MAX_OUTPUT = 4*1024**2


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def entry(path):
    path = Path(path)
    try:
        value = path.lstat()
    except FileNotFoundError:
        return {'path': str(path), 'exists': False}
    return {'path': str(path), 'exists': True, 'mode': value.st_mode,
            'device': value.st_dev, 'inode': value.st_ino,
            'is_directory': stat.S_ISDIR(value.st_mode),
            'is_symlink': stat.S_ISLNK(value.st_mode)}


def text(path, limit):
    value = entry(path)
    if not value['exists']:
        return value
    with Path(path).open('rb') as stream:
        data = stream.read(limit+1)
    need(len(data) <= limit, 'bounded metadata extent exceeded: ' + str(path))
    value.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                 text=data.decode('utf-8', errors='strict'), sampled_unix=time.time())
    return value


def helper(path, expected):
    need(digest(path) == expected, 'reviewed metadata helper differs')
    return runpy.run_path(str(path))


def checked(path, expected):
    need(digest(path) == expected and Path(path).stat().st_size <= 4*1024**2,
         'exact bounded receipt differs')
    return json.loads(Path(path).read_bytes())


started = time.monotonic()
ns = helper(BASE/'transport/build.py',
            '56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb')
native = helper(BASE/'native-api-input-01/controller.py',
                '2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074')
control = helper(BASE/'mm-provider-ioctl-input-0798c1ab-01/controller.py',
                 '6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136')
recipe = checked(BASE/'mm-provider-ioctl-input-0798c1ab-01/recipe.json',
                  'ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7')
recipe['candidate_idle_policy'] = dict(recipe['candidate_idle_policy'],
    boot_id='4a98638f-c01c-4fc9-8de8-69a74346aa0f', expected_taint=0)
before_idle = control['idle'](native, recipe)
need(native['running_notes']()[1] == recipe['build_id'], 'running Build ID differs')
built = checked(KERNEL/'receipts/full-01/result.json',
                 '024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
focused = checked(Path(built['focused_receipt']), built['focused_sha256'])
linked = checked(KERNEL/'receipts/full-01/final-identity.json', built['final_identity_sha256'])
pins = {name: row['sha256'] for name, row in linked['files'].items()}


def preserved():
    value = {'linked16': ns['pins'](KERNEL/'build', pins),
             'source': ns['source_pins'](focused, KERNEL/'source'),
             'protected': ns['protected'](focused), 'boot': ns['boot_files']()}
    need(len(value['linked16']) == 16 and len(focused['package_after']) == 78
         and value['source'] == built['source_after'] and value['protected'] == built['protected_after'],
         'kernel/source/protected identity differs')
    return value


before_pins = preserved()
cpu_raw = bytearray()
with Path('/proc/cpuinfo').open('rb') as stream:
    while True:
        line = stream.readline(65537-len(cpu_raw))
        if not line:
            break
        cpu_raw.extend(line)
        need(len(cpu_raw) <= 65536, 'first CPU block exceeds64KiB')
        if line.strip() == b'':
            break
cpu_text = bytes(cpu_raw).decode('utf-8', errors='strict')
cpu_fields = {key.strip(): value.strip() for line in cpu_text.splitlines()
              if ':' in line for key, value in [line.split(':', 1)]}
flags = cpu_fields.get('flags', '').split()
cpu = {'first_block': cpu_text, 'bytes': len(cpu_raw),
       'sha256': hashlib.sha256(cpu_raw).hexdigest(),
       'fields': {name: cpu_fields.get(name) for name in
                  ('processor', 'vendor_id', 'cpu family', 'model', 'model name', 'stepping', 'flags')},
       'fred_in_first_cpu_flags': 'fred' in flags,
       'hypervisor_in_first_cpu_flags': 'hypervisor' in flags,
       'hypervisor_type': text('/sys/hypervisor/type', 4096),
       'proc_xen': entry('/proc/xen'),
       'cmdline': text('/proc/cmdline', 65536),
       'online_cpus': text('/sys/devices/system/cpu/online', 65536),
       'scope': 'Observed flags and route metadata; configured FRED/XEN_PV alone is not an active-route witness.'}
mounts = text('/proc/self/mountinfo', 262144)
trace_roots = [Path('/sys/kernel/tracing'), Path('/sys/kernel/debug/tracing')]
trace_root = next((path for path in trace_roots if entry(path/'current_tracer')['exists']), None)
tracing = {'root_candidates': [entry(path) for path in trace_roots],
           'selected_read_root': str(trace_root) if trace_root is not None else None,
           'mountinfo': mounts, 'files': {}}
for name, limit in (('current_tracer', 4096), ('tracing_on', 4096),
                    ('function_profile_enabled', 4096), ('enabled_functions', 1048576),
                    ('kprobe_events', 65536), ('uprobe_events', 65536), ('dynamic_events', 65536)):
    if trace_root is None:
        tracing['files'][name] = {'exists': False, 'reason': 'No candidate current_tracer path exists'}
    else:
        tracing['files'][name] = text(trace_root/name, limit)
tracing['ftrace_enabled'] = text('/proc/sys/kernel/ftrace_enabled', 4096)
tracing['stack_tracer_enabled'] = text('/proc/sys/kernel/stack_tracer_enabled', 4096)
kprobes = text('/sys/kernel/debug/kprobes/list', 1048576)
patch_root = Path('/sys/kernel/livepatch')
livepatch = {'root': entry(patch_root), 'patches': []}
if livepatch['root']['exists']:
    entries = sorted(patch_root.iterdir())
    need(len(entries) <= 128, 'livepatch inventory exceeds128 entries')
    for path in entries:
        row = {'entry': entry(path)}
        if path.is_dir():
            row.update(enabled=text(path/'enabled', 4096),
                       transition=text(path/'transition', 4096))
        else:
            row['scope'] = 'Non-directory inventory entry; no patch state inferred.'
        livepatch['patches'].append(row)
config_path = KERNEL/'build/.config'
config_lines = config_path.read_text().splitlines()
selected_config = [line for line in config_lines if any(token in line for token in
    ('FRED', 'XEN_PV', 'XEN_PVH', 'FUNCTION_TRACER', 'FUNCTION_GRAPH_TRACER',
     'FUNCTION_PROFILER', 'STACK_TRACER', 'KPROBES', 'KRETPROBES', 'LIVEPATCH',
     'DYNAMIC_FTRACE', 'CONFIG_FTRACE=', 'CONFIG_BPF', 'CONFIG_HYPERVISOR_GUEST'))]
after_pins = preserved()
after_idle = control['idle'](native, recipe)
need(before_pins == after_pins and before_idle == after_idle
     and native['running_notes']()[1] == recipe['build_id'], 'identity/pins/idle changed during metadata capture')
need(time.monotonic()-started <= 60, 'metadata elapsed bound exceeded')
result = {'status': 'READ_ONLY_RUNTIME_METADATA_CAPTURE_COMPLETE',
          'identity_before': before_idle, 'identity_after': after_idle,
          'pins_before': before_pins, 'pins_after': after_pins, 'package78': focused['package_after'],
          'build_id': recipe['build_id'], 'cpu_route_observations': cpu, 'tracing': tracing,
          'kprobes': kprobes, 'livepatch': livepatch,
          'kernel_config_sha256': digest(config_path), 'selected_kernel_config': selected_config,
          'immutable_dependency_contract_established': False,
          'native_helper_16KiB_premise_established_by_capture': False,
          'mm_user_exclusion_contract_established_by_capture': False,
          'interpretation': 'Inventory is a bounded observation. Empty or missing interfaces do not establish dependency immutability, prevent later text patching, select a native-helper stack premise, or prove exclusion of asynchronous mm users.',
          'knob_mutations': [], 'elapsed_seconds': time.monotonic()-started}
raw = (json.dumps(result, sort_keys=True)+'\n').encode()
need(len(raw) <= MAX_OUTPUT, 'total metadata output exceeds4MiB')
sys.stdout.buffer.write(raw)
sys.stdout.buffer.flush()
