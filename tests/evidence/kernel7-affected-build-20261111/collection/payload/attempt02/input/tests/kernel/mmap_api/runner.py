#!/usr/bin/env python3
"""VM-only controller for the optional ABI2 real mmap/munmap source profile.

--config-json supplies paths, sha256, tools, tool_sha256, bounds, workload,
release, boot_id, repo_head, recovery_policy and contracts. Paths are absolute repo, client,
provider_module, jit_config, kernel_elf, kernel_config, gs_proof, recovery,
source_state, source_manifest and
fresh output. Every input file/tool has its exact SHA256. Workload supplies
threads, iterations, deadline_ms, phase_timeout_ms and rounds (at least two).
The source-host state contains source_git_head/git_status/files and its manifest maps names
to {bytes,sha256}. Recovery policy supplies hostname/pid/exe/image_paths/tag,
maximum_age_seconds and host/root/output floor bytes. The pinned actual host
receipt uses utc, hmp and three images with open_fds/realpath/host_available.
Contracts are immutable_text, auxiliary_context, same_mm, no_external_users,
ordinary_task_context, delayed_cancel and recovery_snapshot, all explicitly true.
No contract flag or receipt hash establishes the underlying external exclusion.

This composes the existing fd workflow, cumulative learning and GNU image
builder. Only the client performs MM syscalls. Publication and JIT_ENTER alone
never establish a returned MM body. Failure retains the original child, fds,
session/producer mappings and source observations for explicit reconciliation.
Writing/importing this module performs no workload or provider operation.
"""

import argparse
import datetime
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import sys
import time


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
HOST_BOUNDS = ("input_bytes", "stdio_bytes", "json_line_bytes", "command_bytes", "event_bytes",
               "wire_log_bytes", "archive_bytes", "source_regions", "source_boundaries", "source_bytes",
               "decode_sites", "decode_window_bytes", "cfg_work_steps", "direct_call_edges",
               "lowered_sites", "lowered_text_bytes", "runtime_block_visits", "build_source_bytes",
               "build_elf_bytes", "build_code_bytes", "build_flat_bytes", "build_diagnostic_bytes",
               "wire_rows", "wire_version_bytes", "wire_symbol_bytes", "wire_artifact_bytes", "recovery_bytes")
TOOLS = ("cpp", "as", "ld", "objcopy", "objdump", "insmod", "rmmod", "dmesg")
CONTRACTS = ("immutable_text", "auxiliary_context", "same_mm", "no_external_users",
             "ordinary_task_context", "delayed_cancel", "recovery_snapshot")
CONFIG_WORDS = ("native_capacity", "event_capacity", "metadata_capacity", "source_byte_capacity",
                "source_regions", "source_region_count", "source_version", "source_version_bytes",
                "current_task_gs_offset", "configuration0", "configuration1", "configuration2", "configuration3",
                "load0", "load1", "load2", "load3", "feedback_capacity", "cycle_capacity", "image_capacity",
                "claim_capacity", "code_capacity", "artifact_capacity", "flat_capacity", "entry_capacity",
                "source_capacity", "observation_capacity", "frame_capacity", "request_capacity",
                "auxiliary_bytes", "required_control_bytes", "proxy_limit")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def durable(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def document(path, value):
    durable(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def bounded(path, limit):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds its explicit byte bound: " + str(path))
    return data


class ClientStream:
    """Drain bounded child output without terminating an outstanding owner."""

    def __init__(self, child, directory, total_limit, line_limit):
        self.child, self.directory = child, directory
        self.total_limit, self.line_limit = total_limit, line_limit
        self.total, self.pending, self.messages = 0, bytearray(), []
        self.selector = selectors.DefaultSelector()
        self.logs = {}
        for name in ("stdout", "stderr"):
            stream = getattr(child, name)
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)
            self.logs[name] = (directory / ("client." + name)).open("xb")

    def pump(self, seconds):
        for key, _ in self.selector.select(seconds):
            data = os.read(key.fileobj.fileno(), min(4096, self.total_limit - self.total + 1))
            if not data:
                self.selector.unregister(key.fileobj)
                continue
            allowed = data[:self.total_limit - self.total]
            output = self.logs[key.data]
            output.write(allowed)
            output.flush()
            os.fsync(output.fileno())
            self.total += len(allowed)
            if len(allowed) != len(data):
                raise ValueError("child output exceeded explicit receipt capacity; child retained")
            if key.data == "stdout":
                self.pending.extend(data)
                while b"\n" in self.pending:
                    line, _, remainder = self.pending.partition(b"\n")
                    self.pending = bytearray(remainder)
                    if len(line) > self.line_limit:
                        raise ValueError("client JSON line exceeds explicit byte bound")
                    if line:
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("client stdout line is not an object")
                        self.messages.append(value)
                if len(self.pending) > self.line_limit:
                    raise ValueError("client partial JSON exceeds explicit byte bound")

    def phase(self, name, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if self.messages:
                value = self.messages.pop(0)
                if value.get("phase") != name:
                    raise ValueError("unexpected client phase: " + repr(value))
                return value
            if self.child.poll() is not None and not self.selector.get_map():
                raise RuntimeError("client ended before phase " + name)
            if time.monotonic() >= deadline:
                raise TimeoutError("client phase " + name + "; original owner/fds remain retained")
            self.pump(min(0.2, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-json", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(bounded(args.config_json, 1024 * 1024))
    paths = {name: Path(value) for name, value in config["paths"].items()}
    required_paths = {"repo", "client", "provider_module", "jit_config", "kernel_elf", "kernel_config",
                      "gs_proof", "recovery", "source_state", "source_manifest", "output"}
    if set(paths) != required_paths or any(not path.is_absolute() or path.resolve() != path for path in paths.values()):
        raise ValueError("exact absolute canonical paths are required")
    if paths["output"].is_relative_to(paths["repo"]):
        raise ValueError("output must be outside the immutable exported source")
    bounds, workload = config["bounds"], config["workload"]
    if set(bounds) != set(HOST_BOUNDS) or any(type(n) is not int or n <= 0 for n in bounds.values()):
        raise ValueError("all finite host capacities must be explicit positive integers")
    if set(workload) != {"threads", "iterations", "deadline_ms", "phase_timeout_ms", "rounds"} or any(
            type(n) is not int or not 0 < n < 1 << 32 for n in workload.values()) or workload["rounds"] < 2:
        raise ValueError("explicit finite workload and at least two rounds are required")
    if set(config["contracts"]) != set(CONTRACTS) or any(config["contracts"][key] is not True for key in CONTRACTS):
        raise ValueError("all declared source/context/external recovery contracts are required")
    seconds = workload["phase_timeout_ms"] / 1000
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("finite phase duration required")
    if os.geteuid() or os.uname().machine != "x86_64" or os.uname().release != config["release"]:
        raise ValueError("the exact designated root Linux x86_64 VM is required")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if boot != config["boot_id"] or int(Path("/proc/sys/kernel/tainted").read_text()) != 0:
        raise ValueError("fresh exact boot with taint0 is required")
    file_names = required_paths - {"repo", "output"}
    if set(config["sha256"]) != file_names or any(digest(paths[key]) != config["sha256"][key] for key in file_names):
        raise ValueError("pinned input file differs")
    source_state = json.loads(bounded(paths["source_state"], bounds["input_bytes"]))
    source_manifest = json.loads(bounded(paths["source_manifest"], bounds["input_bytes"]))
    if (source_state["source_git_head"] != config["repo_head"] or source_state["files"] != len(source_manifest) or
            source_state["git_status"] != ""):
        raise ValueError("source-host export commit/count differs from the pinned config")
    # Source inspection/Git remains on the source host. The VM consumes its
    # pinned export state and exact manifest, with no invented .git directory.
    repo_files = {name: row["sha256"] for name, row in source_manifest.items()}
    required_repo_files = {"tests/kernel/mmap_api/runner.py", "tests/kernel/run_runtime_fixture.py"}
    required_repo_files.update(str(path.relative_to(paths["repo"])) for directory in ("disassem", "include")
                               for path in (paths["repo"] / directory).rglob("*") if path.is_file()
                               and path.suffix in (".py", ".h", ".S", ".inc"))
    if not isinstance(repo_files, dict) or not required_repo_files <= set(repo_files):
        raise ValueError("pin every compiler/include dependency and both source controllers")
    for name, expected in repo_files.items():
        path = paths["repo"] / name
        if (path.resolve() != path or not path.is_relative_to(paths["repo"]) or digest(path) != expected or
                path.stat().st_size != source_manifest[name]["bytes"]):
            raise ValueError("frozen repository input differs: " + name)
    additional = {str(paths[key].relative_to(paths["repo"])) for key in ("source_state", "source_manifest")
                  if paths[key].is_relative_to(paths["repo"])}
    if {str(path.relative_to(paths["repo"])) for path in paths["repo"].rglob("*") if path.is_file()} != set(repo_files) | additional:
        raise ValueError("exported snapshot contains an unknown or missing file")
    tools = config["tools"]
    if set(tools) != set(TOOLS) or set(config["tool_sha256"]) != set(TOOLS):
        raise ValueError("all explicit GNU and module tools are required")
    for key, value in tools.items():
        if not Path(value).is_absolute() or digest(Path(value)) != config["tool_sha256"][key]:
            raise ValueError("exact tool identity differs: " + key)
    binary = bounded(paths["jit_config"], bounds["input_bytes"])
    if len(binary) < 272:
        raise ValueError("ABI2 config header is truncated")
    words = struct.unpack_from("<34Q", binary)
    native = dict(zip(CONFIG_WORDS, words[2:]))
    region_end = 272 + 16 * native["source_region_count"]
    if (words[:2] != (2, 511) or native["source_regions"] or native["source_version"] or
            not native["source_region_count"] or region_end + native["source_version_bytes"] != len(binary)):
        raise ValueError("config ABI/contracts/zero-pointer/exact extents differ")
    regions = tuple(struct.unpack_from("<2Q", binary, offset) for offset in range(272, region_end, 16))
    version = binary[region_end:]
    version.decode("utf-8", errors="strict")
    if (len(regions) > bounds["source_regions"] or not version or
            sum(length for _, length in regions) > bounds["source_bytes"] or
            native["event_capacity"] * 160 + 40 > bounds["event_bytes"] or
            native["image_capacity"] < workload["rounds"] - 1 or
            native["cycle_capacity"] < workload["rounds"] + 1):
        raise ValueError("explicit capacities do not cover this finite round plan")
    proof = json.loads(bounded(paths["gs_proof"], bounds["input_bytes"]))
    if (proof.get("verified_for_running_kernel") is not True or proof.get("boot_id") != boot or
            proof.get("kernel_release") != config["release"] or proof.get("gs_symbol") != "current_task" or
            proof.get("kernel_elf_sha256") != config["sha256"]["kernel_elf"] or
            proof.get("kernel_config_sha256") != config["sha256"]["kernel_config"] or
            int(str(proof["current_task_gs_offset"]), 0) != native["current_task_gs_offset"]):
        raise ValueError("actual boot/kernel/configuration/GS proof differs")
    policy = config["recovery_policy"]
    if (set(policy) != {"hostname", "pid", "exe", "image_paths", "tag", "maximum_age_seconds", "host_floor_bytes",
                       "root_floor_bytes", "output_floor_bytes"} or
            any(type(policy[key]) is not int or policy[key] <= 0 for key in (
                "pid", "maximum_age_seconds", "host_floor_bytes", "root_floor_bytes", "output_floor_bytes")) or
            len(policy["image_paths"]) != 3 or len(set(policy["image_paths"])) != 3 or not policy["tag"]):
        raise ValueError("explicit three-image recovery/age/headroom policy required")

    def recovery():
        if digest(paths["recovery"]) != config["sha256"]["recovery"]:
            raise ValueError("recovery receipt changed")
        actual = json.loads(bounded(paths["recovery"], bounds["input_bytes"]))
        captured = datetime.datetime.fromisoformat(actual["utc"])
        if captured.tzinfo is None or not 0 <= time.time() - captured.timestamp() <= policy["maximum_age_seconds"]:
            raise ValueError("recovery receipt is stale or has no actual timezone")
        if any(actual[key] != policy[key] for key in ("hostname", "pid", "exe")):
            raise ValueError("recovery host/QEMU identity differs")
        images = actual["images"]
        if (len(images) != 3 or {row["path"] for row in images} != set(policy["image_paths"]) or
                any(not row["open_fds"] or row["path"] != row["realpath"] or
                    row["host_available"] < policy["host_floor_bytes"] for row in images)):
            raise ValueError("actual three attached image references/host headroom differ")
        records = actual["hmp"]
        commands = {row["command"]: row["output"] for row in records}
        if len(commands) != len(records) or "VM status: running" not in commands.get("info status", ""):
            raise ValueError("actual recovery monitor status differs")
        listing = commands.get("info snapshots", "")
        if "List of snapshots present on all disks:" not in listing:
            raise ValueError("actual complete recovery list missing")
        common = listing.split("List of snapshots present on all disks:", 1)[1].split("List of partial", 1)[0]
        if not any(policy["tag"] in line.split() for line in common.splitlines()):
            raise ValueError("the exact recovery tag is absent from the all-disks list")
        def free(path):
            stat = os.statvfs(path)
            return stat.f_bavail * stat.f_frsize
        if free(Path("/")) < policy["root_floor_bytes"] or free(paths["output"].parent) < policy["output_floor_bytes"]:
            raise ValueError("actual guest root/output headroom below caller bounds")
        return {"captured_unix": captured.timestamp(), "receipt_sha256": config["sha256"]["recovery"],
                "complete_tag": policy["tag"], "images": images}

    recovery_verified = recovery()
    output = paths["output"]
    output.mkdir(parents=False, exist_ok=False)
    durable(output / "config.json", bounded(args.config_json, bounds["input_bytes"]))
    for key in ("jit_config", "gs_proof", "recovery"):
        durable(output / (key + ".input"), bounded(paths[key], bounds["input_bytes"]))
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(paths["repo"]), str(paths["repo"] / "tests/kernel")]
    from run_runtime_fixture import scan_operation_calls
    from disassem.archive import ArchiveConfig, ShutdownSession
    from disassem.compiler import DiscoveryLimits
    from disassem.image_builder import BuildLimits, GNUImageBuilder, Toolchain
    from disassem.learning import LearningCoordinator, LearningLimits, MergeDisposition
    from disassem.lowering import CodegenLimits, EntryMetadata
    from disassem.session import ChannelStatusError, FeedbackSession, FdTransport, ProducerCatalog, SessionConfig, SessionPhase, SourceExportSession
    from disassem.wire import SourceExportLimits, WireLimits, token_word
    result = {"status": "incomplete", "overall_pass": False, "scope": "real_syscalls_optional_source_prefix", "boot_id": boot,
              "release": config["release"], "controller_pid": os.getpid(), "config_sha256": digest(args.config_json),
              "identities": config["sha256"], "workload": workload, "rounds": [], "cycles": [],
              "meaningful_returned_mm_body": "not_established", "wire": {"attempts": 0, "reserved_bytes": 0}}
    result["recovery_verified"] = recovery_verified
    document(output / "identity.json", result)
    wire = output / "wire"
    wire.mkdir()
    transport = child = client = None
    sessions, event_rows, roots = [], [], set()
    event_prefix = b""
    command_number = signal_number = snapshot_number = 0

    class RecordedTransport(FdTransport):
        def _ioctl(self, flight):
            amount = len(flight.request) + len(flight.output_buffer) + len(flight.header) + 4096
            if amount > bounds["wire_log_bytes"] - result["wire"]["reserved_bytes"]:
                raise ValueError("wire receipt capacity refuses dispatch")
            result["wire"]["reserved_bytes"] += amount
            result["wire"]["attempts"] += 1
            directory = wire / f"attempt-{result['wire']['attempts']:08d}"
            directory.mkdir()
            durable(directory / "request.bin", flight.request)
            metadata = {"operation": int(flight.operation), "sequence": flight.sequence,
                        "request_bytes": len(flight.request), "output_capacity": len(flight.output_buffer)}
            document(directory / "request.json", metadata)
            try:
                reply = super()._ioctl(flight)
            except BaseException as error:
                durable(directory / "observed-envelope.bin", bytes(flight.header))
                durable(directory / "observed-output-capacity.bin", bytes(flight.output_buffer))
                document(directory / "error.json", {"error": repr(error)[:1024], "completed_response": False})
                raise
            durable(directory / "returned-envelope.bin", bytes(flight.header))
            durable(directory / "reply.bin", reply.payload)
            document(directory / "result.json", {"status": reply.status, "sequence": reply.sequence,
                                                "reply_bytes": len(reply.payload), "completed_response": True})
            return reply

    def command(argv, name=None):
        nonlocal command_number
        command_number += 1
        directory = output / f"command-{command_number:04d}"
        directory.mkdir()
        document(directory / "argv.json", argv)
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        log = (directory / "stdout.log").open("xb")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline, total = time.monotonic() + seconds, 0
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise TimeoutError("command outstanding; child retained pid=" + str(process.pid))
                for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                    data = os.read(key.fileobj.fileno(), min(4096, bounds["command_bytes"] - total + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    allowed = data[:bounds["command_bytes"] - total]
                    log.write(allowed); log.flush(); os.fsync(log.fileno())
                    total += len(allowed)
                    if len(allowed) != len(data):
                        raise ValueError("command output bound; process retained pid=" + str(process.pid))
            remaining = max(0.001, deadline - time.monotonic())
            returncode = process.wait(timeout=remaining)
            document(directory / "result.json", {"returncode": returncode, "pid": process.pid})
            if returncode:
                raise RuntimeError("command returned " + str(returncode))
            if name is not None:
                document(output / (name + ".json"), {"directory": str(directory), "returncode": returncode,
                                                    "stdout_sha256": digest(directory / "stdout.log")})
        except BaseException:
            # Keep the process and pipe reachable when the controller retains.
            result.setdefault("retained_commands", []).append({"pid": process.pid, "argv": argv})
            sessions.append((process, selector, log))
            document(directory / "retained.json", {"pid": process.pid, "actual_returncode": process.poll(),
                                                   "outstanding": process.poll() is None})
            raise
        log.close(); selector.close(); process.stdout.close()

    def phase(name):
        value = client.phase(name, seconds)
        document(output / f"phase-{len(result.setdefault('phases', [])):04d}.json", value)
        result["phases"].append(value)
        if (value.get("schema") != 2 or value.get("pid") != child.pid or
                value.get("requested_rounds") != workload["rounds"] or
                value.get("phase_timeout_ms") != workload["phase_timeout_ms"] or
                value.get("cleanup_failed") is not False):
            raise ValueError("actual client phase identity/bounds/failure differs")
        return value

    def profile(value, expected, baseline=None):
        observed = value["profile"]
        gate = observed["native"]
        if (observed["state"] != expected or observed["event_overflow"] or gate["count_overflow"] or
                observed["event_capacity"] != native["event_capacity"] or
                observed["source_regions"] != len(regions) or observed["source_bytes"] != sum(n for _, n in regions) or
                gate["native_capacity"] != native["native_capacity"] or gate["owner_pid"] != child.pid or
                not gate["owner_is_current"] or not gate["source_calls"] or not observed["killable_source_calls"]):
            raise ValueError("actual profile/gate identity or explicit capacities differ")
        if baseline is not None:
            for key in ("mm_identity", "object_identity", "gate_identity", "owner_pid", "owner_tgid"):
                if gate[key] != baseline["native"][key]:
                    raise ValueError("selected object identity changed: " + key)
            for key in ("source_identity", "runtime_identity", "origin_gs"):
                if expected != 5 and observed[key] != baseline[key]:
                    raise ValueError("retained source/runtime identity changed: " + key)
        return observed

    def round_effects(value, number):
        actual = value["workload"]
        count, iterations, page = workload["threads"], workload["iterations"], os.sysconf("SC_PAGE_SIZE")
        if (value["round"] != number or value["completed_rounds"] != number or
                value.get("next_round_allowed") is not (number < workload["rounds"]) or
                actual.get("status") != "syscall_completion_pass" or actual.get("overall_pass") is not True or
                actual["threads"] != count or actual["created_threads"] != count or
                actual["iterations_per_thread"] != iterations or actual["deadline_ms"] != workload["deadline_ms"] or
                actual["page_bytes"] != page or actual["mapping_pages"] != 2 or actual["arena_reservations"] != 1 or
                actual["arena_bytes"] != count * page * 4 or actual["arena_cleanup_errno"] or
                actual["setup_error"] != "none" or actual["setup_errno"] or actual["worker_errors"] or
                actual["deadline_exceeded"] or actual["completed_iterations"] != count * iterations or
                len(actual["workers"]) != count):
            raise AssertionError("joined/unmapped syscall round did not satisfy exact effects")
        for index, worker in enumerate(actual["workers"]):
            expected = {"id": index, "completed": iterations, "mmap_attempts": 3 * iterations,
                "mmap_successes": 3 * iterations, "munmap_attempts": 2 * iterations,
                "munmap_successes": 2 * iterations, "mincore_attempts": 4 * iterations,
                "unmapped_page_checks": 4 * iterations, "reuse_successes": iterations,
                "fresh_zero_bytes": 4 * page * iterations, "written_bytes": 4 * page * iterations,
                "readback_bytes": 4 * page * iterations,
                "slot_address": actual["arena_address"] + index * 4 * page + page}
            if (any(worker[key] != wanted for key, wanted in expected.items()) or worker["tid"] <= 0 or
                    worker["deadline_reached"] or worker["error"] != "none" or worker["errno"]):
                raise AssertionError("worker syscall/byte/reuse observations differ from exact completed work")
        if len({worker["tid"] for worker in actual["workers"]}) != count:
            raise AssertionError("worker task identities repeat within a joined round")

    def joined_execution(images, gate):
        evidence = []
        for entered in event_rows:
            if entered["kind"] != KINDS["JIT_ENTER"] or entered["image"] not in images:
                continue
            same = lambda row: all(row[key] == entered[key] for key in ("state", "node", "acquisition"))
            previous = event_rows[:entered["index"]]
            reserves = [row for row in previous if row["kind"] == KINDS["SLOT_RESERVE"] and same(row)]
            if not reserves:
                continue
            reserve = reserves[-1]
            interval = event_rows[reserve["index"] + 1:entered["index"]]
            grants = [row for row in interval if row["kind"] == KINDS["GRANT"] and same(row) and row["object"] == gate]
            prepared = [row for row in interval if row["kind"] == KINDS["FRAME_PREPARE"] and same(row)
                        and row["origin"] == entered["origin"] and not row["parent"]]
            if (len(grants) != 1 or len(prepared) != 1 or entered["task"] == entered["origin"] or
                    grants[0]["owner_task"] != entered["task"] or grants[0]["origin"] != entered["origin"]):
                continue
            end = next((row["index"] for row in event_rows[entered["index"] + 1:]
                        if same(row) and row["kind"] in (KINDS["SLOT_RESERVE"], KINDS["SLOT_FREE"])), len(event_rows))
            scope = event_rows[entered["index"] + 1:end]
            next_entry = next((row["index"] for row in scope if same(row) and row["kind"] == KINDS["JIT_ENTER"]), end)
            exits = [row for row in scope if row["index"] < next_entry and row["kind"] == KINDS["JIT_EXIT"] and same(row)
                     and row["image"] == entered["image"] and row["task"] == entered["task"]
                     and row["result"] in (1, 2, 3, 4, 5)]
            # No positive instruction-entry claim from an entry lookup failure.
            if not exits:
                continue
            operations = [row for row in scope if same(row) and row["kind"] == KINDS["JIT_OPERATION"]
                          and row["result"] in (7, 9)]
            done = [row for row in scope if same(row) and row["kind"] == KINDS["EPISODE_DONE"]
                    and row["result"] in (3, 5)]
            frees = [row for row in event_rows[end:end + 1] if same(row) and row["kind"] == KINDS["SLOT_FREE"]
                     and row["related"] == reserve["related"] and row["owner"] == reserve["owner"]
                     and row["parent"] == reserve["parent"]]
            evidence.append({"reserve": reserve, "grant": grants[0], "enter": entered,
                             "first_exit": exits[0], "typed_unlocks": operations, "episode_completions": done,
                             "final_free": frees, "source_progress_to_another_ip": exits[0]["ip"] != entered["cursor"],
                             "generated_source_instruction_count": "not_measured",
                             "meaningful_mm_body_completion": "not_established"})
        return evidence

    def advance(sig, label):
        nonlocal signal_number
        if child.poll() is not None:
            raise RuntimeError("client already ended before " + label)
        signal_number += 1
        directory = output / f"signal-{signal_number:04d}"
        directory.mkdir()
        document(directory / "intent.json", {"pid": child.pid, "signal": sig, "phase": label,
                                             "time": time.time(), "boot_id": boot})
        os.kill(child.pid, sig)
        document(directory / "sent.json", {"pid": child.pid, "signal": sig, "sent": True})

    def observe():
        nonlocal event_prefix, snapshot_number
        snapshot_number += 1
        # ABI2 freezes a prefix per open; never reuse an old event fd.
        fd = os.open("/dev/kd_mmap_api_events", os.O_RDONLY | os.O_CLOEXEC)
        try:
            def exact(length, offset):
                chunks = bytearray()
                while len(chunks) < length:
                    data = os.pread(fd, min(65536, length - len(chunks)), offset + len(chunks))
                    if not data:
                        raise ValueError("event prefix is truncated")
                    chunks.extend(data)
                return bytes(chunks)
            header = exact(40, 0)
            abi, words_per_row, capacity, count, overflow = struct.unpack("<5Q", header)
            if (abi != 1 or words_per_row != 20 or capacity != native["event_capacity"] or overflow or
                    count < len(event_rows) or count > capacity or 40 + count * 160 > bounds["event_bytes"]):
                raise ValueError("actual event ABI/capacity/monotonic prefix/overflow differs")
            data = exact(count * 160, 40)
            durable(output / f"events-{snapshot_number:04d}.bin", header + data)
            if not data.startswith(event_prefix):
                raise ValueError("previous immutable event prefix changed")
            for values in struct.iter_unpack("<20Q", data[len(event_prefix):]):
                event_rows.append({**dict(zip(FIELDS, values)), "index": len(event_rows)})
            event_prefix = data
        finally:
            os.close(fd)

    def drive(workflow, stop_phase=None):
        sessions.append(workflow)
        deadline = time.monotonic() + seconds
        while workflow.phase.value != "complete":
            if workflow.phase is stop_phase:
                return workflow
            if time.monotonic() >= deadline:
                raise TimeoutError("existing channel workflow incomplete; all controls retained")
            try:
                workflow.advance()
            except ChannelStatusError as error:
                if error.status not in (-errno.EBUSY, -errno.EAGAIN) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        return workflow.result

    def discover_roots(calls, gate):
        found = []
        by_return = {call["site"] + call["length"]: call for call in calls if call.get("operation") == "lock"}
        for row in event_rows:
            if (row["kind"] != KINDS["FORWARD"] or row["cursor"] not in by_return or
                    row["task"] != row["origin"] or row["parent"]):
                continue
            same = lambda item: all(item[key] == row[key] for key in ("state", "node", "acquisition", "origin"))
            reserves = [item for item in event_rows[:row["index"]] if item["kind"] == KINDS["SLOT_RESERVE"] and same(item)]
            if not reserves:
                continue
            opening = reserves[-1]
            # SLOT_RESERVE.parent is its claim token, not frame ancestry.
            if not opening["parent"] or opening["task"] != row["origin"]:
                continue
            lifetime = event_rows[opening["index"] + 1:row["index"]]
            grants = [item for item in lifetime if item["kind"] == KINDS["GRANT"] and same(item) and item["object"] == gate]
            prepared = [item for item in lifetime if item["kind"] == KINDS["FRAME_PREPARE"] and same(item)
                        and not item["parent"] and item["task"] == row["origin"]]
            disposition = row["result"] - (1 << 64) if row["result"] & (1 << 63) else row["result"]
            eligible_forward = ((not row["image"] and disposition == -errno.ENOENT) or
                                (row["image"] == old and old and disposition == -errno.EXDEV))
            if (len(grants) != 1 or len(prepared) != 1 or grants[0]["task"] != row["origin"] or
                    grants[0]["owner_task"] != row["origin"] or row["phase"] or row["flags"] or
                    row["ip"] or row["related"] or not eligible_forward or
                    any(item["kind"] in (KINDS["SLOT_FREE"], KINDS["JIT_ENTER"], KINDS["JIT_EXIT"], KINDS["JIT_OPERATION"])
                                       and same(item) for item in lifetime)):
                continue
            # No generated instruction executed in this frame before its first
            # forward. cursor is this acquisition's exact reached continuation.
            if row["cursor"] not in roots:
                roots.add(row["cursor"])
                found.append({"entry": row["cursor"], "call": by_return[row["cursor"]],
                              "reserve": opening, "grant": grants[0], "forward": row})
        return found

    try:
        module_name = paths["provider_module"].stem
        if (Path("/sys/module") / module_name).exists() or Path("/dev/kd_mmap_api").exists():
            raise ValueError("provider must start absent in the fresh caller-owned window")
        command([tools["dmesg"], "--raw"], "kernel-log-before")
        result["recovery_at_dispatch"] = recovery()
        command([tools["insmod"], str(paths["provider_module"]), "enable_jit_profile=1"])
        argv = [str(paths["client"]), "--threads", str(workload["threads"]), "--iterations", str(workload["iterations"]),
                "--deadline-ms", str(workload["deadline_ms"]), "--control-device", "/dev/kd_mmap_api", "--quiescent-mm",
                "--jit-config", str(paths["jit_config"]), "--jit-config-bytes", str(len(binary)),
                "--jit-phase-timeout-ms", str(workload["phase_timeout_ms"]), "--jit-rounds", str(workload["rounds"])]
        document(output / "client-argv.json", argv)
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        result["client_pid"] = child.pid
        document(output / "client-started.json", {"pid": child.pid, "boot_id": boot})
        client = ClientStream(child, output, bounds["stdio_bytes"], bounds["json_line_bytes"])
        ready = phase("jit_ready")
        initial = profile(ready, 2)
        if ready.get("round") != 0 or ready.get("completed_rounds") != 0 or ready.get("next_round_allowed") is not True:
            raise ValueError("client ready phase differs from fresh cold state")
        result["ready"] = ready
        limits = WireLimits(native["frame_capacity"], bounds["wire_rows"], bounds["wire_version_bytes"],
                            bounds["wire_symbol_bytes"], bounds["wire_artifact_bytes"])
        transport = RecordedTransport.open("/dev/kd_mmap_jit", limits, bounds["recovery_bytes"])
        exported = drive(SourceExportSession(transport, SourceExportLimits(
            bounds["source_regions"], bounds["source_boundaries"], bounds["source_bytes"])))
        if (exported.epoch.version != version or exported.epoch.current_task_gs_offset != native["current_task_gs_offset"] or
                tuple((region.start, len(region.data)) for region in exported.snapshot.regions) != regions or
                exported.expected_old_image_identity):
            raise ValueError("source export differs from this fresh exact config")
        durable(output / "source-export.bin", exported.raw_reply)
        snapshot, _, calls, indirect = scan_operation_calls(exported, tools["objdump"], output, seconds)
        document(output / "source-metadata.json", {"epoch": exported.epoch.identity.hex(), "version_hex": version.hex(),
                 "configuration": exported.epoch.configuration_identity.hex(), "load": exported.epoch.load_identity.hex(),
                 "regions": [{"start": r.start, "length": len(r.data), "sha256": sha(r.data)} for r in snapshot.regions],
                 "calls": calls, "near_indirect_call_sites": indirect, "slot": exported.slot_identity})
        coordinator = LearningCoordinator(exported.epoch, snapshot, LearningLimits(
            native["feedback_capacity"], native["cycle_capacity"], native["image_capacity"],
            native["image_capacity"], native["image_capacity"]))
        producers = ProducerCatalog(native["image_capacity"], ())
        old, cycle_number = 0, 0

        def compile_cycle(force):
            nonlocal old, cycle_number
            cycle_number += 1
            if cycle_number > native["cycle_capacity"] or not roots:
                raise ValueError("finite cycle capacity or actual acquisition roots unavailable")
            directory = output / f"cycle-{cycle_number:04d}"
            directory.mkdir()
            builder = GNUImageBuilder(Toolchain(tools["cpp"], tools["as"], tools["ld"], tools["objcopy"],
                (str(paths["repo"] / "include"),), (("PATH", "/usr/bin:/bin"), ("LC_ALL", "C")),
                str(directory / "build"), os.sysconf("SC_PAGE_SIZE")), BuildLimits(
                bounds["build_source_bytes"], bounds["build_elf_bytes"], bounds["build_code_bytes"],
                bounds["build_flat_bytes"], bounds["build_diagnostic_bytes"], seconds))
            workflow = FeedbackSession(transport, coordinator, producers, SessionConfig(
                exported.slot_identity, old, 0x1000 + cycle_number, native["claim_capacity"], min(roots),
                DiscoveryLimits(*(bounds[key] for key in ("decode_sites", "decode_window_bytes", "cfg_work_steps", "direct_call_edges"))),
                EntryMetadata("kd_mm_entry", tuple(sorted(roots)), native["current_task_gs_offset"]),
                CodegenLimits(bounds["lowered_sites"], bounds["lowered_text_bytes"], bounds["runtime_block_visits"])), builder)
            sessions.append(workflow)
            drive(workflow, SessionPhase.BUILD_START)
            if workflow.phase is not SessionPhase.BUILD_START:
                raise ValueError("actual claim did not reach retained pre-build state")
            durable(directory / "claim.bin", workflow.raw_reply)
            merged = any(state.recorded.merge is MergeDisposition.MERGED and not state.acknowledgment_identities
                         for state in coordinator.facts())
            if not force and not merged:
                workflow.finish_pending()
            completed = drive(workflow)
            if completed.candidate:
                artifact = completed.candidate.artifact
                built = completed.built_image
                durable(directory / "machine-code.bin", built.machine_code)
                durable(directory / "flat-metadata.bin", built.flat_metadata)
                for index, tool in enumerate(built.tools):
                    durable(directory / f"gnu-{index:02d}.log", tool.diagnostics)
                    document(directory / f"gnu-{index:02d}.json", {"argv": tool.command, "returncode": tool.returncode,
                                                                 "diagnostic_sha256": sha(tool.diagnostics)})
                durable(directory / "image.S", artifact.assembly.encode())
                durable(directory / "metadata.c", artifact.c_metadata.encode())
                durable(directory / "manifest.json", artifact.manifest_json.encode())
                durable(directory / "commit.bin", completed.raw_commit)
                durable(directory / "ack.bin", completed.raw_ack)
                old = token_word(completed.candidate.binding.image_identity)
            result["cycles"].append({"cycle": cycle_number, "image": old, "roots": sorted(roots),
                "published": completed.publication is not None,
                "acknowledged": len(completed.acknowledgment.keys) if completed.acknowledgment else 0})

        for number in range(1, workload["rounds"] + 1):
            advance(signal.SIGUSR2, "round-" + str(number))
            finished = phase("jit_round_complete")
            round_effects(finished, number)
            current_profile = profile(finished, 2, initial)
            result["rounds"].append(finished)
            observe()
            # Client schema is checked before permitting another round below.
            fresh = discover_roots(calls, current_profile["native"]["gate_identity"])
            document(output / f"roots-{number:04d}.json", fresh)
            if number < workload["rounds"]:
                compile_cycle(bool(fresh) or not old)
        publications = {item["image"] for item in result["cycles"] if item["published"]}
        before_leave = joined_execution(publications, initial["native"]["gate_identity"])
        result["borrowed_jit_evidence_before_leave"] = before_leave
        if not any(item["source_progress_to_another_ip"] for item in before_leave):
            raise AssertionError("syscall rounds passed but a nonempty borrowed source prefix is unproved; owner retained")
        advance(signal.SIGUSR1, "leave-original-owner")
        left = phase("jit_owner_left")
        owner_left = profile(left, 3, initial)
        if (not owner_left["owner_left"] or owner_left["storage_identity"] or owner_left["roles"] & 16 or
                left["completed_rounds"] != workload["rounds"] or left["next_round_allowed"] or
                owner_left["native"]["owner_threads"] != 1):
            raise ValueError("original owner/storage retirement did not complete")
        result["owner_left"] = left
        archive = drive(ShutdownSession(transport, coordinator, producers, ArchiveConfig(
            0x1000 + native["cycle_capacity"], native["claim_capacity"], str(output / "shutdown-archive.json"),
            bounds["archive_bytes"], 0o600, (("boot_id", boot), ("kernel_elf", config["sha256"]["kernel_elf"]),
                                         ("runner_config", result["config_sha256"]))))
        result["archive_sha256"] = archive.archive.identity.hex()
        result["settled_keys"] = len(archive.settlement.keys)
        transport.close(); transport = None
        observe()
        # This fresh signal follows actual SHUTDOWN/archive/SETTLE/END+fdclose.
        advance(signal.SIGUSR1, "end-provider-after-host-closure")
        final = phase("jit_finished")
        retired = profile(final, 5, initial)
        if (final.get("status") != "syscall_completion_pass" or final.get("overall_pass") is not True or
                final.get("all_rounds_pass") is not True or final.get("kd_observations") != "raw_source_profile" or
                final["completed_rounds"] != workload["rounds"] or final["cleanup_required"] or final["cleanup_failed"] or
                any(final[key] for key in ("open_errno", "start_errno", "query_errno", "leave_errno", "end_errno", "close_errno", "phase_errno")) or
                not retired["owner_left"] or retired["roles"] or retired["source_identity"] or retired["runtime_identity"] or
                retired["storage_identity"] or retired["native"]["state"] != 2 or retired["native"]["cleanup_required"] or
                not retired["native"]["pool_idle"] or retired["native"]["gate_locked"] or retired["native"]["gate_contended"]):
            raise AssertionError("actual provider END/retirement or client syscall verdict failed")
        result["client_final"] = final
        deadline = time.monotonic() + seconds
        while child.poll() is None or client.selector.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError("client final exit outstanding; original process retained")
            client.pump(min(0.2, max(0, deadline - time.monotonic())))
        if child.returncode or client.messages or client.pending:
            raise RuntimeError("client actual return/output differs from final phase")
        result["client_returncode"] = child.returncode
        result["observation_count"] = len(event_rows)
        result["borrowed_jit_evidence"] = joined_execution(publications, initial["native"]["gate_identity"])
        result["syscall_pass"] = True
        result["borrowed_generated_entry_observed"] = bool(result["borrowed_jit_evidence"])
        result["borrowed_jit_prefix_observed"] = any(item["source_progress_to_another_ip"] for item in result["borrowed_jit_evidence"])
        document(output / "observations.json", {"fields": FIELDS, "kinds": KINDS, "records": event_rows})
        result["facts"] = [{"record": value.recorded.fact.record_identity.hex(),
            "incarnation": value.recorded.fact.incarnation, "producer": value.recorded.fact.producer_identity.hex(),
            "image": value.recorded.fact.image_identity.hex(), "source_ip": value.recorded.fact.exit.source_ip,
            "target": value.recorded.fact.exit.target, "cursor": value.recorded.fact.exit.cursor,
            "kind": value.recorded.fact.exit.kind, "detail": value.recorded.fact.exit.detail,
            "phase": value.recorded.fact.exit.phase, "entry_result": value.recorded.fact.entry_result,
            "classification": value.recorded.fact.classification.value,
            "merge": value.recorded.merge.value, "feedback_disposition": value.recorded.feedback.kind.value,
            "acknowledged": bool(value.acknowledgment_identities)}
            for value in coordinator.facts()]
        command([tools["rmmod"], module_name])
        if (Path("/sys/module") / module_name).exists() or Path("/dev/kd_mmap_api").exists():
            raise RuntimeError("ordinary provider unload did not complete")
        command([tools["dmesg"], "--raw"], "kernel-log-after")
        for key in file_names:
            if digest(paths[key]) != config["sha256"][key]:
                raise ValueError("input changed during the retained source interval: " + key)
        for name, expected in repo_files.items():
            if digest(paths["repo"] / name) != expected:
                raise ValueError("repository source changed during the interval: " + name)
        result["post_taint"] = int(Path("/proc/sys/kernel/tainted").read_text())
        result["post_boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if result["post_boot_id"] != boot or result["post_taint"] not in (4096, 12288):
            raise AssertionError("boot changed or unexpected kernel taint occurred")
        result["status"] = ("syscall_and_borrowed_jit_prefix_pass" if result["borrowed_jit_prefix_observed"] else
                            "syscall_pass_with_dispatch_only" if result["borrowed_generated_entry_observed"] else
                            "syscall_pass_without_borrowed_jit_evidence")
        result["overall_pass"] = result["borrowed_jit_prefix_observed"]
        document(output / "result.json", result)
        print(json.dumps({"status": result["status"], "output": str(output)}), flush=True)
        return 0 if result["borrowed_jit_prefix_observed"] else 1
    except BaseException as error:
        result["status"], result["error"] = "failed_retained", repr(error)
        result["client_pid"] = child.pid if child else None
        result["client_returncode"] = child.poll() if child else None
        result["pending_channel_sequence"] = transport.pending_sequence if transport else None
        try:
            if hasattr(error, "diagnostics"):
                durable(output / "build-failure.log", error.diagnostics)
            document(output / "result.json", result)
        except BaseException as retention_error:
            result["retention_error"] = repr(retention_error)
        try:
            print(json.dumps({"status": "failed_retained", "controller_pid": os.getpid(),
                              "client_pid": result["client_pid"], "error": repr(error),
                              "retention_error": result.get("retention_error")}), flush=True)
        except BaseException:
            pass
        # No automatic signal, replay, kill, close, unload or drain inference.
        # Original process/pipe/fd/session objects remain reachable here.
        while True:
            try:
                signal.pause()
            except BaseException:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
