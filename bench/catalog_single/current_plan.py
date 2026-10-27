#!/usr/bin/env python3
"""Current single-round lock/API catalog; MM suites have separate kernel plans.

The original dated plan remains fixed evidence. This plan selects the active
Linux 7 kernel identity and padded-counter nano profiles, with a new evidence root.
It prints commands and never starts a workload.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commands(guest_root):
    destination = Path(guest_root)
    if (not destination.is_absolute() or '..' in destination.parts or
            destination.parent != Path('/root/kdlock-evidence/10.176.26.71/bench')):
        raise ValueError('Use a new direct child of the guest benchmark evidence directory')
    nano = load('catalog_active_nano', ROOT/'bench/nano/best_case.py')
    args = nano.parser().parse_args(['--output', str(destination), '--plan-only'])
    for profile, argv in nano.commands(args):
        name = 'nano-' + profile
        command = ['bench/rwlock_compare/run.py', *argv[2:]]
        command[command.index('--output') + 1] = str(destination/name)
        yield name, command
    historical = load('catalog_original_micro_api', Path(__file__).with_name('plan.py'))
    for name, argv in historical.commands():
        command = list(argv)
        command[command.index('--output') + 1] = str(destination/name)
        command[command.index('--kernel-source') + 1] = str(args.kernel_source)
        command[command.index('--kernel-baseline') + 1] = str(args.kernel_baseline)
        yield name, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest-root', required=True)
    args = parser.parse_args()
    plan = [dict(workload=name, argv=argv) for name, argv in commands(args.guest_root)]
    if len(plan) != 61 or len({r['workload'] for r in plan}) != len(plan):
        raise ValueError('Current catalog must contain 10 nano and 51 micro/API configurations')
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
