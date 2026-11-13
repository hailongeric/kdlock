"""Exact ordinary rwsem lifetimes; no managed reservation is synthesized."""

ORDINARY = 1 << 14
ENQUEUED, QUEUE_DONE, RETIRABLE = 1, 4, 1 << 11
IDENTITY = ("state", "origin", "task", "object", "acquisition", "related")
ORDINARY_KINDS = ("READ_ACQUIRE", "READ_RELEASE", "NATIVE_WRITE_ACQUIRE", "NATIVE_WRITE_RELEASE",
                  "NATIVE_DOWNGRADE", "NATIVE_READ_RELEASE", "ORDINARY_RWSEM_DONE")


def ordinary_event(row, has):
    # JIT_EXIT uses flags for exit detail, not the observation flag namespace.
    return has(row, "ORDINARY_RWSEM_DONE") or (row["flags"] & ORDINARY and
            any(has(row, name) for name in ORDINARY_KINDS))


def queued_retirement(rows, has, record, done):
    acquired, released = record["acquire"], record["release"]
    scope = [row for row in rows if record["start"] < row["index"] < done["index"]]

    def one(name, predicate):
        found = [row for row in scope if has(row, name) and predicate(row)]
        if len(found) != 1:
            raise AssertionError("ordinary writer lacks unique exact " + name)
        return found[0]

    def node(row):
        return all(row[field] == acquired[field] for field in ("task", "node", "acquisition", "object"))

    def owner(row):
        return row["owner"] == acquired["owner"] and row["task"] == acquired["task"]

    enqueue = one("ENQUEUE", node)
    selected = one("SELECT_LOCAL", node)
    departed = one("QUEUE_DONE", node)
    begin = one("PHYSICAL_BEGIN", owner)
    end = one("PHYSICAL_END", owner)
    retired = one("OWNER_RETIRE", owner)
    for row in (enqueue, selected, departed, begin, end, retired):
        if any(row[field] for field in ("state", "origin", "image", "parent", "source_user", "return_user", "notifier", "result")):
            raise AssertionError("ordinary writer queue manufactured a managed source lifetime")
    if (enqueue["flags"] != ENQUEUED or enqueue["owner"] or enqueue["owner_task"]
            or selected["flags"] != ENQUEUED or departed["flags"] != ENQUEUED | QUEUE_DONE
            or any(row["phase"] != 2 for row in (enqueue, selected, departed))
            or any(row["owner"] != acquired["owner"] or row["owner_task"] != acquired["task"]
                   for row in (selected, departed, begin, end, retired))
            or selected["related"] != acquired["node"]
            or begin["object"] != acquired["object"] or end["object"] != acquired["object"]
            or not begin["related"] or end["related"] != begin["related"]
            or (begin["phase"], end["phase"], retired["phase"]) != (1, 2, 3)
            or not enqueue["index"] < selected["index"] < acquired["index"] < released["index"]
            < begin["index"] < departed["index"] < end["index"] < retired["index"] < done["index"]):
        raise AssertionError("ordinary writer physical/queue retirement differs")
    if record.get("read_release") and retired["index"] >= record["read_release"]["index"]:
        raise AssertionError("ordinary downgrade returned before its own queue retirement")
    return dict(enqueue=enqueue, selected=selected, begin=begin, departed=departed, end=end, retired=retired)


def ordinary_lifetimes(rows, has):
    """Pair native records through DONE, allowing unrelated successors before DONE.

    READ_RELEASE/WRITE_RELEASE are observations before atomic release. DONE is
    subsequent completion and permits record reuse; it is not the admission
    point of another task. Fixture body counters separately prove exclusion.
    """
    active, previous, reads, writes = {}, {}, [], []
    last_index = -1
    for row in rows:
        if row["index"] <= last_index:
            raise AssertionError("ordinary evidence is not in observation order")
        last_index = row["index"]
        if has(row, "SELECT_PROXY") or has(row, "JIT_ENTER"):
            owners = {record["acquire"]["origin"] for record in active.values()}
            if row["task"] in owners or row["origin"] in owners:
                raise AssertionError("ordinary held record lent or served a generated continuation")
        if not ordinary_event(row, has):
            if row["acquisition"] in active and any(has(row, name) for name in ORDINARY_KINDS):
                raise AssertionError("ordinary record changed its observation class")
            continue
        kind = next((name for name in ORDINARY_KINDS if has(row, name)), None)
        if (kind is None or not all(row[field] for field in IDENTITY)
                or row["task"] != row["origin"] or row["related"] != row["acquisition"]
                or any(row[field] for field in ("image", "parent", "ip", "result", "return_user", "notifier"))):
            raise AssertionError("ordinary event lacks exact native record identity")
        key = row["acquisition"]
        if kind in ("READ_ACQUIRE", "NATIVE_WRITE_ACQUIRE"):
            if key in active:
                raise AssertionError("ordinary record reused before final completion")
            read = kind == "READ_ACQUIRE"
            queued = bool(row["flags"] & ENQUEUED)
            if (row["flags"] != ORDINARY | (ENQUEUED if queued else 0)
                    or row["phase"] != (1 if read else 0) or row["owner_task"] != row["task"]
                    or row["source_user"] != (0 if queued else key)
                    or (read and (queued or row["owner"] or row["node"]))
                    or (not read and (not row["owner"] or bool(row["node"]) != queued
                                      or (not queued and row["owner"] != key)))):
                raise AssertionError("ordinary acquisition has inconsistent read/write storage")
            active[key] = dict(acquire=row, read=read, queued=queued,
                               stage="read" if read else "write", start=previous.get(key, -1))
            continue
        record = active.get(key)
        if record is None or any(row[field] != record["acquire"][field] for field in IDENTITY):
            raise AssertionError("ordinary release/completion crossed its acquisition identity")
        acquired, queued = record["acquire"], record["queued"]
        if kind == "ORDINARY_RWSEM_DONE":
            flags = ORDINARY | (QUEUE_DONE | RETIRABLE if queued else 0)
            if (record["stage"] != "released" or row["flags"] != flags
                    or row["phase"] != (1 if record["read"] else 0)
                    or any(row[field] for field in ("owner", "owner_task", "node", "source_user", "cursor"))):
                raise AssertionError("ordinary record lacks final object/queue completion")
            proof = dict(acquire=acquired, release=record["release"], free=row,
                         ordinary_local=True, queued=queued)
            if queued:
                proof["queue"] = queued_retirement(rows, has, record, row)
            if record["read"]:
                reads.append(dict(proof, reserve=None))
            else:
                if "read_release" in record:
                    proof["read_release"] = record["read_release"]
                    reads.append(dict(reserve=None, acquire=record["release"],
                                      release=record["read_release"], free=row, ordinary_local=True,
                                      queued=queued, writer_acquire=acquired))
                writes.append(proof)
            previous[key] = row["index"]
            del active[key]
            continue
        if (row["flags"] != ORDINARY | (ENQUEUED if queued else 0)
                or row["owner_task"] != acquired["task"]
                or row["source_user"] != (0 if queued else key)):
            raise AssertionError("ordinary release changed its exact owner/user")
        if kind in ("NATIVE_WRITE_RELEASE", "NATIVE_DOWNGRADE"):
            if (record["stage"] != "write" or row["owner"] != acquired["owner"]
                    or row["node"] != acquired["node"]
                    or row["phase"] != (1 if queued and kind == "NATIVE_DOWNGRADE" else 0)):
                raise AssertionError("ordinary writer release/downgrade lost its write grant")
            record["release"] = row
            record["stage"] = "converted" if kind == "NATIVE_DOWNGRADE" else "released"
        elif kind in ("READ_RELEASE", "NATIVE_READ_RELEASE"):
            expected = "NATIVE_READ_RELEASE" if queued else "READ_RELEASE"
            if (record["stage"] not in ("read", "converted") or kind != expected
                    or row["phase"] != 1 or row["owner"] or row["node"]):
                raise AssertionError("ordinary read release lost its read or converted grant")
            record["read_release" if record["stage"] == "converted" else "release"] = row
            record["stage"] = "released"
        else:
            raise AssertionError("ordinary record has an unexpected lifetime transition")
    if active:
        raise AssertionError("ordinary record retained an acquisition without final completion")
    return dict(reads=reads, writes=writes)
