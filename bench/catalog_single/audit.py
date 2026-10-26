#!/usr/bin/env python3
"""Read-only archive and arithmetic audit of the completed catalog receipts."""
import csv
import hashlib
import json
import math
import tarfile

from collect import RAW, REPORT
from plan import commands, THREADS


def main():
    results = []
    baseline_health = json.loads((RAW / 'spin-c08-before-health.stdout').read_text())
    modules = sorted(line.split()[0] for line in baseline_health['modules'].splitlines())
    for name, _ in commands():
        source = RAW / name
        plan = json.loads((source / 'plan.json').read_text())
        records = json.loads((source / 'records.json').read_text())
        rows = list(csv.DictReader((REPORT / name / 'table.csv').open()))
        by_name = {r['name']: r for r in records}
        assert len(plan) == len(rows) == len(records) == len(by_name) == 63
        assert {(r['threads'], r['arm']) for r in plan} == {
            (n, arm) for n in THREADS for arm in ('native', 'tclock', 'kdlock')}
        assert all(r['repeat'] == 0 for r in plan)
        assert {r['session'] for r in rows} == set(by_name)
        failures = []
        for row in rows:
            r = by_name[row['session']]
            assert row['status'] == r['execution_status'] and r['drained'] is True
            assert row['host_qualified'] == 'False'
            if r['execution_status'] != 'OK':
                assert r['execution_status'] == 'PREPARATION_FAILED' and r['arm'] == 'kdlock'
                assert r['kind'] == 'xattr' and 'measurement' not in r and 'cleanup_error' not in r
                assert r['error'] == 'helper learning did not establish complete delegation within configured waves'
                assert not row['whole_mops_s'] and not row['peak_mops_s']
                assert row['jit_status'] == 'PREPARATION_FAILED'
                failures.append(dict(workers=r['threads'], backend=r['arm'], status=r['execution_status']))
                continue
            m = r['measurement']
            assert m.get('ok') is True or (m.get('complete') is True and m.get('data_ok') is True)
            assert math.isclose(float(row['whole_mops_s']), m['completed'] * 1e3 / m['wall_ns'], rel_tol=1e-14)
            if row['peak_mops_s']:
                assert math.isclose(float(row['peak_mops_s']), m['peak']['throughput_ops_s'] / 1e6, rel_tol=1e-14)
            for field, original in [('jit_entries', 'jit_bodies'), ('jit_completions', 'jit_completions')]:
                assert row[field] == (str(r[original]) if r.get(original) is not None else '')
        receipt_path = RAW / ('preservation.json' if name == 'spin-c01' else name + '-preservation.json')
        receipt = json.loads(receipt_path.read_text())
        archive = RAW / receipt['archive']
        assert archive.stat().st_size == receipt['bytes']
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == receipt['sha256']
        manifest = json.loads((source / 'source-sha256.json').read_text())
        expected = {name + '/source/' + k: v for k, v in manifest.items()}
        seen = set()
        records_matched = False
        members = 0
        with tarfile.open(archive, mode='r|gz') as tar:
            for member in tar:
                members += 1
                if member.name in expected:
                    assert member.isfile()
                    assert hashlib.sha256(tar.extractfile(member).read()).hexdigest() == expected[member.name]
                    seen.add(member.name)
                elif member.name == name + '/records.json':
                    assert tar.extractfile(member).read() == (source / 'records.json').read_bytes()
                    records_matched = True
        assert members == receipt['members'] and records_matched and seen == set(expected)
        if name != 'spin-c01':
            health = json.loads((RAW / (name + '-after-health.stdout')).read_text())
            assert health['idle'] is True and health['boot_id'] == baseline_health['boot_id']
            assert health['kernel'] == baseline_health['kernel']
            assert sorted(line.split()[0] for line in health['modules'].splitlines()) == modules
        results.append(dict(workload=name, planned=63, attempted=63, measured=63-len(failures),
                            drained=63, preparation_failures=failures, source_files_verified=len(seen),
                            archive=receipt['archive'], archive_sha256=receipt['sha256']))
    initial = RAW / 'attempts/xattr-front-n16-helper-preparation-stop/xattr-front-n16/records.json'
    current = RAW / 'xattr-front-n16'
    assert initial.read_bytes() == (current / 'records-before-continuation.json').read_bytes()
    final = {r['name']: r for r in json.loads((current / 'records.json').read_text())}
    retained = [r for r in json.loads(initial.read_text()) if r['execution_status'] != 'NOT_RUN']
    assert len(retained) == 3 and all(final[r['name']] == r for r in retained)
    result = dict(passed=True, scope='Offline receipt, arithmetic, source archive and recorded health audit',
                  strict_timing_qualified=False, configurations=len(results),
                  planned=sum(r['planned'] for r in results), attempted=sum(r['attempted'] for r in results),
                  measured=sum(r['measured'] for r in results), drained=sum(r['drained'] for r in results),
                  source_files_verified=sum(r['source_files_verified'] for r in results),
                  original_xattr_attempts_retained_without_repeat=3, workloads=results)
    (REPORT / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'workloads'}, indent=2))


if __name__ == '__main__':
    main()
