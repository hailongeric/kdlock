#!/usr/bin/env python3
"""Audit fresh Native/TCLock context separately from owned acceptance.

Reads frozen evidence only. It never builds, runs workloads or changes the VM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

sys.dont_write_bytecode = True
import analyze as report

audit, require = report.audit, report.require


def archive_receipt(path, extracted, expected):
    observed = audit.digest(path)
    require(observed == expected, 'archive SHA256 differs')
    regular = directories = byte_count = 0
    links = []
    names = set()
    with tarfile.open(path, 'r:gz') as archive:
        for item in archive:
            name = Path(item.name)
            require(not name.is_absolute() and '..' not in name.parts and
                    item.name not in names, 'unsafe/duplicate archive member')
            names.add(item.name)
            target = extracted/name
            if item.isfile():
                require(target.is_file() and not target.is_symlink() and
                        target.stat().st_size == item.size, 'missing/different extracted file: ' + item.name)
                stream = archive.extractfile(item)
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
                require(digest.hexdigest() == audit.digest(target),
                        'extracted bytes differ: ' + item.name)
                regular += 1
                byte_count += item.size
            elif item.issym():
                materialized = target.is_symlink()
                require((materialized and str(target.readlink()) == item.linkname) or
                        (not materialized and not target.exists()),
                        'extracted link differs: ' + item.name)
                links.append(dict(path=item.name, target=item.linkname,
                                  materialized=materialized))
            elif item.isdir():
                require(target.is_dir() and not target.is_symlink(),
                        'missing extracted directory: ' + item.name)
                directories += 1
            else:
                require(False, 'unsupported archive member: ' + item.name)
    return dict(path=path.name, sha256=observed, compressed_bytes=path.stat().st_size,
                regular_files=regular, regular_bytes=byte_count, directories=directories,
                symlinks=links, every_regular_file_byte_verified=True,
                symlink_limit='Unmaterialized workspace links are retained as archive target strings; audited JIT/source files are regular files.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--run', required=True, help='relative Native/TCLock control directory')
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--archive-sha256', required=True)
    parser.add_argument('--out', type=Path, default=report.HERE)
    args = parser.parse_args()
    raw = args.raw.resolve()
    folder = audit.declared(raw, ['tclock_control=' + args.run])['tclock_control']
    archive = archive_receipt(args.archive, raw, args.archive_sha256)
    rows, receipt = audit.audit_group('tclock_control', folder, False)
    require({r['arm'] for r in rows} == {'native', 'tclock'},
            'reference group must contain Native and TCLock only')
    report.study.require_fresh(rows, set())
    geometry = set()
    for record in rows:
        layout = record['layout']
        require(layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0 and
                layout['line_bytes'] == 64 and record['post_work_rounds'] == 64,
                'reference alignment or post-work differs')
        geometry.add((layout['lock_addr'] - layout['data_addr'], layout['slots'],
                      tuple(value - layout['data_addr'] for value in layout['slot_addr'])))
    # TCLock's object has a different size; require matching protected-data
    # placement rather than pretending the private lock layouts are identical.
    require(len(geometry) == 1, 'reference protected-data geometry differs')
    for threads in {r['threads'] for r in rows}:
        cohort = [r for r in rows if r['threads'] == threads]
        orders = [[r['arm'] for r in cohort if r['repeat'] == repeat] for repeat in range(3)]
        require(len(cohort) == 6 and orders[0] in (['native', 'tclock'], ['tclock', 'native']) and
                orders[1] == orders[0][::-1] and orders[2] == orders[0] and
                [r['repeat'] for r in cohort] == [0, 0, 1, 1, 2, 2],
                'reference rounds must alternate order')
    require(all(left['measurement']['finished_ns'] < right['measurement']['started_ns']
                for left, right in zip(rows, rows[1:])), 'reference run order differs')
    tables = {name: [] for name in report.TABLES}
    audit.summarize('tclock_control', rows, tables)
    tables['progress'].extend(report.progress_rows('tclock_control', rows))
    contrasts = []
    for threads in sorted({r['threads'] for r in rows}):
        native = report.study.metrics([r for r in rows if r['arm'] == 'native' and r['threads'] == threads])
        tclock = report.study.metrics([r for r in rows if r['arm'] == 'tclock' and r['threads'] == threads])
        contrasts.append(dict(threads=threads, **{
            key + '_ratio_to_paired_native': tclock[key]/native[key]
            for key in ('median_whole', 'best_peak')}))
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ('samples', 'statistics', 'workers', 'batches'):
        audit.csv_write(args.out/('tclock-' + name + '.csv'), tables[name])
    report.write_progress(args.out/'tclock-progress.csv.gz', tables['progress'])
    audit.csv_write(args.out/'tclock-comparisons.csv', contrasts)
    audit.write_json(args.out/'references.json', dict(
        passed=True, command=sys.argv, script_sha256=audit.digest(Path(__file__)),
        evidence_helper_sha256=audit.digest(report.HELPER),
        policy_auditor_sha256=audit.digest(report.HERE/'experiment_policy.py'),
        study_auditor_sha256=audit.digest(report.HERE/'study_audit.py'),
        generic_validator_sha256={name: audit.digest(report.ROOT/'bench/spin_cacheline'/name)
                                  for name in ('bench_runtime.py', 'summarize.py', 'peak.py')},
        archive=archive, run=receipt, progress_rows=len(tables['progress']),
        role='fresh_same_machine_causal_context', contributes_to_owned_acceptance=False,
        limits=['Object sizes differ; workload lock/data alignment and relative data placement are checked.',
                'No candidate performance or confirmation acceptance follows from this reference comparison.']))
    print(json.dumps(dict(passed=True, sessions=len(rows), archive_regular_files=archive['regular_files'],
                          archive_symlinks=len(archive['symlinks']), output=str(args.out))))


if __name__ == '__main__':
    main()
