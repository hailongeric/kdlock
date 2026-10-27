"""Explicit Linux 7 enabled-MM mode admission shared by current MM runners."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'bench/mmap_fault'))
import timing as common
rt = common.rt
RELEASE = '7.0.0-38-kdmm1'
BUILD = Path('/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build')
MODES = {'native': 'off', 'kd': 'on'}
BUNDLES = {mode: Path('/root/kdlock-kernel-baselines/linux70-kdmm1-'+mode+'-20261027')
           for mode in MODES}


def arguments(parser, *, required=True):
    parser.add_argument('--boot-id', required=required)
    parser.add_argument('--host-state', type=Path, required=required)
    parser.add_argument('--host-reference', type=Path, required=required)
    parser.add_argument('--host-reference-sha256', required=required)
    common.kernel_identity.arguments(parser)
    # An unspecified bundle is selected only from the explicit mode below.
    parser.set_defaults(kernel_source=BUILD, kernel_baseline=None, kernel_variant=None)


def guest(args):
    rt.require(args.mode in MODES and bool(args.boot_id), 'explicit MM mode/boot required')
    common.mm_platform.guest(args.boot_id, release=RELEASE)
    variant = 'kdmm1-'+args.mode
    rt.require(args.kernel_variant in (None, variant), 'selected kernel variant/mode differ')
    args.kernel_variant = variant
    if args.kernel_baseline is None:
        args.kernel_baseline = BUNDLES[args.mode]
    rt.require(args.kernel_source == BUILD and args.kernel_baseline == BUNDLES[args.mode],
               'exact enabled-MM build and per-mode bundle required')
    tokens = Path('/proc/cmdline').read_text().split()
    rt.require([token for token in tokens if token.startswith('kd_mmap=')] ==
               ['kd_mmap='+MODES[args.mode]], 'explicit built-in MM boot mode differs')


def binding(identity, build, bundle, mode):
    rt.require(mode in MODES and identity.get('ok') is True and identity.get('schema') == 2 and
               identity.get('runtime_policy_verified') is True and bool(identity.get('running_build_id')),
               'verified schema-2 enabled-MM identity required')
    config = (build/'.config').read_text().splitlines()
    rt.require('CONFIG_KDLOCK_MMAP=y' in config and
               '# CONFIG_KDLOCK_MMAP is not set' not in config,
               'enabled built-in MM adapter required')
    policy = identity['runtime_policy']
    rt.require(policy.get('mmap_mode') == MODES[mode] and
               [token for token in policy['cmdline'].split() if token.startswith('kd_mmap=')] ==
               ['kd_mmap='+MODES[mode]], 'verified runtime MM mode differs')
    manifest = json.loads((bundle/'manifest.json').read_text())
    rt.require(manifest.get('variant') == 'kdmm1-'+mode,
               'explicit enabled-MM manifest variant differs')
    return dict(release=RELEASE, build_id=identity['running_build_id'], variant='kdmm1-'+mode,
                configuration_sha256=rt.digest(build/'.config'),
                manifest_sha256=rt.digest(bundle/'manifest.json'), runtime_policy=policy,
                kernel_mmap_backend=mode, private_backing_locks=False,
                source_files=manifest['source_files'], build_files=manifest['build_files'])


def admit(args, out, *, strict=False):
    guest(args)
    rt.require(args.host_state and args.host_reference and args.host_reference_sha256,
               'fresh fixed-frequency host and hashed reference required')
    gate = common.host_check(args.host_state, out, strict, args.boot_id,
                            reference=args.host_reference, reference_sha256=args.host_reference_sha256)
    identity = common.kernel_identity.capture(args, out, rt.command)
    return dict(kernel_identity=identity,
                kernel_binding=binding(identity,args.kernel_source,args.kernel_baseline,args.mode),
                host_qualification=gate)


def verify_boot(args):
    rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == args.boot_id and
               [token for token in Path('/proc/cmdline').read_text().split() if token.startswith('kd_mmap=')] ==
               ['kd_mmap='+MODES[args.mode]], 'MM boot or backend changed')


def freeze_support(out):
    """Bind executed Python gates, including the copied-bundle verifier inputs."""
    files = {}
    directories = ('bench/mmap_fault','bench/mmap_writer','bench/spin_cacheline','bench/basic',
                   'kernel_integration/linux70','kernel_baseline','tests/protocols','disassem')
    paths={path for directory in directories for path in (ROOT/directory).rglob('*.py')
           if '__pycache__' not in path.parts}
    paths.update(ROOT/name for name in ('bench/archive_run.py','tests/kernel/mmap_writer/run.py',
                 'tests/kernel/mmap_writer/writer_sites.json','bench/mmap_lock/eligibility.py',
                 'disassem/compat/miasm-0.1.5-python314.patch'))
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        target = out/'runtime-source'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes())
        files[str(path)] = files[str(target)] = rt.digest(target)
    rt.write_json(out/'runtime-source-sha256.json',files)
    return files
