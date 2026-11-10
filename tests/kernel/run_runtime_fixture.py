#!/usr/bin/env python3
"""VM-only ordinary-mutex mechanism checks; writing this file runs no checks.

This is synthetic kernel mechanism evidence, not a real-world syscall workload,
MM-body substitute or timing experiment. Completion requires exact protected-episode
trace evidence; the unprotected C-function epilogue remains native.
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
import struct
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
    parser.add_argument("--event-capacity", type=int, required=True)
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
            or not 1 <= args.event_capacity <= ((1 << 63) - 1 - 40) // 160
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
               "event_capacity": args.event_capacity,
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
    event_fd = -1
    event_rows = []
    event_raw = bytearray()
    event_header = b""
    transport = None
    event_fields = ("kind", "task", "state", "origin", "node", "acquisition", "parent",
                    "owner", "owner_task", "object", "image", "ip", "cursor", "related",
                    "phase", "result", "flags", "source_user", "return_user", "notifier")
    event_names = ("SLOT_RESERVE", "SLOT_FREE", "ENQUEUE", "SELECT_LOCAL", "SELECT_PROXY", "GRANT",
                   "PROXY_RETURN", "QUEUE_DONE", "NODE_RETIRE_READY", "RELEASE_BIND", "RELEASE_REQUEST",
                   "RELEASE_DEFER", "RELEASE_UNWIND", "RELEASE_NOTIFY_DONE", "RELEASE_HANDLED",
                   "RELEASE_SOURCE_DROP", "RELEASE_RETURN_DROP", "PHYSICAL_BEGIN", "PHYSICAL_END",
                   "RELEASE_RETIRE", "OWNER_RETIRE", "FRAME_PREPARE", "JIT_ENTER", "JIT_EXIT",
                   "JIT_OPERATION", "CHILD_RETURN", "EPISODE_DONE", "FORWARD", "NATIVE_UNLOCK", "OWNER_STOP")
    kinds = {name: index + 1 for index, name in enumerate(event_names)}

    def read_exact(fd, length):
        copied = bytearray()
        while len(copied) < length:
            block = os.read(fd, min(length - len(copied), 160))
            if not block:
                raise RuntimeError("observation prefix ended before its declared extent")
            copied.extend(block)
        return bytes(copied)

    def observations():
        nonlocal event_header
        if event_fd < 0:
            return event_rows
        os.lseek(event_fd, 0, os.SEEK_SET)
        header = read_exact(event_fd, 40)
        abi, words, capacity, count, overflow = struct.unpack("<5Q", header)
        if (abi != 1 or words != 20 or capacity != args.event_capacity
                or not len(event_rows) <= count <= capacity):
            raise ValueError("actual observation ABI/capacity/immutable prefix differs")
        os.lseek(event_fd, 40 + len(event_rows) * 160, os.SEEK_SET)
        copied = read_exact(event_fd, (count - len(event_rows)) * 160)
        event_raw.extend(copied)
        for values in struct.iter_unpack("<20Q", copied):
            row = dict(zip(event_fields, values))
            row["index"] = len(event_rows)
            event_rows.append(row)
        event_header = header
        results["observation_records"] = count
        results["observation_overflow"] = overflow
        if overflow:
            raise AssertionError("diagnostic observation capacity overflowed; protocol is retained")
        return event_rows

    def save_observations(name):
        observations()
        (args.output / f"{name}.bin").write_bytes(event_header + bytes(event_raw))
        (args.output / f"{name}.json").write_text(json.dumps(
            {"fields": event_fields, "kinds": kinds, "records": event_rows},
            indent=2, sort_keys=True) + "\n")
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

    def wait_scene(predicate, label):
        deadline = time.monotonic() + args.deadline
        while True:
            raw, values = status()
            observations()
            if int(values["overflow"]):
                raise AssertionError("diagnostic observation overflow; source controls remain retained")
            if predicate(values):
                return raw, values
            if time.monotonic() >= deadline:
                (args.output / f"{label}-timeout.txt").write_text(raw)
                raise TimeoutError("scene ordering/completion deadline; no drain or selection inferred")
            time.sleep(0.01)

    def has(row, name):
        return row["kind"] == kinds[name]

    def typed_unlock(row, target, image):
        record = next((call for call in calls if call["site"] == row["ip"]
                       and call.get("operation") == "unlock"), None)
        return (has(row, "JIT_OPERATION") and row["result"] == 2 and row["related"] == target
                and row["image"] == image and record is not None
                and row["cursor"] == record["site"] + record["length"])

    def protected_completion(rows, node, image, task=None, expected=3):
        done = next((row for row in rows if has(row, "EPISODE_DONE") and row["node"] == node
                     and row["result"] == expected and row["flags"] & 512 and row["flags"] & 1024
                     and (task is None or row["task"] == task)), None)
        if done is None:
            raise AssertionError("no exact positive protected-episode completion before outward conversion")
        start = next((row for row in rows if has(row, "FRAME_PREPARE") and row["node"] == node
                      and row["acquisition"] == done["acquisition"]), None)
        if start is None:
            raise AssertionError("positive episode has no retained exact frame lifetime")
        interval = [row for row in rows if start["index"] <= row["index"] <= done["index"]
                    and row["state"] == done["state"] and row["origin"] == done["origin"]]
        if any(has(row, "FORWARD") for row in interval):
            raise AssertionError("a native suffix cannot count as a complete protected JIT episode")
        exits = [row for row in interval if has(row, "JIT_EXIT")]
        if not exits or any(row["result"] != 1 or row["image"] != image for row in exits):
            raise AssertionError("protected episode reached a miss/refusal/resource/special exit")
        if not any(has(row, "JIT_ENTER") and row["image"] == image
                   and row["task"] != row["origin"] for row in interval):
            raise AssertionError("native-only completion supplies no generated execution proof")
        if not any(typed_unlock(row, node, image) for row in interval):
            raise AssertionError("episode completion lacks its exact JIT-handled source unlock")
        return done

    def validate_warm_plain(rows, image):
        selected = [row for row in rows if has(row, "SELECT_PROXY")]
        if not selected:
            raise AssertionError("warm plain case had no actual proxy selection")
        for selection in selected:
            # SLOT lifetimes delimit reuse: choose this selection's most recent
            # prepare and stop at its next SLOT_FREE rather than pooling addresses.
            prepare = next((row for row in reversed(rows) if row["index"] < selection["index"]
                            and has(row, "FRAME_PREPARE") and row["node"] == selection["node"]), None)
            if prepare is None:
                raise AssertionError("proxy selection has no exact prepared frame")
            stop = next((row["index"] for row in rows if row["index"] > selection["index"]
                         and has(row, "SLOT_FREE") and row["node"] == selection["node"]), rows[-1]["index"])
            protected_completion([row for row in rows if prepare["index"] <= row["index"] <= stop],
                                 selection["node"], image)

    def validate_retirement(rows, root, child, mode):
        for request in (root, child):
            grant = next((row for row in rows if has(row, "GRANT")
                          and row["node"] == request["node"] and row["acquisition"] == request["acquisition"]), None)
            if grant is None or not grant["related"] or not grant["owner"]:
                raise AssertionError("selected request lacks its exact release/physical-owner binding")
            release, owner, owner_task = grant["related"], grant["owner"], grant["owner_task"]
            release_rows = [row for row in rows if row["related"] == release and row["owner"] == owner
                            and row["state"] == request["state"]
                            and row["acquisition"] == request["acquisition"]]
            bound = next((row for row in release_rows if has(row, "RELEASE_BIND")
                          and row["source_user"]), None)
            handled = next((row for row in release_rows if has(row, "RELEASE_HANDLED")
                            and row["phase"] == 4 and row["task"] == owner_task), None)
            stopped = next((row for row in rows if has(row, "OWNER_STOP") and row["owner"] == owner
                            and row["task"] == owner_task and row["flags"] & 128), None)
            begin = next((row for row in rows if has(row, "PHYSICAL_BEGIN") and row["owner"] == owner
                          and row["task"] == owner_task and row["object"] == grant["object"]
                          and row["phase"] == 1 and row["related"]), None)
            physical = next((row for row in rows if has(row, "PHYSICAL_END") and row["owner"] == owner
                             and row["task"] == owner_task and row["object"] == grant["object"]
                             and row["phase"] == 2 and row["result"] == 0
                             and begin and row["related"] == begin["related"]), None)
            source_drop = next((row for row in release_rows if has(row, "RELEASE_SOURCE_DROP")
                                and row["phase"] == 5 and bound
                                and row["source_user"] == bound["source_user"]), None)
            retired = next((row for row in release_rows if has(row, "RELEASE_RETIRE")
                            and row["phase"] == 6 and not row["source_user"]
                            and not row["return_user"] and not row["notifier"]), None)
            free = next((row for row in rows if has(row, "SLOT_FREE") and row["node"] == request["node"]
                         and row["acquisition"] == request["acquisition"] and row["phase"] == 3
                         and row["flags"] & (2048 | 32 | 64) == (2048 | 32 | 64)), None)
            ready = next((row for row in rows if has(row, "NODE_RETIRE_READY")
                          and row["node"] == request["node"] and row["acquisition"] == request["acquisition"]
                          and row["phase"] == 6 and row["flags"] & (1 | 4 | 8) == (1 | 4 | 8)
                          and not row["flags"] & 16 and not row["source_user"]
                          and not row["return_user"] and not row["notifier"]), None)
            owner_retired = next((row for row in rows if has(row, "OWNER_RETIRE") and row["owner"] == owner
                                  and row["task"] == owner_task and row["phase"] == 3), None)
            if (not all((bound, handled, stopped, begin, physical, source_drop, retired, free, ready, owner_retired))
                    or not bound["index"] < handled["index"] < begin["index"] < physical["index"]
                    or not stopped["index"] < begin["index"]
                    or not physical["index"] < source_drop["index"] < retired["index"]
                    or not retired["index"] <= ready["index"] < free["index"]
                    or not physical["index"] < owner_retired["index"]):
                raise AssertionError("physical callback/control/last-user retirement proof is incomplete")
            if request is root and mode == 2:
                requested = next((row for row in release_rows if has(row, "RELEASE_REQUEST")
                                  and row["result"] == 2 and row["phase"] == 1 and row["return_user"]), None)
                deferred = next((row for row in release_rows if has(row, "RELEASE_DEFER")
                                 and row["phase"] == 2 and row["notifier"]), None)
                unwind = next((row for row in release_rows if has(row, "RELEASE_UNWIND") and row["phase"] == 3
                               and deferred and row["notifier"] == deferred["notifier"]), None)
                notified = next((row for row in release_rows if has(row, "RELEASE_NOTIFY_DONE")
                                 and deferred and row["notifier"] == deferred["notifier"]), None)
                returned = next((row for row in release_rows if has(row, "RELEASE_RETURN_DROP")
                                and requested and row["return_user"] == requested["return_user"]), None)
                if (not all((requested, deferred, unwind, notified, returned))
                        or not requested["index"] < deferred["index"] < unwind["index"] < handled["index"]
                        or not notified["index"] < retired["index"]
                        or not returned["index"] < retired["index"]):
                    raise AssertionError("deferred outer request/unwind/exact notifier-return tokens differ")

    def scene_case(mode, image):
        begin = len(observations())
        control_command(f"scene {mode}")
        _, first = wait_scene(lambda value: int(value["ready"], 16) == 31, f"scene{mode}-ready")
        tasks = [int(first[f"role{index}"], 16) for index in range(5)]
        control_command("go 0"); control_command("go 1")
        wait_scene(lambda value: int(value["held"], 16) & 3 == 3, f"scene{mode}-holders")
        control_command("go 2")
        wait_scene(lambda value: int(value["queued"], 16) & 4, f"scene{mode}-CA")
        control_command("go 4")
        wait_scene(lambda value: int(value["queued"], 16) & 16, f"scene{mode}-W")
        control_command("go 3")
        wait_scene(lambda value: int(value["queued"], 16) & 8, f"scene{mode}-CB")
        control_command("release 0")
        wait_scene(lambda value: int(value["child"], 16) != 0, f"scene{mode}-child")
        control_command("release 1")
        raw, final = wait_scene(lambda value: int(value["finished"]) == 5, f"scene{mode}-done")
        if (int(final["completed"]) != 5 or int(final["calls"]) != mode + 2
                or int(final["a"]) != 2 or int(final["b"]) != (2 if mode == 2 else 1)
                or any(int(final[key]) for key in ("errors", "core_errors", "origin_errors"))
                or int(final["locks_clear"]) != 1):
            raise AssertionError("five ordinary role effects or physical cleanup differ")
        rows = observations()[begin:]
        root = next(row for row in rows if has(row, "ENQUEUE") and row["task"] == tasks[4]
                    and row["origin"] == tasks[4])
        child = next(row for row in rows if has(row, "ENQUEUE") and row["task"] == tasks[2]
                     and row["origin"] == tasks[4] and row["node"] != root["node"])
        ca = next(row for row in rows if has(row, "ENQUEUE") and row["task"] == tasks[2]
                  and row["origin"] == tasks[2])
        cb = next(row for row in rows if has(row, "ENQUEUE") and row["task"] == tasks[3]
                  and row["origin"] == tasks[3])
        if (root["related"] != ca["node"] or child["related"] != cb["node"]
                or root["state"] != child["state"] or root["state"] != int(final["w_core"], 16)
                or not int(final["w_regs"], 16) or root["acquisition"] == child["acquisition"]):
            raise AssertionError("actual common-MCS queue or one-state/distinct-acquisition relation differs")
        for request, executor, head in ((root, tasks[2], ca), (child, tasks[3], cb)):
            if not any(has(row, "SELECT_LOCAL") and row["node"] == head["node"]
                       and row["task"] == executor and row["owner_task"] == executor for row in rows):
                raise AssertionError("candidate did not become the ordinary physical MCS head")
            if not any(has(row, "SELECT_PROXY") and row["node"] == request["node"]
                       and row["task"] == executor and row["owner_task"] == executor
                       and row["related"] == head["node"] for row in rows):
                raise AssertionError("ordinary optional arbitration did not select the required physical executor")
        prepare = next(row for row in rows if has(row, "FRAME_PREPARE") and row["node"] == child["node"])
        if prepare["parent"] != root["node"] or prepare["state"] != root["state"]:
            raise AssertionError("child is not the exact same-state recursive request")
        lock_b = next((row for row in rows if has(row, "JIT_OPERATION") and row["result"] == 1
                       and row["node"] == root["node"] and row["related"] == child["node"]
                       and row["task"] == tasks[2] and row["image"] == image
                       and row["object"] == int(final["object_b"], 16)), None)
        enter_a = next((row for row in rows if has(row, "JIT_ENTER") and row["node"] == root["node"]
                        and row["task"] == tasks[2] and row["image"] == image), None)
        enter_b = next((row for row in rows if has(row, "JIT_ENTER") and row["node"] == child["node"]
                        and row["task"] == tasks[3] and row["image"] == image), None)
        if not all((lock_b, enter_a, enter_b)) or not enter_a["index"] < lock_b["index"] < child["index"] < enter_b["index"]:
            raise AssertionError("no actual CA source-to-child operation and CB generated entry chain")
        child_done = protected_completion(rows, child["node"], image, tasks[3], 5 if mode == 2 else 3)
        returned = next((row for row in rows if has(row, "CHILD_RETURN") and row["node"] == root["node"]
                         and row["related"] == child["node"] and row["task"] == tasks[2]
                         and row["result"] == child_done["result"] and row["flags"] & 1024
                         and row["return_user"] and row["source_user"]
                         and row["return_user"] != row["source_user"]), None)
        root_done = protected_completion(rows, root["node"], image, tasks[2])
        if (returned is None or not child_done["index"] < returned["index"] < root_done["index"]
                or returned["source_user"] != enter_a["related"]
                or returned["cursor"] != child_done["cursor"]):
            raise AssertionError("no exact current-binding CB-to-CA child return followed by root completion")
        if mode == 1:
            resumed = next((row for row in rows if has(row, "JIT_ENTER") and row["node"] == root["node"]
                            and row["task"] == tasks[2] and row["image"] == image
                            and returned["index"] < row["index"] < root_done["index"]
                            and row["related"] == returned["return_user"]
                            and row["cursor"] == returned["cursor"]), None)
            if resumed is None:
                raise AssertionError("parent resumed neither the exact returned binding nor its current cursor")
        elif root_done["related"] != returned["return_user"] or root_done["cursor"] != returned["cursor"]:
            raise AssertionError("out-of-order root completion revived an old binding or cursor")
        if mode == 2:
            if not any(typed_unlock(row, root["node"], image) and row["task"] == tasks[3]
                       and row["node"] == child["node"] and row["phase"] == 2 for row in rows):
                raise AssertionError("outer logical unlock was not deferred from the actual inner executor")
        validate_retirement(rows, root, child, mode)
        proof = {"name": f"warm-recursive-{mode}", "mode": mode, "start": begin,
                 "end": len(event_rows), "roles": tasks, "state": root["state"],
                 "root": root["node"], "child": child["node"], "raw_status": raw,
                 "root_completion": root_done, "child_completion": child_done,
                 "child_return": returned, "fixed_image": image}
        results["cases"].append(proof)
        control_command("stop")
        return proof

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
                 f"event_capacity={args.event_capacity}", f"source_version={version}"], args.deadline)
        control = os.open("/dev/kd_runtime_fixture_ctl", os.O_RDWR | os.O_CLOEXEC)
        event_fd = os.open("/dev/kd_runtime_fixture_events", os.O_RDONLY | os.O_CLOEXEC)
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

        def compiler_cycle(force=False, run_pending_probe=False, claim_only=False):
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
            if claim_only or (not force and not merged):
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
        # The final candidate is now fixed. No image replacement or pending
        # probe is permitted in these completion checks.
        fixed_image = old
        results["warm_image_identity"] = fixed_image
        warm_start = len(observations())
        body_case("warm-plain", 0, args.workers, args.iterations)
        warm_plain_end = len(observations())
        warm_proofs = [{"name": "warm-plain", "start": warm_start, "end": warm_plain_end}]
        for mode in (1, 2):
            warm_proofs.append(scene_case(mode, fixed_image))
        save_observations("observations-before-shutdown")
        results["warm_completion"] = warm_proofs
        # A final consumer claim must be empty after the fixed-image passes.
        empty_cycle = compiler_cycle(claim_only=True)
        if empty_cycle.claim.records or empty_cycle.publication is not None or old != fixed_image:
            raise AssertionError("warm completion generated misses or replaced its fixed image")
        results["warm_claim_empty"] = True
        validate_warm_plain(event_rows[warm_start:warm_plain_end], fixed_image)
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
        save_observations("observations-final")
        os.close(event_fd)
        event_fd = -1
        os.close(control)
        control = -1
        command([tools["rmmod"], "kd_runtime_fixture"], args.deadline)
        results["returned_full_jit_body"] = "protected_episode_completed"
        results["full_c_function_jit_return"] = "outside_protected_episode_scope"
        results["status"] = "protected_jit_recursive_mechanism_pass"
        (args.output / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        return 0
    except BaseException as error:
        results["status"] = "failed_or_incomplete"
        results["error"] = repr(error)
        if event_header:
            (args.output / "observations-failure.bin").write_bytes(event_header + bytes(event_raw))
        if transport is not None and transport.inflight:
            results["retained_channel_sequence"] = transport.pending_sequence
        (args.output / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        # No guessed drain, forced unload, reset, replay or destruction on failure.
        raise


if __name__ == "__main__":
    raise SystemExit(main())
