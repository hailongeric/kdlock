#!/usr/bin/env python3
"""Read-only source-host audit of this milestone's single evidence archive."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[5]
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-boundary-interior-zero-20261024'


def main():
    digest = lambda b: hashlib.sha256(b).hexdigest()
    archive = RAW / 'collect-1/essential.tar.gz'
    receipt = json.loads((RAW / 'collect-1/receipt.json').read_text())
    assert archive.stat().st_size == receipt['bytes'] and digest(archive.read_bytes()) == receipt['sha256']
    with tarfile.open(archive) as tar:
        members = {p.name: p for p in tar.getmembers()}
        assert len(members) == len(tar.getmembers()) and all(
            p.isfile() and not p.name.startswith('/') and '..' not in Path(p.name).parts
            for p in members.values())
        read = lambda n: tar.extractfile(n).read()
        load = lambda n: json.loads(read(n))
        run, build, inputs = (load(n) for n in
                             ('focused-1/result.json', 'build-1/result.json', 'control/inputs.json'))
        assert run['passed'] and run['drained'] and run['idle'] and not run['new_kernel_faults']
        assert build['passed'] and build['installed'] and build['temporary_build_mount_removed']
        assert build['changed_kernel_sources'] == ['mm/kd_mmap_unmap.inc']
        assert build['runtime_modules'] == 73 and build['unchanged_clients_reused'] == 14
        assert inputs['commit'] == build['source_commit']
        assert 'Unit tests: 2 passed, 0 failed' in read('build-1/basic.log').decode()
        for name, h in inputs['files'].items():
            assert digest(subprocess.check_output(['git', 'show', inputs['commit'] + ':' + name], cwd=ROOT)) == h, name
        sources, generated = 0, {}
        for name in members:
            if not name.startswith('probes-1/') or not name.endswith(('.c', '.h', '.inc', '.py')):
                continue
            if name.endswith('.mod.c'):
                generated[name] = digest(read(name))
                continue
            rel = 'tests/kernel/mmap_lock/' + name[len('probes-1/'):]
            assert rel in inputs['files'] and digest(read(name)) == inputs['files'][rel], rel
            sources += 1
        new, smoke, samples = [], [], []
        hashes = 0
        for case in run['cases']:
            prefix = 'focused-1/' + case['name'] + '/'
            for name, key in [('client.json', 'client_sha256'), ('kernel.log', 'kernel_log_sha256')]:
                assert digest(read(prefix + name)) == case[key]
                hashes += 1
            row, log, controls = load(prefix + 'client.json'), read(prefix + 'kernel.log').decode(), load(prefix + 'receipt-controls.json')
            assert row['idle'] and not row['errors'] and case['passed'] and case['drained'] and controls['passed']
            assert len(controls['rejected_corruptions']) == case['negative_controls']
            interior = not case['name'].endswith('-smoke')
            (new if interior else smoke).append(case)
            tag = 'KD_MM_BOUNDARY_INTERIOR_ZERO' if interior else 'KD_MM_BOUNDARY_(?:SHARED|INTERIOR)_(?:MISSING|EMPTY|ZERO|PRIVATE)'
            bodies = re.findall(tag + r' done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+)[^\n]*', log)
            assert len(bodies) == case['evidence']['remote_boundary_removals']
            for mm, ident, origin, executor in bodies:
                assert origin != executor and int(mm, 16) == row['mm'] and 0 < int(ident) <= row['groups']
            if interior:
                for line in log.splitlines():
                    if 'KD_MM_BOUNDARY_INTERIOR_ZERO done ' in line:
                        fields = dict(re.findall(r'(\w+)=(\S+)', line))
                        assert all(fields[key] == value for key, value in {
                            'target_pte_none': '1', 'target_zero': '1',
                            'target_owned': '0', 'zero_owned': '0',
                            'zero_tlb_complete': '1', 'tables_unchanged': '1',
                        }.items())
                        assert int(fields['target_table_pfn'], 16) > 0
                        assert int(fields['zero_pfn'], 16) > 0
                assert case['evidence']['remote_interior_zero_removals'] == len(bodies)
            if row.get('boundary_interior_test'):
                proofs = log.count('KD_MM_INTERIOR preflight ')
                assert proofs == len(bodies) + case['evidence']['remote_boundary_errors']
                assert log.count('KD_MM_INTERIOR split_bounds ') == (0 if row['injection'] == 1 else proofs)
                assert row['target_rechecks_accessed'] == row['target_rechecks_written'] == sum(
                    not o['layouts'][1]['mapped'] for o in row['origins'])
            if case['name'] in ('interior-target-left-ur', 'interior-target-right-uu',
                                'interior-target-left-error1', 'interior-target-right-error2',
                                'interior-target-left-change-private', 'interior-target-right-fault'):
                samples.append(dict(case=case['name'], counts=row['counts'],
                    table_bytes=[row['table_bytes_before'], row['table_bytes_after']],
                    receipts=[line for line in log.splitlines() if any(tag in line for tag in
                        ('KD_MM_INTERIOR ', 'KD_MM_BOUNDARY_INTERIOR_ZERO ', 'KD_MM_UNMAP handback ',
                         'KD_MM_UNMAP ack ', 'KD_MM_TEST edge_zero_change '))]))
        total = lambda rows, key: sum(c['evidence'].get(key, 0) for c in rows)
        totals = dict(cases=len(run['cases']), new_cases=len(new), preservation_cases=len(smoke),
            negative_controls=sum(c['negative_controls'] for c in new + smoke),
            new_negative_controls=sum(c['negative_controls'] for c in new),
            new_remote=total(new, 'remote_boundary_removals'),
            new_remote_without_private_holds=total(new, 'remote_boundary_without_private_holds'),
            smoke_remote=total(smoke, 'remote_boundary_removals'),
            remote_errors=total(new, 'remote_boundary_errors'), acks=total(new, 'matched_acks'),
            cancelled=total(new, 'cancelled'), native_success_comparisons=len(run['native_comparisons']),
            native_error_comparisons=len(run['native_error_comparisons']))
        assert totals == dict(cases=40, new_cases=34, preservation_cases=6, negative_controls=867,
            new_negative_controls=680, new_remote=16, new_remote_without_private_holds=12,
            smoke_remote=12, remote_errors=4, acks=4, cancelled=2,
            native_success_comparisons=12, native_error_comparisons=4)
        recovery = json.loads((RAW / 'recovery-1/result.json').read_text())
        health = json.loads((RAW / 'final-health.json').read_text())
        host = json.loads((RAW / 'final-host.json').read_text())
        assert recovery['passed'] and recovery['idle'] and recovery['recovery_preserved']
        assert recovery['release'] == health['release'] == '6.1.159-kdclobber2'
        assert health['passed'] and not health['test_modules'] and health['temporary_ram_builds_absent']
        assert host['snapshot_listed'] and host['pins_verified']
        identity = json.loads((RAW / 'identity/receipt.json').read_text())
        assert identity['passed'] and Path(identity['host_path']).stat().st_size == identity['compressed_bytes']
        assert digest(Path(identity['host_path']).read_bytes()) == identity['compressed_sha256']
        print(json.dumps(dict(passed=True, archive=receipt, source_commit=inputs['commit'],
            input_hashes_verified=len(inputs['files']), probe_source_hashes_verified=sources,
            generated_build_sources=generated, case_file_hashes_verified=hashes,
            totals=totals, samples=samples), indent=2))


if __name__ == '__main__':
    main()
