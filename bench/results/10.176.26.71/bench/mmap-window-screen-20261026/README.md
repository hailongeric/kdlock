# Prepared-window screen stopped at Native admission

The authorized 16-worker Native/KD screen stopped on October 26, 2026
(Asia/Shanghai), before any payload or timing. After the installed Native
candidate boot, the first full admission capture contained **82 QEMU tasks**.
The reviewed empty role manifest admitted only the original 67. All 15 extra
tasks were named `worker`, in state `S`, with affinity CPU 63. This single
observation neither proves inactivity nor identifies their creation cause.
No role was added, no admission was retried and no KD boot followed.

This attempt also **omitted settling after the guest idle check**. The
historical procedure required 60 seconds; later user instructions require
90 seconds. The attempt met neither and is retained as an execution failure. It cannot
establish that properly settled admission would fail or pass. No later quiet
observation can qualify this attempt.

## Inputs and completed preparation

- Source/tooling: `b42db2718d8bbac4e1b8fff20749f368f17f3b71`; reviewed commands
  and documentation: `aecd5d0b915a7ebb03c01d3f44165424d07b0d97`.
- Lock implementation and mmap overlay remain the audited `e6fc371` bytes.
  The earlier 137 Native / 161 KD actual mmap assertions and 352 standalone
  assertions plus two basic tests are separate evidence, not rerun here.
- Installed candidate: `6.1.159-kdmm31`, Build ID
  `ef5179e8def44f0255adcd62585f62f118fee30f`, image SHA-256
  `17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040`.
  No kernel was built or installed. Native selected `kd_mmap=off`.
- Reused unchanged build-3 payload and fixed client, bound by receipt SHA-256
  `34dcfa933162bcd068e340a8abd0b140ef9cd432bd9502de7aaca79377f8f2e0`.
  Only the controlled timed userspace client was rebuilt, with
  `gcc -O2 -g -Wall -Wextra -Werror -pthread`; its build-only receipt passed.
- Empty role manifest SHA-256:
  `4f0bd1486aadb5fae237421e8d976cf74ca5b10e1c1e845d0c88087255b580cb`.
  Initial recovery capture passed with 67 tasks before source sync/preparation.
  It was not reused as candidate admission.
- The idle source sync verified 347 selected files, including private `.inc`
  files, and copied 19 changed files. It excluded Markdown and the unrelated
  cleanup README edit. The guest tree was verified directly; this is not a
  claim that the benchmark host mirror was refreshed.

The first preparation launcher kept its own guest evidence log descriptor open.
The unchanged idle check rejected `/proc/12490/fd/3` before compilation. Parent
and child exited with status 1; no completion was uncertain. The corrected
invocation logged on the source host, used a new `client-build-2` directory and
exited 0. Both attempts remain preserved. The separate
[offline checkpoint](../../tests/mmap-window-20261026/README.md) passed 85
focused Python tests, 21 C transport assertions and two basic programs; none
is a measurement-window runtime pass.

## Rejected capture and settling evidence

Native boot ID: `9ac58480-830a-47f2-917b-adea05477e55`. The candidate had the
expected 68 modules, taint 4096, voluntary preemption, CPUs 0–63 and an empty
pending boot entry. The idle check passed. At
`2026-10-25T18:37:05.851740+00:00`, the host capture completed with all original
tasks plus TIDs `553976`, `553977`, and `553983`–`553995`.
Their captured cumulative CPU runtimes ranged from 9,241,870 to 96,555,911 ns;
timeslice counts ranged from 255 to 3,561. There is no paired activity interval
for these tasks. The host capture's `passed` field describes complete identity,
snapshot and placement capture; it does not admit these unreviewed roles.

The local empty-manifest check rejected 82 tasks before generating the
admission-copy request. The subsequent missing-request-file error launched
no SSH command. Neither `paired.py ready` nor the window observer ran.

The retained Native journal implies boot time approximately
`18:36:48.279275 UTC`, about **17.572465 seconds** before the capture. This is
guest journal realtime minus monotonic time, compared with the host clock;
it is not a synchronized boot-to-capture timing measurement. Source receipt
mtime and controller dispatch imply only **8.063903 seconds** after the idle
transport completed. There was no explicit settling receipt. The initial
review recorded the historical 60-second requirement; the separate
`settling-instruction-addendum.json` records the later 90-second requirement
without rewriting that review. The
first journal lookup used an unsupported hyphenated boot-ID spelling and
failed; the corrected read-only lookup and both outcomes are retained.

## Scope consumed and recovery

| Operation | Actual | Authorized maximum |
| --- | ---: | ---: |
| Boots | 2: Native, recovery | 3 |
| Full host captures | 3: initial, rejected Native, final recovery | 8 |
| Payload load/run/unload cycles | 0 | 4 |
| Fixed proofs / timed sessions | 0 / 0 | 2 / 2 |
| Window observers / samples | 0 / 0 | 2 / 194 |

Recovery identity passed at `2026-10-25T18:39:30.630828+00:00`:
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`b632d1e3-8c42-4f58-a7f5-053d063959fa`. Normal `modprobe` restored only the
missing original `nfnetlink` and `tls`; all original 73 modules were present,
taint was zero, `next_entry` was empty and the recovery default was unchanged.
CPU/boot/preemption policy matched, the fault scan and idle checks passed, and
no workload or uncertain command remained. No unrelated module was unloaded.
The final recovery host capture passed after 110.886491 seconds without guest
commands, recorded 68 QEMU tasks and confirmed the recovery snapshot remained
listed. It is recovery
evidence only and cannot qualify the failed Native admission.

## Retained evidence and next step

Source-host raw evidence is under
`bench/results/10.176.26.71/raw/bench/mmap-window-screen-20261026/`.
Guest preparation evidence remains under
`/root/kdlock-evidence/10.176.26.71/bench/mmap-window-screen-20261026/`.
The 78,392-byte guest archive SHA-256 is
`b3f31f10ed3ee2ec48d0b576c1fdde572103f18532d76627c90c6b05540476fe`.
Read-only archive inspection verified its 21 members, exact preparation receipt
and timed executable hash. The raw file inventory is bound by
`evidence-manifest.json`, SHA-256
`a61e16db07214b149a32b3acd553f46b01d410eb58493507cbe84ce4b019d451`.

Raw records include the exact command/request JSON, transport outcomes,
source manifest, prepared sources and executable, both host admissions,
`screen-rejection.json`, `settling-review.json`, recovery checks and scope
accounting. The [maintained runner guide](../../../../mmap_lock/README.md#small-matched-validation-screen)
provides the bounded procedure; it now explicitly records the existing settling
step. Historical rejected captures remain unchanged.

Accepted throughput count is zero; no latency, variability, bottleneck or
optimization gain was measured. The next useful step is to correct admission
preparation and establish reviewed role evidence before another explicitly
authorized small pair. Do not expand the workload or run the 126-session matrix
to work around this refusal.

## Offline admission review and proposed next scope

This section is a proposal, not a new role approval or live-run authorization.
It uses the retained captures and current source; no further VM command or
test followed the final recovery capture.

| Exact gate | Current behavior |
| --- | --- |
| `paired.py:host_check`, legacy branch | Requires the complete original 67-task projection. Preserve this historical policy. |
| `window_controller.py:inventory`; `window.py:core_inventory` | Require the original 64 vCPUs and three service tasks, but allow additional tasks for separate classification. |
| `window.py:resolve_roles` | Matches every extra task against exactly one reviewed `comm`/CPU63 selector. An empty manifest rejects every extra task. |
| `window.py:check_samples` | Requires observed `(tid,start_ticks)` keys to equal the core plus the roles resolved at the first guard scan. Addition, retirement or replacement then rejects the window. |
| `window_host.py:sample`; `host_capture_control.py:capture` | Require complete, consistent reads within each scan. Preserve these failures rather than hiding a disappearing task. |

The actual early stop was the launch command's local
`assert d['passed'] and len(d['qemu'][0]['tasks']) == 67`, before copying
admission. The prepared-window harness did not run. Its empty role manifest
would independently reject these extra tasks at `resolve_roles`; the full
capture itself had passed. The 67 checks in the window core functions are not
total-task limits.

The existing `expected_service` class can represent a variable-size QEMU worker
pool **between preparations**: one selector can match several TIDs, and each
arm resolves its own identities. It already permits recorded CPU/scheduling/I/O
activity. It cannot represent membership changes **inside** the guard/window.
No saved prepared measurement window demonstrates a need to change that
lifetime rule: this attempt stopped before preparation, and the earlier
diagnostic observed guest-control phases rather than a held workload window.

The minimum proposed next change therefore uses the existing class. Review a
prospective selector for `worker`, affinity `[63]`, class `expected_service`,
bound to the retained QEMU process/configuration evidence. The comparison would
explicitly include that VM's service-worker activity. Evidence must establish
membership in the exact QEMU process and the same configuration/placement in
both arms; it need not identify the guest request behind every I/O operation.
The capture records two unchanged qcow2 drives and the QEMU process identity;
it does not identify a specific worker callback. A name, sleep state or nonzero
counter alone is neither role proof nor proof of contamination.

Exact proposed patch/test scope:

1. `window_controller.py`: use the existing role resolver on the admission
   inventory before launching guest preparation. This checks eligibility early;
   the observer still resolves and freezes actual identities after preparation.
   Replace the manual total-count assertion with core plus reviewed-role checks.
2. One reviewed role-evidence record and manifest, identical for Native/KD;
   runner documentation records the required **90 seconds after the idle check**.
   Record actual monotonic elapsed time once; a failed capture is not retried.
3. Extend `test_mmap_window.py` with focused checks for several eligible workers
   with different setup TIDs/counts in each arm, and refusal before guest launch
   for missing/ambiguous roles or wrong affinity. Retain the existing activity,
   frozen-lifetime, core-identity, partial-read, gap and legacy-policy tests.
   Run this directly affected module plus the two basic programs in the VM.
   No client, payload, kernel, report schema or new observer framework is needed.

If reviewed requirements instead permit worker births/deaths inside the timed
window, that is a separate change to `window.py`, `window_host.py` and
`window_replay.py`: resolve eligible extras per complete scan; preserve exact
core identities; keep counters monotonic per lifetime; record births, departures
and the incomplete counter coverage of departed workers. The current
fixed-cardinality `final_deltas` slice would also need replacement. Do not simply
remove the inventory equality assertion or infer complete activity totals from
polling. That extension is not implemented or required by this proposed first
step.

Retain single-owner and guest-idle checks, matched image/configuration, CPU/NUMA
placement, prepared workload and instrumentation. Known competing work rejects
admission regardless of its name. The QEMU-only window does not detect arbitrary
non-QEMU host workloads; it cannot substitute for an independent host isolation
and competing-job check. No claim that those jobs are absent follows from a
`worker` role match. Wrong topology/pins, missing core tasks, changed QEMU
identity, unknown roles or incomplete reads still reject the run.

Under the proposed rule the 82-task capture could establish selector eligibility
only after explicit review; its missing settling/readiness/window still prevents
acceptance. Diagnostic TID 553662's positive counters rule out an inactive role,
but do not by themselves rule out an expected service role. That diagnostic
remains incomplete and rejected. The final 68-task recovery capture cannot
retroactively qualify either attempt.

After review, the proposed next live attempt is the same bounded 16-worker
screen: reuse the existing payload, fixed client and new timed binary; one
Native arm, one KD arm, then recovery; maximum three boots, eight full captures,
four payload cycles, two fixed proofs, two timed sessions and two observers
(194 scans maximum). No retry, kernel build/install or new workload. Report
both rates, role activity and their ratio as one unscored pair, with variability
explicitly unavailable at n=1. A performance conclusion requires a separately
bounded repeated paired run with all per-trial rates, ratios, range and sample
CV; no such run or extension of this screen is authorized here.
