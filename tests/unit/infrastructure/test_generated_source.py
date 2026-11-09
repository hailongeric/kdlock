"""Execute the production generated-text consumer with exact owner-ref checks."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes


def main():
    code = without_includes(read_source(ROOT / "include/kd_source.h"))
    code += without_includes(read_source(ROOT / "kernel_module/kd_source.c"))
    mutations = {
        "wrong-producer-abi": (
            "extent.abi != KD_GENERATED_TEXT_ABI_VERSION ||",
            "false ||",
        ),
        "reply-reference-not-returned": (
            "if (extent.owner)\n\t\tmodule_put(extent.owner);",
            "if (extent.owner)\n\t\t(void)extent.owner;",
        ),
        "duplicate-query-reference-retained": (
            "ret = 0;\n\t\t\tgoto drop_reply;",
            "ret = 0;\n\t\t\treturn ret;",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kdlock-generated-source-") as temporary:
        directory = Path(temporary)
        for name, mutation in [("production", None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert code.count(before) == 1, (name, code.count(before))
                candidate = code.replace(before, after)
            (directory / "generated_source_production.h").write_text(candidate)
            binary = directory / name
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc")) + [
                    "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(directory), "-I", str(ROOT / "include"),
                    str(ROOT / "tests/unit/infrastructure/generated_source_fixture.c"),
                    "-o", str(binary),
                ], check=True, timeout=30,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True,
                                    timeout=15, check=False)
            if mutation:
                assert result.returncode == 1 and "FAIL line" in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print(f"generated source negative control detected: {name}")
            else:
                assert result.returncode == 0, result.stderr
                print(result.stdout, end="")


if __name__ == "__main__":
    main()
