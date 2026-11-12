#!/usr/bin/env python3
"""Freeze committed source and write non-dispatchable validation templates."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile

R = Path('/home/eric/vm/vm-shared/kdlock-main')
OUT = Path('/tmp/kdlock-kernel9-private-rwsem-preparation-20261111-01')
HEAD = '6e486ecec398111fb5d5e30ffc76495f32f557b7'
OLD = Path('/tmp/kdlock-kernel8-fixture-source-0798c1ab-01')
PRIOR = R / 'tests/evidence/kernel8-private-regressions-20261111'
KERNEL = '/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01'
BASE = KERNEL + '/private-rwsem-regression-01'
sha = lambda b: hashlib.sha256(b).hexdigest()


def document(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=R)


OUT.mkdir(mode=0o700)
source = OUT/'source'
source.mkdir()
old = json.loads((OLD/'source-sha256.json').read_text())
assert len(old) == 143
data = {}
manifest = {}
for name in sorted(old):
    row = git('ls-tree', HEAD, '--', name).decode().strip().split()
    assert len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob' and row[3] == name
    b = git('show', HEAD+':'+name)
    data[name] = b
    manifest[name] = {'bytes': len(b), 'sha256': sha(b)}
    target = source/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b)
    target.chmod(0o755 if row[0] == '100755' else 0o644)
with tarfile.open(OUT/'source.tar', 'w', format=tarfile.USTAR_FORMAT) as tar:
    for name, b in data.items():
        t = tarfile.TarInfo(name)
        t.size = len(b)
        t.mode = (source/name).stat().st_mode & 0o777
        t.uid = t.gid = t.mtime = 0
        t.uname = t.gname = ''
        tar.addfile(t, io.BytesIO(b))
document('source-sha256.json', manifest)
selected_status = git('status', '--porcelain=v1', '--', *sorted(old)).decode()
assert not selected_status
global_status = git('status', '--short').decode()
document('source-state.json', {'source_git_head': HEAD, 'files': 143,
    'transfer_bytes': sum(r['bytes'] for r in manifest.values()), 'git_status': selected_status,
    'git_status_scope': 'Only the exact selected tracked 143 source names; not whole-worktree cleanliness.',
    'whole_worktree_status_at_export': global_status,
    'export_method': 'git show of each exact committed regular blob; no recursive worktree copy'})
core_path = R/'tests/evidence/kernel8-mm-prefix-20261111/source-export/kernel-package-0d42063e.json'
old_core = json.loads(core_path.read_text())
assert len(old_core['files']) == 78 and set(old_core['files']) <= set(manifest)
core = {n: manifest[n]['sha256'] for n in sorted(old_core['files'])}
core_delta = {n: {'before': old_core['files'][n], 'after': core[n]} for n in core if old_core['files'][n] != core[n]}
assert set(core_delta) == {'kernel/mutex.c'} and core['kernel/mutex.c'] == '014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564'
document('core-78-sha256.json', {'core_git_head': HEAD, 'code_file_count': 78, 'files': core,
                              'prior_core': old_core['core_git_head'], 'delta': core_delta})
document('source-derivation.json', {'status': 'FROZEN_COMMITTED_SOURCE_ONLY',
    'source_git_head': HEAD, 'names_from': str(OLD/'source-sha256.json'),
    'old_names_manifest_sha256': sha((OLD/'source-sha256.json').read_bytes()),
    'names_exactly_equal_old0798': list(manifest) == sorted(old),
    'files': 143, 'source_bytes': sum(x['bytes'] for x in manifest.values()),
    'changed_from_old0798': {n: {'before': old[n], 'after': manifest[n]} for n in manifest if old[n] != manifest[n]},
    'core78_delta_from_0d': core_delta, 'whole_worktree_status_at_export': global_status,
    'untracked_evidence_not_exported': True,
    'artifacts': {n: {'bytes': (OUT/n).stat().st_size, 'sha256': sha((OUT/n).read_bytes())}
                  for n in ('source.tar', 'source-sha256.json', 'source-state.json', 'core-78-sha256.json')}})

prior_args = json.loads((PRIOR/'source-host/rwsem-arguments.json').read_text())
argv = list(prior_args['argv'])
runner = BASE+'/input/tests/kernel/rwsem/run_rwsem_runtime_fixture.py'
argv[2] = runner
replacements = {'--repo': BASE+'/input', '--module': BASE+'/signed/kd_rwsem_runtime_fixture.ko',
    '--output': BASE+'/runtime', '--expected-release': '7.0.0-38-kdrebuild9',
    '--kernel-elf': KERNEL+'/build/vmlinux', '--kernel-config': KERNEL+'/build/.config',
    '--gs-proof-json': '__UNBOUND_FRESH_KERNEL9_GS_PROOF_ABSOLUTE_PATH__',
    '--gs-offset': '__UNBOUND_ACTUAL_KERNEL9_CURRENT_TASK_GS_OFFSET__',
    '--builtin-source-start': '__UNBOUND_ACTUAL_KERNEL9_ITS_RETURN_THUNK_ADDRESS__',
    '--builtin-source-size': '__UNBOUND_ACTUAL_KERNEL9_ITS_RETURN_THUNK_BYTES__'}
for key, value in replacements.items():
    argv[argv.index(key)+1] = value
document('rwsem-arguments.template.json', {'status': 'NONDISPATCHABLE_UNBOUND_ACTUAL_KERNEL9_INPUTS',
    'argv': argv, 'environment': prior_args['environment'], 'observer_seconds': prior_args['observer_seconds'],
    'host_source_git_head': HEAD, 'host_source_manifest_sha256': sha((OUT/'source-sha256.json').read_bytes()),
    'compiled_module': {'path': BASE+'/signed/kd_rwsem_runtime_fixture.ko',
                        'bytes': '__UNBOUND_ACTUAL_SIGNED_MODULE_BYTES__', 'sha256': '__UNBOUND_ACTUAL_SIGNED_MODULE_SHA256__'},
    'derivation': {'prior_file': str(PRIOR/'source-host/rwsem-arguments.json'),
                   'prior_sha256': sha((PRIOR/'source-host/rwsem-arguments.json').read_bytes()),
                   'only_modified_argv': ['runner_path', *replacements],
                   'all_workload_and_capacity_arguments_unchanged': True},
    'not_a_deterministic_race_reproduction': True})

make = ['/usr/bin/make', '-C', KERNEL+'/source', 'O='+KERNEL+'/build',
        'M='+BASE+'/input/tests/kernel/rwsem/payload', 'MO='+BASE+'/module-build',
        'KERNELRELEASE=7.0.0-38-kdrebuild9', '-j8', 'V=1', 'modules']
module = BASE+'/module-build/kd_rwsem_runtime_fixture.ko'
signed = BASE+'/signed/kd_rwsem_runtime_fixture.ko'
document('module-build-sign.template.json', {'status': 'NONDISPATCHABLE_PENDING_LINKED_KERNEL9_RECEIPTS',
    'source_root': BASE+'/input', 'kernel_source': KERNEL+'/source', 'kernel_build': KERNEL+'/build',
    'kernel_core_git_head': HEAD, 'source_git_head': HEAD,
    'argv': {'build': make, 'sign': [KERNEL+'/build/scripts/sign-file', 'sha512',
        KERNEL+'/build/certs/signing_key.pem', KERNEL+'/build/certs/signing_key.x509', signed],
        'modinfo': [['/usr/sbin/modinfo', '-F', field, signed] for field in ('vermagic', 'signer', 'sig_key', 'sig_hashalgo', 'depends')]},
    'between_build_and_sign': {'operation': 'exclusive lossless copy, fsync and retain both raw hashes',
                              'source_unsigned': module, 'destination_signed': signed},
    'expected_modinfo': {'vermagic_prefix': '7.0.0-38-kdrebuild9', 'signer': 'nonempty',
                        'sig_key': 'nonempty', 'sig_hashalgo': 'sha512', 'depends': ''},
    'bounds': {'module_seconds': 180, 'check_seconds': 60, 'total_seconds': 900,
               'log_bytes': 536870912, 'root_floor_bytes': 1073741824, 'output_floor_bytes': 4294967296},
    'fresh_inputs': {k: '__UNBOUND_ACTUAL_'+k.upper()+'__' for k in
        ('full_build_receipt_sha256', 'linked_kernel16_identity_sha256', 'source78_identity_sha256',
         'protected_identity_sha256', 'public_certificate_sha256', 'sign_tool_sha256',
         'make_sha256', 'modinfo_sha256', 'recovery_receipt_sha256')},
    'other_modules_or_tests_selected': [], 'private_key_data_recorded': False,
    'historical_warning_policy': 'Retain actual diagnostics; prior rwsem build had frame4352 and prototype warnings, not a warning-free baseline.'})

controller = PRIOR/'source-host/controller.py'
shutil.copyfile(controller, OUT/'prior-supervisor-reference.py')
document('supervisor-binding.template.json', {'status': 'NONDISPATCHABLE_REFERENCE_AND_BINDINGS_ONLY',
    'reference': 'prior-supervisor-reference.py', 'reference_sha256': sha(controller.read_bytes()),
    'family': 'rwsem', 'source_git_head': HEAD, 'kernel_core_git_head': HEAD,
    'kernel': KERNEL, 'root': BASE, 'expected_release': '7.0.0-38-kdrebuild9',
    'required_rebindings': {k: '__UNBOUND_ACTUAL_'+k.upper()+'__' for k in
        ('supervisor_sha256', 'arguments_sha256', 'build_receipt_sha256', 'module_build_receipt_sha256',
         'postboot_receipt_sha256', 'gs_proof_sha256', 'linked_build_id', 'fresh_boot_id',
         'initial_taint', 'allowed_post_module_taint', 'recovery_receipt_sha256',
         'metadata_helper_sha256', 'idle_helper_sha256')},
    'old_literal_bindings_must_not_be_reused': ['K02 predecessor/cleanup receipt', 'kernel8 full-build receipt',
        'a991 host-check receipt', 'e001 boot and4096 pre-run taint', 'old BuildID/GS/thunk/module hashes',
        'family mutex branch', 'old frozen source manifest/state and transport-helper constants'],
    'required_runtime_behavior': {'single_child': True, 'family': 'rwsem', 'observer_seconds': 660,
        'log_bytes': 33554432, 'root_floor_bytes': 1073741824, 'output_floor_bytes': 4294967296,
        'failure_or_timeout': 'Record exact child/result/error and preserve controls; no signals or force cleanup.',
        'success_status': 'protected_rwsem_jit_reader_mechanism_pass',
        'source_result': 'protected_episode_completed', 'full_c_function_return': 'outside_protected_episode_scope',
        'required_final_files': ['result.json', 'observations-final.bin', 'observations-final.json', 'shutdown-archive.json'],
        'ordinary_closure': ['child_actual_exit0', 'exact_final_wire_shutdown_archive_settle_end',
            'module_and_devices_absent', 'no_activity', 'source/kernel/protected_pins_unchanged'],
        'fresh_boot_taint_handling': 'Bind actual before taint0 and allow only the actual ordinary OOT-module4096 change; do not copy old same4096 rule.'},
    'scope': 'Private rwsem/query corrected-core regression only; not deterministic race reproduction, MM syscall validation or performance.'})

document('derivation-inputs.json', {str(p): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
    for p in (OLD/'source-sha256.json', OLD/'source-state.json', core_path,
              PRIOR/'source-host/rwsem-arguments.json', controller,
              R/'tests/evidence/kernel8-affected-build-20261111/collection/payload/attempt01/receipts/result.json',
              R/'tests/kernel/rwsem/payload/Kbuild', R/'tests/kernel/rwsem/run_rwsem_runtime_fixture.py')})
document('preparation-result.json', {'status': 'SOURCE_ONLY_PREPARATION_COMPLETE_RUNTIME_UNBOUND',
    'source_files': 143, 'source_bytes': sum(r['bytes'] for r in manifest.values()),
    'selected_core_files': 78, 'selected_runtime_families': ['rwsem'],
    'source_manifest_sha256': sha((OUT/'source-sha256.json').read_bytes()),
    'source_tar_sha256': sha((OUT/'source.tar').read_bytes()),
    'core78_only_code_delta': ['kernel/mutex.c'],
    'prior0798_changed_members': [n for n in manifest if old[n] != manifest[n]],
    'whole_worktree_clean_claim': False, 'vm_commands': 0, 'project_imports': 0,
    'tests_or_builds': 0, 'script_sha256': sha(Path(__file__).read_bytes())})
print(json.dumps(json.loads((OUT/'preparation-result.json').read_text()), sort_keys=True))
