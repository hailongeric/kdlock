"""Verify captured bytes and recorded outcomes offline, without running a case.

This checks an existing regression output directory, not the current checkout
or guest. Self-consistent manifests are not authentic execution certificates;
retain a trusted outer archive hash and the case-specific protocol oracles.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import zlib
from pathlib import Path, PurePosixPath

import regression_evidence as evidence
from regression import FAULTS

MAX_METADATA = 16 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_MEMBERS = 100000
ARCHIVES = {"artifacts", "protocol", "post-case-builds"}
HASH = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def member_name(name):
    if not isinstance(name, str) or not name or name == ".":
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and str(path) == name


def hash_map(value):
    require(isinstance(value, dict), "file hashes must be an object")
    require(len(value) <= MAX_MEMBERS, "file manifest exceeds member limit")
    for name, digest in value.items():
        require(member_name(name), f"unsafe member name: {name!r}")
        require(
            isinstance(digest, str) and HASH.fullmatch(digest), f"invalid hash: {name}"
        )
    return value


def unique_object(pairs):
    # JSON's normal last-key-wins rule could hide contradictory status/hashes.
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


class Snapshot:
    """Bound reads and reject replacement during the whole offline inspection."""

    def __init__(self):
        self.identities = {}

    def read(self, path, limit=None):
        if limit is None:
            limit = MAX_METADATA
        before = path.lstat()
        require(before.st_size <= limit, f"file exceeds read limit: {path}")
        identity = evidence.file_identity(before)
        data, _ = evidence.regular_bytes(path)
        require(
            identity == evidence.file_identity(path.lstat()), f"changed file: {path}"
        )
        require(
            self.identities.setdefault(path, identity) == identity,
            f"replaced file: {path}",
        )
        return data

    def json(self, path):
        try:
            return json.loads(self.read(path), object_pairs_hook=unique_object)
        except (ValueError, RuntimeError) as error:
            raise RuntimeError(f"{path}: {error}") from error

    def unchanged(self):
        for path, identity in self.identities.items():
            require(
                identity == evidence.file_identity(path.lstat()),
                f"changed file: {path}",
            )

    def archive(self, path, record):
        expected = hash_map(record["files"])
        data = self.read(path, MAX_ARCHIVE)
        require(
            evidence.digest(data) == record["sha256"], f"archive hash mismatch: {path}"
        )
        # Bound the entire decompressed stream, including PAX headers, before
        # tarfile can allocate metadata based on an untrusted header length.
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as raw:
            size = 0
            while chunk := raw.read(65536):
                size += len(chunk)
                require(
                    size <= MAX_EXPANDED, f"archive exceeds expansion limit: {path}"
                )
        actual, expanded = {}, 0
        # Do not extract even a trusted archive: link/device members must never
        # become actionable files. Compare exact membership, not just listed files.
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                require(
                    member.type in {tarfile.REGTYPE, tarfile.AREGTYPE}
                    and member_name(member.name),
                    f"unsafe archive member: {member.name}",
                )
                require(
                    member.name not in actual,
                    f"duplicate archive member: {member.name}",
                )
                expanded += member.size
                require(
                    len(actual) < MAX_MEMBERS and 0 <= expanded <= MAX_EXPANDED,
                    f"archive exceeds expansion limit: {path}",
                )
                require(
                    member.name in expected, f"unlisted archive member: {member.name}"
                )
                digest = hashlib.sha256()
                with archive.extractfile(member) as source:
                    while chunk := source.read(65536):
                        digest.update(chunk)
                actual[member.name] = digest.hexdigest()
        require(
            actual == expected, f"archive member hashes/membership mismatch: {path}"
        )
        return len(actual)


def verify_run(directory):
    directory = Path(os.path.abspath(directory))
    require(
        directory.is_dir() and directory.resolve() == directory,
        "run must be a regular local directory",
    )
    snapshot = Snapshot()
    source = hash_map(snapshot.json(directory / "source.json"))
    source_record = snapshot.json(directory / "source-archive.json")
    require(source == source_record["files"], "source manifests disagree")
    snapshot.archive(directory / "source.tar.gz", source_record)
    environment = snapshot.json(directory / "environment.json")
    require(environment["errors"] == {}, "environment capture has errors")
    require(
        evidence.digest(snapshot.read(directory / "kernel.notes"))
        == environment["kernel_notes_sha256"],
        "boot-note hash mismatch",
    )

    selection = snapshot.json(directory / "selection.json")
    require(isinstance(selection, list) and selection, "selection must be nonempty")
    names = []
    for item in selection:
        name = item["name"]
        require(
            member_name(name)
            and len(PurePosixPath(name).parts) == 1
            and name not in names,
            f"invalid/duplicate case: {name!r}",
        )
        require(
            isinstance(item["command"], list)
            and item["command"]
            and all(isinstance(arg, str) for arg in item["command"]),
            f"invalid recorded command: {name}",
        )
        require(
            isinstance(item["env"], dict)
            and all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in item["env"].items()
            ),
            f"invalid recorded environment: {name}",
        )
        names.append(name)
    journal = []
    path = directory / "results.tsv"
    if os.path.lexists(path):
        for line in snapshot.read(path).decode().splitlines():
            name, status = line.split("\t")
            journal.append((name, int(status)))
    require(
        [name for name, _ in journal] == names[: len(journal)],
        "results are not a unique selection prefix",
    )
    require(
        all(not child.is_dir() or child.name in names for child in directory.iterdir()),
        "unselected case directory",
    )
    cases = []
    for index, (name, status) in enumerate(journal):
        case = directory / name
        result = snapshot.json(case / "result.json")
        flags = (
            "kernel_fault",
            "drained",
            "source_unchanged",
            "evidence_complete",
            "accepted",
        )
        require(
            all(type(result[key]) is bool for key in flags),
            f"invalid result flags: {name}",
        )
        require(
            type(result["script_exit"]) is int
            and result["script_exit"]
            == status
            == int(snapshot.read(case / "exit-status")),
            f"exit statuses disagree: {name}",
        )
        require(
            isinstance(result["errors"], list)
            and all(isinstance(e, str) for e in result["errors"]),
            f"invalid result errors: {name}",
        )
        snapshot.read(case / "output.log")
        fault = bool(FAULTS.search(snapshot.read(case / "dmesg.log").decode()))
        require(
            fault == result["kernel_fault"],
            f"kernel-fault result disagrees with log: {name}",
        )
        accepted = (
            status == 0
            and not fault
            and not result["errors"]
            and all(
                result[k] for k in ("drained", "source_unchanged", "evidence_complete")
            )
        )
        require(accepted == result["accepted"], f"acceptance fields disagree: {name}")
        marker = case / "accepted"
        if accepted:
            require(snapshot.read(marker) == b"", f"invalid acceptance marker: {name}")
        else:
            require(
                not os.path.lexists(marker),
                f"failed case has acceptance marker: {name}",
            )
            require(index == len(journal) - 1, "results continue after a failed case")
        require(
            result["drained"] and result["evidence_complete"],
            f"capture incomplete: {name}",
        )
        manifest = snapshot.json(case / "evidence.json")
        require(
            set(manifest["archives"]) == ARCHIVES,
            f"missing/unexpected archives: {name}",
        )
        files = {
            key: snapshot.archive(case / f"{key}.tar.gz", record)
            for key, record in manifest["archives"].items()
        }
        cases.append({"name": name, "recorded_accepted": accepted, "files": files})
    unrecorded = names[len(journal) :]
    require(
        all(not os.path.lexists(directory / name) for name in unrecorded),
        "case started without a complete result",
    )
    snapshot.unchanged()
    return {
        "format": 1,
        "scope": "stored bytes and recorded outcomes; no payload execution or current JIT certification",
        "source_files": len(source),
        "source_archive_sha256": source_record["sha256"],
        "cases": cases,
        "unrecorded_cases": unrecorded,
        "all_recorded_accepted": not unrecorded
        and all(c["recorded_accepted"] for c in cases),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", type=Path, help="existing regression output directory"
    )
    args = parser.parse_args(argv)
    try:
        report = verify_run(args.directory)
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        EOFError,
        tarfile.TarError,
        zlib.error,
    ) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["all_recorded_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
