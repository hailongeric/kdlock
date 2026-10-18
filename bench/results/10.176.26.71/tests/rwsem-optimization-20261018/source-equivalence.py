#!/usr/bin/env python3
"""Offline, read-only source-byte comparison; never imports or runs project code."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess


DIRECTORIES = ('include', 'kernel_module', 'disassem', 'daemon')
MUTEX_PATHS = (
    'include/kd_mutex.h', 'include/kd_mutex_compat.h',
    'include/kd_mutex_direct.h', 'include/kd_mutex_stats.h',
    'kernel_module/kd_mutex.c', 'kernel_module/kd_mutex_local.c',
    'kernel_module/kd_mutex_local.h', 'kernel_module/kd_mutex_osq.c',
    'kernel_module/kd_mutex_tasks.c', 'kernel_module/lock/mutex_calls.inc',
    'kernel_module/mutex/clobber.inc', 'kernel_module/mutex/combiner.inc',
    'kernel_module/mutex/lifecycle.inc', 'kernel_module/mutex/linux-source.json',
    'kernel_module/mutex/queue.inc', 'kernel_module/mutex/waiter.inc',
)
PRIOR_EXCLUSIONS = {
    'daemon/README.md': 'Maintained prose is outside runtime byte-equivalence scope.',
    'disassem/README.md': 'Maintained prose is outside runtime byte-equivalence scope.',
    'disassem/context_symbols.py':
        'Prior feature reintegration added fail-closed ordinary rwsem/helper refusal rules.',
    'include/README.md': 'Maintained prose is outside runtime byte-equivalence scope.',
    'kernel_module/Makefile': 'Prior Kbuild integration adds the independent rwsem object.',
    'kernel_module/README.md': 'Maintained prose is outside runtime byte-equivalence scope.',
}
OPTIMIZED_PATHS = ('include/kd_rwsem.h', 'kernel_module/kd_rwsem.c')
PROBE_PATHS = ('tests/kernel/rwsem/module.c', 'tests/kernel/rwsem/run.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--selected-mutex', default='d2a2304')
    parser.add_argument('--provider-baseline', default='485729f')
    parser.add_argument('--manifest', type=Path, action='append', default=[],
                        help='Local frozen source SHA-256 JSON map; each compared separately.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite receipt: ' + str(args.output))

    def git(*argv):
        return subprocess.check_output(['git', '-C', str(repo), *argv])

    def commit(revision):
        return git('rev-parse', '--verify', revision + '^{commit}').decode().strip()

    def paths_at(revision):
        return sorted(filter(None, git('ls-tree', '-r', '--name-only', '-z',
                                       revision, '--', *DIRECTORIES).decode().split('\0')))

    def relative_path(path):
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or '..' in candidate.parts or str(candidate) != path:
            raise ValueError('Unsafe or noncanonical source path: ' + path)
        return path

    # Cache every byte read and re-read before emitting evidence. This cannot
    # freeze an active checkout, but detects changes during this inspection.
    captured = {}

    def working_bytes(path):
        relative_path(path)
        if path not in captured:
            try:
                captured[path] = (repo / path).read_bytes()
            except FileNotFoundError:
                captured[path] = None
        return captured[path]

    def compare(revision, paths):
        rows = []
        for path in paths:
            baseline = git('show', revision + ':' + path)
            current = working_bytes(path)
            rows.append(dict(path=path, baseline_sha256=digest(baseline),
                             working_tree_sha256=None if current is None else digest(current),
                             byte_identical=current == baseline))
        return dict(baseline_commit=revision, checked_paths=len(rows),
                    all_byte_identical=all(row['byte_identical'] for row in rows),
                    files=rows)

    selected, provider, head = (commit(args.selected_mutex),
                                commit(args.provider_baseline), commit('HEAD'))
    baseline_paths = paths_at(selected)
    if not set(PRIOR_EXCLUSIONS).issubset(baseline_paths):
        raise SystemExit('Selected baseline does not match the reviewed exclusion scope.')
    preserved_paths = [p for p in baseline_paths if p not in PRIOR_EXCLUSIONS]
    if len(preserved_paths) != 112 or not set(MUTEX_PATHS).issubset(preserved_paths):
        raise SystemExit('Selected baseline is not the reviewed 112-file / 16-mutex scope.')
    selected_mutex = compare(selected, MUTEX_PATHS)
    selected_runtime = compare(selected, preserved_paths)
    selected_runtime['excluded_baseline_paths'] = [dict(path=p, reason=r)
                                                   for p, r in PRIOR_EXCLUSIONS.items()]
    selected_runtime['rwsem_files_absent_from_selected_baseline'] = [
        'include/kd_rwsem.h', 'include/kd_rwsem_direct.h', 'kernel_module/kd_rwsem.c']

    provider_paths = paths_at(provider)
    prose_paths = [p for p in provider_paths if p.endswith('.md')]
    provider_runtime = [p for p in provider_paths if p not in prose_paths]
    provider_rest = compare(provider, [p for p in provider_runtime if p not in OPTIMIZED_PATHS])
    provider_rest['excluded_prose_paths'] = prose_paths
    provider_rest['allowed_changed_paths'] = list(OPTIMIZED_PATHS)
    provider_changes = compare(provider, OPTIMIZED_PATHS)
    current_paths = sorted(filter(None, git('ls-files', '--cached', '--others',
        '--exclude-standard', '-z', '--', *DIRECTORIES).decode().split('\0')))
    provider_rest['added_runtime_paths'] = sorted(set(p for p in current_paths
        if not p.endswith('.md')) - set(provider_runtime))
    provider_rest['runtime_path_set_unchanged'] = not provider_rest['added_runtime_paths']

    manifest_checks = []
    for source_manifest in args.manifest:
        raw = source_manifest.read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError('Expected nonempty path-to-SHA256 map: ' + str(source_manifest))
        rows = []
        for path, expected in sorted(manifest.items()):
            relative_path(path)
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('Malformed manifest SHA-256: ' + path)
            current = working_bytes(path)
            actual = None if current is None else digest(current)
            rows.append(dict(path=path, frozen_source_sha256=expected,
                             working_tree_sha256=actual, sha256_match=actual == expected))
        manifest_checks.append(dict(manifest=str(source_manifest.resolve()),
            source_manifest_sha256=digest(raw), source_files_verified=len(rows),
            all_match=all(row['sha256_match'] for row in rows), files=rows))

    reviewed_inputs = {p: digest(working_bytes(p)) for p in
                       (*OPTIMIZED_PATHS, 'include/kd_rwsem_direct.h', *PROBE_PATHS)}
    changed_during_inspection = []
    for path, before in captured.items():
        try:
            after = (repo / path).read_bytes()
        except FileNotFoundError:
            after = None
        if before != after:
            changed_during_inspection.append(path)
    head_unchanged = commit('HEAD') == head
    all_preservation_checks_pass = (
        selected_mutex['all_byte_identical'] and selected_runtime['all_byte_identical']
        and provider_rest['all_byte_identical'] and provider_rest['runtime_path_set_unchanged']
        and all(m['all_match'] for m in manifest_checks)
        and not changed_during_inspection and head_unchanged)
    receipt = dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(),
        source_host=socket.gethostname(), repository=str(repo), working_tree_head=head,
        scope='Offline source-byte equivalence on the source host; no project imports or execution.',
        static_only=True, builds_or_tests_run=False,
        limitations='Source preservation only: no compiled equivalence, runtime correctness, '
                    'performance, RT or whole-kernel integration claim. A manifest check compares '
                    'local frozen hashes to source bytes; it does not verify an entire archive.',
        selected_mutex=selected_mutex, selected_runtime=selected_runtime,
        provider_rest=provider_rest, rwsem_changes=provider_changes,
        reviewed_input_sha256=reviewed_inputs,
        frozen_source_manifest_checks=manifest_checks,
        frozen_source_manifest_status='CHECKED' if manifest_checks else 'NOT_REQUESTED',
        working_tree_diff_name_status=git('diff', '--name-status', 'HEAD').decode().splitlines(),
        source_changed_during_inspection=changed_during_inspection,
        head_unchanged_during_inspection=head_unchanged,
        all_preservation_checks_pass=all_preservation_checks_pass)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), passed=all_preservation_checks_pass,
        selected_mutex_files=selected_mutex['checked_paths'],
        selected_runtime_files=selected_runtime['checked_paths'],
        unchanged_provider_files=provider_rest['checked_paths'],
        frozen_source_manifests=len(manifest_checks))))
    return 0 if all_preservation_checks_pass else 1


if __name__ == '__main__':
    raise SystemExit(main())
