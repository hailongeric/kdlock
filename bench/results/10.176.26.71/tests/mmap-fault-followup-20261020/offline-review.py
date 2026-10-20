#!/usr/bin/env python3
"""Verify inert mmap/fault capture and materialize hashed text for source review."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tarfile
from types import SimpleNamespace


SOURCE = 'f48b90e42e1538a5204d215b573a238ebd95f391'
HELPER = 'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA = '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
STAGE = 'bench/results/10.176.26.71/tests/mmap-fault-followup-20261020/'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'raw', 'report', 'source-output'):
        p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    assert socket.gethostname() == '380G10'
    assert not args.report.exists() and not args.source_output.exists()
    sys.dont_write_bytecode = True
    path = args.repo/HELPER
    assert hashlib.sha256(path.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location('inert_capture_archive', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    a = helper.Audit(SimpleNamespace(**vars(args)))
    groups, links = a.load_archives()
    result, health, manifest, historical, kernel = (a.jread(n+'.json') for n in
        ('result', 'health', 'committed-source', 'historical-audit', 'kernel-source-sha256'))
    a.check(result['passed'] and result['idle'] and result['source_unchanged'] and
            not result['kernel_modified'] and result['builds'] == result['tests'] ==
            result['measured_sessions'] == 0, 'read_only_capture_pass')
    a.check(result['source_commit'] == manifest['commit'] == SOURCE and
            len(manifest['files']) == 497, 'source_identity')
    for path, digest in manifest['files'].items():
        a.check(helper.sha(a.git_bytes(SOURCE, path)) == digest, 'committed_git_source', path)
    a.check(result['capture_script_sha256'] == health['capture_script_sha256'] ==
            a.files['capture.py'] == helper.hashfile(args.repo/STAGE/'capture.py'),
            'capture_script_binding')
    a.check(health['idle'] and health['result_sha256'] == a.files['result.json'] and
            result['boot_id'] == health['boot_id'] == a.archive['boot_id'] ==
            'b65f0205-c8f9-4385-8b13-039cbce243a6', 'health_identity')
    a.check(a.files['historical-audit.json'] == helper.sha(a.git_bytes(SOURCE,
            'bench/results/10.176.26.71/tests/proc-mmap-audit-20261015/audit.json')),
            'historical_capture_binding')
    prior = historical['kernel_source_sha256']
    a.check(len(kernel) == result['captured_source_files'] == 46 and
            len(prior) == result['historical_source_files'] == 25 and
            len(set(kernel)-set(prior)) == result['additional_source_files'] == 21,
            'exact_capture_scope')
    a.check(a.files['kernel-source-sha256.json'] == result['kernel_source_manifest_sha256'] and
            {p[len('kernel/'):] for p in a.files if p.startswith('kernel/')} == set(kernel),
            'kernel_manifest_scope')
    for path, digest in kernel.items():
        a.check(helper.safe_relative(path) and a.files['kernel/'+path] == digest,
                'captured_source_hash', path)
        if path in prior:
            a.check(prior[path] == digest, 'unchanged_historical_source', path)
    identity = a.jread('kernel-identity.json')
    a.check(identity == result['kernel_identity'] and identity['ok'] and identity['config'] and
            identity['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            (identity['source_files'], identity['build_files'], identity['bundle_files']) == (20, 9, 7),
            'live_baseline_identity')
    baseline = a.jread('kernel-baseline/manifest.json')
    a.check(a.files['kernel-baseline/manifest.json'] ==
            '0f44870efd7ff604067a2436edcfd95ac8c4e413b42e3d534a51e3c011d3d013',
            'unchanged_baseline_manifest')
    # The baseline verifier proves its selected input set. Additional captured
    # files are current source bytes, not an independently reproducible build.
    a.check(a.jread('baseline.json') == {k: identity[k] for k in
            ('build_files', 'bundle_files', 'config', 'ok', 'running_build_id', 'source_files')},
            'baseline_command_receipt')
    output = dict(consistent=not a.issues, issues=a.issues, checks=sum(a.counts.values()),
        check_counts=dict(a.counts), source_commit=SOURCE, capture=result,
        groups=groups, files=len(a.files), symlinks=len(links),
        archives_manifest_sha256=helper.hashfile(args.raw/'archives.json'),
        regular_file_hash_map_sha256=helper.canonical(a.files),
        script_sha256=helper.hashfile(Path(__file__)), helper_sha256=HELPER_SHA,
        limits=['No KD mmap/fault execution, kernel build, installation or reboot.',
                'Live Build ID and baseline-selected sources/build files match.',
                'Additional kernel source capture is not a reproducible-build proof.',
                'Control-flow and integration blockers require source review of these exact bytes.'])
    assert not a.issues, a.issues
    args.source_output.mkdir(parents=True)
    for group in a.archive['groups']:
        with tarfile.open(args.raw/group['file'], 'r|gz') as archive:
            for member in archive:
                name = member.name[len(a.prefix):]
                if member.isfile() and name.startswith('kernel/'):
                    data = archive.extractfile(member).read()
                    assert helper.sha(data) == a.files[name] and b'\0' not in data
                    target = args.source_output/name[len('kernel/'):]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
    args.report.mkdir(parents=True)
    for name in ('result.json', 'health.json', 'kernel-identity.json', 'kernel-source-sha256.json'):
        (args.report/name).write_bytes(a.contents[name])
    (args.report/'archives.json').write_bytes((args.raw/'archives.json').read_bytes())
    (args.report/'offline-review.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: output[k] for k in
                     ('consistent', 'issues', 'checks', 'files', 'archives_manifest_sha256')}, sort_keys=True))


if __name__ == '__main__':
    main()
