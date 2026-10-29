"""Guest-only actual root-context admission with substituted CPU accessors."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]


def main():
    with tempfile.TemporaryDirectory(prefix="kd-spin-proxy-context-") as name:
        path = Path(name)
        (path / "proxy_context_production.h").write_bytes(
            (ROOT / "kernel_module/spin/context.inc").read_bytes())
        for rcu in (0, 1):
            binary = path / f"context-{rcu}"
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I", str(path), *(["-DCONFIG_PREEMPT_RCU=1"] if rcu else []),
                str(ROOT / "tests/unit/spin/spin_proxy_context_fixture.c"),
                "-o", str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
