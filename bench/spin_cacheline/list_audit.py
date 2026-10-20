"""Cold ELF and loaded-image checks for the resident-list prefetch variants."""
import hashlib
import os
from pathlib import Path
import re
import subprocess

from elftools.elf.elffile import ELFFile
from bench_runtime import Failure, digest, registry, require, status
from native_image import read_image
from summarize import write_json


READ_PREFETCH = {"prefetchnta", "prefetcht0", "prefetcht1", "prefetcht2"}


def symbol(elf, name):
    table = elf.get_section_by_name(".symtab")
    matches = table.get_symbol_by_name(name) if table is not None else []
    require(matches is not None and len(matches) == 1, "missing/ambiguous symbol: " + name)
    found = matches[0]
    require(isinstance(found["st_shndx"], int), "undefined symbol: " + name)
    return found


def inspect_bytes(code, start, prefetch, output):
    """Decode an exact code interval, excluding headers, comments and decoys."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".bin").write_bytes(code)
    try:
        text = subprocess.check_output(
            ["objdump", "-D", "-w", "-z", "--insn-width=16", "-b", "binary", "-m", "i386:x86-64",
             "--adjust-vma=" + str(start), str(output.with_suffix(".bin"))],
            text=True, stderr=subprocess.STDOUT, timeout=15)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        # This process only decodes saved bytes; check_output has reaped it.
        # Route failure through Session's ordinary drain checks and reporting,
        # never leave a loaded session mislabeled PREPARING or accept a skip.
        partial = error.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        output.with_suffix(".txt").write_text(partial + "\n" + str(error) + "\n")
        raise Failure("PREPARATION_FAILED",
                      "resident-list disassembly failed: " + str(error)) from error
    output.with_suffix(".txt").write_text(text)
    hints, cursor = [], start
    for match in re.finditer(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)([^\n]*)$", text, re.M):
        offset, raw, instruction = int(match[1], 16), bytes.fromhex(match[2]), match[3].strip()
        require(offset == cursor and raw == code[cursor-start:cursor-start+len(raw)] and
                instruction and "(bad)" not in instruction and ".byte" not in instruction,
                "incomplete/invalid resident-list disassembly")
        words = instruction.split(None, 1)
        mnemonic, operand = words[0], words[1] if len(words) == 2 else ""
        require(operand or not re.fullmatch(r"rex(?:\.[A-Za-z]+)?|data16|addr32|repz|repnz|lock|[cdefgs]s",
                                           mnemonic), "truncated instruction prefix")
        if mnemonic.startswith("prefetch"):
            hints.append(dict(offset=offset, mnemonic=mnemonic, operand=operand))
        cursor += len(raw)
    require(code and cursor == start + len(code), "incomplete resident-list code interval")
    require(all(row["mnemonic"] in READ_PREFETCH for row in hints),
            "unexpected write/unknown prefetch in resident-list body")
    require(bool(hints) == prefetch, "resident-list prefetch does not match requested variant")
    return dict(start=start, bytes=len(code), sha256=hashlib.sha256(code).hexdigest(), hints=hints)


def functions(binary, names, prefetch, output):
    """Inspect compiled payloads equally for Native, TCLock and KD."""
    output = Path(output)
    with Path(binary).open("rb") as stream:
        elf = ELFFile(stream)
        require(elf["e_machine"] == "EM_X86_64" and elf["e_type"] == "ET_REL",
                "resident-list payload must be relocatable x86-64 ELF")
        rows = {}
        for name in names:
            entry = symbol(elf, name)
            section = elf.get_section(entry["st_shndx"])
            start, size = entry["st_value"], entry["st_size"]
            require(entry["st_info"]["type"] == "STT_FUNC" and section["sh_flags"] & 4 and
                    size > 0 and start + size <= section["sh_size"],
                    "invalid resident-list function extent")
            rows[name] = inspect_bytes(section.data()[start:start + size], start,
                                       prefetch, output / name)
            rows[name]["section"] = section.name
    result = dict(binary=str(binary), sha256=digest(binary), prefetch=prefetch, functions=rows)
    write_json(output / "audit.json", result)
    return result


def generated_body(obj, upload):
    """Bind generated code bounds to the exact uploaded bytes."""
    with Path(obj).open("rb") as stream:
        elf = ELFFile(stream)
        require(elf["e_machine"] == "EM_X86_64" and elf["e_type"] == "ET_REL",
                "generated list object must be relocatable x86-64 ELF")
        begin, end = symbol(elf, "generated_body"), symbol(elf, "comp_syscall")
        section = elf.get_section(begin["st_shndx"])
        require(begin["st_shndx"] == end["st_shndx"] and section.name == ".text" and
                section["sh_flags"] & 4 and section.data() == upload and
                48 <= begin["st_value"] < end["st_value"] <= len(upload),
                "generated list extent differs from uploaded image")
        for candidate in elf.iter_sections():
            require(not (candidate["sh_flags"] & 2 and candidate["sh_size"] and
                         candidate.name != ".text"), "unexpected allocatable generated section")
            if candidate["sh_type"] in ("SHT_REL", "SHT_RELA"):
                require(candidate["sh_info"] != begin["st_shndx"] or
                        candidate.num_relocations() == 0, "unresolved generated text relocation")
        return begin["st_value"], end["st_value"]


def capture(session_path, publication, prefetch):
    """Read only an owned, quiescent image after its translator has stopped.

    Ordinary spin/rwlock images can be mutable. This proves byte equality at
    this boundary; normal publication checks still bracket the measured run.
    No helper relocation or source-text read is part of this list-only audit.
    """
    session_path = Path(session_path)
    entry = publication["entry"]
    folder = (session_path / "workspace/daemon" / hex(entry["entry"]) /
              str(entry["tgid"]) / "asm")
    upload = (folder / "jit.bin").read_bytes()
    require(len(upload) >= 48 and upload[9:16] == b"KDWB002" and
            upload[25:32] == b"KDWC002" and
            upload[41:45] == b"KDAB" and upload[46] == 2 and
            entry["entry_abi"] in (1, 2, 3) and
            upload[45] == entry["entry_abi"] and upload[47] == entry["requirements"] and
            (entry["requirements"] == 0 or
             (entry["requirements"] == 2 and entry["entry_abi"] == 1)),
            "list audit does not support this generated-image contract")
    require(digest(folder / "jit.bin") == publication["images"]["jit.bin"] and
            digest(folder / "jit.o") == publication["images"]["jit.o"],
            "list publication artifacts changed")
    begin, end = generated_body(folder / "jit.o", upload)
    fd = os.open("/dev/kd_dev", os.O_RDONLY | os.O_CLOEXEC)
    try:
        before, source = registry(), status()
        require(entry in before and source == publication["source"] and
                source["state"] == 0 and source["frames"] == source["writers"] == 0,
                "list image is not quiescent", "UNDRAINED")
        loaded = read_image(entry["code"], len(upload))
        require(loaded == upload, "loaded list image differs from upload", "DATA_ERROR")
        require(registry() == before and status() == source,
                "list registry/source changed during readback", "UNDRAINED")
    finally:
        os.close(fd)
    output = session_path / "list-image"
    result = inspect_bytes(loaded[begin:end], begin, prefetch, output / "generated-body")
    (output / "loaded.bin").write_bytes(loaded)
    result.update(entry=entry, prefetch=prefetch, jit_object_sha256=digest(folder / "jit.o"),
                  uploaded_sha256=hashlib.sha256(upload).hexdigest(),
                  loaded_sha256=hashlib.sha256(loaded).hexdigest(), byte_for_byte_match=True,
                  method="Quiescent /proc/kcore read under readonly provider reference before warmup")
    write_json(output / "audit.json", result)
    return result
