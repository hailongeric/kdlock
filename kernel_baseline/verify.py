#!/usr/bin/env python3
"""Read-only checks for the captured guest, not proof of kernel correctness."""

import argparse
import hashlib
import json
import os
import posixpath
import re
import struct
import sys
import tarfile
from pathlib import Path, PurePosixPath


class BaselineError(ValueError):
    pass


def relative_path(name):
    if not isinstance(name, str):
        raise BaselineError("non-string baseline path")
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or str(path) != name:
        raise BaselineError(f"invalid relative path: {name!r}")
    return path


def digest_stream(source):
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def digest_file(path):
    if path.is_symlink() or not path.is_file():
        raise BaselineError(f"missing or non-regular file: {path}")
    with path.open("rb") as source:
        return digest_stream(source)


def check_digest(path, expected):
    if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
        raise BaselineError(f"invalid expected SHA256: {path}")
    actual = digest_file(path)
    if actual != expected:
        raise BaselineError(
            f"SHA256 mismatch: {path}: expected={expected} actual={actual}"
        )


def check_files(root, records):
    if not isinstance(records, dict) or not records:
        raise BaselineError("empty or invalid file manifest")
    for name, expected in records.items():
        path = root / relative_path(name)
        if not path.resolve().is_relative_to(root.resolve()):
            raise BaselineError(f"file escapes baseline root: {name}")
        check_digest(path, expected)
    return len(records)


def note_build_id(data):
    """Parse the raw, little-endian ELF notes exposed by x86 /sys/kernel/notes."""
    offset = 0
    identities = []
    while offset < len(data):
        if len(data) - offset < 12:
            raise BaselineError("truncated ELF note header")
        name_size, desc_size, kind = struct.unpack_from("<III", data, offset)
        name_start = offset + 12
        desc_start = name_start + ((name_size + 3) & ~3)
        end = desc_start + desc_size
        following = desc_start + ((desc_size + 3) & ~3)
        if following > len(data):
            raise BaselineError("truncated ELF note payload")
        name = data[name_start : name_start + name_size]
        if name == b"GNU\0" and kind == 3:
            identities.append(data[desc_start:end].hex())
        offset = following
    if len(identities) != 1 or not identities[0]:
        raise BaselineError("expected exactly one nonempty GNU Build ID")
    return identities[0]


def check_running(expected, uname, notes):
    for field in ("release", "version", "machine"):
        actual = getattr(uname, field)
        if actual != expected[field]:
            raise BaselineError(f"running {field} mismatch: {actual!r}")
    if expected["machine"] != "x86_64":
        raise BaselineError("only x86_64 raw ELF notes are supported")
    actual = note_build_id(notes)
    if actual != expected["build_id"]:
        raise BaselineError(f"running Build ID mismatch: {actual}")
    return actual


def check_archive(root, archive_path, manifest):
    upstream = manifest["upstream"]
    check_digest(archive_path, upstream["sha256"])
    prefix = upstream["directory"]
    relative_path(prefix)
    seen = set()
    with tarfile.open(archive_path, "r|xz") as archive:
        for member in archive:
            path = relative_path(member.name.rstrip("/"))
            if path.parts[0] != prefix:
                raise BaselineError(f"unexpected archive root: {path}")
            if member.isdir():
                continue
            name = PurePosixPath(*path.parts[1:]).as_posix()
            relative_path(name)
            if name in seen:
                raise BaselineError(f"duplicate archive member: {name}")
            seen.add(name)
            actual = root / name
            if member.issym():
                if not actual.is_symlink() or posixpath.normpath(
                    str(actual.readlink())
                ) != posixpath.normpath(member.linkname):
                    raise BaselineError(f"symlink mismatch: {name}")
            elif member.isfile():
                expected = manifest["source_files"].get(name)
                if expected is None:
                    with archive.extractfile(member) as source:
                        expected = digest_stream(source)
                check_files(root, {name: expected})
            else:
                raise BaselineError(f"unsupported archive member: {name}")
    if len(seen) != upstream["entries"]:
        raise BaselineError(f"archive entry count mismatch: {len(seen)}")
    # This scans official members, not arbitrary added or generated build inputs.
    return len(seen)


def verify(bundle, source, archive=None, build=False, running=False):
    manifest = json.loads((bundle / "manifest.json").read_text())
    if not isinstance(manifest, dict):
        raise BaselineError("baseline manifest must be an object")
    schema = manifest.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
        raise BaselineError("unsupported baseline schema")
    result = {"ok": True}
    result["bundle_files"] = check_files(bundle, manifest["bundle_files"])
    result["source_files"] = check_files(source, manifest["source_files"])
    check_digest(source / ".config", manifest["bundle_files"]["guest.config"])
    result["config"] = True
    if archive is not None:
        result["upstream_members"] = check_archive(source, archive, manifest)
    if build:
        result["build_files"] = check_files(source, manifest["build_files"])
    if running:
        result["running_build_id"] = check_running(
            manifest["running"], os.uname(), Path("/sys/kernel/notes").read_bytes()
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--archive", type=Path, help="also compare all official members"
    )
    parser.add_argument(
        "--build", action="store_true", help="hash captured build outputs"
    )
    parser.add_argument(
        "--running", action="store_true", help="check uname and live Build ID"
    )
    args = parser.parse_args()
    try:
        result = verify(
            Path(__file__).resolve().parent,
            args.source.resolve(),
            args.archive,
            args.build,
            args.running,
        )
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
