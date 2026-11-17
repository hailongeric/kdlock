# Bounded ordinary-waiter service review

Reviewed commit `449078ff0199e2c1802a6bc7a73dbc81bce6092e` by static source
inspection on 380G10. No VM access, build or runtime test was performed by this
reviewer. No immediate ownership or node-lifetime defect was identified; this
is not a complete concurrency proof or runtime validation.

## Invariants checked

* Only the queue head changes links behind itself. It retains the physical
  grant while detaching an eligible ordinary waiter and serving a successor.
* The skipped ordinary node stays pinned and in WAIT. It receives no invented
  continuation and cannot retire until the head later promotes it.
* Every node initialization clears `plain_pass` and `passed`. Only ordinary
  spin queue paths use `probe=true`; raw paths cannot opt in. The `kc->depth`
  guard excludes a nested acquisition performed by an active executor:
  `kd_exec_one()` increments depth before `kd_nested_acquire()` and decrements
  it after the execution loop.
* Task context and enabled IRQs are required. The immediate successor needs
  an entry, compatible context and the combiner's NUMA node. A reschedule
  request prevents the extra reordering.
* Detachment consumes budget. The first ordinary pass establishes an eight
  queue-operation window, including the pass; `kd_batch` remains an independent
  bound. Multiple distinct ordinary nodes may be passed in that same window.
* Each ordinary node can be passed once for its entire queue lifetime. Its
  marker survives reinstatement. A handback restores the deferred prefix before
  publishing RESUME, so a subsequent grant cannot pass that node again.
* Existing deferred NUMA nodes keep their earlier order and can precede the
  ordinary node. The window therefore bounds added work under the current
  physical grant, not total waiting time or wall-clock latency.
* No fast-entry or unlock operation changes. Parameter default remains off.

Master already retains a per-CPU `mode_q/mode_deleg` hint across empty lock-byte
windows. The previous main baseline lacked that behavior. Its performance
figures and explanation cannot be imported as a current master baseline.

## Evidence still required

Report `delegated`, `handback`, `sessions`, `stop_plain`, `plain_deferred`,
`numa_deferred`, and relevant completion counters per measured cell. A nonzero
`plain_deferred` demonstrates taking the new branch, not successful execution
of the following foreign body by itself. Exact worker counts, shared count,
exclusion, normal teardown, and warning checks remain necessary.

Existing general/raw/nested/handback checks are useful regressions but do not
by themselves prove a deliberately ordered mixed raw/ordinary queue. A minimal
additional focused fixture can run a fixed-count mixture of (1) a normal spin
call site deliberately excluded from image publication and (2) an image-backed
call site on the same lock. Require exact shared and per-worker counts, no
overlap, positive plain deferrals with the option on, and zero plain deferrals
with it off. Separate variants replace the ordinary site with a raw or
IRQ-disabled site, and replace the image body with one that actually hands
back. Record actual branch and handback counts; zero means the desired case
was not demonstrated. This stress fixture would still not prove the exact
maximum number of bodies between a particular pass and promotion; that needs
an ordered fixture or a targeted event trace.
