#!/usr/bin/env python3
"""Export committed source and Git-object hashes on the source host only."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

REPO = Path('/home/eric/vm/vm-shared/kdlock-main')
CORE = '2d0ad60b0bc46929f3070aefa364e710c0a81115'
BASE = '1b50e37382d2c739b16953027c47d7e2388562f0'
PATHS = ['AGENTS.md', 'README.md', 'Kbuild', 'Kconfig',
         'disassem', 'include', 'kernel', 'tests/kernel']
FIXTURE = ['tests/kernel/payload/Kbuild',
           'tests/kernel/payload/runtime_fixture.c',
           'tests/kernel/payload/runtime_fixture_observe.inc',
           'tests/kernel/run_runtime_fixture.py',
           'tests/kernel/spin/payload/Kbuild',
           'tests/kernel/spin/payload/spin_runtime_fixture.c',
           'tests/kernel/spin/run_spin_runtime_fixture.py']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package_files(commit, count):
    paths = git('ls-tree', '-r', '--name-only', commit,
                '--', 'Kbuild', 'Kconfig', 'include', 'kernel').decode().splitlines()
    names = [name for name in paths if name in {'Kbuild', 'Kconfig'} or
             (Path(name).parent.as_posix() in {'include', 'kernel'} and
              Path(name).suffix in {'.c', '.h', '.S'})]
    if len(names) != count:
        raise ValueError('unexpected exact kernel package count: ' + repr(names))
    return {name: sha(git('show', commit + ':' + name)) for name in sorted(names)}


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        raise ValueError('an explicit full reviewed fixture commit is required')
    commit = git('rev-parse', '--verify', args.commit + '^{commit}').decode().strip()
    if commit != args.commit:
        raise ValueError('fixture commit differs')
    subprocess.run(['git', 'merge-base', '--is-ancestor', CORE, commit], cwd=REPO, check=True)
    prefix = args.prefix
    if not prefix.is_absolute() or prefix.parent.resolve() != Path('/tmp'):
        raise ValueError('fresh top-level /tmp snapshot prefix required')
    suffixes = ['.tar', '-state.json', '-manifest.json', '-build-inputs.json', '-fixture-inputs.json']
    outputs = [Path(str(prefix) + suffix) for suffix in suffixes]
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise ValueError('snapshot outputs already exist')
    files = package_files(CORE, 67)
    base_files = package_files(BASE, 66)
    for name, expected in files.items():
        if sha(git('show', commit + ':' + name)) != expected:
            raise ValueError('fixture snapshot changes a built core input: ' + name)
    for name in FIXTURE:
        git('cat-file', '-e', commit + ':' + name)
    status_before = git('status', '--short', '--branch').decode()
    archive, state_path, manifest_path, package_path, fixture_path = outputs
    subprocess.run(['git', 'archive', '--format=tar', '--output', str(archive), commit,
                    '--', *PATHS], cwd=REPO, check=True)
    manifest = {}
    with tarfile.open(archive) as source:
        for member in source:
            if member.isdir():
                continue
            if (not member.isfile() or member.name.startswith('/') or
                    '..' in Path(member.name).parts or member.name in manifest):
                raise ValueError('unexpected committed archive member: ' + member.name)
            data = source.extractfile(member).read()
            manifest[member.name] = {'bytes': len(data), 'sha256': sha(data)}
    if not set(FIXTURE) <= manifest.keys() or any(
            manifest[name]['sha256'] != expected for name, expected in files.items()):
        raise ValueError('archive is missing or changes a required kernel/fixture input')
    changed = [name for name, expected in files.items() if expected != base_files.get(name)]
    package = {
        'format': 'kdlock.kernel-build-input-overlay.v2',
        'source_git_head': CORE, 'git_head': CORE, 'core_git_head': CORE,
        'base_git_head': BASE, 'fixture_git_head': commit,
        'intended_kernelrelease': '7.0.0-38-kdrebuild4',
        'build_input_count': len(files), 'files': files, 'base_files': base_files,
        'changed': changed, 'added': [name for name in changed if name not in base_files],
        'scope': 'Exact committed kernel package hashes, distinct from the later fixture revision. '
                 '27 C and 3 concrete assembly units. wrapper.S is a per-image template.',
    }
    state = {
        'commit': commit, 'core_commit': CORE, 'paths': PATHS,
        'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive.read_bytes()),
        'files': len(manifest), 'source_bytes': sum(row['bytes'] for row in manifest.values()),
        'source_worktree_status_before': status_before,
        'source_worktree_status_after': git('status', '--short', '--branch').decode(),
        'scope': 'Exact committed source archive only. No project import, compilation, test, '
                 'source execution, guest transfer or VM change.',
    }
    fixture = {
        'source_git_head': commit, 'core_git_head': CORE,
        'files': {name: manifest[name] for name in FIXTURE},
        'scope': 'Both separate fixture modules and shared runner/private include. '
                 'Invocation bounds are supplied separately. No behavioral evidence.',
    }
    for path, value in [(state_path, state), (manifest_path, manifest),
                        (package_path, package), (fixture_path, fixture)]:
        save(path, value)
    summary = {'source_commit': commit, 'core_commit': CORE,
               'source_files': len(manifest), 'kernel_inputs': len(files),
               'outputs': {str(path): {'bytes': path.stat().st_size,
                                      'sha256': sha(path.read_bytes())} for path in outputs}}
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
