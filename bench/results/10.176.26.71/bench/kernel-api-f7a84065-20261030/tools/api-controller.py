#!/usr/bin/env python3
"""One admitted phase of the frozen original-body syscall comparison.

Source preparation only until invoked with --execute inside the intended VM.
No synchronization, installation, reboot, forced cleanup or automatic retry.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
BUILD = '/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdscope1-native-20261030'
RELEASE = '7.0.0-38-kdscope1'
PHASES = ('basic', 'objects', 'functional', 'measure')
WORKERS = [*range(1, 9), *range(12, 61, 4)]
CASES = ('setfd', 'pipebytes', 'pipecap')
RETIRE = dict(state=2, modules=0, frames=0, writers=0)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def checked(path, expected):
    require(re.fullmatch('[0-9a-f]{64}', expected or '') and digest(path) == expected,
            'reviewed input hash differs: '+str(path))
    return load(path)


def verify_basic(value, boot):
    require(value.get('passed') is True and value.get('final_idle') is True and
            value.get('boot_id') == boot and value.get('mode') == 'FUNCTIONAL_ONLY' and
            value.get('timing_started') is False, 'same-boot basic evidence incomplete')
    rows = value.get('results', [])
    require([row.get('family') for row in rows] == ['spin', 'mutex', 'rwlock', 'rwsem'] and
            all(row.get('passed') is True and row.get('drained') is True and
                row.get('execution') == 'RETURNED_JIT' and row.get('jit_completions', 0) > 0
                for row in rows), 'basic family set or returned-body evidence differs')


def verify_phase(value, phase, boot):
    if phase == 'basic':
        verify_basic(value, boot)
        return
    require(value.get('passed') is True and value.get('drained') is True and
            value.get('final_idle') is True and value.get('boot_id') == boot,
            'same-boot completed/drained evidence required: '+phase)
    rows = value.get('sessions', [])
    if phase == 'objects':
        expected = [(kind, arm) for kind in ('setfd', 'pipe') for arm in ('native', 'kd')]
        require(value.get('scored') is False and
                [(row.get('kind'), row.get('arm')) for row in rows] == expected,
                'semantic participant plan differs')
    else:
        expected = [(kind, arm, count) for kind in CASES
                    for count in ([16] if phase == 'functional' else WORKERS)
                    for arm in ('native', 'kd')]
        require(value.get('action') == phase and value.get('single_round') is True and
                [(row.get('kind'), row.get('arm'), row.get('workers')) for row in rows] == expected and
                all(row.get('round') == 0 and row.get('duration_ms') == 2000 and
                    row.get('collector_cpu') == 63 and row.get('cpus') == list(range(row['workers'])) and
                    row.get('instrumentation') == ('completion' if phase == 'functional' else 'none')
                    for row in rows), 'exact one-round syscall plan differs')
    for row in rows:
        require(row.get('passed') is True and row.get('drained') is True and
                row.get('execution_status') == 'COMPLETE' and row.get('retired') == RETIRE and
                row.get('api_bind') == 'Y', 'session protocol or retirement differs')
        if phase == 'objects':
            require(row.get('semantic', {}).get('joined') is True,
                    'semantic client did not join')
        elif phase == 'functional':
            counters = row.get('functional_jit', {})
            entered, returned = counters.get('entered'), counters.get('returned')
            require(type(entered) is int and type(returned) is int and entered == returned and
                    (entered > 0 if row['arm'] == 'kd' else entered == 0),
                    'required functional returned JIT is missing')
        else:
            require(row.get('jit_execution') == 'not-observed-in-scored-session' and
                    row.get('measurement', {}).get('ok') is True and
                    row.get('whole_throughput_ops_s', 0) > 0,
                    'scored receipt or execution classification differs')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=PHASES)
    generation_arguments(parser)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--snapshot', required=True)
    for name in ('source-state', 'source-manifest', 'host-reference', 'preinstall-result'):
        parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--'+name+'-sha256', required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require(args.campaign.is_absolute() and not args.campaign.is_relative_to(ROOT),
            'absolute external evidence campaign required')
    out = args.campaign/args.phase
    control = args.campaign/(args.phase+'-control')
    kernel = ['--kernel-variant', 'kdscope1-native', '--kernel-source', BUILD,
              '--kernel-baseline', BUNDLE]
    host = ['--host-state', str(args.host_state), '--host-reference', str(args.host_reference),
            '--host-reference-sha256', args.host_reference_sha256]
    if args.phase == 'basic':
        command = [PYTHON, 'bench/basic/run.py', *kernel, *host, '--snapshot-tag', args.snapshot,
                   '--families', 'spin', 'mutex', 'rwlock', 'rwsem', '--output', str(out)]
    elif args.phase == 'objects':
        command = [PYTHON, 'tests/kernel/api_objects/run.py', *kernel, *host,
                   '--boot-id', args.boot_id, '--output', str(out)]
    else:
        command = [PYTHON, 'bench/kernel_api/run.py', args.phase, *kernel, *host,
                   '--boot-id', args.boot_id, '--output', str(out)]
        if args.phase == 'measure':
            command += ['--functional-result', str(args.campaign/'functional/result.json')]
    receipt = dict(schema=1, executed=False, source_commit=args.source_commit,
                   kernel_project_commit=KERNEL_PROJECT_COMMIT,
                   generation_record_sha256=args.generation_record_sha256, phase=args.phase,
                   boot_id=args.boot_id, release=RELEASE, argv=command, output=str(out),
                   scored=args.phase == 'measure', planned_points=126 if args.phase == 'measure' else 0,
                   rounds_per_point=1, performance_accepted=False, host_endpoint='PENDING',
                   limits=['Linked source-site/bridge evidence is retained; live binding is checked by the functional phases.',
                           'Scored sessions do not observe returned JIT; functional proof is separate.'])
    if not args.execute:
        print(json.dumps(receipt, indent=2))
        return
    require(os.geteuid() == 0 and os.uname().release == RELEASE and sys.executable == PYTHON,
            'root with pinned Python on the intended scope kernel required')
    require(not out.exists() and not control.exists(), 'preserve existing phase/attempt evidence')
    control.mkdir(parents=True)

    def save():
        temporary = control/'owner.tmp'
        temporary.write_text(json.dumps(receipt, indent=2)+'\n')
        temporary.replace(control/'owner.json')

    child = None
    completion_checked = False
    receipt.update(drain_unknown=False, child_started=False, child_returncode=None,
                   completed=False, final_idle=False, completion_checks_passed=False)
    receipt.update(executed=True, started=time.time(), state='ADMISSION', driver_pid=os.getpid())
    save()
    try:
        inputs = {'controller.py': Path(__file__), 'host-before.json': args.host_state,
                  'host-reference.json': args.host_reference, 'source-state.json': args.source_state,
                  'source-sha256.json': args.source_manifest, 'preinstall-result.json': args.preinstall_result,
                  'generation-record.json': args.generation_record,
                  'provenance-state.json': args.provenance_state,
                  'provenance-sha256.json': args.provenance_manifest}
        for name, original in inputs.items():
            shutil.copyfile(original, control/name)
        receipt['inputs'] = {name:digest(control/name) for name in inputs}
        save()
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
                'boot differs')
        require([word for word in Path('/proc/cmdline').read_text().split() if word.startswith('kd_mmap=')]
                == ['kd_mmap=off'], 'explicit Native MM mode required')
        require(not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT'),
                'do not export kernel build overrides')
        require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
                os.environ.get('KDLOCK_SNAPSHOT_TAG') == args.snapshot, 'verified actual snapshot required')
        receipt['generation'] = generation_inputs(args, digest)
        for owner_path in args.campaign.glob('*-control/owner.json'):
            if owner_path == control/'owner.json':
                continue
            owner = load(owner_path)
            require(owner.get('generation_record_sha256') == args.generation_record_sha256 and
                    owner.get('source_commit') == args.source_commit,
                    'API campaign contains another source generation: '+str(owner_path))
        source_state = checked(args.source_state, args.source_state_sha256)
        source_files = checked(args.source_manifest, args.source_manifest_sha256)
        require(source_state.get('git_head') == args.source_commit and not source_state.get('git_status') and
                source_state.get('files') == len(source_files) and bool(source_files),
                'clean frozen source generation differs')

        def verify_sources():
            for name, expected in source_files.items():
                relative = Path(name)
                require(not relative.is_absolute() and '..' not in relative.parts and
                        not (ROOT/relative).is_symlink() and digest(ROOT/relative) == expected,
                        'frozen source changed: '+name)

        verify_sources()
        before = load(args.host_state)
        checked(args.host_reference, args.host_reference_sha256)
        age = (datetime.datetime.now(datetime.timezone.utc)-
               datetime.datetime.fromisoformat(before['captured_utc'])).total_seconds()
        require(0 <= age < 240 and before.get('recovery_snapshot') == args.snapshot and
                before.get('snapshot_listed') is True, 'fresh actual-snapshot host capture required')
        preinstall = checked(args.preinstall_result, args.preinstall_result_sha256)
        require(preinstall.get('passed') is True and
                preinstall.get('state') == 'PREINSTALL_ARTIFACTS_VERIFIED_NOT_INSTALLED' and
                preinstall.get('source_commit') == KERNEL_PROJECT_COMMIT and preinstall.get('release') == RELEASE and
                preinstall.get('build') == BUILD and preinstall.get('site_count') == 3 and
                preinstall.get('static_bridge_count') == 4 and
                preinstall.get('kernel_source_build_unchanged') is True,
                'matching static preinstall artifacts required; this does not prove live ABI')
        receipt['kernel_preinstall_proof'] = dict(source_commit=KERNEL_PROJECT_COMMIT,
            sha256=args.preinstall_result_sha256, provider_reused=False,
            scope='Original kernel sites and build proof; not current provider validation')
        prerequisites = {}
        for phase in PHASES[:PHASES.index(args.phase)]:
            previous_control = args.campaign/(phase+'-control')/'owner.json'
            previous_result = args.campaign/phase/'result.json'
            owner, value = load(previous_control), load(previous_result)
            require(owner.get('state') == 'COMPLETE' and owner.get('source_commit') == args.source_commit and
                    owner.get('generation', {}).get('record_sha256') == args.generation_record_sha256 and
                    owner.get('boot_id') == args.boot_id and
                    owner.get('inputs', {}).get('source-sha256.json') == args.source_manifest_sha256 and
                    owner.get('result_sha256') == digest(previous_result),
                    'preceding controller source/boot/result binding differs: '+phase)
            verify_phase(value, phase, args.boot_id)
            prerequisites[str(previous_control)] = digest(previous_control)
            prerequisites[str(previous_result)] = digest(previous_result)
        receipt['prerequisites'] = prerequisites
        receipt['host_capture_age_seconds'] = age
        receipt['state'] = 'RUNNING'
        limit = {'basic':7200, 'objects':3600, 'functional':3600, 'measure':14400}[args.phase]
        env = dict(os.environ, PATH=str(Path(PYTHON).parent)+':/usr/sbin:/usr/bin:/sbin:/bin',
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C')
        with (control/'run.log').open('x') as stream:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     start_new_session=True)
            receipt.update(pid=child.pid, deadline_seconds=limit, child_started=True,
                           drain_unknown=True)
            save()
            try:
                code = child.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                receipt.update(state='DEADLINE_EXCEEDED_CHILD_RETAINED', drain_unknown=True)
                save()
                raise RuntimeError('child retained; inspect PID/modules/tasks before further action')
        receipt.update(returncode=code, child_returncode=code, finished=time.time())
        save()
        require(code == 0, 'runner failed; retain its evidence and any live state')
        result_path = out/'result.json'
        result = load(result_path)
        verify_phase(result, args.phase, args.boot_id)
        if args.phase in ('functional', 'measure'):
            current_inputs = result.get('source_sha256', {})
            require(bool(current_inputs) and all(source_files.get(name) == expected
                    for name, expected in current_inputs.items()), 'API provider source generation differs')
            binaries_path = out/'binaries.json'
            binaries = load(binaries_path)
            require(set(binaries) == {'provider', 'daemon', 'client', 'guard'} and
                    all(result.get('files', {}).get(item['path']) == item['sha256'] and
                        digest(Path(item['path'])) == item['sha256'] for item in binaries.values()),
                    'current API build artifact identity differs')
            receipt['provider_evidence'] = dict(source_commit=args.source_commit,
                binaries_sha256=digest(binaries_path), provider=binaries['provider'],
                validation='same-generation CONFIG-on runner build and functional prerequisites')
        verify_sources()
        require(receipt['generation'] == generation_inputs(args, digest),
                'generation changed during API phase')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id,
                'boot changed during phase')
        require(all(digest(Path(name)) == expected for name, expected in prerequisites.items()),
                'preceding evidence changed during phase')
        completion_checked = True
        receipt.update(state='COMPLETE', completed=True, final_idle=True, drain_unknown=False,
                       completion_checks_passed=True,
                       result_sha256=digest(result_path), finished=time.time())
        save()
        print(json.dumps(receipt, indent=2))
    except BaseException as error:
        receipt.update(completed=False, error=repr(error), failed=time.time())
        if receipt['state'] != 'DEADLINE_EXCEEDED_CHILD_RETAINED':
            receipt['state'] = 'FAILED'
        if child is not None:
            receipt.update(child_started=True, child_returncode=child.poll(),
                           drain_unknown=not completion_checked)
            # Exit status does not prove physical owners, frames or tasks retired.
            if not completion_checked:
                receipt['final_idle'] = False
        save()
        raise


if __name__ == '__main__':
    main()
