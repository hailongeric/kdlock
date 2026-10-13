"""Guest-only production owned mutex protocol checks and fault mutations.

The deterministic scheduler fixture exercises real core functions with modeled
kernel primitives. It does not replace live OSQ or delegated ACK verification.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, without_includes


def main():
    public = without_includes((ROOT / "include/kd_mutex.h").read_text())
    internal = without_includes((ROOT / "include/kd_owned_mutex_internal.h").read_text())
    core = without_includes((ROOT / "kernel_module/owned_mutex/core.c").read_text())
    mutations = {
        "force-self-handoff": (
            "directed |= waiter->kind == KD_OWNED_MUTEX_DELEGATE;",
            "directed = true;",
        ),
        "omit-pickup": (
            "next |= (unsigned long)waiter->task | KD_OWNED_MUTEX_FLAG_PICKUP;",
            "next |= (unsigned long)waiter->task;",
        ),
        "retain-last-flags": (
            "atomic_long_andnot(KD_OWNED_MUTEX_FLAGS, &lock->owner);",
            "atomic_long_andnot(0UL, &lock->owner);",
        ),
        "omit-wake-reference": (
            "get_task_struct(task);",
            "if (false) get_task_struct(task);",
        ),
        "bypass-borrowed-unlock": (
            "if (kd_mutex_task_reroute(current) &&",
            "if (false && kd_mutex_task_reroute(current) &&",
        ),
        "strand-publication-race": (
            "if (!kd_owned_mutex_trylock_common(lock, false)) {\n"
            "\t\t\tkd_owned_mutex_remove_waiter(lock, waiter);",
            "if (false) {\n\t\t\tkd_owned_mutex_remove_waiter(lock, waiter);",
        ),
        "combine-ordinary-under-outer": (
            "if (!kd_owned_mutex_unlock_borrowed(lock, owner))\n"
            "\t\tkd_owned_mutex_release_common(lock, false);",
            "if (!kd_owned_mutex_unlock_borrowed(lock, owner) &&\n"
            "\t    !kd_owned_mutex_combine(lock))\n"
            "\t\tkd_owned_mutex_release_common(lock, false);",
        ),
    }
    with tempfile.TemporaryDirectory(prefix="kd-owned-mutex-core-") as directory:
        path = Path(directory)
        variants = [("production", core)]
        for name, (old, new) in mutations.items():
            assert core.count(old) == 1, (name, core.count(old))
            variants.append((name, core.replace(old, new)))
        for name, body in variants:
            (path / "owned_production.h").write_text(public + internal + body)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + directory,
                str(ROOT / "tests/unit/mutex/owned_mutex_core_fixture.c"),
                "-o", str(binary),
            ], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if name == "production":
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end="")
            else:
                assert result.returncode != 0, f"mutation survived: {name}"
                print(f"[PASS] owned mutex fixture rejects {name}")


if __name__ == "__main__":
    main()
