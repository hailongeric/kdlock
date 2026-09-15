#!/usr/bin/env python3
"""Independent recovery-guest spin/cacheline scan. Never force unload or retry a session."""
import argparse
import importlib.metadata
import json
import os
import shutil
import sys
from pathlib import Path

import kernel_identity
from summarize import summarize, write_json
from bench_session import Session
from assembly import AssemblyArchive, capture_completed
# Preserve the existing Python entry points used by profile.py, dispatch_floor
# and the regression fixtures; implementations now have one responsibility.
from bench_runtime import (
    ROOT, HERE, WORKLOAD, PROVIDER, BINARIES, FAULT, Failure, require, cpu_list,
    make_plan, annotate_topology, digest, command, source_state, idle, status,
    parameters, registry, children, validate_measurement, classify_bodies,
    capture_topology,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cachelines", type=int, nargs="+", choices=(1, 2, 4, 8, 16), default=[1, 2, 4, 8, 16])
    parser.add_argument("--threads", type=int, nargs="+", choices=(1, 4, 8, 12, 16, 20, 24),
                        default=[1, 4, 8, 12, 16, 20, 24])
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=2, help="pairs per point; positive and even")
    parser.add_argument("--cpus", type=cpu_list, default=cpu_list("0-23"))
    parser.add_argument("--output", type=Path)
    kernel_identity.arguments(parser)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    plan = make_plan(args.cachelines, args.threads, args.iterations, args.repeats, args.cpus)
    require(args.output is None or not args.output.exists(), "output directory already exists")
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        print(f"{len(plan) // (args.repeats * 2)} configurations, {len(plan)} sessions")
        return 0
    require(ROOT == Path("/root/host_fs/kdlock") and os.geteuid() == 0 and
            os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1",
            "run as root in the recovery guest after confirming a monitor snapshot")
    require(args.output is not None, "choose a new --output directory outside the checkout")
    out = args.output.resolve()
    require(not out.is_relative_to(ROOT), "output must be outside the checkout")
    idle()
    topology = capture_topology(args.cpus)
    annotate_topology(plan, topology)
    cache = {str(cpu): (Path(f"/sys/devices/system/cpu/cpu{cpu}/cache/index0/coherency_line_size")
                       .read_text().strip()) for cpu in args.cpus}
    require(set(cache.values()) == {"64"}, "guest cacheline size must be 64 bytes")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "plan.json", plan)
    try:
        mount = command(["findmnt", "-T", ROOT, "-n", "-o", "FSTYPE,SOURCE"], out / "mount.txt")
        require(mount.split()[0] == "ext4", "recovery checkout must reside on guest ext4")
        kernel = kernel_identity.capture(args, out, command)
        packages = {p: importlib.metadata.version(p) for p in ("miasm", "future", "pyparsing", "pyelftools")}
        require(packages == dict(miasm="0.1.5", future="1.0.0", pyparsing="2.4.7", pyelftools="0.27"),
                "translation dependencies differ from the pinned runtime")
        cmdline = Path("/proc/cmdline").read_text()
        preempt = Path("/sys/kernel/debug/sched/preempt").read_text()
        require("nokaslr" in cmdline.split() and "(voluntary)" in preempt,
                "requires nokaslr and voluntary preemption")
        write_json(out / "environment.json", dict(
            topology=topology, cacheline_bytes=cache, uname=list(os.uname()), cmdline=cmdline,
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            preemption=preempt, packages=packages, python=sys.executable,
            snapshot_tag=os.environ.get("KDLOCK_SNAPSHOT_TAG"), argv=sys.argv,
            kernel_identity=kernel,
            virtual_machine=True, host_physical_core_exclusivity=False,
            printk=Path("/proc/sys/kernel/printk").read_text()))
        command(["lscpu", "--json"], out / "lscpu.json")
        command(["cc", "--version"], out / "compiler.txt")
        # Recovery checkouts may have older Git metadata than their synced
        # files. Preserve both; content hashes identify the actual inputs.
        command(["git", "rev-parse", "HEAD"], out / "checkout-git-head.txt")
        command(["git", "status", "--porcelain"], out / "checkout-git-status.txt")
        for name, build in (("provider", ["make", "-C", "bench/spin_cacheline", "provider"]),
                            ("daemon", ["make", "-C", "daemon", "CFLAGS=-O2 -Wall -Wextra -Werror"]),
                            ("benchmark", ["make", "-C", "bench/spin_cacheline", "module", "client"])):
            command(build, out / f"build-{name}.log", timeout=120)
        frozen = source_state()
        write_json(out / "source-sha256.json", frozen)
        for relative in frozen:
            target = out / "source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        hashes = {p: digest(ROOT / p) for p in BINARIES}
        write_json(out / "binary-sha256.json", hashes)
        for relative in BINARIES:
            target = out / "binaries" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        command(["objdump", "-dr", WORKLOAD / "spin_cacheline.ko"], out / "payload-disassembly.txt")
        assembly = AssemblyArchive(out)
        for i, spec in enumerate(plan):
            if (out / "STOP").exists():
                raise Failure("STOPPED", "STOP requested at a drained session boundary")
            require(source_state() == frozen and {p: digest(ROOT / p) for p in BINARIES} == hashes,
                    "inputs changed; stopped at session boundary")
            idle()
            print(f"[{i+1}/{len(plan)}] {spec['name']} preparing", flush=True)
            session = Session(out, spec)
            session.execute()
            capture_completed(assembly, session.path)
            r = session.record
            print(f"  OK {r['jit_status']} bodies={r['jit_bodies']} "
                  f"share={r['jit_share']:.4%} drained={r['drained']}", flush=True)
        require(source_state() == frozen, "sources changed during final session")
        summarize(out)
        return 0
    except (Failure, OSError, ValueError, importlib.metadata.PackageNotFoundError) as error:
        write_json(out / "failure.json", dict(error=str(error), status=getattr(error, "status", "FAILED")))
        summarize(out)
        print(f"STOP: {error}. Evidence: {out}; no automatic retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as error:
        raise SystemExit(str(error)) from error
