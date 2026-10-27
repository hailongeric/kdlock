"""Exact Python 3.14 compatibility identity for the pinned Miasm semantic lifter.

Runtime checks never patch dependencies. The explicit --apply operation is
restricted to the designated isolated guest venv and preserves original bytes.
"""
import argparse
import datetime
import difflib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import stat
import sys
import sysconfig
import tempfile

VENV = Path('/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027')
ORIGINAL_SHA256 = 'fc3baced219615c2227a5a5cd50ee3a62b2f1c990aa366bbedd709ae22801fd6'
PATCHED_SHA256 = 'cc4e07d6820a8fe461df71ac47bad434d918c68d3c0473508ebe78657e45fcc6'
PATCH_SHA256 = 'b2e64a61950fbf22b9d1acc6fd1f0f8d80efa08c468d04e7cccd340ac09be820'
PATCH = Path(__file__).with_name('compat') / 'miasm-0.1.5-python314.patch'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target_path():
    require(sys.version_info[:2] == (3, 14), 'this dependency patch requires Python 3.14')
    require(Path(sys.prefix) == VENV and VENV.resolve() == VENV,
            'the designated isolated translation venv is required')
    require(importlib.metadata.version('miasm') == '0.1.5', 'Miasm version differs')
    path = Path(sysconfig.get_path('purelib')) / 'miasm/core/sembuilder.py'
    require(path.resolve().is_relative_to(VENV) and path.is_file() and not path.is_symlink(),
            'dependency source must be a regular file in the isolated venv')
    # Also reject an import shadow that would execute different dependency bytes.
    import miasm.core
    require(Path(miasm.core.__file__).resolve().parent == path.parent,
            'Miasm import path differs from the inspected dependency')
    require(sha(PATCH.read_bytes()) == PATCH_SHA256, 'versioned dependency patch changed')
    return path


def verify_runtime():
    if sys.version_info[:2] < (3, 14):
        return dict(python=sys.version.split()[0], python314_patch_required=False)
    path = target_path()
    require(sha(path.read_bytes()) == PATCHED_SHA256,
            'Miasm Python 3.14 patch missing or changed; run the explicit dependency preflight')
    return dict(python=sys.version.split()[0], miasm='0.1.5', python314_patch_required=True,
                dependency_file=str(path), dependency_sha256=PATCHED_SHA256,
                original_sha256=ORIGINAL_SHA256, patch_sha256=PATCH_SHA256,
                checker_sha256=sha(Path(__file__).read_bytes()))


def patched_source(original):
    require(sha(original) == ORIGINAL_SHA256, 'unrecognized Miasm semantic-builder input')
    before = original.decode()
    changes = (
        ('ast.Num(n=size)', 'ast.Constant(value=size)'),
        ('isinstance(node.func, ast.Str)',
         '(isinstance(node.func, ast.Constant) and\n               isinstance(node.func.value, str))'),
        ('isinstance(node.func.left, ast.Str)',
         'isinstance(node.func.left, ast.Constant) and\n               isinstance(node.func.left.value, str)'),
        ('isinstance(statement.value, ast.Str)',
         'isinstance(statement.value, ast.Constant) and\n                  isinstance(statement.value.value, str)'),
    )
    after = before
    for old, new in changes:
        require(after.count(old) == 1, 'dependency patch context is not unique')
        after = after.replace(old, new)
    actual_patch = ''.join(difflib.unified_diff(before.splitlines(keepends=True),
        after.splitlines(keepends=True), fromfile='a/miasm/core/sembuilder.py',
        tofile='b/miasm/core/sembuilder.py')).encode()
    require(sha(actual_patch) == PATCH_SHA256 and actual_patch == PATCH.read_bytes(),
            'transformation differs from the versioned patch')
    result = after.encode()
    require(sha(result) == PATCHED_SHA256, 'dependency patch output mismatch')
    return result


def apply(receipt_path):
    require(os.geteuid() == 0 and os.uname().release.startswith('7.0.'),
            'apply only in the designated Linux 7 guest')
    require(not receipt_path.exists() and not receipt_path.is_symlink(), 'use a new patch receipt path')
    target = target_path()
    for proc in Path('/proc').glob('[0-9]*'):
        if int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:
            continue
        require(not any(arg.startswith(os.fsencode(VENV) + b'/') and b' ' not in arg for arg in args),
                'another process uses the translation venv: ' + proc.name)
    before = target.read_bytes()
    digest = sha(before)
    require(digest in (ORIGINAL_SHA256, PATCHED_SHA256), 'dependency source changed; refusing patch')
    changed = digest == ORIGINAL_SHA256
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if changed:
        after = patched_source(before)
        backup = receipt_path.with_suffix('.original.py')
        with backup.open('xb') as stream:
            stream.write(before)
        mode = stat.S_IMODE(target.stat().st_mode)
        fd, temporary = tempfile.mkstemp(prefix='.kd-miasm-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            require(target.read_bytes() == before, 'dependency changed during patch preparation')
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    result = dict(applied=changed, idempotent=not changed, before_sha256=digest,
                  verified=verify_runtime(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with receipt_path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.apply:
        require(args.receipt is not None, '--apply requires --receipt')
        result = apply(args.receipt)
    else:
        require(args.receipt is None, '--receipt is for explicit patch application')
        result = verify_runtime()
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
