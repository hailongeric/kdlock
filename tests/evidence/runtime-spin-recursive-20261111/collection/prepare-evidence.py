"""Copy and inventory already saved kernel mechanism records on the source host."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path('/home/eric/vm/vm-shared/kdlock-main')
SAVED = Path('/tmp/kdlock-kernel4-db7-live-collection-20261111-01')
INITIAL = Path('/tmp/kdlock-kernel4-db7-saved-audit-20261111-01')
VERIFIED = Path('/tmp/kdlock-kernel4-db7-saved-audit-20261111-02')
DESTINATIONS = {'spin': 'runtime-spin-recursive-20261111', 'mutex': 'runtime-mutex-regression-20261111'}
GUEST = json.loads((SAVED / 'guest-index.json').read_text())
GUEST_ROWS = {row['path']: row for row in GUEST['files']}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def save_json(path, value):
    save(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def prepare(profile):
    out = REPO / 'tests/evidence' / DESTINATIONS[profile]
    if out.exists():
        raise ValueError('fresh evidence path required: ' + str(out))
    out.mkdir()
    copied = []

    def copy(origin, relative, guest_name=None):
        if origin.is_symlink() or not origin.is_file():
            raise ValueError('regular retained input required: ' + str(origin))
        data = origin.read_bytes()
        row = GUEST_ROWS.get(guest_name) if guest_name else None
        if row and (len(data) != row['bytes'] or sha(data) != row['sha256']):
            raise ValueError('source-host copy differs from guest index: ' + guest_name)
        save(out / relative, data)
        copied.append({'path': relative, 'origin_source_host': str(origin),
                       'origin_guest': row['source_path'] if row else None,
                       'origin_kind': 'verified guest record' if row else 'retained source-host record',
                       'origin_bytes': len(data), 'origin_sha256': sha(data),
                       'storage_bytes': len(data), 'storage_sha256': sha(data), 'encoding': 'exact bytes'})

    for folder, target in [(f'live-{profile}-output', 'runtime'), (f'live-{profile}-controller', 'controller')]:
        for origin in sorted((SAVED / folder).rglob('*')):
            if origin.is_file():
                name = origin.relative_to(SAVED).as_posix()
                copy(origin, target + '/' + origin.relative_to(SAVED / folder).as_posix(), name)
    for suffix in ('child.json', 'result.json'):
        name = profile + '-dispatch-' + suffix
        copy(SAVED / name, 'controller/dispatch-' + suffix, name)
    for suffix in ('stdout', 'stderr'):
        name = profile + '-dispatch.' + suffix
        copy(SAVED / name, 'controller/dispatch.' + suffix, name)
    single = {
        f'kdlock-main-kernel4-db7-{profile}-actual-argv.json': 'controller/dispatched-argv.json',
        'kdlock-main-kernel4-fixture-with-span.py': 'source/fixture-controller.py',
        'kdlock-main-db7d7d6e-kernel4-state.json': 'source/state.json',
        'kdlock-main-db7d7d6e-kernel4-manifest.json': 'source/manifest.json',
        'kdlock-main-db7d7d6e-kernel4-fixture-inputs.json': 'source/fixture-inputs.json',
        'actual-kernel4-build-inputs.json': 'source/kernel-package.json',
        'actual-kernel4-six-kernel-pins.json': 'source/kernel-pins.json',
        'module-build-receipts/result.json': 'source/module-build-result.json',
        'combined-live-poststate.json': 'context/combined-live-poststate.json',
        'combined-live-dmesg.txt': 'context/combined-live-dmesg.txt',
        'kdlock-kernel4-db7-live-recovery.json': 'context/recovery-snapshot.json',
        'preparation.json': 'context/preparation.json',
        'pre-transfer-gates.json': 'context/pre-transfer-gates.json',
    }
    for name, target in single.items():
        copy(SAVED / name, target, name)
    for name in ('guest-index.json', 'verification.json', 'copy-command.json', 'copy.stdout', 'copy.stderr'):
        copy(SAVED / name, 'collection/original-' + name)
    copy(Path('/tmp/kdlock-main-prepare-kernel4-fixture.py'), 'source/export-helper.py')
    copy(Path('/tmp/kdlock-main-kernel4-db7-live-after-build-proposed-argv.json'), 'source/prepared-live-argv.json')
    copy(Path('/tmp/kdlock-copy-db7-live.py'), 'collection/copy-helper.py')
    copy(Path(__file__), 'collection/prepare-evidence.py')
    for source, target in ((INITIAL, 'audit/initial'), (VERIFIED, 'audit/verified')):
        copy(source / 'audit.py', target + '/audit.py')
        for origin in sorted((source / profile).rglob('*')):
            if origin.is_file():
                copy(origin, target + '/' + origin.relative_to(source / profile).as_posix())
    delta = subprocess.run(['diff', '-u', str(INITIAL / 'audit.py'), str(VERIFIED / 'audit.py')],
                           capture_output=True, check=False)
    if delta.returncode != 1:
        raise ValueError('expected the retained metadata correction diff')
    save(out / 'audit/metadata-correction.diff', delta.stdout)
    selected = {row['path']: row for row in copied if row['origin_guest']}
    save_json(out / 'remote-index.json', {
        'scope': 'Exact selected guest files from the complete original two-profile inventory.',
        'original_index_sha256': sha((SAVED / 'guest-index.json').read_bytes()),
        'original_count': GUEST['count'], 'original_bytes': GUEST['bytes'],
        'count': len(selected), 'bytes': sum(row['origin_bytes'] for row in selected.values()),
        'files': selected,
    })
    save_json(out / 'copy-index.json', {'copies': copied, 'copy_count': len(copied),
                                      'origin_bytes': sum(row['origin_bytes'] for row in copied),
                                      'scope': 'Source-host exact-byte preparation from already verified guest copies and retained audit executions.'})
    save_json(out / 'collection.json', {
        'profile': profile, 'source_collection': str(SAVED),
        'original_guest_index_sha256': sha((SAVED / 'guest-index.json').read_bytes()),
        'original_verified_guest_files': GUEST['count'], 'original_verified_guest_bytes': GUEST['bytes'],
        'source_commit': 'db7d7d6e38e1341e24b643553bd83633616d4ea7',
        'core_commit': '2d0ad60b0bc46929f3070aefa364e710c0a81115',
        'initial_auditor_sha256': sha((INITIAL / 'audit.py').read_bytes()),
        'verified_auditor_sha256': sha((VERIFIED / 'audit.py').read_bytes()),
        'scope': 'Copies and static hashes only. The saved audit return codes describe prior source-host byte inspections. No new project import, test, guest/HMP action or runtime execution occurs here.',
    })
    return out


if __name__ == '__main__':
    for profile in DESTINATIONS:
        print(prepare(profile))
