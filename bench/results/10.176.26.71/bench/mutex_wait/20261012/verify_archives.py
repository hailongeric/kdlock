#!/usr/bin/env python3
"""Check copied evidence without running any benchmark, module or unit test.

Requires the three ignored raw archives and their physical-host receipts.
Writes archives.json and validation.json next to this script. These checks
establish internal consistency, not a new execution or independent attestation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

REPORT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(name, data):
    (REPORT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=REPORT.parents[2] / 'raw')
    args = parser.parse_args()
    raw = args.raw_root.resolve()
    copies = []
    paths = {}
    for kind, archive, receipt in (
        ('bench', 'bench-evidence.tar.gz', 'archive-receipt.json'),
        ('tests', 'tests-evidence.tar.gz', 'archive-receipt.json'),
        ('bench', 'followup-analysis.tar.gz', 'followup-analysis-receipt.json')):
        folder = raw / kind / 'mutex-wait-20261012'
        path = folder / archive
        original = json.loads((folder / receipt).read_text())
        assert path.stat().st_size == original['bytes']
        assert file_digest(path) == original['sha256']
        subprocess.run(['gzip', '-t', str(path)], check=True)
        with tarfile.open(path) as saved:
            names = set(saved.getnames())
            assert all(name in names for name in original['members'])
            if archive == 'bench-evidence.tar.gz':
                def sessions(run):
                    return sum(n.startswith('bench/' + run + '/') and
                               n.endswith('/session.json') and len(Path(n).parts) == 5 for n in names)
                assert sessions('mutex-wait-20261012-timed') == 2430
                assert sessions('mutex-wait-20261012-final') == 832
        copies.append(dict(original, source_host_copy=str(path), gzip_integrity=True))
        paths[archive] = path
    with tarfile.open(paths['bench-evidence.tar.gz']) as saved:
        approved = json.load(saved.extractfile('bench/mutex-wait-20261012-timed/source-sha256-approved.json'))
    probes = {}
    with tarfile.open(paths['tests-evidence.tar.gz']) as saved:
        def read(name):
            return saved.extractfile(name).read()
        for run in ('mutex-blocking-wait-20261012-timed-v1', 'mutex-blocking-task-20261012-timed-v1'):
            base = 'tests/' + run + '/'
            sources = json.loads(read(base + 'sources.json'))
            for name, expected in sources.items():
                assert digest(read(base + 'source/' + name)) == expected
                if name in approved:
                    assert approved[name] == expected
            identity = json.loads(read(base + 'identity.json'))
            assert digest(read(base + 'kdlock_km.ko')) == identity['module_sha256']
            result = json.loads(read(base + 'result.json'))
            assert result['passed'] and result['drained']
            probes[run] = dict(source_hashes_verified=len(sources), identity=identity, result=result)
        wait = probes['mutex-blocking-wait-20261012-timed-v1']['result']['results']
        assert {r['spin_limit'] for r in wait} == {0, 1024, 4096}
        assert all(r['rounds'] == 1024 and r['result_sleep'] and r['gate_sleep'] and
                   r['deferred_progress'] and r['drained'] and not r['errors'] and not r['jit_bodies'] for r in wait)
        task = probes['mutex-blocking-task-20261012-timed-v1']['result']
        assert task['mutex_wait_mode'] == 'blocking' and task['acks'] == 4 and not task['jit_bodies']
        logs = {}
        for name, marker in (
            ('mutex-blocking-20261012-timed-v1/unit.log', 'Unit tests: 10 passed, 0 failed'),
            ('mutex-blocking-20261012-timed-v1/direct.log', 'Ran 49 tests'),
            ('mutex-blocking-20261012-timed-v1/rw.log', 'Ran 13 tests'),
            ('mutex-blocking-20261012-timed-v1/report.log', 'Ran 6 tests'),
            ('mutex-blocking-final-audit-20261012/export.log', 'Ran 7 tests')):
            data = read('tests/' + name)
            assert marker in data.decode()
            if name.split('/')[-1] != 'unit.log':
                assert data.decode().rstrip().endswith('OK')
            logs[name] = dict(sha256=digest(data), reported_pass=marker)
    artifacts = {}
    with tarfile.open(paths['followup-analysis.tar.gz']) as saved:
        prefix = 'analysis/mutex-wait-20261012-final-report-v2/'
        for member in saved:
            if member.isfile() and member.name.startswith(prefix):
                relative = member.name[len(prefix):]
                expected = digest(saved.extractfile(member).read())
                assert file_digest(REPORT / relative) == expected, relative
                artifacts[relative] = expected
        health = json.load(saved.extractfile('analysis/mutex-wait-final-health-20261012.json'))
        assert health['idle'] and health['frozen_source_hashes_verified'] == len(approved)
    metadata = {}
    for name in ('environment.json', 'snapshot.log', 'snapshot-recheck.log', 'setup-failure-note.json',
                 'sync-after-matrix.log'):
        path = raw / 'bench/mutex-wait-20261012' / name
        metadata[name] = dict(path=str(path), bytes=path.stat().st_size, sha256=file_digest(path))
    for name in ('environment.json', 'setup-failure-note.json'):
        assert file_digest(REPORT / name) == metadata[name]['sha256']
    for name, count in (('verification', 2430), ('pilot-verification', 78),
                        ('paired-verification', 42), ('superseded-verification', 832)):
        result = json.loads((REPORT / (name + '.json')).read_text())
        assert result['passed'] and result['sessions'] == count
    save('archives.json', dict(checked_utc=datetime.now(timezone.utc).isoformat(),
         check='offline integrity only; no new tests or benchmarks', archives=copies,
         metadata=metadata, published_artifact_sha256=artifacts))
    save('validation.json', dict(probes=probes, checked_log_receipts=logs, final_health=health))
    print(f'PASS: three archive hashes/CRCs, {len(artifacts)} published artifacts, two final probes and saved check logs')


if __name__ == '__main__':
    main()
