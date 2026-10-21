#!/usr/bin/env python3
"""Wait for unchanged host admission without turning an observation into a pass.

Only extra worker threads with the original task set and every other host
control intact are treated as pending. No observation limit grants admission
or declares a blocker. The caller still runs the complete guest gate freshly.
"""
import copy
import time


def classify(original, host, screen):
    reason = screen(original, host)
    if reason is None:
        return 'HOST_PREREQUISITE_PASSED', None
    if reason != 'strict original QEMU task set differs':
        return 'REQUIRES_REVIEW', reason
    before = {task['tid']:task for task in original['qemu'][0]['tasks']}
    after = {task['tid']:task for task in host['qemu'][0]['tasks']}
    if (len(after) != len(host['qemu'][0]['tasks']) or
            any(after.get(tid) != task for tid,task in before.items())):
        return 'REQUIRES_REVIEW', 'original QEMU task identity or placement changed'
    extras = [task for tid,task in after.items() if tid not in before]
    if not extras or any(task['comm'] != 'worker' or task['affinity'] != [63] for task in extras):
        return 'REQUIRES_REVIEW', 'unexpected extra QEMU task or placement'
    # This copy diagnoses why the original gate refused. It is never returned
    # as admitted evidence, and the real capture remains unchanged on disk.
    diagnostic = copy.deepcopy(host)
    diagnostic['qemu'][0]['tasks'] = list(before.values())
    if screen(original, diagnostic) is not None:
        return 'REQUIRES_REVIEW', 'additional host control differs'
    return 'PENDING_EXTRA_WORKERS', reason


def wait(original, observe, screen, record, *, interval=60,
         sleep=time.sleep, monotonic=time.monotonic):
    if interval < 60:
        raise ValueError('read-only observations must be at least sixty seconds apart')
    started = monotonic()
    attempt = 0
    while True:
        attempt += 1
        path, host, digest = observe(attempt)
        state, reason = classify(original, host, screen)
        row = dict(attempt=attempt, state=state, reason=reason, path=str(path),
                   host_sha256=digest, captured_utc=host['captured_utc'],
                   elapsed_seconds=monotonic()-started,
                   threads=len(host['qemu'][0]['tasks']), full_guest_admission=False)
        record(row)
        if state == 'HOST_PREREQUISITE_PASSED':
            return path
        if state != 'PENDING_EXTRA_WORKERS':
            raise RuntimeError('admission requires review: '+str(reason))
        sleep(interval)
