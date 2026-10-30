#!/usr/bin/env python3
"""Fail-closed Linux 7 identity checks; named-source scope, not kernel correctness."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("legacy_identity_primitives", ROOT / "kernel_baseline/verify.py")
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
BaselineError = legacy.BaselineError
digest_file = legacy.digest_file
check_digest = legacy.check_digest
check_files = legacy.check_files
relative_path = legacy.relative_path

RELEASE = "7.0.0-38-kdlock1"
SOURCE_ROOT = Path("/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source")
BUILD_ROOT = SOURCE_ROOT.parent / "build"
BUNDLE_ROOT = Path("/root/kdlock-kernel-baselines/linux70-kdlock1-20261027")
MM_RELEASE = "7.0.0-38-kdmm1"
MM_SOURCE_ROOT = Path("/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source")
MM_BUILD_ROOT = MM_SOURCE_ROOT.parent / "build"
SCOPE_RELEASE = "7.0.0-38-kdscope1"
SCOPE_SOURCE_ROOT = Path("/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/source")
SCOPE_BUILD_ROOT = SCOPE_SOURCE_ROOT.parent / "build"
SCOPE2_RELEASE = "7.0.0-38-kdscope2"
SCOPE2_SOURCE_ROOT = Path("/mnt/kdlock-builds2/linux-7.0.0-38-kdscope2/source")
SCOPE2_BUILD_ROOT = SCOPE2_SOURCE_ROOT.parent / "build"
SCOPE2_VARIANTS = ("kdscope2-native", "kdscope2-kd")
SCOPE_VARIANTS = ("kdscope1-native", "kdscope1-kd", *SCOPE2_VARIANTS)
VARIANTS = ("kdlock1", "kdmm1-native", "kdmm1-kd", *SCOPE_VARIANTS)
SOURCE_SCOPE = "named core/MM inputs; not a complete source-tree audit"
COMPOSED_SCOPE = "named core/MM/API inputs with exact composition; not a complete source-tree audit"
SYSTEM_ROOT = Path("/")
PACKAGE = "linux=7.0.0-38.38"
ACQUISITION_SHA256 = "5c5e8a574cf8affb7aedd66e9f609ca006041c1cde0d3fc4e086a4f9849f545a"
SOURCE_ARCHIVES = {
    "linux_7.0.0.orig.tar.gz": "c6343795c8c7e4feff55f5b309365c8e0eaf49cd6abcb412e32315313f149536",
    "linux_7.0.0-38.38.diff.gz": "98e913d4a1c1f810e4dcfa573cbcf0f1a3a4427bdcd503722555298a794c52b2",
    "linux_7.0.0-38.38.dsc": "016d43577bd8a61629a02e140e3b88072b5ccdd1c90cb1ce2f3c8e5c28756e7e",
}
BASE_SOURCE = {
    "Makefile": "7b16bd89f6768317eed05f31b8e9ebea901751fea90a731223fd4f990d0dcc32",
    "debian.master/changelog": "8fc75f22e2b4d4373e2e9be0ae84372bdd133dee17dc47c294299fe0bef40474",
}
CORE_PATHS = {"arch/x86/mm/pat/set_memory.c", "include/linux/kd_spin_hooks.h",
              "kernel/kallsyms.c", "kernel/locking/spinlock.c", "kernel/sched/core.c"}
BUILD_FILES = {".config", "Makefile", "include/config/auto.conf",
               "include/generated/autoconf.h", "include/config/kernel.release",
               "include/generated/utsrelease.h", "include/generated/utsversion.h",
               "include/generated/uapi/linux/version.h", "Module.symvers", "System.map",
               "vmlinux", "arch/x86/boot/bzImage"}
CONFIG_REQUIRED = {"CONFIG_X86_64": "y", "CONFIG_SMP": "y", "CONFIG_MODULES": "y",
                   "CONFIG_KALLSYMS": "y", "CONFIG_KALLSYMS_ALL": "y",
                   "CONFIG_FRAME_POINTER": "y", "CONFIG_UNWINDER_FRAME_POINTER": "y",
                   "CONFIG_PREEMPT_DYNAMIC": "y", "CONFIG_PREEMPT_RT": "n",
                   "CONFIG_UNWINDER_ORC": "n", "CONFIG_DEBUG_MUTEXES": "n",
                   "CONFIG_DEBUG_LOCK_ALLOC": "n", "CONFIG_LOCKDEP": "n"}


def require(value, message):
    if not value:
        raise BaselineError(message)


def variant_settings(variant="kdlock1"):
    """Select one reviewed release/root/mode tuple; never infer it from a manifest."""
    require(variant in VARIANTS, "unsupported Linux 7 identity variant")
    if variant == "kdlock1":
        return dict(release=RELEASE, source=SOURCE_ROOT, build=BUILD_ROOT,
                    bundle=BUNDLE_ROOT, mmap_mode=None, mmap_config="n")
    if variant in SCOPE2_VARIANTS:
        return dict(release=SCOPE2_RELEASE, source=SCOPE2_SOURCE_ROOT, build=SCOPE2_BUILD_ROOT,
                    bundle=Path("/root/kdlock-kernel-baselines/linux70-" + variant + "-20261031"),
                    mmap_mode="off" if variant == "kdscope2-native" else "on", mmap_config="y")
    if variant in SCOPE_VARIANTS:
        return dict(release=SCOPE_RELEASE, source=SCOPE_SOURCE_ROOT, build=SCOPE_BUILD_ROOT,
                    bundle=Path("/root/kdlock-kernel-baselines/linux70-" + variant + "-20261030"),
                    mmap_mode="off" if variant == "kdscope1-native" else "on", mmap_config="y")
    mode = "off" if variant == "kdmm1-native" else "on"
    return dict(release=MM_RELEASE, source=MM_SOURCE_ROOT, build=MM_BUILD_ROOT,
                bundle=Path("/root/kdlock-kernel-baselines/linux70-" + variant + "-20261027"),
                mmap_mode=mode, mmap_config="y")


def check_variant_config(config, variant="kdlock1"):
    selected = variant_settings(variant)
    require(config.get("CONFIG_KDLOCK_MMAP", "n") == selected["mmap_config"],
            "MM configuration differs from selected identity variant")
    require(config.get("CONFIG_KD_API_LOCKS", "n") == ("y" if variant in SCOPE_VARIANTS else "n"),
            "API configuration differs from selected identity variant")
    if variant in SCOPE_VARIANTS:
        require(config.get("CONFIG_DEBUG_SPINLOCK", "n") == "n", "scope API layout requires native spin geometry")


def read_manifest(bundle):
    # The manifest is the selected identity, not a signature or trusted code.
    require(not (bundle / "manifest.json").is_symlink(), "symlink manifest")
    manifest = json.loads((bundle / "manifest.json").read_text())
    require(isinstance(manifest, dict) and type(manifest.get("schema")) is int
            and manifest["schema"] == 2, "unsupported Linux 7 baseline schema")
    return manifest


def source_directory(build, manifest, *, variant="kdlock1"):
    selected = variant_settings(variant)
    source_root, build_root = selected["source"], selected["build"]
    # Existing kdlock1 bundles predate the variant field. No other variant may
    # omit it, and a supplied MM bundle cannot silently switch a caller's mode.
    require(manifest.get("variant", "kdlock1") == variant, "identity variant mismatch")
    require(str(build) == str(build_root) and build.resolve() == build_root,
            "CLI build root differs from canonical Linux 7 build root")
    require(manifest.get("build_root") == str(build_root), "manifest build root mismatch")
    require(manifest.get("source_root") == str(source_root), "manifest source root mismatch")
    require(source_root.resolve() == source_root, "source root contains a symlink")
    expected = [f"# Automatically generated by {source_root}/Makefile: don't edit",
                f"export KBUILD_OUTPUT = {build_root}", f"include {source_root}/Makefile"]
    require((build / "Makefile").read_text().splitlines() == expected,
            "generated Makefile source/output binding mismatch")
    return source_root


def config_values(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
        elif re.fullmatch(r"# CONFIG_\w+ is not set", line):
            key, value = line.split()[1], "n"
        else:
            continue
        require(key not in values, "duplicate configuration key: " + key)
        values[key] = value
    for key, expected in CONFIG_REQUIRED.items():
        require(values.get(key, "n") == expected, "unsupported configuration: " + key)
    return values


def build_identity(build, *, variant="kdlock1"):
    release = variant_settings(variant)["release"]
    require((build / "include/config/kernel.release").read_text().strip() == release,
            "kernel.release mismatch")
    require((build / "include/generated/utsrelease.h").read_text().strip()
            == f'#define UTS_RELEASE "{release}"', "UTS_RELEASE mismatch")
    version_h = (build / "include/generated/uapi/linux/version.h").read_text()
    require(re.search(r"^#define LINUX_VERSION_CODE 458766$", version_h, re.M),
            "Linux 7.0.14 version code mismatch")
    version = (build / "include/generated/utsversion.h").read_text().strip()
    require(version.startswith("#define UTS_VERSION "), "missing UTS_VERSION")
    version = ast.literal_eval(version.removeprefix("#define UTS_VERSION "))
    result = subprocess.run(["readelf", "-n", str(build / "vmlinux")],
                            check=True, text=True, capture_output=True, timeout=60)
    ids = re.findall(r"Build ID: ([0-9a-f]+)", result.stdout)
    require(len(ids) == 1, "expected one built vmlinux Build ID")
    return dict(release=release, version=version, machine="x86_64", build_id=ids[0])


def runtime_policy(cmdline, preempt_text, *, variant="kdlock1"):
    settings = variant_settings(variant)
    require(isinstance(cmdline, str) and cmdline.strip() == cmdline and "\n" not in cmdline,
            "invalid exact kernel command line")
    tokens = cmdline.split()
    require(tokens.count("nokaslr") == 1 and tokens.count("nopvspin") == 1,
            "runtime requires nokaslr and nopvspin")
    selected = re.findall(r"\((none|voluntary|full|lazy)\)", preempt_text)
    require(len(selected) == 1 and selected[0] in ("lazy", "voluntary"),
            "unsupported active preemption policy")
    requested = [token.split("=", 1)[1] for token in tokens if token.startswith("preempt=")]
    require(not requested or requested == selected, "preempt= differs from active policy")
    require("kd_mmap" not in tokens, "kd_mmap requires an explicit mode")
    modes = [token.split("=", 1)[1] for token in tokens if token.startswith("kd_mmap=")]
    result = dict(cmdline=cmdline, preempt=selected[0], preempt_control=preempt_text.strip())
    if settings["mmap_mode"] is None:
        require(not modes, "kdlock1 requires the disabled mmap backend without kd_mmap=")
    else:
        require(modes == [settings["mmap_mode"]], "kd_mmap= differs from selected identity variant")
        require(selected == ["lazy"], "MM comparison requires lazy preemption")
        result["mmap_mode"] = settings["mmap_mode"]
    return result


def check_runtime(expected, cmdline, preempt_text, *, variant="kdlock1"):
    actual = runtime_policy(cmdline, preempt_text, variant=variant)
    require(actual == expected, "running command line/preemption policy mismatch")
    return actual


def installed_paths(variant="kdlock1"):
    release = variant_settings(variant)["release"]
    return {f"boot/{name}-{release}" for name in ("vmlinuz", "config", "System.map", "initrd.img")}


def check_installed(manifest, build, *, variant="kdlock1"):
    selected = variant_settings(variant)
    release = selected["release"]
    require(set(manifest["installed_files"]) == installed_paths(variant), "installed image manifest scope mismatch")
    check_files(SYSTEM_ROOT, manifest["installed_files"])
    for installed, built in (("vmlinuz", "arch/x86/boot/bzImage"),
                             ("config", ".config"), ("System.map", "System.map")):
        require(manifest["installed_files"][f"boot/{installed}-{release}"]
                == manifest["build_files"][built], "installed/build identity mismatch: " + installed)
    links = manifest["installed_links"]
    required = {f"lib/modules/{release}/build": str(selected["build"])}
    optional = {f"lib/modules/{release}/source": str(selected["source"])}
    require(links == required or links == required | optional,
            "installed module header/source roots mismatch")
    source_link = SYSTEM_ROOT / f"lib/modules/{release}/source"
    require(not (source_link.exists() or source_link.is_symlink()) or
            str(source_link.relative_to(SYSTEM_ROOT)) in links,
            "unrecorded installed source link")
    for name, target in links.items():
        path = SYSTEM_ROOT / name
        require(path.is_symlink() and path.resolve() == Path(target),
                "installed module header/source link mismatch: " + name)


def scope_composer():
    spec = importlib.util.spec_from_file_location("scope_composer", Path(__file__).with_name("compose_scope.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_provenance(bundle, manifest, source, config, *, variant="kdlock1"):
    require(manifest["source_package"] == PACKAGE, "Ubuntu source package mismatch")
    require(manifest["source_archives"] == SOURCE_ARCHIVES, "authenticated source archive identity mismatch")
    scoped = variant in SCOPE_VARIANTS
    require(manifest["source_scope"] == (COMPOSED_SCOPE if scoped else SOURCE_SCOPE),
            "unsupported source scope")
    if not scoped:
        require(manifest.get("api") is None and
                not (source / "include/linux/kd_api_lock.h").exists(),
                "API overlay requires the explicit scope identity variant")
    require(manifest["bundle_files"].get("source-acquisition.json") == ACQUISITION_SHA256,
            "source acquisition receipt mismatch")
    require(manifest["core_patch"] == "core-kernel.patch", "core patch identity missing")
    patch = (bundle / "core-kernel.patch").read_text()
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)
    require(set(paths) == CORE_PATHS and len(paths) == len(CORE_PATHS), "core patch scope mismatch")
    require(CORE_PATHS | set(BASE_SOURCE) <= set(manifest["source_files"]), "core source inputs omitted")
    for name, sha in BASE_SOURCE.items():
        require(manifest["source_files"][name] == sha, "base source identity mismatch: " + name)
    overlay_present = any((source / name).exists() for name in
                          ("include/linux/kd_mmap_lock.h", "kernel/locking/kd_mmap"))
    mmap = manifest.get("mmap")
    require(config.get("CONFIG_KDLOCK_MMAP", "n") in ("n", "y"), "unsupported mmap config")
    if mmap is None:
        require(not scoped, "scope identity requires MM preparation")
        require(not overlay_present and config.get("CONFIG_KDLOCK_MMAP", "n") == "n",
                "MM overlay/config requires preparation identity")
        return
    require(overlay_present, "recorded MM overlay is absent")
    require(mmap["enabled"] is (config.get("CONFIG_KDLOCK_MMAP", "n") == "y"), "MM configuration mismatch")
    require({"mmap-prepare.json", "mmap-lock.patch", "mmap-base-sha256.json"}
            <= set(manifest["bundle_files"]), "MM provenance files omitted")
    receipt = json.loads((bundle / "mmap-prepare.json").read_text())
    require(receipt.get("passed") is True and receipt.get("source_unchanged") is True
            and receipt.get("config_modified") is False and receipt.get("source_package") == PACKAGE,
            "MM preparation did not pass")
    require(manifest["bundle_files"]["mmap-lock.patch"] == receipt["patch_sha256"]
            and manifest["bundle_files"]["mmap-base-sha256.json"] == receipt["base_manifest_sha256"],
            "MM patch/base manifest identity mismatch")
    base = json.loads((bundle / "mmap-base-sha256.json").read_text())
    require(base["source_package"] == PACKAGE and receipt["native_body_sha256"] == base["native_bodies"],
            "MM native-body scope mismatch")
    require(set(base["files"]) <= set(receipt["outputs"]), "MM wrapper outputs omitted")
    require(bool(receipt["inputs"]) and bool(receipt["outputs"]), "empty MM preparation identity")
    for name, sha in receipt["inputs"].items():
        relative_path(name)
        require(manifest["bundle_files"].get("mmap-inputs/" + name) == sha,
                "MM generation input omitted or changed: " + name)
    if scoped:
        try:
            scope_composer().check_bundle(SimpleNamespace(SOURCE_ARCHIVES=SOURCE_ARCHIVES,
                                          CORE_PATHS=CORE_PATHS, BASE_SOURCE=BASE_SOURCE),
                                          bundle, manifest, source, receipt)
        except ValueError as error:
            raise BaselineError(str(error)) from error
    else:
        for name, sha in (receipt["outputs"] | receipt["native_body_sha256"]).items():
            require(manifest["source_files"].get(name) == sha, "MM source output mismatch: " + name)


def verify(bundle, build_root, *, build=True, running=False, variant="kdlock1"):
    selected = variant_settings(variant)
    manifest = read_manifest(bundle)
    source = source_directory(build_root, manifest, variant=variant)
    result = dict(ok=True, schema=2, source_root=str(source), build_root=str(build_root))
    if variant != "kdlock1":
        result.update(variant=variant, mmap_mode=selected["mmap_mode"])
    result["bundle_files"] = check_files(bundle, manifest["bundle_files"])
    require({"guest.config", "core-kernel.patch", "source-acquisition.json"}
            <= set(manifest["bundle_files"]), "required bundle inputs omitted")
    result["source_files"] = check_files(source, manifest["source_files"])
    check_digest(build_root / ".config", manifest["bundle_files"]["guest.config"])
    config = config_values(build_root / ".config")
    check_variant_config(config, variant)
    require(manifest["configuration"] == config, "recorded configuration mismatch")
    check_provenance(bundle, manifest, source, config, variant=variant)
    policy = manifest["runtime_policy"]
    check_runtime(policy, policy["cmdline"], policy["preempt_control"], variant=variant)
    result["config"] = True
    require(BUILD_FILES <= set(manifest["build_files"]), "required build identity omitted")
    if build:
        result["build_files"] = check_files(build_root, manifest["build_files"])
        require(build_identity(build_root, variant=variant) == manifest["running"], "built/running manifest identity mismatch")
        check_installed(manifest, build_root, variant=variant)
        result["installed_files"] = len(manifest["installed_files"])
    if running:
        require(build, "running verification requires build verification")
        result["running_build_id"] = legacy.check_running(
            manifest["running"], os.uname(), Path("/sys/kernel/notes").read_bytes())
        result["runtime_policy"] = check_runtime(manifest["runtime_policy"],
            Path("/proc/cmdline").read_text().strip(),
            Path("/sys/kernel/debug/sched/preempt").read_text(), variant=variant)
        result["runtime_policy_verified"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, default="kdlock1")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--running", action="store_true")
    args = parser.parse_args()
    try:
        selected = variant_settings(args.variant)
        print(json.dumps(verify(args.bundle or selected["bundle"], args.build_root or selected["build"],
                                running=args.running, variant=args.variant), sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps(dict(ok=False, error=str(error))), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
