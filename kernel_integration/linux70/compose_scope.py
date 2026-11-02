#!/usr/bin/env python3
"""Compose reviewed core/MM/API overlays into a new source tree, without building."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE_SHA256 = "c21963b34eca609fd090d4501c5b00cac44da00b59b9b6cdf3ed9146e2b0d3c6"
RULE = "pristine+MM-Makefile-suffix+API-Makefile-suffix-v1"
SHARED = "kernel/locking/Makefile"
MM_SUFFIX = b"\nobj-$(CONFIG_KDLOCK_MMAP) += kd_mmap/\n"
API_SUFFIX = b"\nobj-$(CONFIG_KD_API_LOCKS) += kd_api/\n"
PACKAGE = "linux=7.0.0-38.38"
# Exact reviewed path sets, independent of receipt contents. A coherent extra
# output must not expand the permitted overlay merely by supplying its hash.
MM_PATCH_PATHS = frozenset(("include/linux/mm_types.h", "include/linux/mmap_lock.h",
    "include/linux/sched/mm.h", "kernel/bpf/mmap_unlock_work.h", "kernel/bpf/stackmap.c",
    "kernel/bpf/task_iter.c", "kernel/fork.c", SHARED, "mm/Kconfig", "mm/mmap_lock.c"))
API_PATCH_PATHS = frozenset(("include/linux/fdtable.h", "include/linux/pipe_fs_i.h",
    "fs/file.c", "fs/pipe.c", "fs/locks.c", "fs/proc/fd.c", "io_uring/openclose.c",
    "kernel/watch_queue.c", SHARED, "init/Kconfig", "include/asm-generic/vmlinux.lds.h"))
MM_NATIVE_PATHS = frozenset(("mm/mmap.c", "mm/memory.c", "mm/madvise.c", "mm/rmap.c",
                           "mm/vma.c", "lib/maple_tree.c", "arch/x86/mm/fault.c"))
MM_OUTPUTS = MM_PATCH_PATHS | {
    "include/linux/kd_mmap_config.h", "include/linux/kd_mmap_mutex_types.h",
    "include/linux/kd_mmap_rwsem_types.h", "include/linux/kd_mmap_wait_queue.h",
    "include/linux/kd_mmap_lock_types.h",
    "include/linux/kd_mmap_lock.h", "kernel/locking/kd_mmap/adapter.c",
    "kernel/locking/kd_mmap/pool.c", "kernel/locking/kd_mmap/Makefile",
    *("kernel/locking/kd_mmap/kd_mmap_" + suffix for suffix in
      ("mutex.h", "rwsem.h", "regs.h", "lock.h", "mutex_local.h",
       "mutex_local.c", "mutex_osq.c", "rwsem.c", "wait_queue.c"))}
API_OUTPUTS = API_PATCH_PATHS | {
    "include/linux/kd_api_provider.h", "include/linux/kd_api_lock_types.h",
    "include/linux/kd_api_lock.h", "include/linux/kd_api_control.h",
    "kernel/locking/kd_api/Kconfig", "kernel/locking/kd_api/Makefile",
    "kernel/locking/kd_api/bridge.c", "kernel/locking/kd_api/entry.S",
    *("include/linux/kd_api/" + name for name in ("kd_config.h", "kd_spin_type.h", "kd_mutex_types.h"))}
API_RECIPE = "kernel_integration/real_api/prepare.py"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha(path.read_bytes())


def relative(name):
    require(isinstance(name, str), "relative path must be a string")
    path = Path(name)
    require(isinstance(name, str) and not path.is_absolute() and path.parts and
            all(part not in (".", "..") for part in path.parts) and str(path) == name,
            "invalid relative path: " + str(name))
    return path


def preparation(receipt, kind):
    require(receipt.get("passed") is True and receipt.get("source_unchanged") is True and
            receipt.get("config_modified") is False and receipt.get("source_package") == PACKAGE,
            kind + " preparation did not pass")
    require(bool(receipt.get("inputs")) and bool(receipt.get("outputs")), kind + " preparation is empty")
    for mapping in (receipt["inputs"], receipt["outputs"]):
        for name, expected in mapping.items():
            relative(name)
            require(bool(re.fullmatch("[0-9a-f]{64}", expected)), "invalid preparation hash")


def composed_outputs(mm, api, pristine, mm_file, api_file):
    preparation(mm, "MM")
    preparation(api, "API")
    require(set(mm["outputs"]) & set(api["outputs"]) == {SHARED}, "unexpected overlay collision")
    require(set(mm["outputs"]) == MM_OUTPUTS and set(api["outputs"]) == API_OUTPUTS,
            "overlay output pathname scope differs")
    require(mm_file == pristine + MM_SUFFIX, "MM Makefile is not its exact reviewed append")
    require(api_file == pristine + API_SUFFIX, "API Makefile is not its exact reviewed append")
    require(digest_bytes_match(mm_file, mm["outputs"][SHARED]) and
            digest_bytes_match(api_file, api["outputs"][SHARED]), "intermediate Makefile hash differs")
    result = mm["outputs"] | api["outputs"]
    result[SHARED] = sha(pristine + MM_SUFFIX + API_SUFFIX)
    return result


def digest_bytes_match(data, expected):
    return sha(data) == expected


def api_recipe():
    spec = importlib.util.spec_from_file_location("scope_api_recipe", ROOT / "kernel_integration/real_api/prepare.py")
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    return recipe


def api_bodies(pristine_root, composed_root, expected):
    """Compare only the reviewed lock-call substitutions, not arbitrary rewrites."""
    recipe = api_recipe()
    actual = {}
    for name, functions in recipe.SELECTED.items():
        for function in functions:
            before = recipe.function_text((pristine_root / name).read_text(), function)
            after = recipe.native_body(recipe.function_text((composed_root / name).read_text(), function))
            require(before == after, "native API body changed: " + function)
            actual[name + ":" + function] = sha(before.encode())
    require(actual == expected, "native API body scope or hash differs")


def check_bundle(identity, bundle, manifest, source, mm):
    """Verify the explicit scope profile; never run code from captured inputs."""
    files = manifest["bundle_files"]
    required = {"api-prepare.json", "api-lock-binding.patch", "api-base-sha256.json",
                "composition.json", "scope-base-sha256.json"}
    require(required <= set(files), "scope provenance files omitted")
    require(files["scope-base-sha256.json"] == BASE_SHA256, "scope base identity differs")
    base = json.loads((bundle / "scope-base-sha256.json").read_text())
    api = json.loads((bundle / "api-prepare.json").read_text())
    composition = json.loads((bundle / "composition.json").read_text())
    preparation(api, "API")
    preparation(mm, "MM")
    require(manifest.get("api") == {"enabled": True, "default_backend": "native"}, "API profile differs")
    require(composition.get("schema") == 1 and composition.get("passed") is True and
            composition.get("source_unchanged") is True and composition.get("overlays_unchanged") is True and
            composition.get("config_modified") is False and composition.get("rule") == RULE and
            composition.get("source_package") == PACKAGE, "composition did not pass")
    require(all(composition.get(key) is False for key in ("kernel_built", "installed", "booted")),
            "composition receipt claims a later execution stage")
    require(composition["source"] == mm["source"] == api["source"] and
            composition["composed_source"] == str(source), "composition source binding differs")
    for key, name in (("scope_base_sha256", "scope-base-sha256.json"),
                      ("core_patch_sha256", "core-kernel.patch"),
                      ("mmap_prepare_sha256", "mmap-prepare.json"),
                      ("api_prepare_sha256", "api-prepare.json"),
                      ("acquisition_sha256", "source-acquisition.json")):
        require(composition[key] == files[name], "composition receipt changed: " + name)
    require(composition["source_archives"] == identity.SOURCE_ARCHIVES, "composition archives differ")
    require(api["patch_sha256"] == files["api-lock-binding.patch"] and
            api["manifest_sha256"] == files["api-base-sha256.json"], "API recipe identity differs")
    api_base = json.loads((bundle / "api-base-sha256.json").read_text())
    mm_base = json.loads((bundle / "mmap-base-sha256.json").read_text())
    require(api_base["source_package"] == PACKAGE and
            set(api_base["files"]) == API_PATCH_PATHS and
            set(mm_base["files"]) == MM_PATCH_PATHS and
            set(mm["native_body_sha256"]) == MM_NATIVE_PATHS, "overlay base pathname scope differs")
    for name, expected in api_base["files"].items():
        require(base["files"].get(name) == expected, "API pristine base differs: " + name)
    for name, expected in (mm_base["files"] | mm_base["native_bodies"]).items():
        require(base["files"].get(name) == expected, "MM pristine base differs: " + name)
    patch_paths = re.findall(r"^\+\+\+ b/(.+)$", (bundle / "api-lock-binding.patch").read_text(), re.M)
    require(len(patch_paths) == len(api_base["files"]) and set(patch_paths) == set(api_base["files"]),
            "API patch scope differs")
    for prefix, receipt in (("api-inputs/", api), ("composition-inputs/", composition)):
        require(bool(receipt["inputs"]), "composition inputs omitted")
        for name, expected in receipt["inputs"].items():
            relative(name)
            require(files.get(prefix + name) == expected, "captured input differs: " + name)
    require(api["inputs"].get(API_RECIPE) == digest(ROOT / API_RECIPE),
            "current API normalization recipe differs from captured input")
    require(set(composition["inputs"]) == {"kernel_integration/linux70/compose_scope.py",
                                          "kernel_integration/linux70/scope-base-sha256.json"},
            "composition input scope differs")
    artifact_names = {"base/" + SHARED, "mmap/" + SHARED, "api/" + SHARED,
                      "pristine-api/fs/file.c", "pristine-api/fs/pipe.c"}
    require(set(composition["artifacts"]) == artifact_names, "composition artifact scope differs")
    for name, expected in composition["artifacts"].items():
        require(files.get("composition/" + name) == expected, "composition artifact differs: " + name)
    artifacts = bundle / "composition"
    pristine = (artifacts / "base" / SHARED).read_bytes()
    require(sha(pristine) == base["files"][SHARED], "pristine Makefile differs")
    outputs = composed_outputs(mm, api, pristine, (artifacts / "mmap" / SHARED).read_bytes(),
                               (artifacts / "api" / SHARED).read_bytes())
    final = composition["final_source_files"]
    require(final == manifest["source_files"], "composition final manifest differs")
    expected_names = identity.CORE_PATHS | set(identity.BASE_SOURCE) | set(outputs) | set(mm["native_body_sha256"])
    require(set(final) == expected_names, "composition final named-source scope differs")
    for name, expected in (outputs | mm["native_body_sha256"]).items():
        require(final.get(name) == expected, "composed output differs: " + name)
    overlap = {"path": SHARED, "pristine": sha(pristine), "mmap": mm["outputs"][SHARED],
               "api": api["outputs"][SHARED], "final": outputs[SHARED]}
    require(composition["overlap"] == overlap, "composition overlap record differs")
    for name in ("fs/file.c", "fs/pipe.c"):
        require(digest(artifacts / "pristine-api" / name) == base["files"][name],
                "pristine API source differs: " + name)
    api_bodies(artifacts / "pristine-api", source, api["native_body_sha256"])


def compose(source, output, mmap_prepare, api_prepare, acquisition, archives):
    # Authentication constants and existing primitives are code from the
    # synchronized project, never Python loaded out of a captured bundle.
    spec = importlib.util.spec_from_file_location("scope_identity", HERE / "verify.py")
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    identity.check_digest(acquisition, identity.ACQUISITION_SHA256)
    identity.check_files(archives, identity.SOURCE_ARCHIVES)
    source, output = source.resolve(), output.resolve()
    require(not output.exists() and not output.is_relative_to(source) and
            not output.is_relative_to(ROOT), "new output outside source/project required")
    base_path = HERE / "scope-base-sha256.json"
    require(digest(base_path) == BASE_SHA256, "scope base manifest differs")
    base = json.loads(base_path.read_text())
    for name, expected in base["files"].items():
        relative(name)
        require((source / name).resolve().is_relative_to(source) and not (source / name).is_symlink(),
                "pristine input escapes source: " + name)
        require(digest(source / name) == expected, "pristine source differs: " + name)
    for name in base["new_core_files"]:
        require(not (source / name).exists(), "new core file already exists: " + name)
    mm = json.loads(mmap_prepare.read_text())
    api = json.loads(api_prepare.read_text())
    for receipt, kind in ((mm, "MM"), (api, "API")):
        preparation(receipt, kind)
        require(Path(receipt["source"]).resolve() == source, kind + " uses another pristine tree")
        for name, expected in receipt["inputs"].items():
            require((ROOT / relative(name)).resolve().is_relative_to(ROOT.resolve()),
                    "project input escapes root: " + name)
            require(digest(ROOT / relative(name)) == expected, kind + " project input changed: " + name)
        overlay = Path(receipt["overlay"])
        for name, expected in receipt["outputs"].items():
            require((overlay / relative(name)).resolve().is_relative_to(overlay.resolve()),
                    "staging output escapes overlay: " + name)
            require(digest(overlay / relative(name)) == expected, kind + " overlay changed: " + name)
    require(mm["patch_sha256"] == digest(HERE / "mmap-lock.patch") and
            mm["base_manifest_sha256"] == digest(HERE / "mmap-base-sha256.json"), "MM recipe differs")
    api_root = ROOT / "kernel_integration/real_api"
    require(api["patch_sha256"] == digest(api_root / "lock-binding.patch") and
            api["manifest_sha256"] == digest(api_root / "base-sha256.json"), "API recipe differs")
    pristine = (source / SHARED).read_bytes()
    mm_file = (Path(mm["overlay"]) / SHARED).read_bytes()
    api_file = (Path(api["overlay"]) / SHARED).read_bytes()
    overlay_outputs = composed_outputs(mm, api, pristine, mm_file, api_file)
    patch = HERE / "kernel.patch"
    core = re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(), re.M)
    require(set(core) == identity.CORE_PATHS and len(core) == len(set(core)), "core patch scope differs")
    require(not (set(core) & set(overlay_outputs)), "core/overlay collision is unreviewed")
    output.mkdir(parents=True)
    tree = output / "source"
    result = dict(schema=1, passed=False, source_package=PACKAGE, rule=RULE,
                  source=str(source), composed_source=str(tree),
                  kernel_built=False, installed=False, booted=False, config_modified=False,
                  acquisition_sha256=digest(acquisition), source_archives=identity.SOURCE_ARCHIVES,
                  scope_base_sha256=BASE_SHA256, core_patch_sha256=digest(patch),
                  mmap_prepare_sha256=digest(mmap_prepare), api_prepare_sha256=digest(api_prepare))
    try:
        shutil.copytree(source, tree, symlinks=True)
        for name in set(core) | set(overlay_outputs):
            require((tree / name).resolve().is_relative_to(tree), "composed output escapes tree: " + name)
        command = ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)]
        proc = subprocess.run(command, cwd=tree, capture_output=True, text=True, timeout=60)
        (output / "core-patch.log").write_text(proc.stdout + proc.stderr)
        require(proc.returncode == 0, "core patch failed")
        for receipt in (mm, api):
            for name in receipt["outputs"]:
                if name == SHARED:
                    continue
                dest = tree / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(receipt["overlay"]) / name, dest)
        (tree / SHARED).write_bytes(pristine + MM_SUFFIX + API_SUFFIX)
        for name, expected in overlay_outputs.items():
            require(digest(tree / name) == expected, "composed overlay differs: " + name)
        api_bodies(source, tree, api["native_body_sha256"])
        bodies = json.loads((HERE / "mmap-base-sha256.json").read_text())["native_bodies"]
        require(mm["native_body_sha256"] == bodies, "MM body scope differs")
        for name, expected in bodies.items():
            require(digest(tree / name) == expected, "native MM body changed: " + name)
        final_names = set(core) | set(overlay_outputs) | set(bodies) | set(identity.BASE_SOURCE)
        final = {name: digest(tree / name) for name in sorted(final_names)}
        artifacts = {}
        for name, data in (("base/" + SHARED, pristine), ("mmap/" + SHARED, mm_file),
                           ("api/" + SHARED, api_file),
                           ("pristine-api/fs/file.c", (source / "fs/file.c").read_bytes()),
                           ("pristine-api/fs/pipe.c", (source / "fs/pipe.c").read_bytes())):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            artifacts[name] = sha(data)
        for name, expected in base["files"].items():
            require(digest(source / name) == expected, "pristine input changed: " + name)
        for receipt in (mm, api):
            for name, expected in receipt["outputs"].items():
                require(digest(Path(receipt["overlay"]) / name) == expected, "staging overlay changed: " + name)
        result.update(passed=True, source_unchanged=True, overlays_unchanged=True,
                      inputs={str(Path(__file__).relative_to(ROOT)): digest(Path(__file__)),
                              "kernel_integration/linux70/scope-base-sha256.json": BASE_SHA256},
                      artifacts=artifacts, final_source_files=final,
                      overlap={"path":SHARED, "pristine":sha(pristine), "mmap":sha(mm_file),
                               "api":sha(api_file), "final":final[SHARED]})
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        (output / "composition.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "mmap-prepare", "api-prepare", "acquisition", "source-archives"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release.startswith("7.0."), "designated Linux 7 VM only")
    result = compose(args.source, args.output, args.mmap_prepare, args.api_prepare,
                     args.acquisition, args.source_archives)
    print(json.dumps({key:result[key] for key in ("passed", "composed_source", "kernel_built")}))


if __name__ == "__main__":
    main()
