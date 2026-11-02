#!/usr/bin/env python3
"""Check Linux 7 MM wrapper preservation and selected objects in the VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "kernel_integration/linux70"
WRAPPER_OBJECTS = ("mm/mmap_lock.o", "kernel/fork.o", "kernel/bpf/task_iter.o",
                   "kernel/bpf/stackmap.o", "mm/init-mm.o")
LOCK_OBJECTS = tuple("kernel/locking/kd_mmap/" + name for name in
                     ("adapter.o", "pool.o", "provider.o", "kd_mmap_wait_queue.o",
                      "kd_mmap_admission.o", "kd_mmap_mutex_local.o",
                      "kd_mmap_mutex_osq.o", "kd_mmap_rwsem.o"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def check_sources(pristine, tree, receipt):
    manifest = json.loads((INTEGRATION / "mmap-base-sha256.json").read_text())
    require(receipt["passed"], "preparation did not pass")
    require(receipt.get("wrapper_policy") == "reserved-deferred-read-v2" and
            receipt.get("native_bpf_when_disabled") is True,
            "deferred-read reservation revision is not prepared")
    require(receipt["patch_sha256"] == digest(INTEGRATION / "mmap-lock.patch"),
            "prepared patch identity differs")
    require(receipt["base_manifest_sha256"] ==
            digest(INTEGRATION / "mmap-base-sha256.json"), "base manifest differs")
    for name, expected in (manifest["files"] | manifest["native_bodies"]).items():
        require(digest(pristine / name) == expected, "pristine source differs: " + name)
    for name, expected in manifest["native_bodies"].items():
        require(digest(tree / name) == expected, "native MM body changed: " + name)
    for name, expected in receipt["outputs"].items():
        require(digest(tree / name) == expected, "prepared source differs: " + name)
    for name, expected in receipt["inputs"].items():
        require(digest(ROOT / name) == expected, "generator input changed: " + name)

    header = (tree / "include/linux/mmap_lock.h").read_text()
    native = (pristine / "include/linux/mmap_lock.h").read_text()
    # After the backend-selection preamble, the only permitted differences
    # are lock API names and the explicit lifetime declarations. Equality
    # covers every per-VMA body, writer seqcount, tracing and cleanup guard.
    suffix = header[header.index("DECLARE_TRACEPOINT("):]
    start = suffix.index("static inline void mmap_destroy_lock(")
    end = suffix.index("static inline void mmap_assert_locked(", start)
    suffix = suffix[:start] + suffix[end:]
    suffix = suffix.replace("__mmap_sem_", "")
    for declaration in receipt.get('capture_inline_declarations', []):
        require(declaration in (
            'static inline void mmap_write_lock(',
            'static inline void mmap_write_lock_nested(',
            'static inline int __must_check mmap_write_lock_killable(',
        ), 'unexpected lock-wrapper inline declaration')
        suffix = suffix.replace(declaration.replace('inline', '__always_inline', 1), declaration)
    require(suffix == native[native.index("DECLARE_TRACEPOINT("):],
            "native mmap/per-VMA wrapper semantics changed")
    require("mmap_write_trylock(" not in header, "retired mmap API reintroduced")

    native = (pristine / "mm/mmap_lock.c").read_text()
    current = (tree / "mm/mmap_lock.c").read_text()
    require(current.startswith(native), "native VMA/fault implementation changed")
    lifetime = current[len(native):]
    require(lifetime.strip().startswith("#ifdef CONFIG_KDLOCK_MMAP") and
            lifetime.strip().endswith("#endif /* CONFIG_KDLOCK_MMAP */"),
            "disabled configuration must not compile token implementation")
    for token in ("mmgrab(mm);", "xchg(&token->mm, NULL)", "BUG_ON(!mm);",
                  "mmap_read_unlock_non_owner(mm);", "mmdrop_async(mm);"):
        require(token in lifetime, "read transfer lost lifetime obligation: " + token)
    bpf = (tree / "kernel/bpf/mmap_unlock_work.h").read_text()
    require("cmpxchg(&work->reserved, 0, 1)" in bpf and
            "smp_store_release(&work->reserved, 0)" in bpf and
            "BUG_ON(!irq_work_queue(&work->irq_work))" in bpf,
            "BPF reservation/publication obligations changed")
    task_iter = (tree / "kernel/bpf/task_iter.c").read_text()
    stackmap = (tree / "kernel/bpf/stackmap.c").read_text()
    require(task_iter.count("bpf_mmap_unlock_cancel_irq_work(work);") == 2 and
            stackmap.count("bpf_mmap_unlock_cancel_irq_work(work);") == 1,
            "BPF early exits and completion must release their own reservation")
    fork = (tree / "kernel/fork.c").read_text()
    require(fork.count("\tmmap_destroy_lock(mm);\n") == 2,
            "both final and failed-init destruction need idle checks")
    fork = fork.replace("\tmmap_destroy_lock(mm);\n", "")
    fork = fork.replace("\t__mmap_sem_init_rwsem(", "\tinit_rwsem(")
    fork = fork.replace("\nvoid mmdrop_async(", "\nstatic void mmdrop_async(")
    require(fork == (pristine / "kernel/fork.c").read_text(),
            "native mm initialization/destruction changed beyond lock lifetime")
    config = (tree / "mm/Kconfig").read_text().split("config KDLOCK_MMAP\n", 1)[1]
    config = config.split('\nsource "mm/damon/Kconfig"', 1)[0]
    require("\tdefault n\n" in config and "!PREEMPT_RT" in config and
            "!LOCKDEP && !DEBUG_LOCK_ALLOC && !DEBUG_MUTEXES" in config,
            "experimental defaults or configuration guards weakened")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("disabled", "enabled"), required=True)
    parser.add_argument("--build-output", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--make-arg", action="append", default=[])
    parser.add_argument("--source-check-only", action="store_true")
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release.startswith("7.0."),
            "checks and compilation run only in the Linux 7 VM")
    tree, pristine, out = args.tree.resolve(), args.pristine.resolve(), args.output.resolve()
    require(tree != pristine and not out.exists() and not out.is_relative_to(tree)
            and not out.is_relative_to(ROOT), "independent tree and fresh evidence required")
    require(1 <= args.jobs <= 64, "invalid build parallelism")
    out.mkdir(parents=True)
    result = dict(passed=False, mode=args.mode, kernel_image_built=False,
                  installed=False, booted=False, live_mm_tests=0,
                  source_only=args.source_check_only)
    try:
        receipt = json.loads(args.preparation.read_text())
        manifest = check_sources(pristine, tree, receipt)
        build = args.build_output.resolve() if args.build_output else tree
        config = build / ".config"
        before = digest(config)
        settings = config.read_text().splitlines()
        enabled = "CONFIG_KDLOCK_MMAP=y" in settings
        require(enabled == (args.mode == "enabled"), "selected configuration differs")
        if enabled:
            for forbidden in ("PREEMPT_RT", "LOCKDEP", "DEBUG_LOCK_ALLOC", "DEBUG_MUTEXES"):
                require("CONFIG_" + forbidden + "=y" not in settings,
                        "unsupported enabled configuration: " + forbidden)
        targets = WRAPPER_OBJECTS + (LOCK_OBJECTS if enabled else ())
        if not args.source_check_only:
            command = ["make", "-C", str(tree), "-j" + str(args.jobs), "W=1"]
            if args.build_output:
                command += ["O=" + str(build)]
            command += args.make_arg + list(targets)
            result["command"] = command
            with (out / "affected-objects.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=1200)
            result["objects"] = {name: digest(build / name) for name in targets}
        require(digest(config) == before, "configuration changed while compiling")
        check_sources(pristine, tree, receipt)
        result.update(passed=True, config_sha256=before,
                      native_body_sha256=manifest["native_bodies"],
                      source_unchanged=True,
                      limitation="Source/affected-object checks only; actual-MM runtime and performance remain unvalidated.")
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
