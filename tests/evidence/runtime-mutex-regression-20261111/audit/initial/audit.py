#!/usr/bin/env python3
"""Read saved runtime events and receipts using the Python standard library.

Inputs are completed copies of the fixture's files. Output joins immutable
scalar identities within recorded request lifetimes. This program performs
file reads and writes its fresh audit directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

FIELDS = (
    "kind", "task", "state", "origin", "node", "acquisition", "parent",
    "owner", "owner_task", "object", "image", "ip", "cursor", "related",
    "phase", "result", "flags", "source_user", "return_user", "notifier",
)
NAMES = (
    "SLOT_RESERVE", "SLOT_FREE", "ENQUEUE", "SELECT_LOCAL", "SELECT_PROXY", "GRANT",
    "PROXY_RETURN", "QUEUE_DONE", "NODE_RETIRE_READY", "RELEASE_BIND", "RELEASE_REQUEST",
    "RELEASE_DEFER", "RELEASE_UNWIND", "RELEASE_NOTIFY_DONE", "RELEASE_HANDLED",
    "RELEASE_SOURCE_DROP", "RELEASE_RETURN_DROP", "PHYSICAL_BEGIN", "PHYSICAL_END",
    "RELEASE_RETIRE", "OWNER_RETIRE", "FRAME_PREPARE", "JIT_ENTER", "JIT_EXIT",
    "JIT_OPERATION", "CHILD_RETURN", "EPISODE_DONE", "FORWARD", "NATIVE_UNLOCK", "OWNER_STOP",
)
KINDS = {name: number + 1 for number, name in enumerate(NAMES)}
MASK64 = (1 << 64) - 1


def check(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def signed(word):
    return word - (1 << 64) if word >> 63 else word


def matching(rows, name, **fields):
    return [row for row in rows if row["kind"] == KINDS[name]
            and all(row[key] == value for key, value in fields.items())]


def one(rows, name, **fields):
    found = matching(rows, name, **fields)
    check(len(found) == 1, f"{name} {fields} has rows {[row['index'] for row in found]}")
    return found[0]


def first_after(rows, after, name, **fields):
    found = [row for row in matching(rows, name, **fields) if row["index"] > after["index"]]
    check(bool(found), f"{name} {fields} missing after row {after['index']}")
    return min(found, key=lambda row: row["index"])


class Audit:
    def __init__(self, args):
        self.args = args
        self.root = args.runtime.resolve(strict=True)
        self.inputs = {}
        self.spin = args.profile == "spin"
        self.lock_kind, self.unlock_kind = (4, 5) if self.spin else (1, 2)
        self.result = self.json(self.root / "result.json")
        controller = self.json(args.controller_result)
        expected = "protected_spin_jit_recursive_mechanism_pass" if self.spin else "protected_jit_recursive_mechanism_pass"
        check(controller["returncode"] == 0 and self.result["status"] == expected,
              "actual returned controller and runner completion disagree")
        check(self.result["warm_claim_empty"] is True, "fixed-image warm claim was not empty")
        self.image = self.result["warm_image_identity"]
        raw = self.read(self.root / "observations-final.bin")
        check(len(raw) >= 40, "observation header is truncated")
        abi, words, capacity, count, overflow = struct.unpack_from("<5Q", raw)
        check(abi == 1 and words == 20 and 0 < capacity <= args.max_events,
              "observation ABI or explicit event extent differs")
        check(0 <= count <= capacity and overflow == 0 and len(raw) == 40 + 160 * count,
              "observation count, bytes or overflow differs")
        self.header = {"abi": abi, "words": words, "capacity": capacity, "count": count, "overflow": overflow}
        self.rows = []
        for index, values in enumerate(struct.iter_unpack("<20Q", raw[40:])):
            check(1 <= values[0] <= len(NAMES), "unknown scalar event kind")
            self.rows.append(dict(zip(FIELDS, values), index=index))
        document = self.json(self.root / "observations-final.json")
        check(tuple(document["fields"]) == FIELDS and document["kinds"] == KINDS,
              "saved JSON event schema differs")
        check(document["records"] == self.rows, "binary and JSON event rows differ")
        self.source = self.json(self.root / "source-metadata.json")
        self.regions = []
        for index, region in enumerate(self.source["regions"]):
            data = self.read(self.root / f"source-{index}.bin")
            check(len(data) == region["length"], "source region length differs")
            self.regions.append((region["start"], data))
        self.calls = {record["site"]: record for record in self.result["actual_call_records"]}
        for call in self.calls.values():
            check(self.source_bytes(call["site"], call["length"]) == bytes.fromhex(call["raw_hex"]),
                  "retained decoded CALL bytes disagree with the source export")

    def read(self, path):
        path = Path(path)
        check(not path.is_symlink(), f"input is a symlink {path}")
        before = path.stat()
        check(before.st_size <= self.args.max_file_bytes, f"input exceeds explicit byte limit {path}")
        with path.open("rb") as stream:
            data = stream.read(self.args.max_file_bytes + 1)
        after = path.stat()
        check((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
              (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), f"input changed while reading {path}")
        check(len(data) == before.st_size, f"input byte count differs {path}")
        self.inputs[str(path)] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return data

    def json(self, path):
        return json.loads(self.read(path))

    def source_bytes(self, site, length):
        for start, data in self.regions:
            if start <= site and site + length <= start + len(data):
                return data[site - start:site - start + length]
        raise ValueError(f"source bytes missing at {site:#x}")

    def operation_call(self, event, direction):
        call = self.calls.get(event["ip"])
        check(call is not None and call.get("operation") == direction,
              f"operation at row {event['index']} has no exact source CALL")
        raw = self.source_bytes(call["site"], call["length"])
        check(len(raw) == 5 and raw[0] == 0xe8, "fixture API CALL is not its actual direct rel32 form")
        target = (call["site"] + 5 + int.from_bytes(raw[1:], "little", signed=True)) & MASK64
        expected_cursor = target if direction == "lock" else call["site"] + 5
        check(call["target"] == target and event["cursor"] == expected_cursor,
              "accepted operation target or operation-phase cursor differs")
        return call

    def completion(self, rows, node, task, expected):
        done = one(rows, "EPISODE_DONE", node=node, task=task, result=expected)
        prepared = one(rows, "FRAME_PREPARE", node=node, acquisition=done["acquisition"])
        check(done["flags"] & 1536 == 1536, "positive completion lacks source-closed/current-JIT flags")
        interval = [row for row in rows if prepared["index"] <= row["index"] <= done["index"]
                    and row["state"] == done["state"] and row["origin"] == done["origin"]]
        check(not matching(interval, "FORWARD"), "protected completion contains a native forward")
        entries, exits = matching(interval, "JIT_ENTER"), matching(interval, "JIT_EXIT")
        check(entries and len(entries) == len(exits), "generated entries and exits differ")
        check(all(row["image"] == self.image and row["task"] != row["origin"] for row in entries),
              "generated entry image or executor differs")
        check(all(row["image"] == self.image and row["result"] == 1 for row in exits),
              "protected completion contains another image or a non-operation exit")
        if self.spin:
            check(all(row["flags"] & 4096 for row in entries), "spin generated entry lacks pre-dispatch atomic context")
        unlocks = matching(interval, "JIT_OPERATION", result=self.unlock_kind, related=node)
        check(unlocks, "positive completion has no accepted matching unlock")
        for unlock in unlocks:
            call = self.operation_call(unlock, "unlock")
            check(unlock["image"] == self.image and any(row["ip"] == unlock["ip"]
                  and row["related"] == call["target"] for row in exits), "unlock lacks its exact producing exit")
        return {"frame": prepared, "done": done, "entries": entries, "exits": exits, "unlocks": unlocks}

    def release(self, rows, enqueue):
        node, state, acquisition = enqueue["node"], enqueue["state"], enqueue["acquisition"]
        grant = one(rows, "GRANT", node=node, state=state, acquisition=acquisition)
        owner, task, release = grant["owner"], grant["owner_task"], grant["related"]
        check(owner and task and release, "grant lacks exact owner/release identities")
        members = [row for row in rows if row["owner"] == owner and row["related"] == release
                   and row["state"] == state and row["acquisition"] == acquisition]
        bound = one(members, "RELEASE_BIND")
        check(bound["source_user"], "release has no initial source user")
        requested = one(members, "RELEASE_REQUEST", phase=1)
        handled = one(members, "RELEASE_HANDLED", phase=4, task=task)
        begin = first_after(rows, handled, "PHYSICAL_BEGIN", owner=owner, task=task,
                            object=grant["object"], phase=1)
        end = first_after(rows, begin, "PHYSICAL_END", owner=owner, task=task,
                          object=grant["object"], phase=2, result=0, related=begin["related"])
        drop = one(members, "RELEASE_SOURCE_DROP", phase=5, source_user=bound["source_user"])
        retired = one(members, "RELEASE_RETIRE", phase=6, task=task)
        ready = one(rows, "NODE_RETIRE_READY", node=node, state=state, acquisition=acquisition, phase=6)
        free = one(rows, "SLOT_FREE", node=node, state=state, acquisition=acquisition, phase=3)
        owner_retired = first_after(rows, end, "OWNER_RETIRE", owner=owner, task=task, phase=3)
        stopped = [row for row in matching(rows, "OWNER_STOP", owner=owner, task=task)
                   if bound["index"] <= row["index"] < owner_retired["index"]]
        check(len(stopped) == 1 and stopped[0]["flags"] & 128, "owner control-stop proof differs")
        check(bound["index"] < requested["index"] < handled["index"] < begin["index"] < end["index"],
              "source request, owner handling and physical callback order differs")
        check(begin["related"] and end["index"] < drop["index"] < retired["index"] <= ready["index"] < free["index"],
              "physical completion and exact source-user retirement order differs")
        if not self.spin:
            check(stopped[0]["index"] < begin["index"], "mutex physical callback precedes control stop")
        check(ready["flags"] & 15 == 15 and not ready["flags"] & 16,
              "node readiness lacks final queue/result conditions")
        check(free["flags"] & 0x86f == 0x86f and not free["flags"] & 16,
              "slot free lacks acquired retirable, empty users or idle components")
        check(all(not row[key] for row in (retired, ready, free)
                  for key in ("source_user", "return_user", "notifier")), "release users remain at retirement")
        return {"grant": grant, "bind": bound, "request": requested, "handled": handled,
                "physical_begin": begin, "physical_end": end, "source_drop": drop,
                "retired": retired, "ready": ready, "free": free,
                "control_stopped": stopped[0], "owner_retired": owner_retired, "members": members}

    def recursive(self, case):
        rows = self.rows[case["start"]:case["end"]]
        roles = case["roles"]
        check(len(set(roles)) == 5, "recursive roles do not identify five tasks")
        origin, ca, cb = roles[4], roles[2], roles[3]
        root = one(rows, "ENQUEUE", node=case["root"], task=origin, origin=origin, state=case["state"])
        child = one(rows, "ENQUEUE", node=case["child"], task=ca, origin=origin, state=case["state"])
        check(root["node"] != child["node"] and root["acquisition"] != child["acquisition"],
              "recursive acquisitions are not distinct")
        one(rows, "FRAME_PREPARE", node=child["node"], parent=root["node"], state=root["state"])
        selections = []
        for request, executor in ((root, ca), (child, cb)):
            selected = one(rows, "SELECT_PROXY", node=request["node"], task=executor,
                           owner_task=executor, related=request["related"])
            candidate_rows = matching(rows, "ENQUEUE", node=request["related"], task=executor, origin=executor)
            before = [row for row in candidate_rows if row["index"] < request["index"]]
            check(len(before) == 1, "request predecessor is not the exact earlier candidate")
            candidate = before[0]
            if self.spin:
                requeues = [row for row in candidate_rows if row["index"] > selected["index"] and row["phase"] == 2]
                check(len(requeues) == 1, "spin candidate has another number of local requeues")
                local = first_after(rows, requeues[0], "SELECT_LOCAL", node=candidate["node"],
                                    acquisition=candidate["acquisition"], task=executor)
            else:
                local = one(rows, "SELECT_LOCAL", node=candidate["node"], task=executor, owner_task=executor)
                check(local["owner"] == selected["owner"], "mutex selection has another batch owner")
            selections.append({"selection": selected, "candidate": candidate, "local": local})
        parent = self.completion(rows, root["node"], ca, 3)
        inner = self.completion(rows, child["node"], cb, 3 if self.spin or case["mode"] == 1 else 5)
        lock = one(rows, "JIT_OPERATION", node=root["node"], related=child["node"], task=ca,
                   result=self.lock_kind, image=self.image)
        self.operation_call(lock, "lock")
        returned = one(rows, "CHILD_RETURN", node=root["node"], related=child["node"], task=ca)
        check(returned["flags"] & 1024 and returned["result"] == inner["done"]["result"],
              "child return has another outcome or lacks current-JIT proof")
        check(returned["source_user"] == parent["entries"][0]["related"]
              and len({returned["source_user"], returned["return_user"], inner["done"]["related"]}) == 3,
              "child/current-parent endpoint identities differ")
        check(parent["entries"][0]["index"] < lock["index"] < child["index"] < inner["entries"][0]["index"],
              "C_A to child to C_B generated execution order differs")
        check(inner["done"]["index"] < returned["index"] < parent["done"]["index"]
              and returned["cursor"] == inner["done"]["cursor"], "child return revived another cursor")
        if case["mode"] == 1:
            resumed = one(rows, "JIT_ENTER", node=root["node"], task=ca, image=self.image,
                           related=returned["return_user"], cursor=returned["cursor"])
            check(returned["index"] < resumed["index"] < parent["done"]["index"], "parent reentry order differs")
        else:
            resumed = None
            check(parent["done"]["related"] == returned["return_user"]
                  and parent["done"]["cursor"] == returned["cursor"], "closed parent returned to an earlier endpoint")
        a, b = self.release(rows, root), self.release(rows, child)
        outer = None
        if case["mode"] == 2:
            if self.spin:
                check(a["request"]["result"] == 3 and a["request"]["task"] == cb,
                      "spin outer unlock lacks its foreign atomic request")
                outer = one(rows, "JIT_OPERATION", node=child["node"], related=root["node"],
                            result=self.unlock_kind, task=cb, phase=3, image=self.image)
                self.operation_call(outer, "unlock")
                continuation = first_after(rows, outer, "JIT_ENTER", node=child["node"], task=cb,
                                            image=self.image, cursor=outer["cursor"])
                check(a["physical_end"]["index"] < outer["index"] < continuation["index"]
                      and continuation["flags"] & 4096, "spin child continued before physical ACK")
                check(not any(matching(a["members"], name) for name in
                              ("RELEASE_DEFER", "RELEASE_UNWIND", "RELEASE_NOTIFY_DONE")),
                      "spin outer unlock has a deferred mutex phase")
            else:
                deferred = one(a["members"], "RELEASE_DEFER", phase=2)
                check(deferred["notifier"] and a["request"]["return_user"], "deferred mutex users are absent")
                unwind = one(a["members"], "RELEASE_UNWIND", phase=3, notifier=deferred["notifier"])
                notified = one(a["members"], "RELEASE_NOTIFY_DONE", notifier=deferred["notifier"])
                return_drop = one(a["members"], "RELEASE_RETURN_DROP", return_user=a["request"]["return_user"])
                check(a["request"]["result"] == 2 and a["request"]["index"] < deferred["index"] < unwind["index"] < a["handled"]["index"],
                      "deferred mutex request/unwind order differs")
                check(inner["done"]["index"] < unwind["index"] < returned["index"]
                      and notified["index"] < a["retired"]["index"]
                      and return_drop["index"] < a["retired"]["index"], "deferred mutex token retirement differs")
                outer = one(rows, "JIT_OPERATION", node=child["node"], related=root["node"],
                            result=self.unlock_kind, task=cb, phase=2, image=self.image)
        status = dict(item.split("=", 1) for item in case["raw_status"].split())
        check(int(status["w_core"], 16) == int(status["w_regs"], 16) == case["state"],
              "worker canonical state/regs backing differs")
        self.native_status(status, 5)
        return {"mode": case["mode"], "identities": {"state": root["state"], "origin": origin,
                "C_A": ca, "C_B": cb, "root": root["node"], "child": child["node"],
                "root_acquisition": root["acquisition"], "child_acquisition": child["acquisition"]},
                "root_enqueue": root, "child_enqueue": child,
                "selections": selections, "parent": parent, "child": inner, "lock": lock,
                "returned": returned, "parent_reentry": resumed, "outer_unlock": outer,
                "root_release": a, "child_release": b}

    def native_status(self, status, workers):
        check(all(int(status[name]) == 0 for name in ("errors", "core_errors", "origin_errors"))
              and int(status["locks_clear"]) == 1, "native effects or physical cleanup reported errors")
        if self.spin:
            expected = self.result["spin_context"]["role_cpus"][:workers]
            check([int(status[f"cpu{index}"]) for index in range(workers)] == expected
                  and int(status["pin_errors"]) == 0, "native spin CPU or pin checks differ")

    def frame(self, payload, operation, fixed_count, row_words=0, blob_count=0):
        check(len(payload) >= 32, "wire frame header is truncated")
        abi, op, length, count = struct.unpack_from("<4Q", payload)
        check(abi == 1 and op == operation and length == len(payload)
              and (row_words > 0 or count == 0) and count <= self.args.max_facts, "wire frame header differs")
        offset = 32 + fixed_count * 8
        check(offset + count * row_words * 8 <= len(payload), "wire fixed/row words are truncated")
        fixed = struct.unpack_from(f"<{fixed_count}Q", payload, 32)
        rows = []
        for _ in range(count):
            rows.append(struct.unpack_from(f"<{row_words}Q", payload, offset))
            offset += row_words * 8
        blobs = []
        for _ in range(blob_count):
            check(offset + 8 <= len(payload), "wire blob length is truncated")
            size = struct.unpack_from("<Q", payload, offset)[0]
            offset += 8
            check(offset + size <= len(payload), "wire blob bytes are truncated")
            blobs.append(payload[offset:offset + size])
            offset += size
        check(offset == len(payload), "wire frame has trailing or unparsed bytes")
        return fixed, rows, blobs

    def flat_image(self, payload):
        check(len(payload) >= 72, "flat image header is truncated")
        abi, image_abi, packet, io, gs, entries, sites, observed, version_size = struct.unpack_from("<9Q", payload)
        check((abi, image_abi, packet, io) == (1, 1, 168, 56), "flat image ABI differs")
        check(sites <= self.args.max_events and observed <= self.args.max_facts,
              "flat source/observation counts exceed audit limits")
        cursor = 72
        version = payload[cursor:cursor + version_size]
        cursor += version_size
        check(version.decode("utf-8") == self.source["version"], "flat source version differs")
        check(gs == int(str(self.result["gs_proof"]["current_task_gs_offset"]), 0), "flat GS input differs")
        check(cursor + entries * 8 <= len(payload), "flat entry table is truncated")
        entry_sites = struct.unpack_from(f"<{entries}Q", payload, cursor)
        cursor += entries * 8
        source = {}
        for _ in range(sites):
            check(cursor + 32 <= len(payload), "flat source row is truncated")
            ip, next_ip, kind, length = struct.unpack_from("<4Q", payload, cursor)
            cursor += 32
            check(kind <= 2 and 1 <= length <= 15 and cursor + length <= len(payload), "flat source row differs")
            raw = payload[cursor:cursor + length]
            cursor += length
            check(ip not in source and next_ip == ip + length and raw == self.source_bytes(ip, length),
                  "flat source bytes or continuation differ")
            source[ip] = {"kind": kind, "next": next_ip, "raw": raw.hex()}
        observations = []
        for _ in range(observed):
            check(cursor + 32 <= len(payload), "flat observation row is truncated")
            row = struct.unpack_from("<4Q", payload, cursor)
            check(row[2] <= 1 and row[3] <= 3, "flat observation kind/outcome differs")
            observations.append(row)
            cursor += 32
        check(cursor == len(payload) and entries > 0, "flat image extent or entries differ")
        return {"source": source, "observations": observations, "entry_sites": entry_sites}

    @staticmethod
    def indirect_kind(source):
        raw = bytes.fromhex(source["raw"])
        offset = 0
        while offset < len(raw) and (raw[offset] in (0x26, 0x2e, 0x36, 0x3e, 0x64, 0x65, 0x66, 0x67, 0xf0, 0xf2, 0xf3)
                                     or 0x40 <= raw[offset] <= 0x4f):
            offset += 1
        if offset + 1 < len(raw) and raw[offset] == 0xff:
            group = raw[offset + 1] >> 3 & 7
            if group == 2 and source["kind"] == 0:
                return 0
            if group == 4 and source["kind"] == 1:
                return 1
        return None

    def control_receipts(self):
        directories = sorted((self.root / "wire").glob("attempt-*"))
        check(0 < len(directories) <= self.args.max_wire_attempts, "wire attempt count exceeds audit limit")
        attempts, claims, facts, candidates, images, publications = [], {}, {}, {}, {}, {}
        acknowledged, settled = set(), set()
        source_epoch = None
        previous_image = self.source["old"]
        next_sequence = 1
        pending_busy = None
        archive_claim_payload = None
        archive_digest = hashlib.sha256(self.read(self.root / "shutdown-archive.json")).digest()
        archive = self.json(self.root / "shutdown-archive.json")
        check(archive["format"] == "kdlock.feedback-archive" and archive["learning_closed"] is True,
              "archive format or closed-source disposition differs")
        for directory in directories:
            request_info = self.json(directory / "request.json")
            response_info = self.json(directory / "result.json")
            request = self.read(directory / "request.bin")
            response = self.read(directory / "reply.bin")
            envelope = self.read(directory / "returned-envelope.bin")
            check(len(envelope) == 72, "returned ioctl envelope size differs")
            abi, op, seq, _, input_size, _, output_capacity, output_size, status = struct.unpack("<9Q", envelope)
            check(abi == 1 and op == request_info["operation"] and seq == request_info["sequence"]
                  and input_size == len(request) == request_info["request_bytes"]
                  and output_size == len(response) == response_info["reply_bytes"]
                  and output_capacity == request_info["output_capacity"] and output_size <= output_capacity
                  and signed(status) == response_info["status"] and signed(status) in (0, -11, -16)
                  and response_info["completed_response"] is True,
                  "actual ioctl envelope and copied wire bytes differ")
            attempts.append({"operation": op, "sequence": seq, "status": signed(status), "directory": directory.name})
            if op == 0:
                check(seq == 0 and len(attempts) == 1 and len(response) == 48,
                      "fresh fixture query shape differs")
                check(struct.unpack("<6Q", response) == (1, 0, 0, 0, 0, 0), "query recovered an unrecorded exchange")
                continue
            check(seq == next_sequence, "wire sequence was replayed or skipped")
            next_sequence += 1
            if pending_busy is not None:
                check(pending_busy == (op, request), "busy operation changed before its actual completed reply")
            if signed(status):
                pending_busy = (op, request)
                continue
            pending_busy = None
            if op == 8:
                check(len(response) >= 88, "source export header is truncated")
                source_epoch, _, _, gs, boundaries, slot, old = struct.unpack_from("<7Q", response, 32)
                check(slot == self.source["slot"] and old == previous_image
                      and gs == int(str(self.result["gs_proof"]["current_task_gs_offset"]), 0),
                      "actual source export slot/base or GS differs")
                check(response == self.read(self.root / "source-export.bin"), "source export wire/copy differ")
            elif op in (1, 10):
                fixed, raw_rows, blobs = self.frame(response, op, 3, 12, 1)
                check(fixed[2] == source_epoch and blobs[0].decode("utf-8") == self.source["version"],
                      "claim epoch or version differs")
                claim = {"identity": fixed[0], "holder": fixed[1], "rows": {}}
                for row in raw_rows:
                    key = (row[0], row[1])
                    check(all(key) and key not in claim["rows"], "claim record identity/incarnation duplicates")
                    check(key not in facts or facts[key] == row, "record incarnation changed immutable fact scalars")
                    claim["rows"][key] = row
                    facts[key] = row
                claims[(fixed[0], fixed[1])] = claim
                if op == 10:
                    archive_claim_payload = response
            elif op == 2:
                requested, _, _ = self.frame(request, op, 5)
                fixed, _, symbols = self.frame(response, op, 12, 0, 4)
                check((requested[0], requested[1]) in claims and fixed[1] == requested[3]
                      and fixed[7] == requested[4] == previous_image and fixed[9] == source_epoch,
                      "build reservation baseline or exact claim differs")
                candidates[fixed[0]] = {"fixed": fixed, "claim": (requested[0], requested[1]), "symbols": symbols}
            elif op == 3:
                requested, _, blobs = self.frame(request, op, 1, 0, 5)
                candidate = candidates[requested[0]]
                reply, _, _ = self.frame(response, op, 1)
                check(reply == requested and 0 < len(blobs[3]) <= candidate["fixed"][11], "actual code stage differs")
                candidate["flat"] = self.flat_image(blobs[4])
                candidate["machine_sha256"] = hashlib.sha256(blobs[3]).hexdigest()
                manifest = json.loads(blobs[2])
                version = manifest["source_version"]
                expected_version = self.source["version"].encode("utf-8")
                check(version == {"encoding": "utf-8", "bytes_hex": expected_version.hex(),
                                  "length": len(expected_version)}, "artifact source version differs")
                images[candidate["fixed"][2]] = candidate
            elif op == 4:
                requested, included, _ = self.frame(request, op, 3, 2)
                actual, actual_included, _ = self.frame(response, op, 14, 2)
                candidate = candidates[requested[0]]
                fixed = candidate["fixed"]
                claim = claims[(requested[1], requested[2])]
                check(candidate["claim"] == (requested[1], requested[2]) and included == actual_included,
                      "publication included a different actual claim selection")
                check(actual[1:3] == requested[1:] and actual[3] == fixed[1] and actual[4] == fixed[5]
                      and actual[5] == fixed[6] and actual[6] == actual[8] == previous_image
                      and actual[7] == fixed[2] and actual[9] == source_epoch and actual[10] == fixed[8]
                      and actual[11] == fixed[3] and actual[12] == fixed[4] and actual[13] == requested[0],
                      "actual publication owner/update/old/new/retired binding differs")
                emitted = {tuple(row[:3]) for row in candidate["flat"]["observations"] if row[3] == 0}
                expected_ack = []
                for key in included:
                    fact = claim["rows"][key]
                    producer = images[fact[3]]
                    instruction = producer["flat"]["source"].get(fact[6])
                    transfer = self.indirect_kind(instruction) if instruction else None
                    cursor_matches = (fact[8] == fact[6] if fact[9] == 1 else fact[8] == fact[7])
                    eligible = (fact[2] == producer["fixed"][4] and fact[4] == 3 and 0 <= fact[5] <= 15
                                and fact[10] == 1 and signed(fact[11]) == 0 and transfer is not None
                                and fact[9] in ((1, 2) if transfer == 0 else (4,)) and cursor_matches)
                    if eligible and (fact[6], fact[7], transfer) in emitted:
                        expected_ack.append(key)
                publications[actual[0]] = {"receipt": actual, "included": included,
                                            "expected_ack": expected_ack, "ack": None}
                previous_image = actual[7]
            elif op == 5:
                requested, _, _ = self.frame(request, op, 1)
                fixed, keys, _ = self.frame(response, op, 5, 2)
                publication = publications[requested[0]]
                check(publication["ack"] is None and fixed[1] == requested[0]
                      and fixed[2:4] == publication["receipt"][1:3] and fixed[4] == source_epoch
                      and keys == publication["expected_ack"], "actual acknowledgment subset differs")
                publication["ack"] = fixed[0]
                check(not acknowledged.intersection(keys), "fact was acknowledged more than once")
                acknowledged.update(keys)
            elif op == 11:
                fixed, keys, blobs = self.frame(request, op, 2, 2, 1)
                reply, actual_keys, _ = self.frame(response, op, 3, 2)
                claim = claims[fixed]
                check(reply[1:] == fixed and keys == actual_keys == list(claim["rows"])
                      and blobs[0] == archive_digest, "actual archive settlement differs")
                check(not acknowledged.intersection(keys), "archived settlement overlaps coverage acknowledgment")
                settled.update(keys)
            elif op == 6:
                requested, _, _ = self.frame(request, op, 2)
                reply, _, _ = self.frame(response, op, 2)
                check(requested == reply and requested in claims, "claim end identities differ")
            elif op == 9:
                fixed, _, _ = self.frame(response, op, 1)
                check(fixed[0] == source_epoch, "shutdown epoch differs")
            else:
                raise ValueError(f"unexpected successful workflow operation {op}")
        check(pending_busy is None and previous_image == self.image
              and all(pub["ack"] is not None for pub in publications.values()),
              "warm image is not the last actually published/acknowledged candidate")
        check(archive_claim_payload is not None and bytes.fromhex(archive["raw_claim"]["bytes_hex"]) == archive_claim_payload,
              "archive does not preserve its exact actual claim bytes")
        check(acknowledged | settled == set(facts) and len(archive["facts"]) == len(settled),
              "recorded facts remain unaccounted for or archival records differ")
        check(archive_digest.hex() == self.result["archive_sha256"] and len(settled) == self.result["settled_keys"],
              "archive digest or actual settled-key count differs")
        return {"attempts": attempts, "publications": list(publications.values()),
                "acknowledged_keys": sorted(acknowledged), "settled_keys": sorted(settled),
                "archive_sha256": archive_digest.hex(), "fact_count": len(facts)}

    def native_miss(self):
        case = self.result["spin_miss_handback"]
        rows = self.rows[case["start"]:case["end"]]
        status = dict(item.split("=", 1) for item in case["raw_status"].split())
        self.native_status(status, 5)
        check(int(status["miss_checks"]) == int(status["w_miss_checks"]) == 1,
              "native miss checkpoint count differs")
        ca, origin = case["roles"][2], case["roles"][4]
        root = one(rows, "ENQUEUE", node=case["root"], task=origin, origin=origin, state=case["state"])
        selected = one(rows, "SELECT_PROXY", node=root["node"], task=ca, related=root["related"])
        entered = one(rows, "JIT_ENTER", node=root["node"], task=ca, image=self.image)
        check(entered["flags"] & 4096, "native suffix producer lacked a physical spin pin")
        target = int(status["miss_target"], 16)
        call = [call for call in self.calls.values() if call["target"] == target and not call["indirect"]]
        check(len(call) == 1, "native miss target lacks its exact decoded direct CALL")
        call = call[0]
        raw = self.source_bytes(call["site"], call["length"])
        check(len(raw) == 5 and raw[0] == 0xe8
              and (call["site"] + 5 + int.from_bytes(raw[1:], "little", signed=True)) & MASK64 == target,
              "native miss CALL bytes disagree with its target")
        exited = one(rows, "JIT_EXIT", node=root["node"], image=self.image, result=3,
                     ip=call["site"], related=target, cursor=target, phase=2)
        forwarded = one(rows, "FORWARD", node=root["node"], ip=call["site"], related=target,
                        cursor=target, phase=2, flags=3)
        unlocked = one(rows, "NATIVE_UNLOCK", node=root["node"], state=root["state"], task=origin, phase=3)
        check(selected["index"] < entered["index"] < exited["index"] < forwarded["index"] < unlocked["index"],
              "native handback did not follow one staged direct source CALL")
        check(not matching(rows, "EPISODE_DONE", node=root["node"]), "native suffix was counted as generated completion")
        release = self.release(rows, root)
        check(release["physical_end"]["index"] < unlocked["index"], "native unlock returned before physical ACK")
        nesting = [case for case in self.result["cases"] if case["name"] == "spin-native-nesting"]
        check(len(nesting) == 1, "native spin nesting case is missing")
        nesting = nesting[0]
        values = nesting["values"]
        self.native_status(values, nesting["workers"])
        check(int(values["pin_checks"]) == 6 * nesting["workers"] * nesting["iterations"],
              "native baseline/nested pin sample count differs")
        return {"identities": {"state": root["state"], "origin": origin, "executor": ca,
                                "node": root["node"], "acquisition": root["acquisition"]},
                "selected": selected, "entered": entered, "exited": exited,
                "forwarded": forwarded, "native_unlock": unlocked, "release": release,
                "native_checkpoint_calls": int(status["w_miss_checks"]),
                "native_nesting_samples": int(values["pin_checks"])}

    def run(self):
        wire = self.control_receipts()
        recursive_cases = self.result["warm_completion"][1:]
        check(len(recursive_cases) == 2 and {case["mode"] for case in recursive_cases} == {1, 2},
              "both recursive completion modes are required")
        recursive = [self.recursive(case) for case in recursive_cases]
        plain = self.result["warm_completion"][0]
        rows = self.rows[plain["start"]:plain["end"]]
        plain_proofs = []
        for selected in matching(rows, "SELECT_PROXY"):
            frames = [row for row in matching(rows, "FRAME_PREPARE", node=selected["node"])
                      if row["index"] < selected["index"]]
            check(frames, "plain selected request has no preceding frame")
            start = frames[-1]
            free = first_after(rows, selected, "SLOT_FREE", node=selected["node"], acquisition=selected["acquisition"])
            lifetime = [row for row in rows if start["index"] <= row["index"] <= free["index"]]
            plain_proofs.append(self.completion(lifetime, selected["node"], selected["task"], 3))
        check(plain_proofs, "warm plain generated completion is absent")
        native = self.native_miss() if self.spin else None
        post = self.json(self.root / "poststate.json")
        check(post["module_present"] is False and not post["devices"] and not post["active_rows"],
              "saved poststate still has fixture or build activity")
        return {"status": "SAVED_RUNTIME_RELATIONS_VERIFIED", "profile": self.args.profile,
                "scope": "Protected source lock/unlock episodes, exact saved return and physical-release records",
                "producer_detail_contract": "The live adapter checks exact EmittedExit fields. This saved-output audit checks the recorded ABI detail domain, source transfer and cursor.",
                "header": self.header, "fixed_image": self.image,
                "warm_plain_positive_lifetimes": len(plain_proofs), "plain": plain_proofs,
                "recursive": recursive, "native_miss": native, "control": wire, "poststate": post,
                "inputs": self.inputs}


def compact(value):
    if isinstance(value, dict):
        if all(field in value for field in FIELDS) and "index" in value:
            return value["index"]
        return {key: compact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [compact(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--controller-result", type=Path, required=True)
    parser.add_argument("--profile", choices=("mutex", "spin"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-file-bytes", type=int, required=True)
    parser.add_argument("--max-events", type=int, required=True)
    parser.add_argument("--max-facts", type=int, required=True)
    parser.add_argument("--max-wire-attempts", type=int, required=True)
    args = parser.parse_args()
    check(all(getattr(args, name) > 0 for name in
              ("max_file_bytes", "max_events", "max_facts", "max_wire_attempts")), "positive finite audit extents required")
    check(not args.output.exists(), "fresh output directory required")
    audit = Audit(args)
    result = compact(audit.run())
    args.output.mkdir(parents=False)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    (args.output / "proof.json").write_bytes(payload)
    summary = {"status": result["status"], "profile": args.profile,
               "events": result["header"]["count"], "plain_positive": result["warm_plain_positive_lifetimes"],
               "recursive_cases": len(result["recursive"]), "wire_attempts": len(result["control"]["attempts"]),
               "acknowledged": len(result["control"]["acknowledged_keys"]),
               "settled": len(result["control"]["settled_keys"]),
               "proof_sha256": hashlib.sha256(payload).hexdigest()}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
