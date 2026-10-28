"""Guest-only build refusal for configurations excluded by every KD family.

Preprocess the real object headers with empty kernel dependency headers so the
test isolates configuration admission. Normal Kbuild checks the actual kernel
types separately; this does not claim execution on an unsupported kernel.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = ("CONFIG_PREEMPT_RT", "CONFIG_DEBUG_MUTEXES",
           "CONFIG_DEBUG_LOCK_ALLOC", "CONFIG_LOCKDEP")
HEADERS = ("kd_config.h", "kd_spin_type.h", "kd_mutex_types.h", "kd_rwsem_types.h")


def main():
    with tempfile.TemporaryDirectory(prefix="kd-config-") as directory:
        path = Path(directory)
        for name in ("atomic.h", "types.h", "spinlock.h", "osq_lock.h", "wait.h"):
            header = path / "linux" / name
            header.parent.mkdir(exist_ok=True)
            header.write_text("/* Preprocessing-only kernel dependency. */\n")
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-E", "-P", "-x", "c", "-I", directory, "-I", str(ROOT / "include"),
            *(f"-U{config}" for config in CONFIGS),
        ]
        for header in HEADERS:
            source = f'#include "{header}"\n'
            subprocess.run(command + ["-"], input=source, text=True,
                           capture_output=True, check=True, timeout=10)
            for config in CONFIGS:
                rejected = subprocess.run(command + [f"-D{config}=1", "-"],
                                          input=source, text=True,
                                          capture_output=True, timeout=10)
                assert rejected.returncode, (header, config, "unexpected success")
                assert f"kdlock does not support {config}" in rejected.stderr, (
                    header, config, rejected.stderr)
    print("PASS shared configuration contract: four supported-header preprocesses "
          "and 16 explicit unsupported-configuration refusals")


if __name__ == "__main__":
    main()
