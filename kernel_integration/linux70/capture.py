#!/usr/bin/env python3
"""Capture the installed and booted Linux 7 development kernel in the VM.

The selected source-file set binds the core patch, optional MM overlay and
untouched MM bodies. It does not assert that every upstream file was audited.
Run after installation and boot; a build alone cannot produce a runtime pass.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("linux70_identity", HERE / "verify.py")
identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity)


def capture(args):
    variant = getattr(args, "variant", "kdlock1")
    selected = identity.variant_settings(variant)
    identity.require(os.geteuid() == 0 and os.uname().release == selected["release"],
                     "capture requires the installed custom Linux 7 guest to be booted")
    source, build = args.source or selected["source"], args.build or selected["build"]
    output = args.output or selected["bundle"]
    identity.require(source == selected["source"] and build == selected["build"],
                     "only the canonical development source/build pair is supported")
    if variant != "kdlock1":
        identity.require(output == selected["bundle"], "MM capture requires its canonical mode bundle")
        identity.require(args.mmap_prepare is not None, "MM capture requires preparation provenance")
    identity.require(not output.exists(), "capture output already exists")
    identity.check_digest(args.acquisition, identity.ACQUISITION_SHA256)
    identity.check_files(args.source_archives, identity.SOURCE_ARCHIVES)
    config = identity.config_values(build / ".config")
    identity.check_variant_config(config, variant)
    running = identity.build_identity(build, variant=variant)
    identity.legacy.check_running(running, os.uname(), Path("/sys/kernel/notes").read_bytes())
    policy = identity.runtime_policy(Path("/proc/cmdline").read_text().strip(),
                                     Path("/sys/kernel/debug/sched/preempt").read_text(), variant=variant)
    identity.require(policy["preempt"] == args.preempt, "active preemption differs from requested capture policy")
    # A new directory prevents overwriting the identity used by previous runs.
    output.mkdir(parents=True)
    files = {}

    def preserve(path, name):
        identity.relative_path(name)
        expected = identity.digest_file(path)
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        identity.check_digest(target, expected)
        files[name] = expected

    preserve(build / ".config", "guest.config")
    preserve(HERE / "kernel.patch", "core-kernel.patch")
    preserve(args.acquisition, "source-acquisition.json")
    sources = {name: identity.digest_file(source / name)
               for name in sorted(identity.CORE_PATHS | set(identity.BASE_SOURCE))}
    mmap = None
    if args.mmap_prepare is not None:
        receipt = json.loads(args.mmap_prepare.read_text())
        preserve(args.mmap_prepare, "mmap-prepare.json")
        preserve(HERE / "mmap-lock.patch", "mmap-lock.patch")
        preserve(HERE / "mmap-base-sha256.json", "mmap-base-sha256.json")
        for name, expected in receipt["inputs"].items():
            identity.relative_path(name)
            path = ROOT / name
            identity.require(path.resolve().is_relative_to(ROOT.resolve()), "MM input escapes project")
            identity.check_digest(path, expected)
            preserve(path, "mmap-inputs/" + name)
        for name, expected in (receipt["outputs"] | receipt["native_body_sha256"]).items():
            identity.relative_path(name)
            identity.require((source / name).resolve().is_relative_to(source), "MM output escapes source")
            identity.check_digest(source / name, expected)
            sources[name] = expected
        mmap = dict(enabled=config.get("CONFIG_KDLOCK_MMAP", "n") == "y")
    release = selected["release"]
    installed_links = {f"lib/modules/{release}/build": str(build)}
    source_link = Path(f"/lib/modules/{release}/source")
    if source_link.exists() or source_link.is_symlink():
        installed_links[str(source_link.relative_to("/"))] = str(source)
    manifest = dict(schema=2, variant=variant, source_package=identity.PACKAGE,
                    source_archives=identity.SOURCE_ARCHIVES,
                    source_scope="named core/MM inputs; not a complete source-tree audit",
                    source_root=str(source), build_root=str(build),
                    core_patch="core-kernel.patch", mmap=mmap,
                    bundle_files=files, source_files=sources,
                    build_files={name: identity.digest_file(build / name)
                                 for name in sorted(identity.BUILD_FILES)},
                    configuration=config, running=running, runtime_policy=policy,
                    installed_files={name: identity.digest_file(Path("/") / name)
                                     for name in sorted(identity.installed_paths(variant))},
                    installed_links=installed_links)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return identity.verify(output, build, running=True, variant=variant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=identity.VARIANTS, default="kdlock1")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--acquisition", type=Path, default=Path(
        "/mnt/kdlock-builds/ubuntu-7.0.0-38-source/source-acquisition.json"))
    parser.add_argument("--source-archives", type=Path, default=Path(
        "/mnt/kdlock-builds/ubuntu-7.0.0-38-source/downloads"))
    parser.add_argument("--mmap-prepare", type=Path,
                        help="required if the development source includes the MM overlay, even when disabled")
    parser.add_argument("--preempt", choices=("lazy", "voluntary"), default="lazy")
    args = parser.parse_args()
    print(json.dumps(capture(args), sort_keys=True))


if __name__ == "__main__":
    main()
