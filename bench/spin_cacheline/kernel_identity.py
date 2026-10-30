#!/usr/bin/env python3
"""Check the selected legacy or Linux 7 kernel identity bundle.

An experimental kernel has its own captured bundle; the original baseline is
never rewritten or silently skipped. All named source/config/build files and
the running Build ID must match before any workload is loaded.
"""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ('kdlock1', 'kdmm1-native', 'kdmm1-kd', 'kdscope1-native', 'kdscope1-kd',
            'kdscope2-native', 'kdscope2-kd')
BENCHMARK_PROFILES = {
    'kdlock1': dict(release='7.0.0-38-kdlock1',
                   build=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'),
                   bundle=Path('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027')),
    **{variant: dict(release='7.0.0-38-kdscope1',
                    build=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build'),
                    bundle=Path('/root/kdlock-kernel-baselines/linux70-'+variant+'-20261030'))
       for variant in ('kdscope1-native', 'kdscope1-kd')},
    **{variant: dict(release='7.0.0-38-kdscope2',
                    build=Path('/mnt/kdlock-builds2/linux-7.0.0-38-kdscope2/build'),
                    bundle=Path('/root/kdlock-kernel-baselines/linux70-'+variant+'-20261031'))
       for variant in ('kdscope2-native', 'kdscope2-kd')},
}


def arguments(parser, *, variants=VARIANTS):
    parser.add_argument('--kernel-variant', choices=variants, default='kdlock1',
                        help='explicit reviewed Linux 7 release/MM mode; never inferred from a bundle')
    parser.add_argument('--kernel-source', type=Path,
                        default=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'),
                        help='kernel build directory (KDIR); schema 2 binds its separate source tree')
    parser.add_argument('--kernel-baseline', type=Path,
                        default=Path('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'))


def benchmark_arguments(parser):
    arguments(parser, variants=tuple(BENCHMARK_PROFILES))
    # Resolve only a reviewed explicit profile; an unspecified path is not a
    # license to infer the profile from the manifest or running release.
    parser.set_defaults(kernel_source=None, kernel_baseline=None)


def benchmark_profile(args, *, release=None):
    variant = getattr(args, 'kernel_variant', 'kdlock1')
    if variant not in BENCHMARK_PROFILES:
        raise ValueError('unsupported benchmark kernel profile')
    profile = BENCHMARK_PROFILES[variant]
    if args.kernel_source is None:
        args.kernel_source = profile['build']
    if args.kernel_baseline is None:
        args.kernel_baseline = profile['bundle']
    if (args.kernel_source != profile['build'] or
            args.kernel_baseline != profile['bundle']):
        raise ValueError('exact benchmark profile build and bundle required')
    if release is not None and release != profile['release']:
        raise ValueError('running release differs from benchmark profile')
    return profile


def verifier_for(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    schema = manifest.get('schema') if isinstance(manifest, dict) else None
    if type(schema) is not int or schema not in (1, 2):
        raise ValueError('unsupported kernel identity schema')
    path = ('kernel_baseline/verify.py' if schema == 1 else
            'kernel_integration/linux70/verify.py')
    spec = importlib.util.spec_from_file_location('captured_kernel_verify',
                                                ROOT / path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return schema, manifest, verifier


def check(source, bundle, variant='kdlock1'):
    schema, _, verifier = verifier_for(bundle)
    # Preserve the literal schema-2 KDIR for the canonical-root check. Resolving
    # it first would silently accept a different caller-selected symlink path.
    selected = source.resolve() if schema == 1 else source
    if schema == 1:
        if variant != 'kdlock1':
            raise ValueError('Linux 7 MM variant cannot use a legacy identity')
        return verifier.verify(bundle.resolve(), selected, build=True, running=True)
    return verifier.verify(bundle.resolve(), selected, build=True, running=True, variant=variant)


def source_directory(build, bundle, variant='kdlock1'):
    """Locate original implementation files; callers still use KDIR to build."""
    schema, manifest, verifier = verifier_for(bundle)
    if schema == 1:
        if variant != 'kdlock1':
            raise ValueError('Linux 7 MM variant cannot use a legacy identity')
        return build.resolve()
    return verifier.source_directory(build, manifest, variant=variant)


def capture(args, out, command):
    variant = getattr(args, 'kernel_variant', 'kdlock1')
    result = command(['python3', Path(__file__).resolve(), '--kernel-source', args.kernel_source,
                      '--kernel-baseline', args.kernel_baseline,
                      '--kernel-variant', variant], out / 'baseline.json')
    # Copy only named, verified bundle inputs, with paths already validated by
    # the verifier. Preserve the manifest itself alongside those exact bytes.
    bundle = args.kernel_baseline.resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    target = out / 'kernel-baseline'
    target.mkdir()
    for name in ['manifest.json', *manifest['bundle_files']]:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / name, dest)
    # Verify the captured copy too: a concurrent bundle edit must not leave a
    # result associated with different inputs than the ones actually retained.
    copied = check(args.kernel_source, target, variant=variant)
    if copied != json.loads(result):
        raise RuntimeError('captured kernel identity differs from preflight')
    return dict(source=str(args.kernel_source.resolve()), baseline=str(bundle), **copied)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    args = parser.parse_args()
    print(json.dumps(check(args.kernel_source, args.kernel_baseline, variant=args.kernel_variant), sort_keys=True))
