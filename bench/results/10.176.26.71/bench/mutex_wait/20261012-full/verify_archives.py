#!/usr/bin/env python3
"""Verify copied archives and published evidence without executing a benchmark.

Run on the source host after copying the three archives and physical-host
receipts. These are integrity checks, not independent execution attestation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

REPORT = Path(__file__).resolve().parent
RUN = 'full-wait-20261012'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(saved, name):
    return saved.extractfile(name).read()


def save(name, data):
    (REPORT/name).write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=REPORT.parents[2]/'raw')
    args = parser.parse_args()
    raw = args.raw_root.resolve()
    copies, paths = [], {}
    for kind, archive, receipt in (
            ('bench', 'bench-evidence.tar.gz', 'archive-receipt.json'),
            ('tests', 'tests-evidence.tar.gz', 'archive-receipt.json'),
            ('bench', 'analysis-evidence.tar.gz', 'analysis-receipt.json')):
        folder = raw/kind/RUN
        path = folder/archive
        original = json.loads((folder/receipt).read_text())
        assert path.stat().st_size == original['bytes']
        assert file_digest(path) == original['sha256']
        subprocess.run(['gzip', '-t', str(path)], check=True)
        with tarfile.open(path) as saved:
            names = set(saved.getnames())
            assert all(name in names for name in original['members'])
            if archive == 'bench-evidence.tar.gz':
                assert sum(n.startswith('bench/'+RUN+'/') and n.endswith('/session.json')
                           and len(Path(n).parts) == 5 for n in names) == 8910
                assert sum(n.startswith('bench/'+RUN+'-acceptance/') and n.endswith('/session.json')
                           and len(Path(n).parts) == 4 for n in names) == 15
                state = json.loads(read(saved, 'bench/'+RUN+'/matrix-status.json'))
                assert state['state'] == 'COMPLETE'
                assert len(state['groups']) == 14 and all(g['complete'] for g in state['groups'])
                approved = json.loads(read(saved, 'bench/'+RUN+'/source-sha256-approved.json'))
                acceptance = json.loads(read(saved, 'bench/'+RUN+'-acceptance/acceptance-audit.json'))
                assert acceptance['passed'] and acceptance['sessions'] == 15
                prefix = 'bench/'+RUN+'-acceptance/'
                records_data = read(saved, prefix+'records.json')
                assert digest(records_data) == acceptance['evidence']['records_sha256']
                records = json.loads(records_data)
                assert len(records) == 15 and all(r['drained'] and r['execution_status'] == 'OK' for r in records)
                kd = [r for r in records if r['arm'] == 'kdlock']
                assert len(kd) == 6 and all(r['jit_bodies'] > 0 for r in kd)
        copies.append(dict(original, source_host_copy=str(path), gzip_integrity=True))
        paths[archive] = path
    with tarfile.open(paths['tests-evidence.tar.gz']) as saved:
        logs = {}
        for name, marker in (
                ('basic.log', 'Unit tests: 2 passed, 0 failed'),
                ('api-plan.log', 'Ran 4 tests'),
                ('api-report.log', 'Ran 6 tests'),
                ('matrix-plan.log', 'Ran 2 tests'),
                ('export.log', 'Ran 11 tests'),
                ('export-final.log', 'Ran 14 tests'),
                ('direct.log', 'Ran 49 tests'),
                ('rwlock.log', 'Ran 13 tests')):
            data = read(saved, 'tests/'+RUN+'/'+name)
            assert marker in data.decode(), name
            if name != 'basic.log':
                assert data.decode().rstrip().endswith('OK'), name
            logs[name] = dict(sha256=digest(data), reported_pass=marker)
        kernel = json.loads(read(saved, 'tests/'+RUN+'/kernel-identity.json'))
        assert kernel['ok'] and kernel['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
        assert b'No broken requirements found.' in read(saved, 'tests/'+RUN+'/pip-check.log')
    artifacts = {}
    with tarfile.open(paths['analysis-evidence.tar.gz']) as saved:
        prefix = 'analysis/'+RUN+'-report/'
        for member in saved:
            if member.isfile() and member.name.startswith(prefix):
                relative = member.name[len(prefix):]
                expected = digest(saved.extractfile(member).read())
                assert file_digest(REPORT/relative) == expected, relative
                artifacts[relative] = expected
        health = json.loads(read(saved, 'analysis/'+RUN+'-final-health.json'))
        assert health['idle'] and health['frozen_source_hashes_verified'] == len(approved)
        assert not health['kernel_faults']
    verification = json.loads((REPORT/'verification.json').read_text())
    assert verification['passed'] and verification['sessions'] == 8910
    assert verification['subjects'] == 31 and verification['comparisons'] == 682
    assert verification['statuses'] == {'OK': 8908, 'NO_JIT': 2}
    analysis = json.loads((REPORT/'analysis.json').read_text())
    for name, expected in analysis['input_sha256'].items():
        assert file_digest(REPORT/name) == expected, name
    metadata = {}
    for name in ('host-environment.json', 'snapshot-create.log', 'snapshots.log',
                 'source-state.json', 'preexisting.patch', 'restore64.json'):
        path = raw/'bench'/RUN/name
        metadata[name] = dict(path=str(path), bytes=path.stat().st_size, sha256=file_digest(path))
    restored = json.loads((raw/'bench'/RUN/'restore64.json').read_text())
    assert restored['passed'] and restored['vcpus'] == 64
    for name in ('host-environment.json', 'source-state.json', 'restore64.json'):
        assert file_digest(REPORT/name) == metadata[name]['sha256']
    save('archives.json', dict(checked_utc=datetime.now(timezone.utc).isoformat(),
         check='offline integrity only; no new tests or benchmarks', archives=copies,
         metadata=metadata, published_artifact_sha256=artifacts))
    save('validation.json', dict(checked_log_receipts=logs, kernel_identity=kernel,
         final_health=health, acceptance=acceptance, restored=restored))
    print(f'PASS: three archive hashes/CRCs, 8,910 main and 15 separate acceptance sessions, '
          f'{len(artifacts)} published artifacts, saved check logs and restored topology')


if __name__ == '__main__':
    main()
