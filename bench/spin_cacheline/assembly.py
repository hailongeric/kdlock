#!/usr/bin/env python3
"""Export completed sessions' assembly for inspection, without executing a workload.

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
    """A fresh directory per invocation; existing runs and source evidence stay intact."""

    def __init__(self, run, root=TEMP_ROOT):
        self.run = Path(run).resolve()
        self.root = Path(root)
        self.path = None
        self.sessions = []

    def capture(self, session):
        session = Path(session).resolve()
        if session.parent != self.run:
            raise ValueError("session does not belong to this run")
        result = artifacts(session)
        if result is None:
            return None
        files, metadata = result
        if self.path is None:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path = Path(tempfile.mkdtemp(prefix=self.run.name[:80] + "-", dir=self.root))
        destination = self.path / session.name
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"assembly session already exported: {destination}")
        # A session becomes visible only when every file and its metadata exist.
        staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.path))
        try:
            for name, data in files.items():
                (staging / name).write_bytes(data)
            (staging / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        self.sessions.append(metadata)
        self.index()
        return destination

    def index(self):
        replace_text(self.path / "index.json", json.dumps(dict(
            schema=1, source_run=str(self.run), sessions=self.sessions), indent=2) + "\n")
        lines = [
            "# Spinlock 汇编查看目录", "", f"原始结果：`{self.run}`。", "",
            "每行来自一个已完成并排空的 kdlock 会话。NO_JIT 表示测量期未执行正文；",
            "有生成文件不能作为实际 JIT 执行证据。原生组没有 JIT 生成物。", "",
            "- `native.S`：翻译前的完整 `sc_body_N`，提取自已保存模块的反汇编；",
            "  地址为 ELF 节内偏移，保留重定位注释，不是 guest 运行地址。",
            "- `JIT.S`：生成器 `asm/jit.S` 的原样副本（仅改变文件名大小写）。",
            "- `bin.txt`：JIT 机器码（含 wrapper）的反汇编，地址从二进制偏移 0 开始。",
            "- `metadata.json`：原始路径、入口/TGID、参数、JIT 次数/占比和文件 SHA256。", "",
            "索引随已排空会话更新；导出不执行汇编、不重跑测试、不改变历史结果。", "",
            "| 会话 | cacheline | 线程 | repeat | JIT 状态 | JIT 次数 | JIT 占比 | 翻译前 | 生成源码 | JIT 反汇编 |",
            "| --- | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | --- |",
        ]
        for row in self.sessions:
            name = row["name"]
            lines.append(
                f"| [{name}]({name}/metadata.json) | {row['cachelines']} | {row['threads']} | "
                f"{row['repeat']} | {row['jit_status']} | {row['jit_bodies']} | "
                f"{row['jit_share']:.4%} | [native.S]({name}/native.S) | "
                f"[JIT.S]({name}/JIT.S) | [bin.txt]({name}/bin.txt) |")
        replace_text(self.path / "README.md", "\n".join(lines) + "\n")


def capture_completed(archive, session):
    """Runner boundary: export and record its location after successful cleanup."""
    destination = archive.capture(session)
    if destination is not None:
        replace_text(archive.run / "assembly-export.json", json.dumps(dict(
            directory=str(archive.path), index=str(archive.path / "README.md"),
            exported_sessions=len(archive.sessions)), indent=2) + "\n")
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
                          exported_sessions=len(archive.sessions))))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Assembly export failed: {error}") from error
