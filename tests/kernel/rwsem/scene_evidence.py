"""Exact scene 6 prelude and queue ordering, independent of generated-body proof."""

from .ordinary_evidence import ORDINARY, ordinary_lifetimes


def one(rows, predicate, description):
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        raise AssertionError("scene 6 lacks unique exact " + description)
    return matches[0]


def same_request(row, request):
    return all(row[field] == request[field]
               for field in ("state", "origin", "node", "acquisition"))


def offered_request(rows, has, task, object_a, image):
    # A withdrawn combiner later rejoins as SELECTED_LOCAL. The first request,
    # including its offer identity, must precede that separate queue visit.
    requests = [row for row in rows if has(row, "ENQUEUE") and row["origin"] == task
                and row["task"] == task and row["object"] == object_a]
    if not requests:
        raise AssertionError("scene 6 lacks a managed writer request")
    request = requests[0]
    if (request["phase"] != 1 or request["flags"] != 17
            or not all(request[field] for field in ("state", "node", "acquisition"))):
        raise AssertionError("scene 6 writer was not an exact offered request")
    if any(not same_request(row, request) or row["phase"] != 2 for row in requests[1:]):
        raise AssertionError("scene 6 writer changed identity or republished its offer")
    prior = [row for row in rows if row["index"] < request["index"]]
    reserve = one(prior, lambda row: has(row, "SLOT_RESERVE") and same_request(row, request)
                  and row["task"] == task, "writer reservation")
    prepared = one(prior, lambda row: has(row, "FRAME_PREPARE") and same_request(row, request)
                   and row["task"] == task and row["image"] == image and image
                   and row["phase"] == 3, "admitted writer frame")
    if (reserve["phase"] != 1 or reserve["parent"] != request["acquisition"]
            or not reserve["owner"] or not reserve["related"]
            or not reserve["index"] < prepared["index"] < request["index"]
            or any(has(row, "SLOT_FREE") and same_request(row, request) for row in prior)):
        raise AssertionError("scene 6 writer escaped its reserved frame lifetime")
    return request


def scene6_prelude(rows, has, tasks, object_a, image):
    """H_B's ordinary read forces H_A into the actual managed writer queue."""
    acquired = one(rows, lambda row: has(row, "READ_ACQUIRE") and row["task"] == tasks[1]
                   and row["origin"] == tasks[1] and row["object"] == object_a,
                   "ordinary prelude acquisition")
    done = one(rows, lambda row: has(row, "ORDINARY_RWSEM_DONE")
               and row["index"] > acquired["index"]
               and all(row[field] == acquired[field] for field in
                       ("task", "origin", "state", "object", "acquisition", "related")),
               "ordinary prelude completion")
    # H_B may reuse its ordinary record for B immediately after DONE. Validate
    # this completed read prefix without treating the later live write as done.
    prefix = [row for row in rows if row["index"] <= done["index"]]
    ordinary = ordinary_lifetimes(prefix, has)
    reads = [pair for pair in ordinary["reads"] if pair["acquire"] == acquired]
    if len(reads) != 1 or acquired["flags"] != ORDINARY:
        raise AssertionError("scene 6 prelude did not retain one ordinary read")
    reader = reads[0]
    holder = offered_request(rows, has, tasks[0], object_a, image)
    selected = one(rows, lambda row: has(row, "SELECT_LOCAL") and same_request(row, holder)
                   and row["task"] == tasks[0] and row["object"] == object_a
                   and row["owner_task"] == tasks[0] and row["owner"]
                   and row["phase"] == 2, "holder local selection")
    grant = one(rows, lambda row: has(row, "GRANT") and same_request(row, holder)
                and row["task"] == tasks[0] and row["object"] == object_a
                and row["owner_task"] == tasks[0] and row["owner"] == selected["owner"]
                and row["related"] and row["flags"] & 2, "holder physical grant")
    if (holder["related"] or not acquired["index"] < holder["index"]
            < reader["release"]["index"] < selected["index"] < grant["index"]):
        raise AssertionError("scene 6 holder was not queued behind the held prelude read")
    return dict(reader=reader, holder=holder, selected=selected, grant=grant)


def scene6_ordering(rows, has, tasks, object_a, image, *, before_release):
    """Prove H_A -> C_A -> W while H_A holds A, then its exact handoff."""
    proof = scene6_prelude(rows, has, tasks, object_a, image)
    holder, grant = proof["holder"], proof["grant"]
    candidate = offered_request(rows, has, tasks[2], object_a, image)
    waiter = offered_request(rows, has, tasks[4], object_a, image)
    if (candidate["related"] != holder["node"] or waiter["related"] != candidate["node"]
            or any(len({row[field] for row in (holder, candidate, waiter)}) != 3
                   for field in ("state", "node", "acquisition"))
            or not max(grant["index"], proof["reader"]["free"]["index"])
            < candidate["index"] < waiter["index"]):
        raise AssertionError("scene 6 did not establish the exact held H_A -> C_A -> W queue")
    proof.update(candidate=candidate, waiter=waiter)
    releases = [row for row in rows if has(row, "RELEASE_REQUEST")
                and row["state"] == holder["state"] and row["acquisition"] == holder["acquisition"]]
    ended = [row for row in rows if (has(row, "PHYSICAL_BEGIN") or has(row, "PHYSICAL_END"))
             and row["owner"] == grant["owner"]]
    departures = [row for row in rows if has(row, "QUEUE_DONE") and same_request(row, holder)]
    selections = [row for row in rows if (has(row, "SELECT_LOCAL") or has(row, "SELECT_PROXY"))
                  and (same_request(row, candidate) or same_request(row, waiter))]
    if before_release:
        if releases or ended or departures or selections:
            raise AssertionError("scene 6 holder or successor advanced before the release gate")
        return proof
    released = one(releases, lambda row: row["owner"] == grant["owner"]
                   and row["related"] == grant["related"] and row["object"] == object_a
                   and row["task"] == tasks[0] and row["owner_task"] == tasks[0]
                   and row["phase"] == 1,
                   "holder release request")
    departed = one(departures, lambda row: row["related"] == candidate["node"]
                   and row["owner"] == grant["owner"] and row["object"] == object_a
                   and row["task"] == tasks[0] and row["owner_task"] == tasks[0]
                   and row["phase"] == 2 and row["flags"] & 4,
                   "holder queue handoff")
    selected = one(selections, lambda row: has(row, "SELECT_PROXY") and same_request(row, waiter)
                   and row["task"] == tasks[2] and row["owner_task"] == tasks[2]
                   and row["object"] == object_a and row["related"] == candidate["node"]
                   and row["phase"] == 3, "C_A selection of W")
    if (not waiter["index"] < released["index"] < departed["index"] < selected["index"]
            or any(row["index"] <= waiter["index"] for row in ended)
            or any(row["index"] < departed["index"] for row in selections)):
        raise AssertionError("scene 6 queue advanced before the complete offer chain")
    proof.update(released=released, departed=departed, proxy_selected=selected)
    return proof
