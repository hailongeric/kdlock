"""Saved scalar-record evidence for completed real-MM protected ranges.

No workload, pointer dereference, runtime classification or compiler operation
occurs here. Call bytes come from the existing source scanner and are checked
again against the retained source export. Function names only attribute evidence
to the pinned ELF. They never select an execution route or model a helper.
"""

from pathlib import Path
import struct


FUNCTIONS = ("vm_mmap_pgoff", "__vm_munmap")
NAMES = ("SLOT_RESERVE", "SLOT_FREE", "ENQUEUE", "SELECT_LOCAL", "SELECT_PROXY", "GRANT",
         "PROXY_RETURN", "QUEUE_DONE", "NODE_RETIRE_READY", "RELEASE_BIND", "RELEASE_REQUEST",
         "RELEASE_DEFER", "RELEASE_UNWIND", "RELEASE_NOTIFY_DONE", "RELEASE_HANDLED",
         "RELEASE_SOURCE_DROP", "RELEASE_RETURN_DROP", "PHYSICAL_BEGIN", "PHYSICAL_END",
         "RELEASE_RETIRE", "OWNER_RETIRE", "FRAME_PREPARE", "JIT_ENTER", "JIT_EXIT",
         "JIT_OPERATION", "CHILD_RETURN", "EPISODE_DONE", "FORWARD", "NATIVE_UNLOCK", "OWNER_STOP",
         "READ_ACQUIRE", "READ_RELEASE", "WRITE_DOWNGRADE_REAL", "WRITE_DOWNGRADE_RETAINED",
         "NATIVE_MODE", "NATIVE_READ_ACQUIRE", "NATIVE_READ_RELEASE", "NATIVE_WRITE_ACQUIRE",
         "NATIVE_WRITE_RELEASE", "NATIVE_DOWNGRADE", "NATIVE_CANCEL", "NATIVE_TRY_MISS",
         "ACQUIRE_CANCELLED", "QUERY_RESULT")
K = {name: index + 1 for index, name in enumerate(NAMES)}
CONTROL = {K[name] for name in ("JIT_ENTER", "JIT_EXIT", "JIT_OPERATION", "QUERY_RESULT",
                              "WRITE_DOWNGRADE_RETAINED", "FORWARD", "EPISODE_DONE", "ACQUIRE_CANCELLED")}
SCOPE = ("Exact protected-range witnesses in passed real-syscall rounds. No per-address, "
         "individual successful mmap, whole-function, context-equivalence or performance claim.")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_function_spans(path):
    """Read two exact STT_FUNC spans from a bounded ELF64 x86-64 SYMTAB.

    The caller pins the entire ELF independently. Extended section numbering,
    ambiguous symbols and non-file-backed executable spans are refused.
    """
    path = Path(path)
    before = path.stat()
    with path.open("rb") as source:
        def read(offset, length):
            require(0 <= offset <= before.st_size and 0 <= length <= 64 * 1024 * 1024 and
                    offset + length <= before.st_size, "ELF metadata extent exceeds its finite bound")
            source.seek(offset)
            data = source.read(length)
            require(len(data) == length, "truncated ELF metadata")
            return data

        header = read(0, 64)
        require(header[:7] == b"\x7fELF\x02\x01\x01" and struct.unpack_from("<H", header, 18)[0] == 62,
                "ELF64 little-endian x86-64 required")
        offset = struct.unpack_from("<Q", header, 40)[0]
        width, count = struct.unpack_from("<HH", header, 58)
        require(width == 64 and 0 < count <= 8192, "ordinary bounded ELF section table required")
        table = read(offset, count * width)
        sections = [struct.unpack_from("<IIQQQQIIQQ", table, index * width) for index in range(count)]
        symbols = [row for row in sections if row[1] == 2]
        require(len(symbols) == 1, "one actual ELF SYMTAB required")
        symtab = symbols[0]
        require(symtab[9] == 24 and symtab[5] % 24 == 0 and symtab[5] // 24 <= 2 * 1024 * 1024 and
                symtab[6] < count and sections[symtab[6]][1] == 3, "ELF symbol/string table shape differs")
        names = read(sections[symtab[6]][4], sections[symtab[6]][5])
        data = read(symtab[4], symtab[5])
        found = {}
        for name_at, info, other, section_index, start, size in struct.iter_unpack("<IBBHQQ", data):
            if info & 15 != 2:
                continue
            require(name_at < len(names), "ELF function name offset escaped string table")
            end_name = names.find(b"\0", name_at)
            require(end_name >= 0, "unterminated ELF function name")
            name = names[name_at:end_name]
            if name not in tuple(item.encode() for item in FUNCTIONS):
                continue
            name = name.decode("ascii")
            require(name not in found and 0 < section_index < count and size > 0 and start + size < 1 << 64,
                    "ambiguous, undefined or empty required ELF function")
            section = sections[section_index]
            require(section[1] != 8 and section[2] & 4 and section[3] <= start and
                    start + size <= section[3] + section[5] and section[4] + section[5] <= before.st_size,
                    "required function is not in file-backed executable source")
            found[name] = {"start": start, "end": start + size, "bytes": size, "section": section_index}
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "ELF changed while reading function spans")
    require(set(found) == set(FUNCTIONS), "both exact MM root function spans required")
    return found


def completion_report(records, calls, function_spans, rounds, gate, read_source):
    """Return positive/rejected root candidates without changing acceptance.

    rounds contain event offsets begin/end (end exclusive), fixed image and
    effects_passed from the caller's actual round checks. Later records may
    finish exact retirement. All identities here are copied scalars only.
    """
    require(set(function_spans) == set(FUNCTIONS), "exact two-function source attribution required")
    require(all(row["index"] == index for index, row in enumerate(records)), "event indices are not one prefix")
    by_return = {}
    by_site = {}
    for call in calls:
        if "operation" not in call:
            continue
        if call["site"] in by_site:
            # Coherent overlapping source regions can repeat the same decoded
            # CALL. Distinct metadata at one actual instruction is ambiguous.
            require(by_site[call["site"]] == call, "conflicting typed source CALL metadata")
            continue
        by_site[call["site"]] = call
        if call["operation"] == "lock":
            require(call["site"] + call["length"] not in by_return, "ambiguous acquisition return")
            by_return[call["site"] + call["length"]] = call
    report = {"scope": SCOPE, "positive": [], "rejected": [], "counts": {"mmap": 0, "munmap_retained": 0}}

    def checked_call(call):
        require(call is not None and not call["indirect"] and 0 < call["length"] <= 15,
                "exact direct prefix-aware typed source CALL required")
        raw = bytes.fromhex(call["raw_hex"])
        require(len(raw) == call["length"] and read_source(call["site"], call["length"]) == raw,
                "typed CALL bytes differ from the retained source export")
        return call

    last_end, seen_rounds = 0, set()
    for round_row in rounds:
        begin, limit = round_row["begin"], round_row["end"]
        require(last_end <= begin <= limit <= len(records) and round_row["round"] not in seen_rounds,
                "round event extent escaped, overlapped or repeated")
        last_end = limit
        seen_rounds.add(round_row["round"])
        image = round_row["image"]
        for frame in records[begin:limit]:
            if frame["kind"] != K["FRAME_PREPARE"] or frame["parent"]:
                continue
            candidate = {"round": round_row["round"], "frame": frame, "accepted": False}
            same = lambda row: all(row[key] == frame[key] for key in ("state", "node", "acquisition", "origin"))
            preceding = [row for row in records[:frame["index"]] if row["kind"] == K["SLOT_RESERVE"] and same(row)]
            if not preceding:
                continue
            reserve = preceding[-1]
            end = next((row["index"] for row in records[reserve["index"] + 1:]
                        if row["kind"] in (K["SLOT_FREE"], K["SLOT_RESERVE"]) and
                        row["owner"] == reserve["owner"] and row["related"] == reserve["related"]), len(records))
            slot = [row for row in records[reserve["index"] + 1:end] if same(row)]
            grants = [row for row in slot if row["kind"] == K["GRANT"] and row["object"] == gate]
            if not grants:
                continue
            candidate["reserve"] = reserve
            try:
                require(round_row["effects_passed"] is True and image, "round effects or fixed image unestablished")
                require(len(grants) == 1 and begin <= reserve["index"] < frame["index"] < end and
                        reserve["parent"] and reserve["owner"] and reserve["related"] and
                        reserve["task"] == frame["origin"] == frame["task"] and frame["image"] == image,
                        "root reservation/frame/grant incarnation differs")
                grant = grants[0]
                candidate["grant"] = grant
                entries = [row for row in slot if row["kind"] == K["JIT_ENTER"]]
                require(bool(entries), "no generated root entry")
                entered = entries[0]
                executor, binding = entered["task"], entered["related"]
                require(frame["index"] < grant["index"] < entered["index"] < limit and
                        grant["owner"] and grant["related"] and executor != frame["origin"] and
                        grant["owner_task"] == executor and grant["flags"] & 3 == 3 and
                        not grant["phase"] and entered["image"] == image and binding,
                        "root current foreign executor/image/physical grant differs")
                enqueues = [row for row in slot if row["kind"] == K["ENQUEUE"] and
                            frame["index"] < row["index"] < grant["index"] and row["object"] == gate and
                            row["task"] == frame["origin"]]
                selects = [row for row in slot if row["kind"] == K["SELECT_PROXY"] and
                           row["index"] < grant["index"] and row["owner"] == grant["owner"] and
                           row["owner_task"] == executor and row["object"] == gate]
                require(len(enqueues) == len(selects) == 1, "exact original enqueue/proxy selection missing")
                root_call = checked_call(by_return.get(entered["cursor"]))
                attributed = [name for name, span in function_spans.items()
                              if span["start"] <= root_call["site"] and
                              root_call["site"] + root_call["length"] <= span["end"]]
                require(len(attributed) == 1, "root CALL is outside the two exact MM function spans")
                path = "mmap" if attributed[0] == "vm_mmap_pgoff" else "munmap_retained"
                candidate.update(path=path, root_call=root_call, enter=entered,
                                 enqueue=enqueues[0], selection=selects[0])
                require(not any(row["kind"] in CONTROL and row["state"] == frame["state"] and
                                row["origin"] == frame["origin"] for row in
                                records[reserve["index"] + 1:entered["index"]]),
                        "root or child source control occurred before the root generated entry")
                # Include child controls from the same S_W while the root runs.
                # A handback or miss in a child cannot be hidden by filtering it
                # out of the root node's rows.
                controls = [row for row in records[entered["index"]:min(end, limit)] if
                            row["state"] == frame["state"] and row["origin"] == frame["origin"] and
                            row["kind"] in CONTROL]
                position, retained, final_operation, terminal = 0, None, None, None
                operations = []
                candidate["operations"] = operations

                def current(row):
                    require(same(row) and row["task"] == executor and row["image"] == image and
                            not row["parent"], "source control changed root/executor/image")

                while position < len(controls):
                    enter = controls[position]
                    current(enter)
                    require(enter["kind"] == K["JIT_ENTER"] and enter["related"] == binding,
                            "handback or unsupported source control before completion")
                    require(position + 2 < len(controls), "generated entry has no accepted typed operation")
                    exited, operation = controls[position + 1:position + 3]
                    current(exited)
                    current(operation)
                    call = checked_call(by_site.get(exited["ip"]))
                    expected = {"query": 4, "mode_change": 3, "unlock": 2}.get(call["operation"])
                    require(expected is not None and exited["kind"] == K["JIT_EXIT"] and
                            exited["result"] == 1 and exited["flags"] == expected and exited["phase"] == 1 and
                            exited["cursor"] == call["site"] and exited["related"] == call["target"],
                            "coverage/SPECIAL/resource/refused or nonmatching typed source exit")
                    require(operation["kind"] == K["JIT_OPERATION"] and operation["ip"] == call["site"] and
                            operation["object"] == gate, "typed operation does not name the selected gate/CALL")
                    step = {"enter": enter, "exit": exited, "operation": operation, "call": call}
                    operations.append(step)
                    position += 3
                    after_call = call["site"] + call["length"]
                    if call["operation"] == "query":
                        require(operation["result"] in (16, 17) and operation["phase"] == 2 and
                                operation["cursor"] == call["target"] and not operation["related"] and
                                position < len(controls), "query prepared operation differs")
                        result = controls[position]
                        current(result)
                        require(result["kind"] == K["QUERY_RESULT"] and result["related"] == operation["result"] and
                                result["result"] in (0, 1) and result["phase"] == 5 and
                                result["ip"] == call["site"] and result["cursor"] == after_call and
                                result["object"] == gate, "query Boolean or canonical return differs")
                        step["query"] = result
                        position += 1
                    elif call["operation"] == "mode_change":
                        require(path == "munmap_retained" and retained is None and operation["result"] == 10 and
                                operation["phase"] == 5 and operation["related"] == frame["node"] and
                                operation["cursor"] == after_call and position < len(controls),
                                "same-grant retained downgrade is missing or repeated")
                        retained = controls[position]
                        require(same(retained) and retained["task"] == executor and
                                retained["kind"] == K["WRITE_DOWNGRADE_RETAINED"] and retained["object"] == gate and
                                retained["owner"] == grant["owner"] and retained["related"] == binding and
                                retained["phase"] == 2 and retained["result"] == 0 and retained["cursor"] == after_call,
                                "logical read did not retain the original physical writer")
                        step["retained"] = retained
                        position += 1
                    else:
                        kind, actions = (9, (0, 1)) if path == "mmap" else (7, (4,))
                        require(operation["result"] == kind and operation["phase"] in actions and
                                operation["related"] == frame["node"] and operation["cursor"] == after_call and
                                (path == "mmap" or retained is not None), "final typed unlock/mode/return differs")
                        require(position < len(controls), "final accepted unlock has no completion disposition")
                        terminal = controls[position]
                        require(same(terminal) and terminal["task"] == executor and terminal["cursor"] == after_call,
                                "terminal disposition lost the exact root post-CALL cursor")
                        if path == "mmap":
                            require(terminal["kind"] == K["EPISODE_DONE"] and terminal["result"] == 3 and
                                    terminal["flags"] & (512 | 1024) == 512 | 1024 and terminal["related"] == binding,
                                    "write unlock lacks current-JIT positive root completion")
                        else:
                            require(terminal["kind"] == K["FORWARD"] and terminal["image"] == image and
                                    not terminal["result"] and not terminal["phase"] and not terminal["flags"] and
                                    terminal["ip"] == call["site"] and terminal["related"] == call["target"],
                                    "retained up_read did not transfer its exact completed native continuation")
                        final_operation = operation
                        break
                    require(position < len(controls) and controls[position]["cursor"] == after_call,
                            "typed return did not reenter at its exact post-CALL cursor")
                require(terminal is not None and final_operation is not None, "protected interval did not complete")
                require(not any(row["kind"] == K["JIT_ENTER"] and row["index"] > terminal["index"] for row in slot),
                        "source reentered after terminal protected completion")
                require(not any(row["state"] == frame["state"] and row["origin"] == frame["origin"] and
                                entered["index"] <= row["index"] <= terminal["index"] and
                                row["kind"] in (K["READ_ACQUIRE"], K["READ_RELEASE"], K["WRITE_DOWNGRADE_REAL"],
                                                K["GRANT"], K["ENQUEUE"])
                                for row in records), "unexpected nested grant/credit or real conversion inside root interval")
                retirement = _retirement(records, reserve, grant, slot, end, final_operation, path, gate, executor)
                candidate.update(accepted=True, terminal=terminal, retirement=retirement)
                report["positive"].append(candidate)
                report["counts"][path] += 1
            except (ValueError, KeyError, IndexError) as error:
                candidate["reason"] = str(error)
                report["rejected"].append(candidate)
    return report


def _retirement(records, reserve, grant, slot, end, operation, path, gate, executor):
    """Join a release lifetime and its separate shared owner incarnation."""
    owner, release = grant["owner"], grant["related"]
    same = lambda row: row["state"] == grant["state"] and row["acquisition"] == grant["acquisition"]
    prior_owner_end = max((row["index"] for row in records[:grant["index"]]
                           if row["kind"] == K["OWNER_RETIRE"] and row["owner"] == owner), default=-1)
    owner_end = next((row for row in records[grant["index"] + 1:] if
                      row["kind"] == K["OWNER_RETIRE"] and row["owner"] == owner), None)
    require(owner_end is not None and owner_end["phase"] == 3 and owner_end["owner_task"] == executor,
            "physical owner has not retired its exact incarnation")
    owner_rows = [row for row in records[prior_owner_end + 1:owner_end["index"]] if row["owner"] == owner]
    bindings = [row for row in owner_rows if row["kind"] == K["RELEASE_BIND"] and same(row) and row["related"] == release]
    requests = [row for row in owner_rows if row["kind"] == K["RELEASE_REQUEST"] and same(row) and row["related"] == release]
    retired = [row for row in owner_rows if row["kind"] == K["RELEASE_RETIRE"] and same(row) and row["related"] == release]
    handled = [row for row in owner_rows if row["kind"] == K["RELEASE_HANDLED"] and same(row) and row["related"] == release]
    source_drops = [row for row in owner_rows if row["kind"] == K["RELEASE_SOURCE_DROP"] and same(row) and row["related"] == release]
    stopped = [row for row in owner_rows if row["kind"] == K["OWNER_STOP"] and row["flags"] & 128]
    physical_begin = [row for row in owner_rows if row["kind"] == K["PHYSICAL_BEGIN"]]
    physical_end = [row for row in owner_rows if row["kind"] == K["PHYSICAL_END"]]
    require(len(bindings) == len(requests) == len(retired) == len(handled) == len(source_drops) ==
            len(stopped) == len(physical_begin) == len(physical_end) == 1,
            "release/owner lifetime has missing, repeated or reused records")
    bound, request, retired, begun, physical = bindings[0], requests[0], retired[0], physical_begin[0], physical_end[0]
    handled, source_drop, stopped = handled[0], source_drops[0], stopped[0]
    require(bound["index"] < grant["index"] < request["index"] < operation["index"] and
            request["result"] == (1 if path == "mmap" else 4) and
            request["phase"] == 1 and
            bound["source_user"] and not bound["phase"] and
            all(row["object"] == gate and row["owner_task"] == executor for row in (bound, request, begun, physical)) and
            all(row["task"] == executor for row in (begun, physical, owner_end)) and
            request["index"] < begun["index"] < physical["index"] < retired["index"] < end and
            begun["phase"] == 1 and begun["related"] and physical["related"] == begun["related"] and
            physical["phase"] == 2 and not physical["result"] and retired["phase"] == 6 and
            retired["owner_task"] == executor and retired["result"] == request["result"] and
            not any(retired[key] for key in ("source_user", "return_user", "notifier")),
            "release route, physical ACK or exact user retirement differs")
    require(request["index"] < handled["index"] < begun["index"] and handled["phase"] == 4 and
            handled["task"] == executor and handled["result"] == request["result"] and
            physical["index"] < source_drop["index"] < retired["index"] and
            source_drop["source_user"] == bound["source_user"] and source_drop["phase"] == 5 and
            stopped["task"] == executor and stopped["owner_task"] == executor and
            stopped["object"] == gate and stopped["index"] < owner_end["index"],
            "owner handling, exact source-user drop or stopped control is unproved")
    return_drops = [row for row in owner_rows if row["kind"] == K["RELEASE_RETURN_DROP"] and same(row) and row["related"] == release]
    if bound["return_user"]:
        require(len(return_drops) == 1 and return_drops[0]["return_user"] == bound["return_user"] and
                grant["index"] < return_drops[0]["index"] < retired["index"],
                "exact return-user retirement missing")
    if path == "munmap_retained":
        require(request["index"] < begun["index"] < physical["index"] < operation["index"],
                "retained up_read was accepted before its physical ACK")
    free = records[end] if end < len(records) else None
    require(free is not None and free["kind"] == K["SLOT_FREE"] and
            all(free[key] == reserve[key] for key in ("owner", "related", "parent", "state", "node", "acquisition", "origin")) and
            free["phase"] == 3 and free["object"] == gate and
            free["flags"] & (1 | 2 | 4 | 8 | 32 | 64 | 2048) == (1 | 2 | 4 | 8 | 32 | 64 | 2048) and
            not free["flags"] & 16 and not any(free[key] for key in ("source_user", "return_user", "notifier")),
            "matching request has not completed exact slot retirement before reuse")
    queued = [row for row in slot if row["kind"] == K["QUEUE_DONE"]]
    ready = [row for row in slot if row["kind"] == K["NODE_RETIRE_READY"]]
    require(len(queued) == len(ready) == 1 and reserve["index"] < queued[0]["index"] <= ready[0]["index"] < end and
            retired["index"] <= ready[0]["index"] and ready[0]["phase"] == 6 and
            ready[0]["flags"] & (1 | 4 | 8) == (1 | 4 | 8) and not ready[0]["flags"] & 16 and
            ready[0]["owner"] == owner and ready[0]["owner_task"] == executor and ready[0]["object"] == gate and
            ready[0]["related"] == release and
            not any(ready[0][key] for key in ("source_user", "return_user", "notifier")),
            "queue/node retirement is missing, repeated or out of order")
    return {"release_bind": bound, "request": request, "physical_begin": begun, "physical_end": physical,
            "release_handled": handled, "source_drop": source_drop, "return_drops": return_drops,
            "release_retire": retired, "owner_stop": stopped, "owner_retire": owner_end, "queue_done": queued[0],
            "node_retire_ready": ready[0], "slot_free": free}
