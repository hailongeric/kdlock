#!/usr/bin/env python3
"""Use the standard archiver after exact experimental-kernel verification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--kernel-source', type=Path, required=True)
    parser.add_argument('--kernel-baseline', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    rt.require(os.geteuid() == 0 and str(ROOT).startswith('/root/') and
               re.fullmatch(r'6\.1\.159-kdmm[0-9]+', os.uname().release), 'experimental guest required')
    identity = kernel_identity.check(args.kernel_source, args.kernel_baseline)
    spec = importlib.util.spec_from_file_location('archive_run', ROOT / 'bench/archive_run.py')
    archiver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archiver)
    rt.require(archiver.RELEASE == '6.1.159-kdclobber2', 'archiver default changed')
    # The wrapper replaces only the release guard after the stronger exact
    # source/config/build/live check. Idle, open-FD, inventory, health, fault,
    # timeout and archive checks all execute in the original maintained tool.
    archiver.RELEASE = os.uname().release
    sys.argv = [str(ROOT / 'bench/archive_run.py'), *remaining]
    archiver.main()
    out = Path(remaining[remaining.index('--output') + 1])
    receipt = json.loads((out / 'archives.json').read_text())
    receipt.update(experimental_kernel_identity=identity,
                   kernel_manifest_sha256=rt.digest(args.kernel_baseline / 'manifest.json'),
                   wrapper_sha256=rt.digest(Path(__file__)))
    archiver.save(out / 'archives.json', receipt)
    (out / 'experiment-archive.py').write_bytes(Path(__file__).read_bytes())


if __name__ == '__main__':
    main()
