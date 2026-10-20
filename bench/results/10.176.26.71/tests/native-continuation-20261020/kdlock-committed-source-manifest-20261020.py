#!/usr/bin/env python3
"""Read committed Git blobs on the source host; do not build or execute tests."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if socket.gethostname() != '380G10' or args.output.exists():
        raise RuntimeError('use a new manifest path on the source host')

    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(args.repo), *arguments], timeout=30)

    git('diff', '--quiet', 'HEAD', '--')
    commit = git('rev-parse', 'HEAD').decode().strip()
    loops = [node for node in ast.walk(ast.parse(args.runner.read_text()))
             if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
             and node.target.id == 'directory']
    if len(loops) != 1:
        raise RuntimeError('runner source selection is ambiguous')
    directories = ast.literal_eval(loops[0].iter)
    entries = []
    for row in git('ls-tree', '-rz', commit).split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, kind, oid = header.split()
        name = name.decode()
        if (name != 'bench/archive_run.py'
                and not any(name.startswith(directory + '/') for directory in directories)):
            continue
        if kind != b'blob' or mode not in (b'100644', b'100755'):
            raise RuntimeError('selected source must be a regular committed blob: ' + name)
        entries.append((name, oid))
    request = b''.join(oid + b'\n' for _, oid in entries)
    raw = subprocess.run(['git', '-C', str(args.repo), 'cat-file', '--batch'],
                         input=request, capture_output=True, check=True, timeout=60).stdout
    offset, files = 0, {}
    for name, oid in entries:
        end = raw.index(b'\n', offset)
        found_oid, kind, size = raw[offset:end].split()
        if found_oid != oid or kind != b'blob':
            raise RuntimeError('unexpected Git object response')
        begin, size = end + 1, int(size)
        contents = raw[begin:begin + size]
        offset = begin + size
        if raw[offset:offset + 1] != b'\n':
            raise RuntimeError('truncated Git object')
        offset += 1
        expected = hashlib.sha256(contents).hexdigest()
        if hashlib.sha256((args.repo / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('worktree source differs from committed blob: ' + name)
        files[name] = expected
    if offset != len(raw) or not files or git('rev-parse', 'HEAD').decode().strip() != commit:
        raise RuntimeError('source identity changed or response is incomplete')
    git('diff', '--quiet', 'HEAD', '--')
    receipt = dict(commit=commit, files=files, directories=directories,
                   captured_utc=datetime.now(timezone.utc).isoformat(),
                   source_host=socket.gethostname(), source_path=str(args.repo.resolve()),
                   policy='SHA256 of committed regular Git blobs, checked against the clean worktree',
                   generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(commit=commit, files=len(files), manifest=str(args.output))))


if __name__ == '__main__':
    main()
