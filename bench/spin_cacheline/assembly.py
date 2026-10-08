#!/usr/bin/env python3
"""Export distinct critical sections' assembly, without executing a workload.

The runner calls capture only after Session.execute has joined workers, stopped
translators and retired/unloaded modules. Saved evidence can use the same path.
bin.txt disassembles the JIT binary; native.S supplies the pre-JIT comparison.
"""
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path


TEMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp/spin_cacheline"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def component(name):
    """Session names from a saved plan must stay one directory component."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError(f"invalid session name: {name!r}")
    return name


def native_body(disassembly, cachelines):
    """Keep one complete ELF symbol, including its relocation annotations."""
    symbol = f"sc_body_{cachelines}"
    boundaries = list(re.finditer(
        r"^(?:[0-9a-fA-F]+ <([^>]+)>:|Disassembly of section .+:)$",
        disassembly, re.MULTILINE))
    found = [i for i, match in enumerate(boundaries) if match[1] == symbol]
    if len(found) != 1:
        raise ValueError(f"expected one {symbol} in payload-disassembly.txt")
    i = found[0]
    end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(disassembly)
    header = (f"# Pre-JIT {symbol}, from the saved module's objdump -dr output.\n"
              "# Addresses are ELF section offsets; relocation lines name their targets.\n")
    return (header + disassembly[boundaries[i].start():end].rstrip() + "\n").encode()


def artifacts(session):
    """Use the recorded RIP/TGID, never an arbitrary first workspace match.

    Incomplete/undrained sessions are skipped before touching their workspace.
    Published-but-unused NO_JIT images remain useful, with their status intact.
    """
    record_bytes = (session / "session.json").read_bytes()
    record = json.loads(record_bytes)
    if (record.get("arm") != "kdlock" or record.get("execution_status") != "OK" or
            record.get("drained") is not True):
        return None
    if component(record["name"]) != session.name:
        raise ValueError("session name does not match its directory")
    publication = record.get("published_before")
    if not publication or publication != record.get("published_after"):
        raise ValueError(f"{session.name}: missing or changed publication")
    if record.get("retired") != dict(state=2, modules=0, frames=0, writers=0):
        raise ValueError(f"{session.name}: retirement did not confirm drain")
    entry = publication["entry"]
    folder = session / "workspace/daemon" / hex(entry["entry"]) / str(entry["tgid"]) / "asm"
    if not folder.resolve().is_relative_to(session.resolve()):
        raise ValueError("assembly workspace escapes its session")
    inputs = {}
    for name in ("jit.bin", "jit.S", "bin.txt"):
        source = folder / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"missing regular assembly artifact: {source}")
        data = source.read_bytes()
        if not data:
            raise ValueError(f"empty assembly artifact: {source}")
        # Older sessions hash jit.bin/jit.S only. Keep them exportable while
        # recording that bin.txt's hash was first collected at export time.
        expected = publication["images"].get(name)
        if name != "bin.txt" and expected is None:
            raise ValueError(f"{session.name}: missing published hash for {name}")
        if expected is not None and sha256(data) != expected:
            raise ValueError(f"{session.name}: published hash mismatch for {name}")
        inputs[name] = data
    payload = (session.parent / "payload-disassembly.txt").read_bytes()
    files = {"bin.txt": inputs["bin.txt"], "JIT.S": inputs["jit.S"],
             "native.S": native_body(payload.decode(), record["cachelines"])}
    metadata = {key: record[key] for key in (
        "name", "cachelines", "threads", "iterations", "repeat", "cpus",
        "execution_status", "drained", "jit_status", "jit_bodies", "jit_share")}
    metadata.update(
        entry=entry, source_session=str(session), session_sha256=sha256(record_bytes),
        source_asm=str(folder.relative_to(session)),
        jit_binary_sha256=sha256(inputs["jit.bin"]),
        bin_txt_hashed_during_measurement="bin.txt" in publication["images"],
        payload_disassembly_sha256=sha256(payload),
        source_names={"bin.txt": "bin.txt", "JIT.S": "jit.S",
                      "native.S": f"payload-disassembly.txt:sc_body_{record['cachelines']}"},
        sha256={name: sha256(data) for name, data in files.items()})
    return files, metadata


def replace_text(path, text):
    """One writer publishes complete indexes for readers following a scan."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".index-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class AssemblyArchive:
    """One copy per payload/content pair, independent of threads and repeats.

    Each invocation has its own directory so separate frozen runs stay distinct.
    Content hashes avoid hiding a changed translation behind its symbol.
    """

    def __init__(self, run, root=TEMP_ROOT):
        self.run = Path(run).resolve()
        self.root = Path(root)
        self.path = None
        self.sessions = set()
        self.sections = {}

    def capture(self, session):
        session = Path(session).resolve()
        if session.parent != self.run:
            raise ValueError("session does not belong to this run")
        if session.name in self.sessions:
            raise FileExistsError(f"assembly source already recorded: {session}")
        result = artifacts(session)
        if result is None:
            return None
        files, metadata = result
        symbol = f"sc_body_{metadata['cachelines']}"
        # Include all three views. JIT output may differ at the same payload
        # size; keep such content distinct without introducing thread groups.
        fingerprint = sha256(json.dumps(metadata["sha256"], sort_keys=True).encode())
        key = (symbol, fingerprint)
        source = {k: v for k, v in metadata.items() if k not in (
            "cachelines", "threads", "iterations", "repeat", "cpus", "sha256", "source_names")}
        if key in self.sections:
            section = self.sections[key]
            section["sources"].append(source)
            destination = self.path / section["directory"]
            replace_text(destination / "metadata.json", json.dumps(section, indent=2) + "\n")
            self.sessions.add(session.name)
            self.index()
            return destination
        if self.path is None:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path = Path(tempfile.mkdtemp(prefix=self.run.name[:80] + "-", dir=self.root))
        directory = symbol
        if any(existing[0] == symbol for existing in self.sections):
            directory += "-" + fingerprint[:12]
        destination = self.path / directory
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"assembly content already exported: {destination}")
        section = dict(critical_section=symbol, cachelines=metadata["cachelines"],
                       directory=directory, sha256=metadata["sha256"],
                       source_names=metadata["source_names"], sources=[source])
        # A critical section becomes visible only when all views exist. Later
        # matching sessions extend provenance, never create another code copy.
        staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.path))
        try:
            for name, data in files.items():
                (staging / name).write_bytes(data)
            (staging / "metadata.json").write_text(json.dumps(section, indent=2) + "\n")
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        self.sections[key] = section
        self.sessions.add(session.name)
        self.index()
        return destination

    def index(self):
        sections = sorted(self.sections.values(), key=lambda r: (r["cachelines"], r["directory"]))
        replace_text(self.path / "index.json", json.dumps(dict(
            schema=2, source_run=str(self.run), source_sessions=len(self.sessions),
            critical_sections=sections), indent=2) + "\n")
        lines = [
            "# Spin assembly archive", "", f"Original evidence: `{self.run}`.", "",
            "Group by critical section. Identical assembly is stored once; metadata.json",
            "lists every drained source session. JIT execution still requires each session's",
            "returned-body evidence. Different contents receive a hash suffix.", "",
            "- `native.S`: full source body disassembly with relocations and ELF section offsets.",
            "- `JIT.S`: unchanged copy of the generator's asm/jit.S.",
            "- `bin.txt`: JIT machine-code disassembly, including the wrapper, from binary offset zero.",
            "- `metadata.json`: section identity, SHA256 hashes and drained source sessions.", "",
            "Export updates the index; it does not execute assembly or rerun measurements.", "",
            "| Critical section | Cachelines | Source sessions | Native | Generated | JIT disassembly |",
            "| --- | ---: | ---: | --- | --- | --- |",
        ]
        for row in sections:
            name = row["directory"]
            lines.append(
                f"| [{name}]({name}/metadata.json) | {row['cachelines']} | {len(row['sources'])} | "
                f"[native.S]({name}/native.S) | "
                f"[JIT.S]({name}/JIT.S) | [bin.txt]({name}/bin.txt) |")
        replace_text(self.path / "README.md", "\n".join(lines) + "\n")


def capture_completed(archive, session):
    """Runner boundary: export and record its location after successful cleanup."""
    previous = len(archive.sections)
    destination = archive.capture(session)
    if destination is not None:
        replace_text(archive.run / "assembly-export.json", json.dumps(dict(
            directory=str(archive.path), index=str(archive.path / "README.md"),
            source_sessions=len(archive.sessions),
            exported_critical_sections=len(archive.sections)), indent=2) + "\n")
        if len(archive.sections) > previous:
            print(f"  Assembly: {destination}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="saved benchmark output containing plan.json")
    args = parser.parse_args(argv)
    archive = AssemblyArchive(args.run)
    for spec in json.loads((archive.run / "plan.json").read_text()):
        session = archive.run / component(spec["name"])
        if (session / "session.json").is_file():
            archive.capture(session)
    # Offline export deliberately does not add a pointer to immutable old evidence.
    print(json.dumps(dict(directory=str(archive.path) if archive.path else None,
                          source_sessions=len(archive.sessions),
                          exported_critical_sections=len(archive.sections))))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Assembly export failed: {error}") from error
