#!/usr/bin/env python3
"""VM-only private managed-killable rwsem mechanism checks.

A failure retains this controller, its transport and all original child actors.
No failure path kills children, releases a holder, unloads or retries a body.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import sys
import time

NAME = "kd_rwsem_killable_fixture"
RUN, GO, RELEASE, RESET, RETIRE, EXIT_ACK = range(0x5301, 0x5307)
H, R, C, W, D = range(5)
FIELDS = ("kind", "task", "state", "origin", "node", "acquisition", "parent", "owner",
          "owner_task", "object", "image", "ip", "cursor", "related", "phase", "result",
          "flags", "source_user", "return_user", "notifier")
NAMES = ("SLOT_RESERVE", "SLOT_FREE", "ENQUEUE", "SELECT_LOCAL", "SELECT_PROXY", "GRANT",
         "PROXY_RETURN", "QUEUE_DONE", "NODE_RETIRE_READY", "RELEASE_BIND", "RELEASE_REQUEST",
         "RELEASE_DEFER", "RELEASE_UNWIND", "RELEASE_NOTIFY_DONE", "RELEASE_HANDLED",
         "RELEASE_SOURCE_DROP", "RELEASE_RETURN_DROP", "PHYSICAL_BEGIN", "PHYSICAL_END",
         "RELEASE_RETIRE", "OWNER_RETIRE", "FRAME_PREPARE", "JIT_ENTER", "JIT_EXIT",
         "JIT_OPERATION", "CHILD_RETURN", "EPISODE_DONE", "FORWARD", "NATIVE_UNLOCK", "OWNER_STOP",
         "READ_ACQUIRE", "READ_RELEASE", "WRITE_DOWNGRADE_REAL", "WRITE_DOWNGRADE_RETAINED",
         "NATIVE_MODE", "NATIVE_READ_ACQUIRE", "NATIVE_READ_RELEASE", "NATIVE_WRITE_ACQUIRE",
         "NATIVE_WRITE_RELEASE", "NATIVE_DOWNGRADE", "NATIVE_CANCEL", "NATIVE_TRY_MISS",
         "ACQUIRE_CANCELLED")
KINDS = {name: index + 1 for index, name in enumerate(NAMES)}
MODULE_LIMITS = ("dependency_page_limit", "total_source_byte_limit", "native_capacity", "request_capacity",
                 "auxiliary_bytes", "control_bytes", "proxy_limit", "feedback_capacity", "cycle_capacity",
                 "image_capacity", "claim_capacity", "frame_capacity", "code_capacity", "artifact_capacity",
                 "flat_capacity", "entry_capacity", "source_capacity", "observation_capacity", "event_capacity")
HOST_LIMITS = ("wire_log_bytes", "archive_bytes", "learning_passes", "runtime_block_visits",
               "decode_sites", "decode_window_bytes", "cfg_work_steps", "direct_call_edges",
               "lowered_sites", "lowered_text_bytes", "build_source_bytes", "build_metadata_bytes",
               "build_code_bytes", "build_flat_bytes", "build_manifest_bytes", "wire_rows",
               "wire_version_bytes", "wire_symbol_bytes", "wire_artifact_bytes", "recovery_bytes")


def signed(value):
    return value - (1 << 64) if value & (1 << 63) else value


def durable(path, data):
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def document(path, value):
    durable(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "module", "output", "kernel-elf", "kernel-config", "gs-proof-json", "limits-json"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--builtin-source-start", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--builtin-source-size", type=int, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--immutable-text-contract", action="store_true", required=True)
    parser.add_argument("--auxiliary-stack-contract", action="store_true", required=True)
    args = parser.parse_args()
    if (os.geteuid() or os.uname().machine != "x86_64" or os.uname().release != args.expected_release
            or not args.expected_release.startswith("7.") or not math.isfinite(args.deadline) or args.deadline <= 0):
        raise ValueError("the exact designated Linux 7 VM and finite deadline are required")
    bounds = json.loads(args.limits_json.read_text())
    if set(bounds) != set(MODULE_LIMITS + HOST_LIMITS) or any(type(value) is not int or value <= 0 for value in bounds.values()):
        raise ValueError("every module and host capacity must be explicit and positive")
    if any(value >= 1 << 64 for value in bounds.values()):
        raise ValueError("explicit capacities must fit unsigned words")
    if not 0 < args.builtin_source_size <= os.sysconf("SC_PAGE_SIZE") or not 0 < args.builtin_source_start < 1 << 64:
        raise ValueError("built-in source requires a nonempty finite span")
    if bounds["event_capacity"] > ((1 << 63) - 41) // 160:
        raise ValueError("event stream exceeds signed file offsets")
    if bounds["image_capacity"] < bounds["learning_passes"] + 1 or bounds["cycle_capacity"] < bounds["learning_passes"] + 3:
        raise ValueError("caller image/cycle capacities do not cover the finite scene plan")
    if bounds["learning_passes"] > 64:
        raise ValueError("controlled learning pass count must be within 1..64")
    for key in MODULE_LIMITS:
        if key not in ("total_source_byte_limit", "auxiliary_bytes", "control_bytes", "frame_capacity", "event_capacity") and bounds[key] >= 1 << 32:
            raise ValueError("module uint capacity is out of range")
    args.repo = args.repo.resolve()
    args.module = args.module.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=False, exist_ok=False)
    sys.path.insert(0, str(args.repo))
    sys.path.insert(0, str(args.repo / "tests/kernel"))
    from run_runtime_fixture import command, digest, executable_elf_bytes, scan_operation_calls, symbol_size
    from disassem.archive import ArchiveConfig, ShutdownSession
    from disassem.compiler import DiscoveryLimits
    from disassem.image_builder import BuildLimits, GNUImageBuilder, Toolchain
    from disassem.learning import LearningCoordinator, LearningLimits, MergeDisposition
    from disassem.lowering import CodegenLimits, EntryMetadata
    from disassem.session import ChannelStatusError, FeedbackSession, FdTransport, ProducerCatalog, SessionConfig, SessionPhase, SourceExportSession
    from disassem.wire import SourceExportLimits, WireLimits, token_word
    proof = json.loads(args.gs_proof_json.read_text())
    if (proof.get("verified_for_running_kernel") is not True or proof.get("kernel_release") != args.expected_release
            or proof.get("boot_id") != Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            or proof.get("gs_symbol") != "current_task"
            or proof.get("kernel_elf_sha256") != digest(args.kernel_elf)
            or proof.get("kernel_config_sha256") != digest(args.kernel_config)):
        raise ValueError("running boot/ELF/configuration GS proof differs")
    gs = int(str(proof["current_task_gs_offset"]), 0)
    configuration = args.kernel_config.read_text()
    if "CONFIG_PREEMPT_RT=y" in configuration or "CONFIG_KDLOCK_REBUILD=y" not in configuration:
        raise ValueError("the rebuilt non-RT configuration is required")
    builtin = executable_elf_bytes(args.kernel_elf, args.builtin_source_start, args.builtin_source_size)
    tools = {name: shutil.which(name) for name in ("nm", "objdump", "cpp", "as", "ld", "objcopy", "insmod", "rmmod")}
    if not all(tools.values()):
        raise ValueError("a required tool is unavailable")
    sizes = {name: symbol_size(args.module, symbol, tools["nm"], args.deadline)
             for name, symbol in (("killable_size", "fixture_killable_body"), ("writer_size", "fixture_writer_body"),
                                  ("step_size", "fixture_source_step"))}
    version = "killable-" + digest(args.module) + "-" + proof["kernel_elf_sha256"] + "-" + proof["kernel_config_sha256"]
    results = {"scope": "private-kernel-mechanism", "status": "incomplete", "gs_proof": proof,
               "module_sha256": digest(args.module), "source_version": version, "bounds": bounds,
               "sizes": sizes, "cases": [], "children": [], "wire": {"reserved_bytes": 0, "attempts": 0},
               "full_c_function_jit_return": "outside_protected_scope", "mm_jit": "not_exercised"}
    document(args.output / "identity.json", results)
    durable(args.output / "module.disassembly.txt", command([tools["objdump"], "-dr", str(args.module)], args.deadline))
    ctl = event_fd = -1
    transport = None
    rows, raw = [], bytearray()
    header = b""
    children = {}
    wire_dir = args.output / "wire"
    wire_dir.mkdir()

    class RecordedTransport(FdTransport):
        def _ioctl(self, flight):
            required = len(flight.request) + len(flight.output_buffer) + len(flight.header) + 4096
            if required > bounds["wire_log_bytes"] - results["wire"]["reserved_bytes"]:
                raise ValueError("wire receipt capacity refuses dispatch before ioctl")
            results["wire"]["reserved_bytes"] += required
            results["wire"]["attempts"] += 1
            directory = wire_dir / f"attempt-{results['wire']['attempts']:08d}"
            directory.mkdir()
            metadata = {"operation": int(flight.operation), "sequence": flight.sequence,
                        "request_bytes": len(flight.request), "output_capacity": len(flight.output_buffer)}
            metadata_bytes = 0
            def record_metadata(name, value):
                nonlocal metadata_bytes
                encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
                if len(encoded) > 4096 - metadata_bytes:
                    raise ValueError("wire metadata exceeds its pre-dispatch reservation")
                metadata_bytes += len(encoded)
                durable(directory / name, encoded)
            durable(directory / "request.bin", flight.request)
            record_metadata("request.json", metadata)
            try:
                reply = super()._ioctl(flight)
            except BaseException as error:
                durable(directory / "observed-envelope.bin", bytes(flight.header))
                durable(directory / "observed-output-capacity.bin", bytes(flight.output_buffer))
                record_metadata("error.json", {**metadata, "completed_response": False, "error": repr(error)[:1024]})
                raise
            durable(directory / "returned-envelope.bin", bytes(flight.header))
            durable(directory / "reply.bin", reply.payload)
            record_metadata("result.json", {**metadata, "completed_response": True,
                     "returned_sequence": reply.sequence, "status": reply.status, "reply_bytes": len(reply.payload)})
            return reply

    def ioctl(operation, role=0, action=0, gated=0):
        return fcntl.ioctl(ctl, operation, struct.pack("<4Q", role, action, gated, 0))

    def status():
        value = json.loads(os.pread(ctl, 8192, 0))
        if value["setup_error"] or value["cleanup_error"]:
            results["setup_status"] = value
            raise RuntimeError("fixture construction/cleanup is retained and queryable")
        if value["overflow"] or any(role["error"] for role in value["roles"]):
            raise AssertionError("fixture reported diagnostic overflow or a role error")
        return value

    def pread_exact(length, offset):
        result = bytearray()
        while len(result) < length:
            block = os.pread(event_fd, min(160, length - len(result)), offset + len(result))
            if not block:
                raise ValueError("event prefix is truncated")
            result.extend(block)
        return bytes(result)

    def observe():
        nonlocal header
        header = pread_exact(40, 0)
        abi, words, capacity, count, overflow = struct.unpack("<5Q", header)
        if abi != 1 or words != 20 or capacity != bounds["event_capacity"] or overflow or not len(rows) <= count <= capacity:
            raise ValueError("event ABI, capacity or prefix differs")
        copied = pread_exact((count - len(rows)) * 160, 40 + len(rows) * 160)
        raw.extend(copied)
        for values in struct.iter_unpack("<20Q", copied):
            rows.append({**dict(zip(FIELDS, values)), "index": len(rows)})
        return rows

    def wait(predicate, label):
        deadline = time.monotonic() + args.deadline
        while True:
            current = status()
            observe()
            if predicate(current):
                return current
            if time.monotonic() >= deadline:
                raise TimeoutError(label + "; original actors and controls remain retained")
            time.sleep(0.01)

    def spawn(role, action, gated=False):
        pid = os.fork()
        if not pid:
            for fd in (ctl, event_fd, transport.fd if transport else -1):
                if fd >= 0:
                    os.close(fd)
            fd = os.open(f"/dev/{NAME}_ctl", os.O_RDWR | os.O_CLOEXEC)
            try:
                fcntl.ioctl(fd, RUN, struct.pack("<4Q", role, action, int(gated), 0))
                os._exit(0)
            except BaseException:
                os._exit(1)
        children[role] = pid
        results["children"].append({"role": role, "pid": pid, "action": action, "gated": gated})
        wait(lambda value: value["roles"][role]["pid"] == pid and value["roles"][role]["ready"], "role readiness")
        return pid

    def joined(role, killed=False):
        pid = children[role]
        completed = wait(lambda value: value["roles"][role]["done"], "source API/body completion before exit")
        # RUN retains its exact task/storage endpoint until this explicit ACK.
        # The original task clears its raw observer before returning to do_exit.
        results.setdefault("before_exit_ack", []).append({"role": role, "status": completed})
        ioctl(EXIT_ACK, role)
        deadline = time.monotonic() + args.deadline
        while True:
            returned, code = os.waitpid(pid, os.WNOHANG)
            if returned:
                record = {"role": role, "pid": returned, "wait_status": code,
                          "observed_at": time.monotonic(), "events_before_observation": len(observe())}
                results.setdefault("waitpid", []).append(record)
                if (killed and (not os.WIFSIGNALED(code) or os.WTERMSIG(code) != signal.SIGKILL)) or (
                        not killed and (not os.WIFEXITED(code) or os.WEXITSTATUS(code))):
                    raise AssertionError("actual child exit disposition differs")
                del children[role]
                return record
            if time.monotonic() >= deadline:
                raise TimeoutError("actual child exit is unverified; holder remains unchanged")
            time.sleep(0.01)

    def matching(kind, begin, **fields):
        return [row for row in observe()[begin:] if row["kind"] == KINDS[kind]
                and all(row[key] == value for key, value in fields.items())]

    def enqueue(role, begin):
        task = status()["roles"][role]["task"]
        wait(lambda value: bool(matching("ENQUEUE", begin, task=task)), "exact enqueue")
        return matching("ENQUEUE", begin, task=task)[0]

    def kill(role):
        # Only the explicit, reached cancellation scene sends this signal.
        os.kill(children[role], signal.SIGKILL)

    def reset():
        final = wait(lambda value: not value["readers"] and not value["writer_pending"] and not value["writer"]
                     and not value["tail"] and not value["owner"] and value["pool_idle"] and not value["native_scopes"],
                     "exact gate and native-source finalization")
        if children:
            raise AssertionError("reset cannot substitute for waitpid")
        ioctl(RESET)
        return final

    def cancelled(role, begin, final):
        task = final["roles"][role]["task"]
        events = matching("ACQUIRE_CANCELLED", begin, origin=task)
        if len(events) != 1 or signed(events[0]["result"]) != -errno.EINTR or events[0]["phase"] != 5:
            raise AssertionError("no exact canonical canceled-operation result")
        event = events[0]
        if event["state"] != final["roles"][role]["state"] or matching("GRANT", begin, node=event["node"]) or matching("JIT_ENTER", begin, node=event["node"]):
            raise AssertionError("canceled acquisition gained source or physical authority")
        if final["roles"][role]["result"] != -errno.EINTR or final["roles"][role]["effects"] or final["roles"][role]["steps"]:
            raise AssertionError("canceled source returned another value or executed body effects")
        ready = matching("NODE_RETIRE_READY", begin, node=event["node"])
        freed = matching("SLOT_FREE", begin, node=event["node"])
        if (len(ready) != 1 or len(freed) != 1 or ready[0]["index"] >= freed[0]["index"]
                or ready[0]["flags"] & 12 != 12 or ready[0]["flags"] & 18
                or ready[0]["source_user"] or ready[0]["return_user"] or ready[0]["notifier"]
                or freed[0]["flags"] & (32 | 64 | 2048) != (32 | 64 | 2048)):
            raise AssertionError("canceled request lacks exact queue/user/slot retirement")
        return {"cancelled": event, "retire_ready": ready[0], "slot_free": freed[0]}

    def success(role, begin, final):
        actor = final["roles"][role]
        grants = matching("GRANT", begin, origin=actor["task"])
        if len(grants) != 1 or actor["result"] or actor["effects"] != 1 or actor["steps"] != 1 or actor["seen_task"] != actor["task"]:
            raise AssertionError("successful source lacks its exact grant and once-only effects")
        if grants[0]["state"] != actor["state"] or matching("ACQUIRE_CANCELLED", begin, node=grants[0]["node"]):
            raise AssertionError("successful integer grant changed canonical state or canceled")
        grant = grants[0]
        bound = matching("RELEASE_BIND", begin, related=grant["related"], state=grant["state"],
                         acquisition=grant["acquisition"], owner=grant["owner"])
        physical = matching("PHYSICAL_END", begin, owner=grant["owner"], owner_task=grant["owner_task"])
        if len(bound) != 1 or not bound[0]["source_user"] or len(physical) != 1:
            raise AssertionError("grant has no exact source token or physical release")
        end = physical[0]
        starts = matching("PHYSICAL_BEGIN", begin, owner=grant["owner"], owner_task=grant["owner_task"],
                          object=end["object"], related=end["related"])
        drops = matching("RELEASE_SOURCE_DROP", begin, related=grant["related"], state=grant["state"],
                         acquisition=grant["acquisition"], source_user=bound[0]["source_user"])
        retired = matching("RELEASE_RETIRE", begin, related=grant["related"], state=grant["state"],
                           acquisition=grant["acquisition"], owner=grant["owner"])
        owners = matching("OWNER_RETIRE", begin, owner=grant["owner"], owner_task=grant["owner_task"])
        stopped = matching("OWNER_STOP", begin, owner=grant["owner"], owner_task=grant["owner_task"])
        ready = matching("NODE_RETIRE_READY", begin, node=grant["node"], acquisition=grant["acquisition"])
        freed = matching("SLOT_FREE", begin, node=grant["node"], acquisition=grant["acquisition"])
        if (len(starts) != 1 or not end["related"] or end["result"] or end["phase"] != 2
                or len(drops) != 1 or drops[0]["phase"] != 5 or len(retired) != 1
                or retired[0]["phase"] != 6 or retired[0]["source_user"] or retired[0]["return_user"]
                or retired[0]["notifier"] or len(owners) != 1 or len(stopped) != 1
                or not stopped[0]["flags"] & 128 or len(ready) != 1 or len(freed) != 1
                or not starts[0]["index"] < end["index"] < drops[0]["index"] < retired[0]["index"]
                or not stopped[0]["index"] < owners[0]["index"] < ready[0]["index"] < freed[0]["index"]
                or retired[0]["index"] >= owners[0]["index"]
                or freed[0]["flags"] & (32 | 64 | 2048) != (32 | 64 | 2048)
                or freed[0]["flags"] & 16):
            raise AssertionError("physical callback, last source user and final retirement do not join")
        results.setdefault("retirement", []).append({"grant": grant, "bind": bound[0],
            "physical_begin": starts[0], "physical_end": end, "source_drop": drops[0],
            "release_retire": retired[0], "owner_stop": stopped[0], "owner_retire": owners[0],
            "node_ready": ready[0], "slot_free": freed[0]})
        return grant

    def save_case(name, begin, final, **proofs):
        value = {"name": name, "start": begin, "end": len(observe()), "status": final, **proofs}
        results["cases"].append(value)
        document(args.output / (name + ".json"), value)
        return value

    def drive(workflow):
        end = time.monotonic() + args.deadline
        while workflow.phase.name != "COMPLETE":
            try:
                workflow.advance()
            except ChannelStatusError as error:
                if error.status not in (-errno.EBUSY, -errno.EAGAIN) or time.monotonic() >= end:
                    raise
                time.sleep(0.01)
        return workflow.result

    try:
        parameters = {**{key: bounds[key] for key in MODULE_LIMITS}, **sizes,
                      "gs_offset": gs, "gs_verified": 1, "immutable_text": 1, "auxiliary_contract": 1,
                      "source_version": version, "builtin_source_start": args.builtin_source_start,
                      "builtin_source_size": args.builtin_source_size}
        command([tools["insmod"], str(args.module), *(f"{key}={value}" for key, value in parameters.items())], args.deadline)
        ctl = os.open(f"/dev/{NAME}_ctl", os.O_RDWR | os.O_CLOEXEC)
        loaded = status()
        if not loaded["setup_complete"]:
            raise RuntimeError("module loaded without complete source/runtime composition")
        event_fd = os.open(f"/dev/{NAME}_events", os.O_RDONLY | os.O_CLOEXEC)

        begin = len(observe())
        spawn(W, 0); kill(W); ioctl(GO, W)
        joined(W, killed=True)
        final = reset()
        save_case("ready-before-fatal-cancel", begin, final, grant=success(W, begin, final))

        begin = len(observe())
        spawn(R, 3); ioctl(GO, R)
        wait(lambda value: value["readers"] == 1, "native reader acquired")
        spawn(W, 0); ioctl(GO, W); enqueue(W, begin)
        wait(lambda value: value["writer_pending"] and value["roles"][W]["turn"], "local ungranted writer head")
        kill(W); joined(W, killed=True)
        held = status()
        if held["readers"] != 1:
            raise AssertionError("cancellation consumed the original reader")
        ioctl(RELEASE, R); joined(R)
        final = reset()
        save_case("reader-drain-cancel", begin, final, held_reader=held, **cancelled(W, begin, final))

        begin = len(observe())
        spawn(H, 2); ioctl(GO, H)
        wait(lambda value: value["writer"] != 0, "native writer acquired")
        spawn(W, 0); ioctl(GO, W)
        queued = enqueue(W, begin)
        kill(W)
        exited = joined(W, killed=True)
        held = status()
        if not held["writer"] or held["roles"][H]["done"] or not held["native_scopes"]:
            raise AssertionError("queued caller exit did not retain the blocked queue/native source")
        if matching("NODE_RETIRE_READY", begin, node=queued["node"]) or matching("SLOT_FREE", begin, node=queued["node"]):
            raise AssertionError("queue predecessor was bypassed by premature retirement")
        durable(args.output / "queued-exit-before-holder-release.bin", header + bytes(raw))
        ioctl(RELEASE, H); joined(H)
        final = reset()
        save_case("queued-exit-before-holder-release", begin, final, actual_exit=exited,
                  holder_before_release=held, **cancelled(W, begin, final))

        limits = WireLimits(bounds["frame_capacity"], bounds["wire_rows"], bounds["wire_version_bytes"],
                            bounds["wire_symbol_bytes"], bounds["wire_artifact_bytes"])
        transport = RecordedTransport.open(f"/dev/{NAME}", limits, bounds["recovery_bytes"])
        exported = drive(SourceExportSession(transport, SourceExportLimits(
            3 + bounds["dependency_page_limit"], bounds["entry_capacity"], bounds["total_source_byte_limit"])))
        supplied = [region for region in exported.snapshot.regions if region.start == args.builtin_source_start
                    and len(region.data) == args.builtin_source_size]
        if len(supplied) != 1 or supplied[0].data != builtin:
            raise ValueError("actual built-in dependency differs from linked ELF bytes")
        durable(args.output / "source-export.bin", exported.raw_reply)
        snapshot, roots, calls, indirect = scan_operation_calls(exported, tools["objdump"], args.output, args.deadline)
        document(args.output / "source-metadata.json", {"version": snapshot.version,
                 "regions": [{"start": region.start, "length": len(region.data)} for region in snapshot.regions],
                 "calls": calls, "roots": roots, "near_indirect_call_sites": indirect,
                 "slot": exported.slot_identity, "old": exported.expected_old_image_identity,
                 "builtin_sha256": hashlib.sha256(builtin).hexdigest(), "builtin_matches_elf": True})
        killable_span = exported.snapshot.regions[0]
        killable_returns = {call["site"] + call["length"] for call in calls
                            if killable_span.start <= call["site"] < killable_span.end
                            and call.get("operation") == "lock"}
        if len(killable_returns) != 1:
            raise AssertionError("killable body lacks one exact typed source CALL")
        for case in results["cases"]:
            if "cancelled" in case and case["cancelled"]["cursor"] not in killable_returns:
                raise AssertionError("canceled root resumed a different source CALL continuation")
        coordinator = LearningCoordinator(exported.epoch, snapshot, LearningLimits(
            bounds["feedback_capacity"], bounds["cycle_capacity"], bounds["image_capacity"],
            bounds["image_capacity"], bounds["image_capacity"]))
        producers = ProducerCatalog(bounds["image_capacity"], ())
        old = exported.expected_old_image_identity
        cycle_number = 0

        def cycle(force=False, claim_only=False):
            nonlocal old, cycle_number
            cycle_number += 1
            if cycle_number > bounds["cycle_capacity"]:
                raise ValueError("explicit compiler cycle capacity ended")
            directory = args.output / f"cycle-{cycle_number}"
            directory.mkdir()
            builder = GNUImageBuilder(Toolchain(tools["cpp"], tools["as"], tools["ld"], tools["objcopy"],
                (str(args.repo / "include"),), (("PATH", "/usr/bin:/bin"), ("LC_ALL", "C")),
                str(directory / "build"), os.sysconf("SC_PAGE_SIZE")), BuildLimits(
                bounds["build_source_bytes"], bounds["build_metadata_bytes"], bounds["build_code_bytes"],
                bounds["build_flat_bytes"], bounds["build_manifest_bytes"], args.deadline))
            session = FeedbackSession(transport, coordinator, producers, SessionConfig(
                exported.slot_identity, old, 0x1000 + cycle_number, bounds["claim_capacity"], roots[0],
                DiscoveryLimits(*(bounds[key] for key in ("decode_sites", "decode_window_bytes", "cfg_work_steps", "direct_call_edges"))),
                EntryMetadata("kd_fixture_entry", tuple(sorted({call["site"] + call["length"] for call in calls if "operation" in call})), gs),
                CodegenLimits(bounds["lowered_sites"], bounds["lowered_text_bytes"], bounds["runtime_block_visits"])), builder)
            session.advance(); session.advance()
            if session.phase is not SessionPhase.BUILD_START:
                raise AssertionError("claim did not reach pre-build state")
            durable(directory / "claim.bin", session.raw_reply)
            merged = any(state.recorded.merge is MergeDisposition.MERGED for state in coordinator.facts()
                         if not state.acknowledgment_identities)
            if claim_only or not force and not merged:
                session.finish_pending()
            result = drive(session)
            if result.candidate is not None:
                artifact = result.candidate.artifact
                durable(directory / "image.S", artifact.assembly.encode())
                durable(directory / "metadata.c", artifact.c_metadata.encode())
                durable(directory / "manifest.json", artifact.manifest_json.encode())
                durable(directory / "commit.bin", result.raw_commit)
                durable(directory / "ack.bin", result.raw_ack)
                old = token_word(result.candidate.binding.image_identity)
            results.setdefault("cycles", []).append({"number": cycle_number, "image": old,
                "published": result.publication is not None,
                "acknowledged": len(result.acknowledgment.keys) if result.acknowledgment else 0})
            return result

        def proxy_scene(kill_candidate, name):
            begin = len(observe())
            spawn(H, 2); ioctl(GO, H)
            wait(lambda value: bool(value["writer"]), "writer holder")
            spawn(C, 0 if kill_candidate else 1); ioctl(GO, C); ce = enqueue(C, begin)
            spawn(W, 1, True); ioctl(GO, W); we = enqueue(W, begin)
            if kill_candidate:
                spawn(D, 1); ioctl(GO, D); de = enqueue(D, begin)
                if de["related"] != we["node"]:
                    raise AssertionError("D was not the actual W successor")
            if we["related"] != ce["node"]:
                raise AssertionError("W was not the actual C successor")
            ioctl(RELEASE, H); joined(H)
            entered = wait(lambda value: value["roles"][W]["helper_entered"], "W native completion handback")
            wt, ct = entered["roles"][W]["task"], entered["roles"][C]["task"]
            grant = matching("GRANT", begin, origin=wt)
            if (entered["roles"][C]["state"] == entered["roles"][W]["state"]
                    or not entered["roles"][C]["regs"] or not entered["roles"][W]["regs"]
                    or entered["roles"][C]["regs"] == entered["roles"][W]["regs"]):
                raise AssertionError("C and W do not have distinct original canonical storage")
            if len(grant) != 1 or grant[0]["owner_task"] != ct or not matching("JIT_ENTER", begin, node=grant[0]["node"], task=ct, image=old, state=entered["roles"][W]["state"]):
                raise AssertionError("C did not actually borrow W through the fixed generated image")
            if kill_candidate:
                kill(C)
                pending = wait(lambda value: value["roles"][C]["admission"] == 2, "C cancellation while W is live")
                if pending["roles"][C]["done"] or pending["roles"][D]["effects"] or matching("PHYSICAL_END", begin, owner=grant[0]["owner"]):
                    raise AssertionError("C error or next service preceded current W physical completion")
            ioctl(RELEASE, W); joined(W)
            joined(C, killed=kill_candidate)
            if kill_candidate:
                joined(D)
            final = reset()
            wg = success(W, begin, final)
            if final["roles"][W]["helper_returned"] != 1:
                raise AssertionError("native completion helper ran more than once or did not return")
            writer_span = exported.snapshot.regions[1]
            return_ip = final["roles"][W]["helper_return_ip"]
            actual_calls = [call for call in calls if writer_span.start <= call["site"] < writer_span.end
                            and call["site"] + call["length"] == return_ip]
            forwards = matching("FORWARD", begin, node=wg["node"], state=wg["state"],
                                image=old, related=final["native_helper"])
            value = {"w_grant": wg, "fixed_image": old, "native_helper_call": actual_calls,
                     "native_helper_forwards": forwards}
            if len(actual_calls) != 1:
                raise AssertionError("native helper did not receive an actual retained source CALL word")
            if kill_candidate:
                if (len(forwards) != 1 or forwards[0]["phase"] not in (1, 2, 4)
                        or (forwards[0]["phase"] == 1 and forwards[0]["cursor"] != forwards[0]["ip"])
                        or (forwards[0]["phase"] in (2, 4) and forwards[0]["cursor"] != final["native_helper"])
                        or signed(forwards[0]["result"])):
                    raise AssertionError("fixed generated image did not hand back this actual helper CALL")
            if kill_candidate:
                value.update(cancelled(C, begin, final))
                physical = matching("PHYSICAL_END", begin, owner=wg["owner"])
                if len(physical) != 1 or physical[0]["index"] >= value["cancelled"]["index"]:
                    raise AssertionError("C EINTR preceded actual W physical ACK")
                if len(matching("ENQUEUE", begin, task=ct)) != 1:
                    raise AssertionError("canceled C requeued")
                dg = success(D, begin, final)
                if dg["owner_task"] == ct:
                    raise AssertionError("canceled C continued to serve D")
                value["d_grant"] = dg
            else:
                value["c_grant"] = success(C, begin, final)
            return save_case(name, begin, final, **value)

        cycle(force=True)
        for number in range(bounds["learning_passes"]):
            training = proxy_scene(False, f"learning-{number}")
            learned = cycle()
            ordinary = [state for state in coordinator.facts() if state.recorded.feedback.observation is not None]
            if learned.publication is None and ordinary and all(state.acknowledgment_identities for state in ordinary):
                if len(training["native_helper_forwards"]) != 1:
                    raise AssertionError("learning stopped before the native completion frontier")
                break
        else:
            raise AssertionError("finite learning passes did not establish ordinary-edge ACK")
        fixed = old
        baseline = set(coordinator.pending_keys())
        results["fixed_image"] = fixed

        begin = len(observe())
        spawn(R, 3); ioctl(GO, R)
        wait(lambda value: value["readers"] == 1, "remote scene reader")
        spawn(H, 4); ioctl(GO, H)
        wait(lambda value: value["writer_pending"], "native H ungranted head")
        spawn(C, 1); ioctl(GO, C); ce = enqueue(C, begin)
        spawn(W, 0); ioctl(GO, W); we = enqueue(W, begin)
        if we["related"] != ce["node"]:
            raise AssertionError("remote W lacks actual C predecessor")
        kill(H); joined(H, killed=True)
        remote = wait(lambda value: value["readers"] == 1 and value["writer_pending"] and
                      value["roles"][W]["selection"] == 3 and value["roles"][W]["cancel_waiter"] == value["roles"][C]["task"],
                      "root W registered foreign physical wait")
        kill(W); exited = joined(W, killed=True)
        if status()["readers"] != 1:
            raise AssertionError("remote cancellation needed the original reader release")
        ioctl(RELEASE, R); joined(R); joined(C)
        final = reset()
        remote_proof = cancelled(W, begin, final)
        if remote_proof["cancelled"]["cursor"] not in killable_returns:
            raise AssertionError("remote cancel changed the original source continuation")
        save_case("origin-signal-wakes-foreign-c", begin, final, registered_foreign_wait=remote,
                  actual_exit=exited, **remote_proof)
        proxy_scene(True, "candidate-cancel-drains-current-w")
        final_claim = cycle(claim_only=True)
        if old != fixed or final_claim.publication is not None or set(coordinator.pending_keys()) != baseline:
            raise AssertionError("fixed-image checks added an unlearned fact or replaced the image")
        results["fixed_claim_no_new_facts"] = True
        results["pending_before_shutdown"] = len(coordinator.pending_keys())
        archive_config = ArchiveConfig(
            0x2000, bounds["claim_capacity"], str(args.output / "shutdown-archive.json"), bounds["archive_bytes"], 0o600,
            (("scope", "private-managed-killable-mechanism"), ("module_sha256", results["module_sha256"])))
        archive = drive(ShutdownSession(transport, coordinator, producers, archive_config))
        results["archive_sha256"] = archive.archive.identity.hex()
        results["settled_keys"] = len(archive.settlement.keys)
        results["facts"] = [{"record": state.recorded.fact.record_identity.hex(), "incarnation": state.recorded.fact.incarnation,
            "source_ip": state.recorded.fact.exit.source_ip, "target": state.recorded.fact.exit.target,
            "phase": state.recorded.fact.exit.phase, "acknowledged": bool(state.acknowledgment_identities)} for state in coordinator.facts()]
        transport.close(); transport = None
        ioctl(RETIRE)
        final = status()
        if not final["retired"] or final["native_scopes"] or not final["pool_idle"]:
            raise AssertionError("ordinary runtime/provider/binding retirement is incomplete")
        observe()
        durable(args.output / "observations-final.bin", header + bytes(raw))
        document(args.output / "observations-final.json", {"fields": FIELDS, "kinds": KINDS, "records": rows})
        results["final"] = final
        os.close(event_fd); event_fd = -1
        os.close(ctl); ctl = -1
        command([tools["rmmod"], NAME], args.deadline)
        results["status"] = "managed_killable_mechanism_pass"
        document(args.output / "result.json", results)
    except BaseException as error:
        results["status"] = "failed_retained"
        results["error"] = repr(error)
        results["controller_pid"] = os.getpid()
        results["live_children"] = children
        try:
            if event_fd >= 0:
                try:
                    observe()
                except BaseException as observation_error:
                    results["observation_error"] = repr(observation_error)
                    actual_header = pread_exact(40, 0)
                    durable(args.output / "observed-failure-header.bin", actual_header)
                durable(args.output / "observations-failure.bin", header + bytes(raw))
            document(args.output / "result.json", results)
        except BaseException as retention_error:
            results["retention_error"] = repr(retention_error)
            print(json.dumps({"status": "failed_retained", "retention_error": repr(retention_error),
                              "controller_pid": os.getpid()}), flush=True)
        print(json.dumps({"status": "failed_retained", "controller_pid": os.getpid(), "error": repr(error)}), flush=True)
        # Only a later explicitly reviewed recovery may reconcile these actors.
        # Retain original fd/flight/ledger/owner objects; timeout is not drain.
        while True:
            signal.pause()


if __name__ == "__main__":
    main()
