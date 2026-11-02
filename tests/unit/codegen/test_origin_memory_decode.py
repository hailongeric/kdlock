"""VM-only execution of the production GS decoder and effective-address code."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    source = (ROOT / "kernel_module/execution/origin_memory.inc").read_text()
    code = source[source.index("struct kd_memory_operand {"):
                  source.index("int kd_exec_cont_memory_prepare(")]
    mutations = {
        "production": None,
        "source-rip-shifted": ("case KD_MEMORY_RIP: return next_ip;",
                               "case KD_MEMORY_RIP: return next_ip + 1;"),
        "displacement-zero-extended": ("(long)operand.displacement;",
                                       "(u32)operand.displacement;"),
        "rex-index-lost": ("((rex & 2) << 2)", "0"),
    }
    with tempfile.TemporaryDirectory(prefix="kd-origin-memory-decode-") as temporary:
        temporary = Path(temporary)
        for name, mutation in mutations.items():
            production = code
            if mutation:
                before, after = mutation
                assert before in production, name
                production = production.replace(before, after)
            (temporary / "production.h").write_text(production)
            binary = temporary / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "include"), "-I", str(temporary),
                str(ROOT / "tests/unit/codegen/origin_memory_decode_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15)
            if mutation:
                assert result.returncode == 1 and "FAIL line=" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print("GS decoder mutation detected:", name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end="")


if __name__ == "__main__":
    main()
