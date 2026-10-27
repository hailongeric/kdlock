#!/usr/bin/env python3
"""Execute exact patched BPF unlock helpers in a userspace ownership fixture.

Run only in the designated Linux 7 guest. This compiles extracted production
functions with substituted kernel primitives; it does not load a BPF program,
exercise live IRQ/NMI scheduling, or establish actual-MM support.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
INTEGRATION = ROOT / "kernel_integration/linux70"
PRISTINE = Path("/mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definition(source, first):
    matches = list(re.finditer(r"(?m)^" + re.escape(first), source))
    if len(matches) != 1:
        raise ValueError("expected one production definition: " + first)
    start = matches[0].start()
    return source[start:source.index("\n}", start) + 2] + "\n"


def production(tree, patched):
    header = (tree / "kernel/bpf/mmap_unlock_work.h").read_text()
    header = re.sub(r"(?m)^#include[^\n]*\n", "", header)
    result = ""
    if patched:
        mmap_header = (tree / "include/linux/mmap_lock.h").read_text()
        token = re.search(r"(?m)^struct mmap_read_token \{\n.*?^};\n", mmap_header, re.S)
        if not token:
            raise ValueError("read transfer token definition missing")
        result += token[0]
        result += "void mmap_read_unlock_prepare(struct mmap_read_token *, struct mm_struct *);\n"
        result += "void mmap_read_unlock_complete(struct mmap_read_token *);\n"
    result += header
    if patched:
        body = (tree / "mm/mmap_lock.c").read_text()
        result += "\n#ifdef CONFIG_KDLOCK_MMAP\n"
        result += definition(body, "void mmap_read_unlock_prepare(")
        result += definition(body, "void mmap_read_unlock_complete(")
        result += "#endif\n"
    task = (tree / "kernel/bpf/task_iter.c").read_text()
    result += definition(task, "BPF_CALL_5(bpf_find_vma,")
    result += definition(task, "static void do_mmap_read_unlock(")
    stack = (tree / "kernel/bpf/stackmap.c").read_text()
    result += definition(stack, "static void stack_map_get_build_id_offset(")
    return result


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("mutation no longer selects one production site: " + before)
    return text.replace(before, after)


def mutate_function(code, first, before, after):
    body = definition(code, first)
    return code.replace(body, replace_once(body, before, after), 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine", type=Path, default=PRISTINE)
    args = parser.parse_args()
    if not os.uname().release.startswith("7.0.") or not args.pristine.is_dir():
        raise SystemExit("run in the Linux 7 development guest with authenticated source")
    manifest_path = INTEGRATION / "mmap-base-sha256.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["source_package"] != "linux=7.0.0-38.38":
        raise ValueError("unexpected source package")
    patch = INTEGRATION / "mmap-lock.patch"
    files = manifest["files"]

    def verify_pristine():
        for name, expected in files.items():
            if digest(args.pristine / name) != expected:
                raise ValueError("pristine input changed: " + name)

    verify_pristine()
    with tempfile.TemporaryDirectory(prefix="kd-linux70-mmap-unlock-") as temporary:
        out = Path(temporary)
        tree = out / "patched"
        for name in files:
            destination = tree / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.pristine / name, destination)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
                       cwd=tree, check=True, capture_output=True, text=True, timeout=30)
        original = production(args.pristine, False)
        code = production(tree, True)
        mutations = {
            "unreserved-get": replace_once(code,
                "|| cmpxchg(&work->reserved, 0, 1)", "|| false"),
            "foreign-cancel": replace_once(code, "work = NULL;\n#endif", "(void)work;\n#endif"),
            "find-vma-cancel-leak": mutate_function(code, "BPF_CALL_5(bpf_find_vma,",
                "bpf_mmap_unlock_cancel_irq_work(work);", "(void)work;"),
            "stackmap-cancel-leak": mutate_function(code,
                "static void stack_map_get_build_id_offset(",
                "bpf_mmap_unlock_cancel_irq_work(work);", "(void)work;"),
            "early-reservation-release": replace_once(code,
                "mmap_read_unlock_complete(&work->token);\n\tbpf_mmap_unlock_cancel_irq_work(work);",
                "bpf_mmap_unlock_cancel_irq_work(work);\n\tmmap_read_unlock_complete(&work->token);"),
            "missing-mm-reference": replace_once(code, "\tmmgrab(mm);", "\t(void)mm;"),
            "leaked-mm-reference": replace_once(code, "\tmmdrop_async(mm);", "\t(void)mm;"),
        }
        cases = [("upstream-native", original, False, False),
                 ("patched-native", code, False, False),
                 ("patched-kd", code, True, False)]
        cases += [(name, candidate, True, True) for name, candidate in mutations.items()]
        for name, candidate, enabled, negative in cases:
            (out / "mmap_unlock_production.h").write_text(candidate)
            binary = out / name
            command = shlex.split(os.environ.get("CC", "cc")) + [
                "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                # Kernel source keeps int loop indices against u32 trace_nr.
                "-Wno-sign-compare", "-Wno-unused-function", "-Wno-unused-parameter",
                "-I", str(out),
                str(HERE / "linux70_mmap_unlock_fixture.c"), "-o", str(binary)]
            if enabled:
                command.append("-DCONFIG_KDLOCK_MMAP=1")
            subprocess.run(command, check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15)
            if negative:
                if result.returncode != 1 or "FAIL line" not in result.stderr:
                    raise AssertionError((name, result.returncode, result.stdout, result.stderr))
                print("PASS mutation detected: " + name, flush=True)
            else:
                if result.returncode:
                    raise AssertionError((name, result.returncode, result.stdout, result.stderr))
                print(name + ": " + result.stdout.strip(), flush=True)
    verify_pristine()
    print(json.dumps(dict(passed=True, production_cases=3, rejected_mutations=len(mutations),
                          patch_sha256=digest(patch), base_manifest_sha256=digest(manifest_path),
                          pristine_unchanged=True, live_bpf_tests=False)), flush=True)


if __name__ == "__main__":
    main()
