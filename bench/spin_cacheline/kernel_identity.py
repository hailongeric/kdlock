#!/usr/bin/env python3
"""Check a selected kernel bundle with the existing exact baseline verifier.

An experimental kernel has its own captured bundle; the original baseline is
never rewritten or silently skipped. All named source/config/build files and
the running Build ID must match before any workload is loaded.
"""
import argparse
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def arguments(parser):
    parser.add_argument('--kernel-source', type=Path,
                        default=Path('/root/linux-6.1.159-kdclobber2'))
    parser.add_argument('--kernel-baseline', type=Path,
                        default=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))


def check(source, bundle):
    spec = importlib.util.spec_from_file_location('captured_kernel_verify',
                                                ROOT / 'kernel_baseline/verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return verifier.verify(bundle.resolve(), source.resolve(), build=True, running=True)


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
