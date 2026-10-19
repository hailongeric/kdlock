#!/usr/bin/env python3
"""Bind the retained static code review to inert archived ELF bytes.

Only tar/JSON/Git reads and host nm/objdump inspection are performed. Temporary
ELF copies are data for those readers; no archived program or module is run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import tarfile
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report, raw = args.report.resolve(), args.raw.resolve()
    output = report / 'code-binding-review.json'
    if output.exists():
        raise ValueError('preserve the existing review; choose another report directory')
    receipt = json.loads((raw / 'archives.json').read_text())
    review_bytes = (report / 'code-review.json').read_bytes()
    review = json.loads(review_bytes)
    prefix = receipt['archive_prefix'] + '/'
    paths = {
        'baseline_provider': 'packed32/pipe/build/kdlock_km.ko',
        'baseline_workload': 'packed32/pipe/build/kdlock-pipebytes/real_api.ko',
        'candidate_provider': 'candidate/pipe/build/kdlock_km.ko',
        'candidate_workload': 'candidate/pipe/build/kdlock-pipebytes/real_api.ko',
    }
    needed = set(paths.values()) | {
        'packed32/matrix.json', 'candidate/matrix.json', 'prefetch/matrix.json',
        'packed32/pipe/binaries.json', 'candidate/pipe/binaries.json',
        'prefetch/pipe/build/kdlock_km.ko', 'code-review.json',
        'offline-code-review.py', 'code-review-manual.md',
    }
    contents, members = {}, {}
    for group in receipt['groups']:
        if group['group'] not in ('packed32', 'candidate', 'prefetch', 'metadata'):
            continue
        with tarfile.open(raw / group['file'], 'r:gz') as archive:
            for member in archive:
                relative = member.name.removeprefix(prefix)
                if relative in needed:
                    if not member.isfile() or relative in contents:
                        raise ValueError('invalid or duplicate selected member: ' + relative)
                    contents[relative] = archive.extractfile(member).read()
                    members[relative] = {'archive': group['file'], 'member': member.name,
                                         'sha256': sha(contents[relative]), 'bytes': member.size}
    if set(contents) != needed:
        raise ValueError('missing selected archive members: ' + repr(needed - set(contents)))
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    check('review JSON is the archived metadata copy', contents['code-review.json'] == review_bytes)
    check('review script matches its recorded digest',
          sha(contents['offline-code-review.py']) == review['script_sha256'])
    check('manual review is the archived metadata copy',
          contents['code-review-manual.md'] == (report / 'code-review-manual.md').read_bytes())
    commits = {arm: json.loads(contents[arm + '/matrix.json'])['source_commit']
               for arm in ('packed32', 'candidate', 'prefetch')}
    resolved = {}
    for arm, revision in commits.items():
        if not re.fullmatch(r'[0-9a-f]{7,40}', revision):
            raise ValueError('invalid retained Git revision: ' + repr(revision))
        resolved[arm] = subprocess.check_output(
            ['git', 'rev-parse', revision + '^{commit}'], timeout=30).decode().strip()
    check('review candidate is the held checked revision',
          resolved['candidate'] == '76af84414bd4548e11f60c67ae7174ec63644496', resolved)
    check('review candidate provider is distinct from the prefetch trial',
          sha(contents[paths['candidate_provider']]) != sha(contents['prefetch/pipe/build/kdlock_km.ko']))
    inputs, full_workload = {}, []
    with tempfile.TemporaryDirectory(prefix='kdlock-cacheline-static-binding-') as temporary:
        for key, member in paths.items():
            data = contents[member]
            expected = review['inputs'][key]
            check(key + ': reviewed ELF hash equals archived bytes', sha(data) == expected['elf_sha256'])
            arm = member.split('/', 1)[0]
            manifest = json.loads(contents[arm + '/pipe/binaries.json'])
            binary = member.split('/pipe/build/', 1)[1]
            check(key + ': archived build manifest binds the same ELF',
                  manifest[binary]['sha256'] == sha(data), manifest[binary])
            local = Path(temporary) / key / Path(member).name
            local.parent.mkdir()
            local.write_bytes(data)
            inspected = {}
            for tool, options in (('nm', ['-S', '--defined-only']),
                                  ('objdump', ['-dr', '--no-show-raw-insn'])):
                command = [tool, *options, str(local)]
                observed = subprocess.check_output(command, timeout=60)
                normalized = observed
                if tool == 'objdump':
                    # objdump prints its input path once in the file header.
                    check(key + ': exactly one objdump file header path',
                          observed.count(str(local).encode()) == 1)
                    normalized = observed.replace(str(local).encode(), expected['path'].encode())
                check(key + ': independently inspected ' + tool + ' output matches review',
                      sha(normalized) == expected[tool]['stdout_sha256'])
                inspected[tool] = {'command': command, 'stdout_sha256': sha(observed),
                                   'normalized_stdout_sha256': sha(normalized)}
                if key == 'candidate_workload' and tool == 'nm':
                    symbols = [line.split() for line in observed.decode().splitlines()]
                    body, = [line for line in symbols if len(line) == 4 and line[3] == 'rb_body']
                    start, size = int(body[0], 16), int(body[1], 16)
                if key == 'candidate_workload' and tool == 'objdump':
                    # Include internal continuation labels, which split the
                    # original review's symbol-based disassembly dictionary.
                    section = None
                    for line in observed.decode().splitlines():
                        if line.startswith('Disassembly of section '):
                            section = line.removeprefix('Disassembly of section ').removesuffix(':')
                        match = re.match(r'^\s*([0-9a-f]+)(?::| <)', line)
                        if section == '.text' and match and start <= int(match[1], 16) < start + size:
                            full_workload.append(line)
            inputs[key] = {**members[member], 'inspection': inspected}
    result = {
        'schema': 1, 'host': socket.gethostname(),
        'scope': 'Independent inert archive binding and static ELF reader replay; no archived code executed.',
        'script_sha256': sha(Path(__file__).read_bytes()),
        'archive_receipt_sha256': sha((raw / 'archives.json').read_bytes()),
        'code_review_sha256': sha(review_bytes),
        'manual_review_sha256': sha(contents['code-review-manual.md']),
        'source_commits': commits, 'resolved_source_commits': resolved, 'inputs': inputs,
        'candidate_rb_body_full_disassembly': full_workload,
        'checks': checks, 'passed': all(row['passed'] for row in checks),
        'issues': [row for row in checks if not row['passed']],
        'limitations': [
            'ELF inspection does not execute the module or establish a performance result.',
            'objdump path normalization changes only the recorded input filename in its header.',
            'Manual concurrency review and live checks remain separate evidence.',
        ],
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'inputs': len(inputs),
                      'issues': result['issues'], 'output': str(output)}, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
