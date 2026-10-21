"""Bounded accounting-sample selection, never an environment admission gate."""
import hashlib
import json
import queue
import time

SECOND = 1000000000
WINDOW_NS = 120*SECOND
CAPTURE_BUDGET_NS = 25*SECOND
MAX_AGE_NS = 2*SECOND
COOLDOWN_NS = 15*SECOND


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def task_rows(tasks):
    rows = []
    identities = []
    for task in tasks:
        if (task['complete'] is not True or task['identity_matches'] is not True or
                task['identity_before'] != task['identity_after'] or
                task['identity_before'][0] != task['tid']):
            raise ValueError('incomplete or changing task identity')
        rows.append(dict(tid=task['tid'], comm=task['comm'], affinity=task['affinity']))
        identities.append(task['identity_before'])
    if len({r['tid'] for r in rows}) != len(rows):
        raise ValueError('duplicate task identity')
    return sorted(rows, key=lambda row: row['tid']), sorted(identities)


def reference(original, sample):
    expected = sorted(original, key=lambda row: row['tid'])
    wanted = {row['tid'] for row in expected}
    if len(expected) != 67 or len(wanted) != 67:
        raise ValueError('original reference must have exactly 67 unique tasks')
    rows, identities = task_rows([task for task in sample['tasks'] if task['tid'] in wanted])
    if rows != expected:
        raise ValueError('anchor sample differs from original tasks')
    return dict(tasks=rows, identities=identities, sample_sequence=sample['sequence'],
                sample_sha256=digest(sample))


def candidate(event, anchor, marker_ns, now_ns):
    """Local queue age and host scan age use their own clock domains."""
    sample = event['remote']
    if not sample['scan_began']['mono_ns'] <= sample['scan_finished']['mono_ns'] <= sample['mono_ns']:
        return 'invalid host scan clock order'
    if sample['scan_began']['mono_ns'] < marker_ns:
        return 'scan predates held marker'
    age = now_ns-event['received']['mono_ns']
    if not 0 <= age <= MAX_AGE_NS:
        return 'local queue residence exceeds two seconds or is negative'
    try:
        rows, identities = task_rows(sample['tasks'])
    except (KeyError, TypeError, ValueError) as error:
        return 'invalid task accounting: '+str(error)
    if rows != anchor['tasks'] or identities != anchor['identities']:
        return 'original exact task set, placement or lifetime differs'
    return None


def capture_age(trigger, remote):
    """A prompt request still needs a same-host-clock freshness check."""
    elapsed = remote['capture_began']['mono_ns']-trigger['scan_began_ns']
    return dict(qualified=0 <= elapsed <= MAX_AGE_NS, sample_to_capture_ns=elapsed,
                maximum_ns=MAX_AGE_NS)


def triggers(observer, anchor, marker_ns, began_ns, decisions, save,
             clock=time.monotonic_ns, sleep=time.sleep):
    """One queue consumer; at most four candidates plus a terminal capture.

    Capture ACK waits consume unmatched rows, which remain in observer.jsonl.
    They cannot become triggers. A candidate must start by 95 seconds, leaving
    its 25-second request budget before the terminal request at 120 seconds.
    The guest's unchanged 210-second hold timeout bounds lost coordination.
    """
    deadline = began_ns+WINDOW_NS
    latest_candidate = deadline-CAPTURE_BUDGET_NS
    next_allowed, previous, count = began_ns, -1, 0
    while clock() < latest_candidate and count < 4:
        try:
            event = observer.items.get(timeout=max(.001, min(6, (latest_candidate-clock())/SECOND)))
        except queue.Empty:
            continue
        if event is None or 'reader_error' in event:
            raise RuntimeError('observer ended or failed during held selection')
        sample = event['remote']
        if sample['event'] == 'complete':
            raise RuntimeError('observer expired during held selection')
        if sample['event'] != 'sample':
            raise RuntimeError('unsolicited observer message during held selection')
        now = clock()
        reason = candidate(event, anchor, marker_ns, now)
        if sample['sequence'] <= previous:
            reason = 'duplicate or reordered sample'
        previous = max(previous, sample['sequence'])
        if now < next_allowed:
            reason = 'capture refusal cooldown'
        if now >= latest_candidate:
            reason = 'candidate request window expired'
        decision = dict(sequence=sample['sequence'], sample_sha256=digest(sample),
            received_ns=event['received']['mono_ns'], decision_ns=now,
            scan_began_ns=sample['scan_began']['mono_ns'], scan_finished_ns=sample['scan_finished']['mono_ns'],
            task_count=len(sample['tasks']), candidate=reason is None, reason=reason)
        decisions.append(decision)
        save()
        if reason is None:
            yield dict(kind='sample', **decision)
            count += 1
            # Execution resumes only after the capture ACK and its validation;
            # cooldown therefore starts no earlier than refusal receipt.
            next_allowed = clock()+COOLDOWN_NS
    while clock() < deadline:
        sleep(max(0, min(60, (deadline-clock())/SECOND)))
    yield dict(kind='terminal', decision_ns=clock(), reason='bounded observation window ended')
