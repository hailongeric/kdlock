#!/usr/bin/env python3
"""VM-only ordinary-mutex mechanism checks; writing this file runs no checks.

This is synthetic kernel mechanism evidence, not a real-world syscall workload,
MM-body substitute, timing experiment or proof of whole-body JIT completion.
Failures preserve the loaded fixture, channel controls and output artifacts.
"""

import argparse
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import time


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def command(arguments, timeout):
    result = subprocess.run(arguments, check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError(f"command failed {arguments!r}: {result.stdout.decode(errors='replace')}")
    return result.stdout


def symbol_size(module, symbol, nm, timeout):
    for line in command([nm, "-S", "--defined-only", str(module)], timeout).decode().splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] == symbol:
            size = int(fields[1], 16)
            if not 0 < size <= 65536:
                raise ValueError(f"actual ELF size is outside fixture extent: {symbol}={size}")
            return size
    raise ValueError(f"actual module ELF has no sized symbol {symbol}")


def scan_operation_calls(exported, objdump, directory, timeout):
    """Generic actual-byte CALL records, checked by the pinned source decoder.

    GNU disassembly supplies instruction starts even when a prefix before the
    first lock is outside the pinned decoder. Every selected CALL is decoded at
    its ACTUAL source address and its target/length must agree. No opcode search,
    guessed wrapper length or application-specific lowering is used.
    """
    from disassem.compiler import SourceSite, SourceSnapshot
    from disassem.fragment import BoundaryKind, SourceCall
    from disassem.source_decode import SourceBytes, decode_source

    boundaries = {site.site: site.boundary for site in exported.snapshot.sites}
    api = {site.site: site.boundary for site in exported.snapshot.sites
           if site.boundary in (BoundaryKind.LOCK, BoundaryKind.UNLOCK)}
    calls, lock_roots, indirect = [], [], []
    line_pattern = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(\S+)(?:\s+(.*))?$")
    for index, region in enumerate(exported.snapshot.regions):
        binary = directory / f"source-{index}.bin"
        binary.write_bytes(region.data)
        listing = command([objdump, "-D", "-b", "binary", "-m", "i386:x86-64",
                           "--insn-width=16", f"--adjust-vma={region.start}", str(binary)], timeout)
        (directory / f"source-{index}.disassembly.txt").write_bytes(listing)
        for line in listing.decode("ascii", errors="strict").splitlines():
            match = line_pattern.match(line)
            if not match or match[3] not in ("call", "callq"):
                continue
            site = int(match[1], 16)
            raw = bytes.fromhex(match[2])
            if not region.start <= site < region.end:
                raise ValueError("disassembler CALL escaped its exact supplied region")
            decoded = decode_source({site: SourceBytes(exported.snapshot.window(site))})
            record = decoded.instructions.get(site)
            node = decoded.graph.get(site)
            if record is None or not isinstance(node, SourceCall) or record.raw != raw:
                raise ValueError(f"actual CALL has no matching pinned decode at {site:#x}")
            item = {"site": site, "length": record.length, "target": node.target,
                    "indirect": node.indirect, "raw_hex": record.raw.hex()}
            calls.append(item)
            if node.indirect:
                indirect.append(site)
            if node.target in api:
                kind = api[node.target]
                old = boundaries.get(site)
                if old is not None and old is not kind:
                    raise ValueError("actual CALL and supplied source boundary disagree")
                boundaries[site] = kind
                item["operation"] = kind.value
                if kind is BoundaryKind.LOCK:
                    lock_roots.append(record.next_site)
    if not lock_roots:
        raise ValueError("no actual source CALL to the exported ordinary lock entry")
    sites = tuple(SourceSite(site, kind) for site, kind in sorted(boundaries.items()) if kind is not None)
    snapshot = SourceSnapshot(exported.snapshot.version, exported.snapshot.regions,
                              sites, exported.snapshot.observed_targets)
    return snapshot, tuple(sorted(set(lock_roots))), tuple(calls), tuple(indirect)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--kernel-elf", type=Path, required=True)
    parser.add_argument("--kernel-config", type=Path, required=True)
    parser.add_argument("--gs-proof-json", type=Path, required=True)
    parser.add_argument("--gs-offset", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--dependency-page-limit", type=int, required=True)
    parser.add_argument("--total-source-byte-limit", type=int, required=True)
    parser.add_argument("--wire-log-byte-limit", type=int, required=True)
    parser.add_argument("--immutable-text-contract", action="store_true", required=True)
    parser.add_argument("--auxiliary-stack-contract", action="store_true", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=32)
    parser.add_argument("--deadline", type=float, default=120.0)
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().machine != "x86_64":
        raise ValueError("fixture requires root in the designated x86_64 VM")
    if not os.uname().release.startswith("7.") or os.uname().release != args.expected_release:
        raise ValueError("actual kernel release differs from the explicit Linux 7 target")
    if (not 2 <= args.workers <= 8 or not 1 <= args.iterations <= 64
            or not math.isfinite(args.deadline) or args.deadline <= 0
            or not 0 <= args.gs_offset < 1 << 64
            or not 1 <= args.dependency_page_limit <= 4096 - 2
            or not 1 <= args.total_source_byte_limit < 1 << 64
            or not 1 <= args.wire_log_byte_limit < 1 << 64
            or args.total_source_byte_limit + (2 + args.dependency_page_limit) * 16
                + 32 + 7 * 8 + 64 * 16 + 8 + 256 > 2 * 1024 * 1024):
        raise ValueError("fixture worker/iteration/source/deadline extent is invalid")
    proof = json.loads(args.gs_proof_json.read_text())
    if (proof.get("verified_for_running_kernel") is not True
            or proof.get("kernel_release") != os.uname().release
            or proof.get("gs_symbol") != "current_task"
            or int(str(proof.get("current_task_gs_offset")), 0) != args.gs_offset
            or proof.get("kernel_elf_sha256") != digest(args.kernel_elf)
            or proof.get("kernel_config_sha256") != digest(args.kernel_config)):
        raise ValueError("GS proof is not the exact root-verified running-target ELF/configuration receipt")
    configuration = args.kernel_config.read_text()
    if "CONFIG_PREEMPT_RT=y" in configuration or "CONFIG_KDLOCK_REBUILD=y" not in configuration:
        raise ValueError("actual config is outside this rebuilt non-RT fixture lane")
    args.output = args.output.resolve()
    args.output.mkdir(parents=False, exist_ok=False)
    args.repo = args.repo.resolve()
    args.module = args.module.resolve()
    sys.path.insert(0, str(args.repo))
    from disassem.archive import ArchiveConfig, ShutdownSession
    from disassem.compiler import DiscoveryLimits
    from disassem.feedback import ExitKind
    from disassem.image_builder import BuildLimits, GNUImageBuilder, Toolchain
    from disassem.learning import FactKey, LearningCoordinator, LearningLimits, MergeDisposition
    from disassem.lowering import CodegenLimits, EntryMetadata
    from disassem.session import (
        ChannelStatusError, FeedbackSession, FdTransport, ProducerCatalog,
        SessionConfig, SessionPhase, SourceExportSession,
    )
    from disassem.wire import Operation, SourceExportLimits, WireLimits, decode, token, token_word

    tools = {name: shutil.which(name) for name in ("nm", "objdump", "cpp", "as", "ld", "objcopy", "insmod", "rmmod")}
    if not all(tools.values()):
        raise ValueError("a required actual build/control tool is absent")
    body_size = symbol_size(args.module, "fixture_source_body", tools["nm"], args.deadline)
    step_size = symbol_size(args.module, "fixture_source_step", tools["nm"], args.deadline)
    version = "fixture-" + digest(args.module) + "-" + proof["kernel_elf_sha256"] + "-" + proof["kernel_config_sha256"]
    results = {"evidence": "kernel-mechanism", "kernel_release": os.uname().release,
               "module_sha256": digest(args.module), "source_version": version,
               "gs_proof": proof, "module_sizes": {"body": body_size, "callee": step_size},
               "source_limits": {"dependency_pages": args.dependency_page_limit,
                                 "total_source_bytes": args.total_source_byte_limit},
               "wire_log": {"byte_limit": args.wire_log_byte_limit,
                            "reserved_bytes": 0, "reservations": 0},
               "workers": args.workers, "iterations": args.iterations, "cases": [],
               "status": "incomplete", "returned_full_jit_body": "not_established"}
    (args.output / "identity.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    module_listing = command([tools["objdump"], "-dr", str(args.module)], args.deadline)
    (args.output / "module.disassembly.txt").write_bytes(module_listing)
    results["compiler_thunk_symbols"] = sorted(set(re.findall(
        r"__(?:x86_indirect|x86_return)_thunk[A-Za-z0-9_]*", module_listing.decode(errors="replace"))))
    control = -1
    transport = None
    wire_directory = args.output / "wire"
    wire_directory.mkdir()

    class RecordedTransport(FdTransport):
        """Observe actual transport calls; never dispatch, replay or settle twice.

        An output-write failure propagates before exchange clears its flight, so
        actual kernel controls remain for explicit reconciliation. A saved file
        alone is no protocol/ownership proof; retain its returned status too.
        """

        def _ioctl(self, flight):
            # Reserve complete observed output even on delivery failure, plus
            # both bounded JSON records, before any ioctl can change controls.
            metadata_limit = 4096
            required = len(flight.request) + len(flight.output_buffer) + len(flight.header) + metadata_limit
            retained = results["wire_log"]["reserved_bytes"]
            if required > args.wire_log_byte_limit - retained:
                results["wire_log"]["refused"] = {
                    "operation": int(flight.operation), "sequence": flight.sequence,
                    "required_bytes": required,
                }
                raise ValueError("explicit wire-log byte limit cannot retain the next exchange")
            results["wire_log"]["reserved_bytes"] = retained + required
            results["wire_log"]["reservations"] += 1
            metadata_bytes = 0
            attempt = getattr(self, "_recorded_attempts", 0) + 1
            self._recorded_attempts = attempt
            directory = wire_directory / f"attempt-{attempt:08d}"
            directory.mkdir()

            def metadata(name, value):
                nonlocal metadata_bytes
                copied = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
                if len(copied) > metadata_limit - metadata_bytes:
                    raise ValueError("wire observer metadata exceeds its reserved byte extent")
                metadata_bytes += len(copied)
                (directory / name).write_bytes(copied)

            (directory / "request.bin").write_bytes(flight.request)
            identity = {"operation": int(flight.operation), "sequence": flight.sequence,
                        "request_bytes": len(flight.request),
                        "output_capacity": len(flight.output_buffer)}
            metadata("request.json", identity)
            try:
                result = super()._ioctl(flight)
            except BaseException as error:
                # These are observed buffers, not a claimed completed response.
                (directory / "observed-envelope.bin").write_bytes(bytes(flight.header))
                (directory / "observed-output-capacity.bin").write_bytes(bytes(flight.output_buffer))
                metadata("error.json", {**identity, "error": repr(error), "completed_response": False})
                raise
            (directory / "returned-envelope.bin").write_bytes(bytes(flight.header))
            (directory / "reply.bin").write_bytes(result.payload)
            metadata("result.json", {**identity, "returned_sequence": result.sequence,
                "status": result.status, "reply_bytes": len(result.payload), "completed_response": True})
            return result

    def status():
        os.lseek(control, 0, os.SEEK_SET)
        raw = os.read(control, 8192).decode("ascii", errors="strict")
        values = dict(part.split("=", 1) for part in raw.split())
        return raw, values

    def control_command(text):
        payload = (text + "\n").encode("ascii")
        if os.write(control, payload) != len(payload):
            raise RuntimeError("fixture control did not consume the exact command")

    def managed_fork_case():
        # Actual ordinary fd calls and fork/wait/exit syscalls exercise the
        # managed-parent kernel hooks. No child register state is fabricated.
        control_command("enter")
        parent_raw, parent = status()
        keys = ("self_root", "self_core", "self_regs", "self_binding")

        def identities(values):
            return tuple(int(values[key], 16) for key in keys)

        def native_scope(values, pid):
            return (int(values["self_pid"]) == pid
                    and all(int(values[key]) == 1 for key in
                            ("self_own", "self_native", "self_managed"))
                    and all(identities(values)))

        if not native_scope(parent, os.getpid()):
            raise AssertionError("actual parent native task/root identity is absent")
        read_pipe, write_pipe = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(read_pipe)
            child_result = 1
            try:
                child_raw, child_values = status()
                row = {"pid": os.getpid(), "raw_status": child_raw, "values": child_values}
                payload = (json.dumps(row, sort_keys=True) + "\n").encode("ascii")
                if len(payload) > 4096 or os.write(write_pipe, payload) != len(payload):
                    raise RuntimeError("child identity record was not transferred exactly")
                child_result = 0
            except BaseException as error:
                failure = (json.dumps({"pid": os.getpid(), "error": repr(error)}) + "\n").encode("ascii")
                try:
                    os.write(write_pipe, failure[:4096])
                except OSError:
                    pass
            finally:
                os.close(write_pipe)
                # No explicit leave: actual child do_exit must drain/release
                # its independently inherited provider/context lifetime.
                os._exit(child_result)
        os.close(write_pipe)
        results["managed_fork_exit"] = {"child_pid": child_pid, "parent_before": parent_raw,
                                        "status": "child_not_yet_reaped"}
        deadline = time.monotonic() + args.deadline
        copied = bytearray()
        try:
            while not copied.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select((read_pipe,), (), (), max(0, remaining))[0]:
                    raise TimeoutError("managed child identity wait expired; no child kill/drain inferred")
                block = os.read(read_pipe, 4096 - len(copied))
                if not block:
                    raise RuntimeError("managed child exited without its complete identity record")
                copied.extend(block)
                if len(copied) >= 4096 and not copied.endswith(b"\n"):
                    raise ValueError("managed child identity record exceeds fixture extent")
            child = json.loads(copied)
            results["managed_fork_exit"]["child_record"] = child
            while True:
                reaped, wait_status = os.waitpid(child_pid, os.WNOHANG)
                if reaped == child_pid:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("managed child exit-hook wait expired; process/module retained")
                time.sleep(0.02)
        finally:
            os.close(read_pipe)
            (args.output / "managed-child-record.bin").write_bytes(copied)
        results["managed_fork_exit"]["wait_status"] = wait_status
        if (not os.WIFEXITED(wait_status) or os.WEXITSTATUS(wait_status)
                or child["pid"] != child_pid or not native_scope(child["values"], child_pid)
                or any(first == second for first, second in
                       zip(identities(parent), identities(child["values"])))):
            raise AssertionError("child inherited a parent's core/binding or lacks its own native origin")
        after_raw, after = status()
        if not native_scope(after, os.getpid()) or identities(parent) != identities(after):
            raise AssertionError("managed fork changed the parent's current root/core/binding")
        while True:
            try:
                control_command("leave")
                break
            except OSError as error:
                if error.errno not in (errno.EBUSY, errno.EAGAIN) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        detached_raw, detached = status()
        if any(identities(detached)) or any(int(detached[key]) for key in
                                          ("self_own", "self_native", "self_managed")):
            raise AssertionError("parent leave did not remove its actual native task context")
        results["managed_fork_exit"].update({"status": "child_exited_parent_detached",
                                            "parent_after": after_raw, "parent_detached": detached_raw,
                                            "packet_contents_copied": False})

    def body_case(name, mode, workers, iterations):
        control_command(f"start {mode} {workers} {iterations}")
        deadline = time.monotonic() + args.deadline
        while True:
            raw, values = status()
            if int(values["finished"]) == workers:
                break
            if time.monotonic() >= deadline:
                (args.output / f"{name}-timeout.txt").write_text(raw)
                raise TimeoutError("worker completion deadline expired; no drain/unload inferred")
            time.sleep(0.02)
        expected = workers * iterations
        expected_b = 0 if mode == 0 else expected * (2 if mode == 2 else 1)
        expected_calls = expected * (mode + 1)
        if (int(values["completed"]) != expected or int(values["calls"]) != expected_calls
                or int(values["a"]) != expected or int(values["b"]) != expected_b
                or int(values["errors"]) or int(values["origin_errors"]) or int(values["core_errors"])
                or int(values["locks_clear"]) != 1):
            (args.output / f"{name}-failure.txt").write_text(raw)
            raise AssertionError("ordinary source effects/current/core/physical cleanup differ")
        results["cases"].append({"name": name, "mode": mode, "workers": workers,
                                 "iterations": iterations, "raw_status": raw, "values": values,
                                 "expected_call_effects": expected_calls,
                                 "actual_call_effects": int(values["calls"]),
                                 "native_body_completion": True})
        control_command("stop")

    def drive(workflow):
        deadline = time.monotonic() + args.deadline
        while workflow.phase.name != "COMPLETE":
            try:
                workflow.advance()
            except ChannelStatusError as error:
                if error.status not in (-errno.EBUSY, -errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("metadata progress deadline; retained controls are not drained") from error
                time.sleep(0.02)
        return workflow.result

    try:
        command([tools["insmod"], str(args.module), f"gs_offset={args.gs_offset}", "gs_verified=1",
                 "immutable_text=1", "auxiliary_contract=1", f"source_size={body_size}",
                 f"step_size={step_size}", f"dependency_page_limit={args.dependency_page_limit}",
                 f"total_source_byte_limit={args.total_source_byte_limit}",
                 f"source_version={version}"], args.deadline)
        control = os.open("/dev/kd_runtime_fixture_ctl", os.O_RDWR | os.O_CLOEXEC)
        managed_fork_case()
        body_case("native-local", 0, 1, args.iterations)
        limits = WireLimits(2 * 1024 * 1024, 4096, 256, 256, 512 * 1024)
        transport = RecordedTransport.open("/dev/kd_runtime_fixture", limits, 4 * 1024 * 1024 + 48)
        exported = drive(SourceExportSession(transport, SourceExportLimits(
            2 + args.dependency_page_limit, 64, args.total_source_byte_limit)))
        snapshot, roots, calls, indirect = scan_operation_calls(exported, tools["objdump"], args.output, args.deadline)
        results["actual_source_regions"] = [{"start": region.start, "length": len(region.data)}
                                            for region in snapshot.regions]
        results["actual_source_region_count"] = len(snapshot.regions)
        results["actual_dependency_page_count"] = len(snapshot.regions) - 2
        results["actual_source_bytes"] = sum(len(region.data) for region in snapshot.regions)
        results["actual_call_records"] = calls
        results["near_indirect_call_sites"] = indirect
        results["root_entry"] = roots[0]
        results["ordinary_indirect_kernel_learning"] = "unverified"
        (args.output / "source-export.bin").write_bytes(exported.raw_reply)
        (args.output / "source-metadata.json").write_text(json.dumps({
            "version": snapshot.version, "regions": results["actual_source_regions"],
            "region_count": results["actual_source_region_count"],
            "dependency_page_count": results["actual_dependency_page_count"],
            "source_bytes": results["actual_source_bytes"], "limits": results["source_limits"],
            "sites": [{"site": s.site, "boundary": s.boundary.value if s.boundary else None} for s in snapshot.sites],
            "slot": exported.slot_identity, "old": exported.expected_old_image_identity,
        }, indent=2, sort_keys=True) + "\n")
        coordinator = LearningCoordinator(exported.epoch, snapshot, LearningLimits(4096, 32, 16, 16, 16))
        producers = ProducerCatalog(16, ())
        old = exported.expected_old_image_identity
        cycle_number = 0

        def compiler_cycle(force=False, run_pending_probe=False):
            nonlocal old, cycle_number
            cycle_number += 1
            cycle = args.output / f"cycle-{cycle_number}"
            cycle.mkdir()
            builder = GNUImageBuilder(Toolchain(
                tools["cpp"], tools["as"], tools["ld"], tools["objcopy"],
                (str(args.repo / "include"),), (("PATH", "/usr/bin:/bin"), ("LC_ALL", "C")),
                str(cycle / "build"), os.sysconf("SC_PAGE_SIZE")),
                BuildLimits(2 * 1024 * 1024, 2 * 1024 * 1024, 128 * 1024, 256 * 1024, 256 * 1024, args.deadline))
            session = FeedbackSession(transport, coordinator, producers, SessionConfig(
                exported.slot_identity, old, 0x1000 + cycle_number, 4096, roots[0],
                DiscoveryLimits(4096, 15 * 4096, 32768, 5),
                EntryMetadata("kd_fixture_entry", tuple(sorted({record["site"] + record["length"]
                              for record in calls if "operation" in record})), args.gs_offset),
                CodegenLimits(4096, 64 * 1024, 1000000)), builder)
            session.advance(); session.advance()  # actual claim, then copied/merged claim
            if session.phase is not SessionPhase.BUILD_START:
                raise AssertionError("actual claim did not reach the documented pre-build state")
            if run_pending_probe:
                body_case("jit-while-pending", 1, args.workers, max(1, args.iterations // 2))
            raw_claim = session.raw_reply
            (cycle / "claim.bin").write_bytes(raw_claim)
            copied = decode(raw_claim, Operation.CLAIM, 3, 12, (limits.version_bytes,), limits)
            claimed_keys = {FactKey(exported.epoch.identity, token(row[0]), row[1]) for row in copied.rows}
            merged = any(state.recorded.fact.key in claimed_keys
                         and state.recorded.merge is MergeDisposition.MERGED
                         for state in coordinator.facts())
            if not force and not merged:
                session.finish_pending()
            result = drive(session)
            if result.candidate is not None:
                artifact = result.candidate.artifact
                (cycle / "image.S").write_text(artifact.assembly)
                (cycle / "metadata.c").write_text(artifact.c_metadata)
                (cycle / "manifest.json").write_text(artifact.manifest_json)
                (cycle / "commit.bin").write_bytes(result.raw_commit)
                (cycle / "ack.bin").write_bytes(result.raw_ack)
                old = token_word(result.candidate.binding.image_identity)
            results.setdefault("compiler_cycles", []).append({
                "claim_rows": len(result.claim.records), "published": result.publication is not None,
                "acknowledged_keys": len(result.acknowledgment.keys) if result.acknowledgment else 0,
            })
            return result

        compiler_cycle(force=True)
        for number, mode in enumerate((0, 1, 2)):
            body_case(("contended-local", "nested", "out-of-order")[number], mode, args.workers, args.iterations)
            compiler_cycle(run_pending_probe=number == 0)
        states = coordinator.facts()
        successful_exits = tuple(state for state in states if state.recorded.fact.entry_result == 0
                                 and state.recorded.fact.exit.kind == int(ExitKind.COVERAGE_MISS))
        ordinary = tuple(state for state in states if state.recorded.feedback.observation is not None)

        def exact_key(state):
            fact = state.recorded.fact
            return {"epoch": fact.epoch.identity.hex(), "record": fact.record_identity.hex(),
                    "incarnation": fact.incarnation}

        results["ordinary_indirect_learning"] = {
            "observed": [exact_key(state) for state in ordinary],
            "merged": [exact_key(state) for state in ordinary
                       if state.recorded.merge is MergeDisposition.MERGED],
            "candidate_inputs": [exact_key(state) for state in ordinary if state.input_candidate_identities],
            "emitted": [exact_key(state) for state in ordinary if state.emitted_candidate_identities],
            "published_inputs": [exact_key(state) for state in ordinary if state.publication_identities],
            "acknowledged": [exact_key(state) for state in ordinary if state.acknowledgment_identities],
        }
        for stage in ("acknowledged", "published_inputs", "emitted", "candidate_inputs", "merged", "observed"):
            if results["ordinary_indirect_learning"][stage]:
                results["ordinary_indirect_kernel_learning"] = stage
                break
        results["typed_generated_exit_records"] = len(successful_exits)
        results["generated_exit_seen"] = bool(successful_exits)
        results["generated_exit_records"] = [{
            "record": state.recorded.fact.record_identity.hex(),
            "incarnation": state.recorded.fact.incarnation,
            "producer": state.recorded.fact.producer_identity.hex(),
            "image": state.recorded.fact.image_identity.hex(),
            "entry_result": state.recorded.fact.entry_result,
            "exit": vars(state.recorded.fact.exit),
            "matching_source_call": next((record for record in calls
                if record["site"] == state.recorded.fact.exit.source_ip), None),
            "source_region": next(({"index": index, "start": region.start,
                "offset": state.recorded.fact.exit.source_ip - region.start}
                for index, region in enumerate(snapshot.regions)
                if region.start <= state.recorded.fact.exit.source_ip < region.end), None),
            "classification": state.recorded.fact.classification.value,
            "disposition": state.recorded.feedback.kind.value,
            "merge": state.recorded.merge.value,
            "ordinary_observation": (None if state.recorded.feedback.observation is None else {
                "source_version": state.recorded.feedback.observation.source_version,
                "source_ip": state.recorded.feedback.observation.site,
                "target": state.recorded.feedback.observation.target,
                "kind": state.recorded.feedback.observation.kind.value,
            }),
            "input_candidates": [value.hex() for value in state.input_candidate_identities],
            "emitted_candidates": [value.hex() for value in state.emitted_candidate_identities],
            "published": [value.hex() for value in state.publication_identities],
            "acknowledged": [value.hex() for value in state.acknowledgment_identities],
        } for state in states]
        results["pending_before_shutdown"] = len(coordinator.pending_keys())
        archive = drive(ShutdownSession(transport, coordinator, producers, ArchiveConfig(
            0x2000, 4096, str(args.output / "shutdown-archive.json"), 64 * 1024 * 1024, 0o600,
            (("module_sha256", results["module_sha256"]), ("kernel_release", os.uname().release),
             ("evidence", "kernel-mechanism")),)))
        results["managed_fork_exit"]["shutdown_native_holds_drained"] = True
        results["archive_sha256"] = archive.archive.identity.hex()
        results["settled_keys"] = len(archive.settlement.keys)
        transport.close()
        transport = None
        control_command("destroy")
        os.close(control)
        control = -1
        command([tools["rmmod"], "kd_runtime_fixture"], args.deadline)
        results["status"] = "partial_jit_mechanism_pass" if successful_exits else "inconclusive_generated_execution_not_observed"
        (args.output / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        return 0 if successful_exits else 2
    except BaseException as error:
        results["status"] = "failed_or_incomplete"
        results["error"] = repr(error)
        if transport is not None and transport.inflight:
            results["retained_channel_sequence"] = transport.pending_sequence
        (args.output / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        # No guessed drain, forced unload, reset, replay or destruction on failure.
        raise


if __name__ == "__main__":
    raise SystemExit(main())
