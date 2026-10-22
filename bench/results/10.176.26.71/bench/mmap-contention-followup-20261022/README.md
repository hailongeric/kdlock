# Pending-admission mmap diagnostic continuation, 2026-10-22

Status: focused checks passed; original admission-only coordinator retired with
explicit approval; preparing the same-boot settling continuation, `pair-2`.
Main agent only writes and executes VM work; helpers remain read-only. Start
from clean `a03204f`. The same VM was freshly verified idle on recovery
`6.1.159-kdclobber2`, boot `68924d08-9913-4e43-91f8-3643e3331c09`, with exactly
73 modules and all 5,686 recovery module files preserved. The real recovery
snapshot and original pins were verified. Source process checks found no
observed competing writable checkout descriptors; inaccessible processes and
the absence of an application task registry are recorded limits.

All eight prior contention-stage archives and all 31 earlier archives remain
unchanged. The original `pair-1` refusal at 72 versus 67 and both unrun profiles
stay fixed in the [preceding report](../mmap-contention-20261022/README.md).

## Continuation contract

Only repository-side coordination changes. Keep the guest profiler, candidate
image, validated workload/payload, original full admission and fixed endpoint
checks unchanged. Run one Native then one KD profile, serially. Concurrent
readers stay local; mmap stays separate from fault cycles. TCLock actual-MM
workloads remain excluded. New p95 is deferred and earlier latency evidence
remains fixed.

After each candidate boot, a refused capture with only extra worker threads
is pending admission. Preserve every capture and remain on that same boot.
Observe at least 60 seconds apart, with fresh source ownership and guest drain
checks before each observation. Original task identities, affinity, all host
controls and the complete guest gate must pass before a profile starts. A
count alone never grants admission. No observation count grants acceptance or
declares a persistent blocker. Other changes require diagnosis; no host
settings, services, networking, credentials or access controls may change.

The original guest driver performs the complete admission immediately before
loading. The source controller preserves the immediate endpoint after recorder
exit including flush, before validation and normal unload. Later captures can
admit a distinct unrun mode; they never replace an endpoint or rerun a completed
profile. Record observation, profile-command attempt, actual completion, mode,
boot and endpoint separately. A timeout retains uncertain state and prevents
another run or automatic reboot.

Once both profiles complete and drain, seal/review their evidence and restore
recovery. If a specifically established persistent condition prevents progress,
retain its duration/evidence and exact missing condition, verify drain before
restoring recovery, and report it. A first transient refusal is not completion.

The predeclared source hypothesis and stack interpretation from the preceding
stage still apply. Filter exact worker TIDs/CPUs and active intervals; separate
leaf symbols from supported caller ancestry, account globally for loss/throttle
and unresolved frames, and retain profiler configuration and overhead limits.
One sampled pair supplies intrusive diagnostic evidence, not accepted plain
throughput, repetition variance or an isolated protocol-cost proof. All 24 prior
timings remain rejected and all seven original causes remain unresolved unless
new demonstrated evidence resolves a specific claim.

## Focused checks before transition

Synchronization of `601541e` copied 18 changed files, verified all 4,060 tracked
hashes and deleted no project files. The frozen `checks-1` contains 198 source
files, including private daemon `.inc` files and both admission helper/test
files. In the same recovery boot, both basic C programs and all five directly
affected pending-admission tests passed; dependency validation passed. The
daemon-policy test's deliberately failed children are expected negative cases.
No full suite ran. The unchanged guest profiler's four and serial driver's ten
focused tests remain the separately recorded preceding-stage evidence.

The new checks result SHA-256 is
`fbcf9f3b7ba530280781f3616925bca49c830e3ae03cc74b657f812daff82836`.
Exact baseline modules, idle state, recovery preservation and no fault-pattern
matches were rechecked before archiving. Local evidence is under
`bench/results/10.176.26.71/raw/bench/mmap-contention-followup-20261022/`;
guest evidence is under the corresponding
`/root/kdlock-evidence/10.176.26.71/bench/mmap-contention-followup-20261022/`.
The `pretransition/archives/archives.json` SHA-256 is
`827bba69b1d461e1e086e596039820942a38364d9fa3e32c4c99ae1e76219cd0`;
its two archives total 519,757 bytes. All 39 earlier archives remain separate.

Read-only protocol review found no blocker to the first attempt. On a guest
refusal, `ADMISSION` alone does not prove no payload loaded: retain the exact
trace and verify launch state plus fresh drain. Resume a returned recorder only
through its existing finish step and original endpoint; never repeat a
completed profile. All source files stay frozen while the pair controller runs.

## Approved retirement and settling continuation

The original follow-up `pair-1` retained 434 pending observations over roughly
7 hours 27 minutes. Neither profile was attempted. The user explicitly approved
retiring only the waiting coordinator and resuming on the same Native boot with
60 seconds settling after every guest idle check. No admission criterion changes.

At `2026-10-22T02:57:30.280546Z`, a parent-only pidfd SIGINT retired coordinator
PID 792734 (start ticks 970588747). The traceback locates interruption in
`admission_wait.wait` at `sleep(interval)`; its tool session returned 130. The
process and its command chain exited. All 880 original command receipts report
EXITED/0, and the final state records zero profile attempts and completions.
The old `KeyboardInterrupt()` and `drain_requires_review` state remain fixed;
subsequent drain proof is separate. The signal was observed about 0.216 seconds
after the latest pending branch, not claimed to have an atomic timing guarantee.
No workload, recorder, process group or VM worker received a signal.

Fresh guest idle and preservation checks then passed on unchanged Native boot
`89400671-89e1-4797-b703-70cb4ac71c67`, release `6.1.159-kdmm1`, `kd_mmap=off`,
with exactly 73 baseline modules and no profiler or mmap/fault workers. The
candidate, recovery/default boot configuration and all 5,686 recovery module
files remain preserved. `control-stop-1.json` binds the retirement, final pair
state, command receipts and fresh checks; SHA-256:
`e66d9493141afff777563b65ce2e84abd9711128858b302be80c686c7a781dd1`.
The original final `pair-1/result.json` SHA-256 remains
`4a6aa252b8ad9f8344230cc8fc5f8d45d3aa7575585136bdab1bd9aa67fb8e39`.

`run_pair_resume.py` creates separate `pair-2` source evidence and `native-2`,
`kd-2`, `recovery-2` guest blocks. It requires the stopped coordinator's exact
receipt, absent old process, zero prior attempts, fresh idle and unchanged
Native boot. The copied original transition/request/host-capture hash chain
retains that boot's provenance. Every new observation follows a guest idle
check, a recorded 60-second settling interval, a source ownership check and the
unchanged complete host capture. Extra-thread refusals remain pending; the
original complete guest gate still runs before loading. The guest profiler,
frozen inputs, candidate image, recording settings and immediate endpoint are
unchanged. Only the source coordinator and this report change; no guest source
synchronization or new workload build is needed.

The source coordinator is reviewed statically. Existing focused VM checks cover
the unchanged admission helper and recording/endpoint drivers; they do not claim
to test the new same-boot orchestration. The new run must retain its actual
admission, command, endpoint, completion, drain and recovery receipts. This
continuation is not performance acceptance; all seven original causes remain
unresolved.
