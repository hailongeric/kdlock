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


def arguments(parser):
    parser.add_argument('--kernel-source', type=Path,
                        default=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'),
                        help='kernel build directory (KDIR); schema 2 binds its separate source tree')
    parser.add_argument('--kernel-baseline', type=Path,
                        default=Path('/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'))


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


def check(source, bundle):
    schema, _, verifier = verifier_for(bundle)
    # Preserve the literal schema-2 KDIR for the canonical-root check. Resolving
    # it first would silently accept a different caller-selected symlink path.
    selected = source.resolve() if schema == 1 else source
    return verifier.verify(bundle.resolve(), selected, build=True, running=True)


def source_directory(build, bundle):
    """Locate original implementation files; callers still use KDIR to build."""
    schema, manifest, verifier = verifier_for(bundle)
    if schema == 1:
        return build.resolve()
    return verifier.source_directory(build, manifest)


def capture(args, out, command):
    result = command(['python3', Path(__file__).resolve(), '--kernel-source', args.kernel_source,
                      '--kernel-baseline', args.kernel_baseline], out / 'baseline.json')
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
    copied = check(args.kernel_source, target)
    if copied != json.loads(result):
        raise RuntimeError('captured kernel identity differs from preflight')
    return dict(source=str(args.kernel_source.resolve()), baseline=str(bundle), **copied)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    args = parser.parse_args()
    print(json.dumps(check(args.kernel_source, args.kernel_baseline), sort_keys=True))
