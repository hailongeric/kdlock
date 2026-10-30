#!/usr/bin/env python3
"""Draft one-step VM controller. Not executed during its source-only preparation.

No kernel install/reboot, host capture, synchronization, forced cleanup or retry.
Invoke once per step with a NEW host capture; a human/controller owns boot changes
and endpoint qualification. --execute is required to start a maintained runner.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path('/root/host_fs/kdlock')
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
BUILD = Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build')
UPSTREAM = '75f66e45697e6f5f49c33dd950c4e6b289198f8f'
STEPS = ('sites', 'api', 'mapping', 'faults', 'completed', 'shared-prepare',
         'shared-measure', 'mmap1-prepare', 'mmap1-identity', 'mmap1-measure')
PREREQUISITES = ('api', 'mapping', 'faults', 'completed')

# Distinct diagnostic-only adapter; frozen provider/scored sources stay at f7.
IDENTITY_RUNNER = Path('/tmp/kdlock-scope-mmap1-identity-runner-r1-20261030.py')
IDENTITY_RUNNER_SHA256 = '5c23db457fc9cfc91ff68c7f392e5c003812cb54a66fe082a0e73a0b459b6120'
IDENTITY_RUNNER_COMMIT = 'd22a36567de28c024ebb8d1c79997c0d39541bd2'
IDENTITY_MAINTAINED_SHA256 = '70f256264db17e60ebcfe5187595f5f403ed3d1f7cbab3e6a873410640311f37'

# Exact historical snapshot extras retained by nondeleting synchronization.
# These are not f7 tracked sources and are not built/run by the two basics or probe.
NATIVE_A_RETAINED_UNIT_SNAPSHOTS = {'tests/unit/infrastructure/test_jit_escape_runner.py': 'cb2b4cb51bca344719323a4da7927ee3871aa9887796e580faec8dd326bfaef2',
 'tests/unit/infrastructure/test_mutex_proxy_runner.py': '0ce62047039cb801b0182c49ada87eba5bf7f6473277577c67f9c3cea57936e0',
 'tests/unit/mutex/mutex_complete_fixture.c': '34481fe52f0f9aa58d320c60bb1ae25966a6adb1d2704d1552ea1b7cb0ca91d9',
 'tests/unit/mutex/mutex_custody_acquire_fixture.c': '5667c2ea6c1b0b975c96d1ea4a23e57f500e55f6209f9877c88d2e97561cbb65',
 'tests/unit/mutex/mutex_custody_fixture.c': '2e9bd6b60ed3196236927e87d2a7b15fda8feb9a9fd4494ac33cf8666595612c',
 'tests/unit/mutex/mutex_pin_diag_fixture.inc': '3dfbf5b4f76ad3148efb00538b2c634c16958be8bfec24e1ea8a85011f75b1aa',
 'tests/unit/mutex/mutex_pin_window_fixture.c': 'fe183e54a4aabe55e2f3d48c6f186667b5c4f9e69d0270185b89a601c89e9845',
 'tests/unit/mutex/mutex_proxy_pin_fixture.c': '1ffed92f0a2a4e3c6334b72108d7b6d6d25c089057a3ff286ded9c24870cc7ec',
 'tests/unit/mutex/mutex_publication_fixture.c': 'fe2bc4767ab43c7c1b9e6b12a3b9c70c713d9874cda31486c15caa18df33510a',
 'tests/unit/mutex/mutex_unlock_fixture.c': '226821098ac7b46e138c076b2994b5ca027ed2f6821688f931076d8cec8ad1e3',
 'tests/unit/mutex/mutex_wait_budget_fixture.c': '42dcb7681a8f912d9f541358bdd62ff760145619da16646575f15f77de0dd0a3',
 'tests/unit/mutex/test_mutex_complete.py': 'f5caaae8e5f2becd84c699cbd9377d2b72e53343c95c2795535bb5f729125493',
 'tests/unit/mutex/test_mutex_custody.py': '3d0e63659b5e3ea7ab6412d29460587ee857b13597f90963a0bcf58a333a1962',
 'tests/unit/mutex/test_mutex_custody_acquire.py': '2997180d96f3c87d3c2d2712a5a8f1ae0d403f96496800e60f774512860fb394',
 'tests/unit/mutex/test_mutex_pin_diag.py': '826b6d101f012391ce4abc4b9fa3c8ee0bda6b9a53553a9825753452cbf3d10a',
 'tests/unit/mutex/test_mutex_pin_window.py': '5e39ec0a1ad94772ef294ed22c62ceface52c4c97cb617987580ac8e509fc41a',
 'tests/unit/mutex/test_mutex_prefetch.py': 'ff01ee60bcb16d9f19bd18b6f5517254ad3af33b80d31813252d8b02cf1c8bd8',
 'tests/unit/mutex/test_mutex_proxy_pin.py': '4879f59347c25d350ec4e299f5da79a5341804249411be78f4067f1275dc94bf',
 'tests/unit/mutex/test_mutex_publication.py': '3eca2cf42f3bc3943a9a33fb72e4b28e38876901aea0da93fe493e28b77384c2',
 'tests/unit/mutex/test_mutex_unlock.py': '0e54508d2e3dbe45462ae2825fe4ffa44142e76041af14e75dd9801b838d9837',
 'tests/unit/mutex/test_mutex_wait_budget.py': '4847d51ee419052b3f96928bef0f686eb87b231604576a639f10959d103c544a'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Shared reviewed admission block; identical in the three r2 controllers.
KERNEL_PROJECT_COMMIT = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
API_SHARED_INPUTS = ('include/kd_config.h', 'include/kd_spin_type.h',
                     'include/kd_mutex_types.h', 'include/kd_api_control.h')


def generation_arguments(parser, *, source_arguments=True):
    if source_arguments:
        parser.add_argument('--source-commit', required=True)
    parser.add_argument('--provenance-root', type=Path, required=True)
    for name in ('provenance-state', 'provenance-manifest', 'generation-record'):
        parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--'+name+'-sha256', required=True)


def generation_inputs(args, digest_file):
    """Authenticate two source generations; never reinterpret an old receipt."""
    def checked_json(path, expected):
        require(path.is_absolute() and path.resolve() == path and not path.is_symlink()
                and path.is_file() and re.fullmatch('[0-9a-f]{64}', expected or '')
                and digest_file(path) == expected, 'generation receipt differs: '+str(path))
        return json.loads(path.read_text())

    def sources(root, state_path, state_sha, manifest_path, manifest_sha, commit):
        require(re.fullmatch('[0-9a-f]{40}', commit or '') and root.is_absolute()
                and root.resolve() == root and not root.is_symlink() and root.is_dir(),
                'canonical source root and exact commit required')
        state = checked_json(state_path, state_sha)
        files = checked_json(manifest_path, manifest_sha)
        require(state.get('git_head') == commit and not state.get('git_status') and
                type(files) is dict and bool(files) and state.get('files') == len(files),
                'clean source generation differs: '+str(root))
        for name, expected in files.items():
            relative = Path(name)
            path = root/relative
            require(type(name) is str and not relative.is_absolute() and '..' not in relative.parts
                    and str(relative) == name and path.resolve() == path and path.is_file()
                    and not path.is_symlink() and re.fullmatch('[0-9a-f]{64}', expected or '')
                    and digest_file(path) == expected, 'source generation changed: '+str(path))
        return files

    expected_root = Path('/mnt/kdlock-builds/kdlock-kernel-provenance')/KERNEL_PROJECT_COMMIT
    require(args.provenance_root == expected_root and not ROOT.is_relative_to(expected_root),
            'separate canonical immutable kernel provenance root required')
    current = sources(ROOT, args.source_state, args.source_state_sha256,
                      args.source_manifest, args.source_manifest_sha256, args.source_commit)
    original = sources(args.provenance_root, args.provenance_state, args.provenance_state_sha256,
                       args.provenance_manifest, args.provenance_manifest_sha256,
                       KERNEL_PROJECT_COMMIT)
    binding = dict(schema=1, provider_source_commit=args.source_commit,
        provider_source_state_sha256=args.source_state_sha256,
        provider_source_manifest_sha256=args.source_manifest_sha256,
        kernel_project_commit=KERNEL_PROJECT_COMMIT, provenance_root=str(args.provenance_root),
        provenance_state_sha256=args.provenance_state_sha256,
        provenance_manifest_sha256=args.provenance_manifest_sha256)
    require(not args.generation_record.is_relative_to(ROOT) and
            not args.generation_record.is_relative_to(args.provenance_root),
            'campaign generation record must be outside both source roots')
    require(checked_json(args.generation_record, args.generation_record_sha256) == binding,
            'campaign provider/kernel generation binding differs')
    prefixes = ('kernel_integration/', 'kernel_baseline/')
    old_recipes = {name for name in original if name.startswith(prefixes)}
    new_recipes = {name for name in current if name.startswith(prefixes)}
    require(old_recipes and old_recipes == new_recipes,
            'current and original kernel recipe pathname sets differ')
    required = old_recipes | set(API_SHARED_INPUTS)
    require(required <= current.keys() and required <= original.keys() and
            all(current[name] == original[name] for name in required),
            'current API ABI inputs or kernel recipe bytes differ from built kernel generation')
    preparation = {}
    for label, path in (
        ('mmap', Path('/mnt/kdlock-builds/kdscope1-mmap-prepare/prepare.json')),
        ('api', Path('/mnt/kdlock-builds/kdscope1-api-prepare-r2/prepare.json')),
        ('composition', Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/composition.json'))):
        require(path.resolve() == path and path.is_file() and not path.is_symlink(),
                'canonical preparation receipt required: '+label)
        value = json.loads(path.read_text())
        inputs = value.get('inputs', {})
        require(value.get('passed') is True and type(inputs) is dict and bool(inputs) and
                all(original.get(name) == expected for name, expected in inputs.items()),
                'built kernel preparation does not match original source generation: '+label)
        preparation[label] = dict(path=str(path), sha256=digest_file(path))
    return dict(binding=binding, record=str(args.generation_record),
                record_sha256=args.generation_record_sha256,
                compatible_kernel_api_inputs={name:original[name] for name in sorted(required)},
                preparation=preparation)
# End shared generation admission block.


def reusable_native_probe(args, sources):
    """Derive a runner prebuilt receipt from one completed ordinary Native-A run."""
    original = args.campaign/'native-a'
    owner_path = original/'api-controller.json'
    result_path = original/'api/result.json'
    require(args.reuse_probe_owner == owner_path and
            digest(owner_path) == args.reuse_probe_owner_sha256,
            'exact reviewed Native-A API owner required for probe reuse')
    owner = json.loads(owner_path.read_text())
    require(owner.get('boot') == 'native-a' and owner.get('step') == 'api' and
            owner.get('state') == 'COMPLETE' and owner.get('passed') is True and
            owner.get('drained') is True and owner.get('final_idle') is True and
            owner.get('completion_checks_passed') is True and
            owner.get('drain_unknown') is False and owner.get('child_returncode') == 0 and
            owner.get('source_commit') == args.source_commit and
            owner.get('source_manifest_sha256') == args.source_manifest_sha256 and
            owner.get('source_state_sha256') == args.source_state_sha256 and
            owner.get('generation_record_sha256') == args.generation_record_sha256 and
            owner.get('output') == str(original/'api') and
            owner.get('expected_boot_id') != args.boot_id and
            owner.get('result_sha256') == digest(result_path),
            'Native-A API owner completion/source/result differs')
    result = json.loads(result_path.read_text())
    require(result.get('state') == 'COMPLETE' and result.get('passed') is True and
            result.get('drained') is True and result.get('source_unchanged') is True and
            result.get('mode') == 'native' and result.get('boot_id') == owner['expected_boot_id'] and
            result.get('basic_programs') == 2 and 'reused_probe' not in result and
            result.get('probe', {}).get('use_kd') == 0 and
            result['probe'].get('errors') == 0 and result['probe'].get('idle') == 1,
            'reuse requires the successful original Native-A build and fresh probe')
    manifest_path = original/'api/source-sha256.json'
    captured = json.loads(manifest_path.read_text())
    selected = {}
    prefixes = ('tests/kernel/mmap_lock/', 'tests/unit/', 'include/', 'daemon/')
    for name, expected in sources.items():
        relative = Path(name)
        if (name.startswith(prefixes) and
                not any(part.startswith('.') or part == '__pycache__' for part in relative.parts) and
                not relative.name.endswith('.mod.c') and
                (relative.suffix in ('.c', '.h', '.inc', '.S', '.py', '.def') or
                 relative.name == 'Makefile')):
            selected[name] = expected
    require(bool(selected) and not (selected.keys() & NATIVE_A_RETAINED_UNIT_SNAPSHOTS.keys()) and
            captured == {**selected, **NATIVE_A_RETAINED_UNIT_SNAPSHOTS},
            'probe/basic tracked inputs or exact retained unit snapshots differ')
    bindings = {str(owner_path):args.reuse_probe_owner_sha256,
                str(result_path):owner['result_sha256'], str(manifest_path):digest(manifest_path)}
    for name, expected in captured.items():
        path = original/'api/source'/name
        require(digest(path) == expected, 'original probe/basic source changed: '+name)
        bindings[str(path)] = expected
    # The fresh runner snapshots these same retained files; bind them separately
    # without relabeling them as part of the tracked source generation.
    for name, expected in NATIVE_A_RETAINED_UNIT_SNAPSHOTS.items():
        require(digest(ROOT/name) == expected, 'retained original unit snapshot changed: '+name)
        bindings[str(ROOT/name)] = expected
    for name in ('basic.log', 'build.log', 'dependencies.log'):
        path = original/'api'/name
        require(path.is_file(), 'original ordinary build evidence missing: '+name)
        bindings[str(path)] = digest(path)
    module = original/'api/source/tests/kernel/mmap_lock/payload/kd_mmap_probe.ko'
    require(digest(module) == result.get('probe_sha256'), 'original probe module changed')
    kernel = result.get('kernel_binding', {})
    vmlinux = BUILD/'vmlinux'
    require(kernel.get('release') == '7.0.0-38-kdscope1' and
            kernel.get('variant') == 'kdscope1-native' and
            kernel.get('kernel_mmap_backend') == 'native' and
            kernel.get('build_files', {}).get('vmlinux') == digest(vmlinux) and
            kernel.get('configuration_sha256') == digest(BUILD/'.config'),
            'probe reuse requires the same compiled kernel ELF/configuration')
    # The existing runner compares this compiled BTF with the current live BTF,
    # requires split BTF in the module, and rechecks the release before loading.
    from elftools.elf.elffile import ELFFile
    with vmlinux.open('rb') as stream:
        section = ELFFile(stream).get_section_by_name('.BTF')
        require(section is not None, 'compiled base BTF unavailable for probe reuse')
        base_btf = hashlib.sha256(section.data()).hexdigest()
    bindings.update({str(module):result['probe_sha256'],
                     str(vmlinux):kernel['build_files']['vmlinux'],
                     str(BUILD/'.config'):kernel['configuration_sha256']})
    origin = dict(owner=str(owner_path), owner_sha256=args.reuse_probe_owner_sha256,
                  result=str(result_path), result_sha256=owner['result_sha256'],
                  boot_id=result['boot_id'], source_commit=args.source_commit,
                  source_manifest_sha256=args.source_manifest_sha256,
                  source_state_sha256=args.source_state_sha256,
                  generation_record_sha256=args.generation_record_sha256,
                  tracked_snapshot_files=len(selected),
                  retained_untracked_unit_snapshots=NATIVE_A_RETAINED_UNIT_SNAPSHOTS)
    prebuilt = dict(schema=1, passed=True,
                    purpose='Reuse build/basic evidence; each boot executes a fresh probe.',
                    source={name:expected for name, expected in captured.items()
                            if name.startswith('tests/kernel/mmap_lock/payload/')},
                    module=str(module), sha256=result['probe_sha256'],
                    vmlinux_sha256=kernel['build_files']['vmlinux'], base_btf_sha256=base_btf,
                    origin=origin, basic_programs_reused=2)
    return prebuilt, bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boot', choices=('native-a', 'kd', 'native-b', 'kd-b'))
    parser.add_argument('step', choices=STEPS)
    generation_arguments(parser, source_arguments=False)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--source-manifest-sha256', required=True)
    parser.add_argument('--source-state', type=Path, required=True)
    parser.add_argument('--source-state-sha256', required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--host-reference', type=Path, required=True)
    parser.add_argument('--host-reference-sha256', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--writer-sites-sha256', help='reviewed exact current-boot sites receipt')
    parser.add_argument('--reuse-probe-owner', type=Path,
                        help='completed ordinary native-a/api-controller.json; later api boots only')
    parser.add_argument('--reuse-probe-owner-sha256',
                        help='reviewed exact Native-A API controller receipt SHA256')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    reuse_probe = args.reuse_probe_owner is not None
    require(reuse_probe == (args.reuse_probe_owner_sha256 is not None),
            'probe reuse requires both the original owner path and its SHA256')
    if reuse_probe:
        require(args.step == 'api' and args.boot in ('kd', 'native-b', 'kd-b') and
                re.fullmatch('[0-9a-f]{64}', args.reuse_probe_owner_sha256 or ''),
                'probe reuse is only a hash-bound later-boot API action')
    require(args.campaign.is_absolute() and not args.campaign.is_relative_to(ROOT),
            'external absolute evidence campaign required')
    require(re.fullmatch('[0-9a-f]{40}', args.source_commit), 'exact frozen Git commit required')
    require(re.fullmatch('[0-9a-f]{64}', args.host_reference_sha256), 'exact host reference hash required')
    mode = 'kd' if args.boot.startswith('kd') else 'native'
    base = args.campaign / args.boot
    out = base / args.step
    active_log = args.campaign.with_name(args.campaign.name+'-controller-logs') / args.boot / (args.step+'-r4.log')
    archived_log = base/(args.step+'-controller.log')
    reuse_path = base/'api-reuse-probe.json'
    variant = 'kdscope1-' + mode
    kernel = ['--kernel-variant', variant, '--kernel-source', str(BUILD),
              '--kernel-baseline', '/root/kdlock-kernel-baselines/linux70-'+variant+'-20261030']
    host = ['--host-state', str(args.host_state), '--host-reference', str(args.host_reference),
            '--host-reference-sha256', args.host_reference_sha256]
    platform = ['--mode', mode, '--boot-id', args.boot_id, *kernel, *host]
    checks = [item for name in PREREQUISITES
              for item in ('--'+name+'-result', str(base/name/'result.json'))]
    original = args.campaign/'native-a'/'shared-prepare'
    kdprep = args.campaign/'kd'/'shared-prepare'
    mmap_inputs = args.campaign/'native-a'/'mmap1-prepare'/'inputs.json'
    if args.step == 'sites':
        command = [PYTHON, 'bench/mmap_writer/sites.py', '--mode', mode,
                   '--boot-id', args.boot_id, *kernel, '--output', str(out)]
    elif args.step == 'api':
        command = [PYTHON, 'tests/kernel/mmap_lock/run.py', *platform, '--output', str(out)]
        if reuse_probe:
            command += ['--reuse-probe', str(reuse_path)]
    elif args.step == 'mapping':
        require(re.fullmatch('[0-9a-f]{64}', args.writer_sites_sha256 or ''),
                'review sites disassembly, then supply the exact receipt hash')
        command = [PYTHON, 'tests/kernel/mmap_lock/mapping.py', *platform,
                   '--api-result', str(base/'api/result.json'),
                   '--writer-sites', str(base/'sites/writer-sites.json'),
                   '--writer-sites-sha256', args.writer_sites_sha256, '--output', str(out)]
    elif args.step in ('faults', 'completed'):
        runner = ('tests/kernel/mmap_lock/faults.py' if args.step == 'faults' else
                  'tests/kernel/mmap_lock/page_fault_completed/run.py')
        command = [PYTHON, runner, *platform, '--output', str(out)]
    elif args.step == 'shared-prepare':
        require(args.boot in ('native-a', 'kd'), 'later boots reuse the original preparation')
        command = [PYTHON, 'bench/mmap_writer/linux70.py', 'prepare', *platform,
                   *checks, '--output', str(out)]
        if args.boot == 'kd':
            command += ['--reuse-inputs', str(original/'inputs.json')]
    elif args.step == 'shared-measure':
        require(args.boot in ('kd', 'native-b'), 'localized measurements use KD then Native-B')
        selected, other = (kdprep, original) if mode == 'kd' else (original, kdprep)
        command = [PYTHON, 'bench/mmap_writer/linux70.py', 'measure', *platform,
                   *checks, '--inputs', str(selected/'inputs.json'),
                   '--other-preparation', str(other/'result.json'),
                   '--exploratory-host', '--output', str(out)]
    elif args.step == 'mmap1-prepare':
        require(args.boot == 'native-a' and args.upstream is not None,
                'build the unchanged pinned pair exactly once on Native-A')
        command = [PYTHON, 'bench/mmap1/run.py', 'prepare', *platform,
                   '--upstream', str(args.upstream), '--output', str(out)]
    elif args.step == 'mmap1-identity':
        command = [PYTHON, str(IDENTITY_RUNNER), *platform,
                   '--inputs', str(mmap_inputs), '--output', str(out)]
    else:
        require(args.boot in ('native-b', 'kd-b'),
                'finish and review both localized grids before final mmap1 measurement')
        command = [PYTHON, 'bench/mmap1/run.py', 'measure', *platform, *checks,
                   '--inputs', str(mmap_inputs), '--identity-result', str(base/'mmap1-identity/result.json'),
                   '--model', 'both', '--output', str(out)]
    receipt = dict(schema=1, draft=True, executed=False, boot=args.boot, step=args.step,
                   expected_boot_id=args.boot_id, source_commit=args.source_commit,
                   kernel_project_commit=KERNEL_PROJECT_COMMIT,
                   generation_record_sha256=args.generation_record_sha256,
                   cwd=str(ROOT), argv=command, output=str(out),
                   active_child_log=str(active_log), archived_child_log=str(archived_log),
                   child_log_archived=False,
                   upstream_revision=UPSTREAM, host_endpoint='PENDING',
                   limitation='A runner PASS is not host endpoint/performance acceptance.')
    if args.step == 'mmap1-identity':
        receipt['diagnostic_runner'] = dict(path=str(IDENTITY_RUNNER),
            sha256=IDENTITY_RUNNER_SHA256, source_commit=IDENTITY_RUNNER_COMMIT,
            maintained_sha256=IDENTITY_MAINTAINED_SHA256)
    if reuse_probe:
        receipt['probe_reuse'] = dict(original_owner=str(args.reuse_probe_owner),
            original_owner_sha256=args.reuse_probe_owner_sha256, receipt=str(reuse_path),
            reused_basic_programs=2, reused_payload_build=True, fresh_probe_passed=False)
    if not args.execute:
        print(json.dumps(receipt, indent=2))
        return
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdscope1', 'VM root/scope kernel required')
    require(sys.executable == PYTHON, 'run this controller with the pinned guest Python')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id, 'boot differs')
    require(not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT'),
            'do not export kernel build overrides into external-module runners')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == args.snapshot, 'confirmed actual recovery snapshot required')
    receipt['generation'] = generation_inputs(args, digest)
    for owner_path in args.campaign.glob('*/*-controller.json'):
        owner = json.loads(owner_path.read_text())
        require(owner.get('generation_record_sha256') == args.generation_record_sha256 and
                owner.get('source_commit') == args.source_commit,
                'MM campaign contains another source generation: '+str(owner_path))
    # Maintained synchronization transfers tracked bytes, not the Git directory.
    # Authenticate its host-created snapshot manifests instead of assuming .git.
    require(digest(args.source_state) == args.source_state_sha256 and
            digest(args.source_manifest) == args.source_manifest_sha256, 'sync manifest hashes differ')
    state = json.loads(args.source_state.read_text())
    sources = json.loads(args.source_manifest.read_text())
    require(state.get('git_head') == args.source_commit and not state.get('git_status') and
            state.get('files') == len(sources) and bool(sources), 'clean frozen snapshot identity differs')
    for name, expected in sources.items():
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts and
                not (ROOT/path).is_symlink() and digest(ROOT/path) == expected,
                'frozen transferred input changed: '+name)
    require(digest(args.host_reference) == args.host_reference_sha256, 'reference hash differs')
    current = json.loads(args.host_state.read_text())
    age = (datetime.datetime.now(datetime.timezone.utc) -
           datetime.datetime.fromisoformat(current['captured_utc'])).total_seconds()
    require(0 <= age < 240, 'fresh capture required (controller margin; runner limit is 300 s)')
    require(current['recovery_snapshot'] == args.snapshot, 'capture snapshot differs')
    require(not out.exists(), 'step evidence already exists; preserve it and do not silently retry')
    if args.step == 'mmap1-measure':
        # A changed boot label must not silently add a second scored round.
        alternative = {'native-a': 'native-b', 'native-b': 'native-a', 'kd': 'kd-b', 'kd-b': 'kd'}
        alternate = args.campaign/alternative[args.boot]/'mmap1-measure'
        require(not alternate.exists(), 'this mode already has an mmap1 measurement attempt')
        localized = {}
        for label, backend in (('kd', 'kd'), ('native-b', 'native')):
            result_path = args.campaign/label/'shared-measure'/'result.json'
            result = json.loads(result_path.read_text())
            points = result.get('sessions', [])
            require(result.get('passed') is True and result.get('drained') is True and
                    result.get('mode') == backend and result.get('action') == 'measure' and
                    result.get('single_round') is True and len(points) == 21 and
                    [point.get('threads') for point in points] ==
                    [*range(1, 9), *range(12, 61, 4)] and
                    all(point.get('passed') is True and point.get('drained') is True
                        for point in points), 'localized grid incomplete: '+label)
            localized[label] = dict(path=str(result_path), sha256=digest(result_path))
        receipt['localized_completed_results'] = localized
        receipt['localized_performance_review'] = 'external controller obligation; not inferred from PASS'
    prior_controls = []
    if args.step == 'shared-prepare' and args.boot == 'kd':
        prior_controls.append(args.campaign/'native-a/shared-prepare-controller.json')
    if args.step == 'shared-measure':
        prior_controls += [args.campaign/label/'shared-prepare-controller.json'
                           for label in ('native-a', 'kd')]
    if args.step in ('mmap1-identity', 'mmap1-measure'):
        prior_controls.append(args.campaign/'native-a/mmap1-prepare-controller.json')
    if args.step == 'mmap1-measure':
        prior_controls += [base/'mmap1-identity-controller.json',
                           args.campaign/'kd/shared-measure-controller.json',
                           args.campaign/'native-b/shared-measure-controller.json']
    if args.step in ('mapping', 'shared-prepare', 'shared-measure', 'mmap1-measure'):
        needed = ('sites', 'api') if args.step == 'mapping' else PREREQUISITES
        prior_controls += [base/(name+'-controller.json') for name in needed]
    prebuilt, bindings = ({}, {})
    if reuse_probe:
        require(not reuse_path.exists(), 'preserve prior probe reuse receipt; no silent retry')
        prebuilt, bindings = reusable_native_probe(args, sources)
    if args.step == 'mmap1-identity':
        require(digest(IDENTITY_RUNNER) == IDENTITY_RUNNER_SHA256,
                'diagnostic-only identity runner differs')
        bindings[str(IDENTITY_RUNNER)] = IDENTITY_RUNNER_SHA256
    for path in prior_controls:
        owner = json.loads(path.read_text())
        expected_step = path.name.removesuffix('-controller.json')
        require(owner.get('step') == expected_step and expected_step in STEPS,
                'prerequisite step identity differs: '+str(path))
        expected_result = path.parent/expected_step/('writer-sites.json' if expected_step == 'sites' else 'result.json')
        require(owner.get('state') == 'COMPLETE' and owner.get('passed') is True and
                owner.get('source_commit') == args.source_commit and
                owner.get('generation_record_sha256') == args.generation_record_sha256 and
                owner.get('result_sha256') == digest(expected_result),
                'reused prerequisite source/result differs: '+str(path))
        if path.parent == base:
            require(owner.get('expected_boot_id') == args.boot_id,
                    'same-boot MM prerequisite differs: '+str(path))
        bindings[str(path)] = digest(path)
        bindings[str(expected_result)] = digest(expected_result)
    receipt['prerequisite_bindings'] = bindings
    base.mkdir(parents=True, exist_ok=True)
    control = base/(args.step+'-controller.json')
    require(not control.exists(), 'controller receipt already exists')
    receipt.update(executed=True, draft=False, host_state_sha256=digest(args.host_state),
                   source_manifest_sha256=args.source_manifest_sha256,
                   source_state_sha256=args.source_state_sha256)
    # Close staged owner writes before exposing the replacement in evidence.
    # RUNNING updates can otherwise race the child's parent-scope idle scan.
    active_log.parent.mkdir(parents=True, exist_ok=True)
    def save():
        temporary = active_log.parent/('.'+control.name+'.tmp')
        with temporary.open('w') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(control)

    child = None
    completion_checked = False
    receipt.update(state='ADMISSION', passed=False, drained=False, final_idle=False,
                   child_started=False, child_returncode=None, drain_unknown=False,
                   completion_checks_passed=False)
    save()
    env = dict(os.environ, PATH=str(Path(PYTHON).parent)+':/usr/sbin:/usr/bin:/sbin:/bin',
               PYTHONDONTWRITEBYTECODE='1', LC_ALL='C')
    limit = 5400 if args.step == 'mmap1-measure' else 3600
    try:
        if reuse_probe:
            with reuse_path.open('x') as stream:
                json.dump(prebuilt, stream, indent=2, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            bindings[str(reuse_path)] = digest(reuse_path)
            receipt['probe_reuse'].update(receipt_sha256=bindings[str(reuse_path)],
                                          origin=prebuilt['origin'])
            save()
        # Runner idle checks inspect the whole per-boot evidence directory.
        # Keep both parent and child log descriptors outside that scope.
        require(not archived_log.exists(), 'preserve the prior controller log')
        with active_log.open('x') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            receipt.update(state='RUNNING', pid=child.pid, deadline_seconds=limit,
                           child_started=True, drain_unknown=True)
            save()
            try:
                code = child.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                receipt.update(state='DEADLINE_EXCEEDED_CHILD_RETAINED', passed=False,
                               drained=False, drain_unknown=True)
                save()
                raise RuntimeError('child retained: inspect PID/modules/tasks before any further action')
        receipt.update(returncode=code, child_returncode=code)
        save()
        # The child exited and our descriptor closed. Keep the external original;
        # a copied failed-run log does not establish inherited-writer drain.
        with active_log.open('rb') as source_log, archived_log.open('xb') as saved_log:
            shutil.copyfileobj(source_log, saved_log)
            saved_log.flush()
            os.fsync(saved_log.fileno())
        receipt.update(child_log_archived=True, archived_child_log_sha256=digest(archived_log))
        save()
        require(code == 0, 'runner failed; retain its evidence and any live state')
        require(receipt['generation'] == generation_inputs(args, digest),
                'generation changed during MM step')
        require(all(digest(Path(name)) == expected for name, expected in bindings.items()),
                'MM prerequisite evidence changed during step')
        result_path = out/('writer-sites.json' if args.step == 'sites' else 'result.json')
        result = json.loads(result_path.read_text())
        receipt.update(result_sha256=digest(result_path), runner_drained=result.get('drained'),
                       runner_final_idle=result.get('final_idle'))
        passed = (result.get('captured') is True if args.step == 'sites' else
                  result.get('passed') is True and result.get('drained') is True)
        require(passed, 'step result failed; preserve all artifacts, no automatic cleanup or retry')
        if args.step == 'mmap1-identity':
            diagnostic = result.get('diagnostic_runner', {})
            retained_runner = out/'diagnostic-runner.py'
            require(diagnostic.get('path') == str(IDENTITY_RUNNER) and
                    diagnostic.get('retained') == str(retained_runner) and
                    diagnostic.get('source_commit') == IDENTITY_RUNNER_COMMIT and
                    diagnostic.get('maintained_sha256') == IDENTITY_MAINTAINED_SHA256 and
                    diagnostic.get('sha256') == IDENTITY_RUNNER_SHA256 and
                    result.get('files', {}).get(str(IDENTITY_RUNNER)) == IDENTITY_RUNNER_SHA256 and
                    result['files'].get(str(retained_runner)) == IDENTITY_RUNNER_SHA256 and
                    digest(retained_runner) == IDENTITY_RUNNER_SHA256 and
                    'kd_mmap1_identity.mod.c' not in result.get('source_sha256', {}),
                    'diagnostic runner binding or corrected build-source snapshot differs')
        if reuse_probe:
            require(result.get('boot_id') == args.boot_id and result.get('mode') == mode and
                    result.get('source_unchanged') is True and result.get('basic_programs') == 0 and
                    result.get('reused_probe') == str(reuse_path) and
                    result.get('probe_sha256') == prebuilt['sha256'] and
                    result.get('base_btf_sha256') == prebuilt['base_btf_sha256'] and
                    result.get('probe', {}).get('use_kd') == int(mode == 'kd') and
                    result['probe'].get('errors') == 0 and result['probe'].get('idle') == 1 and
                    digest(out/'prebuilt.json') == bindings[str(reuse_path)],
                    'fresh current-boot probe execution or reused artifact differs')
        # Reuse the maintained read-only task/module idle check. The active helper
        # and its dependencies are bound by generation_inputs(), never a bundle.
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location('scope_mmap_final_idle', ROOT/'bench/mmap1/run.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.idle()
        helper.mm.writer.check.idle(out)
        receipt['idle_check'] = dict(helpers=['bench/mmap1/run.py:idle',
            'tests/kernel/mmap_writer/run.py:idle'], evidence_scope=str(out), passed=True)
        require(receipt['generation'] == generation_inputs(args, digest),
                'generation changed during MM completion checks')
        require(all(digest(Path(name)) == expected for name, expected in bindings.items()),
                'MM prerequisite evidence changed during completion checks')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
                'boot changed during MM step')
        if reuse_probe:
            receipt['probe_reuse']['fresh_probe_passed'] = True
        completion_checked = True
        # Sites is a read-only capture and has no runner retirement assertion.
        # Do not manufacture drained=true from captured=true or a zero exit.
        receipt.update(state='COMPLETE', passed=True, final_idle=True, drain_unknown=False,
                       completion_checks_passed=True,
                       drained=None if args.step == 'sites' else result['drained'])
        save()
        print(json.dumps(receipt, indent=2))
    except BaseException as error:
        receipt.update(passed=False, error=repr(error))
        if receipt['state'] != 'DEADLINE_EXCEEDED_CHILD_RETAINED':
            receipt['state'] = 'FAILED'
        if child is not None:
            receipt.update(child_started=True, child_returncode=child.poll(),
                           drain_unknown=not completion_checked)
            # An exited runner may leave live kernel work. Keep that uncertainty
            # until its explicit completion, retirement and idle checks pass.
            if not completion_checked:
                receipt.update(drained=False, final_idle=False)
        save()
        raise


if __name__ == '__main__':
    main()
