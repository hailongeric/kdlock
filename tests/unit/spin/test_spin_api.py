"""Guest-only ordinary spin facade: actual compiler clobbers and code identity.

Use the existing destructive-callee fixture with the public macros, including
two GS gates, both acquisition routes and nested/early release. Compare a
compiled ordinary pair against DIRECT including relocations. Physical queue
concurrency and returned kernel JIT bodies remain separate live evidence.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/unit/spin/spin_paired_abi_fixture.c"


def function_image(obj, directory):
    symbols = subprocess.check_output(
        ["nm", "-S", "--defined-only", str(obj)], text=True, timeout=10)
    match = re.search(r"^([0-9a-f]+) ([0-9a-f]+) T api_equivalent_pair$",
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
    assert any("kd_spin_lock_pinned_clobber_v1" in target
               for _, _, target in relocations), relocations
    assert any("kd_spin_unlock_clobber_v1" in target
               for _, _, target in relocations), relocations
    return code, relocations


def main():
    with tempfile.TemporaryDirectory(prefix="kd-spin-api-") as directory:
        path = Path(directory)
        for source, target in (("kd_spin_direct.h", "paired.h"),
                               ("kd_spin_api.h", "api.h")):
            header = (ROOT / "include" / source).read_text()
            (path / target).write_text(re.sub(r"^#include .*$", "", header, flags=re.M))
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-fno-omit-frame-pointer",
            "-fno-optimize-sibling-calls", "-mno-red-zone",
            "-mpreferred-stack-boundary=4", "-I", directory, str(FIXTURE),
        ]
        binary = path / "public-api"
        subprocess.run(command + ["-DKD_TEST_PUBLIC_API", "-o", str(binary)],
                       check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)
        rejected = subprocess.run(
            command + ["-DKD_TEST_PUBLIC_API", "-DKD_TEST_SPIN_API_BAD_TYPE",
                       "-c", "-o", str(path / "bad.o")],
            capture_output=True, text=True, timeout=30)
        assert rejected.returncode and re.search(
            r"incompatible.pointer|incompatible pointer", rejected.stderr), rejected.stderr
        images = []
        for public in (False, True):
            obj = path / ("public.o" if public else "direct.o")
            options = ["-DKD_TEST_SPIN_API_EQUIVALENCE"]
            if public:
                options.append("-DKD_TEST_PUBLIC_API")
            subprocess.run(command + options + ["-c", "-o", str(obj)],
                           check=True, timeout=30)
            images.append(function_image(obj, path))
        assert images[0] == images[1], (
            "public facade changed DIRECT code or relocation identity", images)
    print("PASS spin facade: typed single-evaluation void macros, compiler-owned spills, "
          "nested release and identical DIRECT instructions/relocations")


if __name__ == "__main__":
    main()
