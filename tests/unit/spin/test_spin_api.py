"""Guest-only public spin compiler contract and exact unpinned control CALLs.

Compile the production public macros and shared assembly, run destructive
provider substitutes at root and nested sites, then compare code/relocations
against the raw unpinned clobber shell. These tests do not execute the JIT or
validate native provider admission; live ownership and performance are separate.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/unit/spin/spin_api_fixture.c"


def macro(header, name):
    lines = header.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if re.match(r"#define " + name + r"\(", line))
    end = start
    while lines[end].endswith("\\"):
        end += 1
    return "\n".join(lines[start:end + 1])


def function_image(obj, directory, function):
    symbols = subprocess.check_output(
        ["nm", "-S", "--defined-only", str(obj)], text=True, timeout=10)
    match = re.search(r"^([0-9a-f]+) ([0-9a-f]+) T " + function + r"$",
                      symbols, re.M)
    assert match, symbols
    start, length = (int(value, 16) for value in match.groups())
    raw = directory / (obj.stem + ".text")
    subprocess.run(["objcopy", "--dump-section", f".text={raw}", str(obj)],
                   check=True, timeout=10)
    code = raw.read_bytes()[start:start + length]
    assert len(code) == length and length
    records = subprocess.check_output(
        ["objdump", "-r", "-j", ".text", str(obj)], text=True, timeout=10)
    relocations = []
    for line in records.splitlines():
        fields = line.split()
        if len(fields) != 3 or not re.fullmatch(r"[0-9a-f]+", fields[0]):
            continue
        offset = int(fields[0], 16)
        if start <= offset < start + length:
            relocations.append((offset - start, *fields[1:]))
    targets = [target.split("-", 1)[0] for _, _, target in relocations]
    assert targets.count("kd_spin_lock_clobber_v1") == 1, relocations
    assert targets.count("kd_spin_unlock_clobber_v1") == 1, relocations
    assert not any("pinned_clobber" in target or "hotlock" in target or
                   "preempt" in target for target in targets), relocations
    if function == "api_nested_pair":
        assert targets.count("kd_mutex_direct_lock_clobber_v1") == 1, relocations
        assert targets.count("kd_mutex_direct_unlock_clobber_v1") == 1, relocations
    return code, relocations


def main():
    with tempfile.TemporaryDirectory(prefix="kd-spin-api-") as directory:
        path = Path(directory)
        caller = []
        for source, names in (
            ("kd_spin_direct.h", ("KD_SPIN_DIRECT_CALL",)),
            ("kd_mutex_direct.h", ("KD_MUTEX_DIRECT_CALL", "KD_MUTEX_DIRECT_LOCK",
                                    "KD_MUTEX_DIRECT_UNLOCK")),
            ("kd_mutex_api.h", ("kd_mutex_lock", "kd_mutex_unlock")),
        ):
            header = (ROOT / "include" / source).read_text()
            caller.extend(macro(header, name) for name in names)
        (path / "caller.h").write_text("\n".join(caller) + "\n")
        api = (ROOT / "include/kd_spin_api.h").read_text()
        (path / "api.h").write_text(re.sub(r"^#include .*$", "", api, flags=re.M))
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-fno-omit-frame-pointer", "-fno-optimize-sibling-calls",
            "-mno-red-zone", "-mpreferred-stack-boundary=4",
            "-I", directory, str(FIXTURE),
        ]
        for bad in ("LOCK", "UNLOCK"):
            rejected = subprocess.run(
                command + ["-DKD_TEST_PUBLIC_API", f"-DKD_TEST_SPIN_API_BAD_{bad}",
                           "-c", "-o", str(path / "bad.o")],
                capture_output=True, text=True, timeout=30)
            assert rejected.returncode and re.search(
                r"incompatible.pointer|incompatible pointer", rejected.stderr), rejected.stderr
        images = []
        for public in (False, True):
            name = "public" if public else "raw-clobber"
            options = ["-DKD_TEST_PUBLIC_API"] if public else []
            binary, obj = path / name, path / (name + ".o")
            subprocess.run(command + options + ["-o", str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)
            subprocess.run(command + options + ["-DKD_TEST_SPIN_API_EQUIVALENCE",
                           "-c", "-o", str(obj)], check=True, timeout=30)
            images.append([function_image(obj, path, name) for name in
                           ("api_root_pair", "api_nested_pair")])
        assert images[0] == images[1], (
            "public facade changed raw clobber root/nested code or relocations", images)
    print("PASS spin API: typed single-evaluation void macros, root/nested compiler spills, "
          "exact unpinned control CALLs and raw-clobber instruction/relocation identity")


if __name__ == "__main__":
    main()
