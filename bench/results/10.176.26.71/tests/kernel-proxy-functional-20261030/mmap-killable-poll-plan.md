# Local mmap writer admission: bounded source-only optimization review

Reviewed 2026-10-30 at candidate `e9ad910c45661170710aaf3051034a70a2700860`; the relevant KD/local-generator files remain unchanged in the later `ae170584` tree. This is a design review only: no edits to project source, no compilation, tests, VM access or measurements. It refines `/tmp/kdlock-mm-engineering-plan-20261030.md`, whose old statement that an mmap1 runner is missing is now historical: `bench/mmap1/run.py` and the separate identity probe have since been added.

## Recommendation

After preserving the new same-image Native/KD mmap1 baseline, try one isolated change: bounded **unpublished, preemptible phase-admission polling only in `kd_down_write_killable()`**. Keep its reservation predicate, physical mutex acquisition, reader-drain timeout loop, rollback, release and downgrade unchanged. Do not extend polling to reader drain, interruptible acquisition or ordinary/prepared writers in this candidate. There is a concrete scheduling-cost hypothesis, not evidence of a gain. Native being faster at all 21 historical localized points does not establish a result for the new kernel/image or explain its cause.

## Verified current path

- Ubuntu `mm/util.c:565–588`: `vm_mmap_pgoff()` takes `mmap_write_lock_killable()`, executes native `do_mmap()`, and unlocks. `mm/vma.c:3259–3274`: `__vm_munmap()` takes the same killable writer. A successful mapped unmap with `unlock=true` reaches `vms_complete_munmap_vmas():1311–1347`, downgrades at1321 and ultimately releases its read share at1347. Unmapping nothing or errors need not follow that same downgrade path. Preserve all paths rather than assuming every munmap downgrades.
- Captured `include/linux/mmap_lock.h:600–609,620–637`: successful write acquisition begins the per-VMA sequence; write unlock/downgrade invokes `vma_end_write_all()` before the backend operation. These bodies/order do not need modification.
- Project `kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c:66–96`: immutable per-object backend dispatch selects `kd_mmap_down_write_killable`, ordinary local release and downgrade; Native mode uses original rwsem operations.
- `kernel_integration/mmap_lock/prepare.py:41–92` namespaces the actual KD local primitives, changes only local unlock routing and removes the positive delegated-writer portion. New helper code before that removed section is generated automatically. This generator's retired Linux6 main is not an execution path for Linux7 preparation.
- `kernel_module/kd_rwsem.c:191–204`: local phase reservation requires admission0 **and no reader OSQ tail**, then the same fully ordered `cmpxchg(0,-1)`. Phase release occurs after physical unlock and uses ordered xchg plus wake. This is the exact exclusion authority; a polling count must never replace it.
- Ordinary local `kd_down_write():207–212` invokes the existing 16,384-probe polling macro at18–35 before publishing a phase waiter. `kd_down_write_killable():237–253` goes directly to `wait_event_killable` for phase admission, then the existing killable physical gate and reader drain. This means an immediate condition attempt is still made; it does **not** mean every killable acquisition parks.
- Killable drain at80–102 has an immediate zero-reader condition and, when needed, one-jiffy timeout waits. `kd_up_read():68–76` deliberately omits a waitqueue wake in IRQ-disabled/atomic context; the timer is essential to progress. With captured `CONFIG_HZ=1000`, one jiffy is nominally1ms, but timeout wake/scheduling latency is not bounded to1ms. A successful phase reservation is **not** permission to enter with readers remaining.
- Physical mutex `kd_mutex_local.c:273–315` already has its own fast attempt and optimistic OSQ slowpath. Once a local rwsem writer exclusively owns admission=-1, previous compliant writers released the physical gate before phase0; the gate often has no competing writer. This inference makes phase wait a more direct first target than tuning the already-existing mutex spin code, but needs measurements to establish actual cost.
- Downgrade `kd_rwsem.c:280–289` verifies admission=-1 and exact physical task ownership, publishes a reader, unlocks gate, then reopens phase. A later writer must still drain the downgraded reader. No change here is required by admission polling.

The captured Native Linux7 build has `CONFIG_RWSEM_SPIN_ON_OWNER=y`. Native `kernel/locking/rwsem.c:1311–1332` sends ordinary and killable writers through the same state-parametrized acquire. The writer slowpath at1117 tries optimistic spin **before** waiter publication at1131–1132. Its owner-aware OSQ spin at816–931 is not equivalent to KD's proposed all-entrant bounded phase polling: Native serializes optimistic spinners, checks running writer state, and limits reader-owned spinning. Do not describe the proposed16384 probes as reproducing Native's algorithm.

## Smallest safe helper and ordering

Use a private typed helper, optionally `__always_inline` to retain a short uncontended path, called only from killable writer admission. It returns a Boolean reservation result, not an errno:

1. Try the unchanged `kd_rwsem_reserve_local(sem)` exactly once for this iteration. If it succeeds, return true immediately; never test that side-effecting predicate again.
2. Only after a failed attempt, stop polling for `need_resched()` or `signal_pending_state(TASK_KILLABLE,current)`.
3. Otherwise `cpu_relax()` and decrement a fixed positive budget, initially the existing16384-probe bound as an isolated hypothesis.
4. On every false result (budget, reschedule or signal), use the **existing** `wait_event_killable(sem->phase_wait, kd_rwsem_reserve_local(sem))`. Preserve its negative result mapping to `-EINTR` and all later gate/drain/rollback code.

Do not return a new immediate `-EINTR` from the polling helper. Do not pin the task, publish any OSQ/delegation node or waiter, acquire `phase_wait.lock`, set task sleep state, inspect/dereference the physical owner's task, or add new acquisition authority. A pure admission-word/reader-tail retry is safe while schedulable. Owner-pointer spinning while preemptible would require a separate task/RCU lifetime proof and is outside this change.

Exact Linux7 condition-versus-signal semantics are verified in authenticated pristine source:

- `include/linux/wait.h:931–937` evaluates the condition before invoking the wait loop.
- `___wait_event` at310–317 calls `prepare_to_wait_event`, then tests the condition **before** returning the pending-signal error.
- `kernel/sched/wait.c:290–322` detects the signal and removes the wait entry under the waitqueue lock; otherwise it enqueues and sets task state. The surrounding macro keeps its final condition rechecks and `finish_wait`.
- `include/linux/sched/signal.h:408–415` limits TASK_KILLABLE interruption to fatal signals; SIGUSR1 must not end a killable acquisition.

Therefore free/reservable condition wins an already-pending or racing signal in the same way as the existing path. A signal observed after a failed poll only selects the original wait macro, which may still win the condition race. After the phase CAS succeeds, a later signal can cancel in the existing physical-gate or reader-drain stages; both release the exact phase once and never execute the user body on an `-EINTR` return. If every acquisition stage succeeds before cancellation wins, success remains valid even with a subsequently pending signal. Do not invent a stronger promise that SIGKILL always prevents acquisition.

## Concrete failure cases to preserve

- A successful predicate evaluated twice would see its own admission=-1, potentially park forever while owning the phase. Test a success-at-first and success-at-final-probe case with an exact single reservation record.
- Phase release between the last failed poll and waiter publication must not be lost. Keep the unchanged enqueue/condition-recheck macro; never replace it with blind scheduling.
- A nonempty reader OSQ tail must still reject reservation even when admission0. If its last member aborts/unlinks, the existing barrier+wake at `kd_rwsem.c:144–152` remains necessary.
- Concurrent writers must each perform the real0→-1 CAS; a read of0, retry budget or approximate count never grants ownership.
- SIGUSR1 should not terminate the killable poll/wait; fatal signal after a failed probe should promptly leave the busy loop. Predicate success concurrent with SIGKILL must not be rolled back twice or reported cancelled after a body executes.
- Reader-drain failure retains the original unlock-before-phase-release order. A still-held reader must exclude the body after phase acquisition or downgrade. The final IRQ-disabled read decrement must retain the timeout progress path.
- Existing WAITERS/HANDOFF/PICKUP behavior of the physical gate and all source/module lifetimes are outside this change. Ordinary nano calls and prepared delegated writers must not invoke the new helper.

## Direct validation and measurement gates

A new actual-helper fixture is necessary: `test_rwsem_api.py` exercises routing/release/downgrade with substituted acquisition and does not execute the killable function. `test_rwsem_read_admission.py` checks shared read/reservation predicates but not this new wait sequence.

Suggested focused fixture: extract the actual new helper, `kd_down_write_killable`, reserve/release and drain functions, and use the exact target `wait_event_killable`/`___wait_event` macros with explicit queue primitives or an explicitly labeled deterministic wait substitution. Trace acquisition, signal, queue publication/removal, mutex lock/unlock, reader zero and phase release. Cases: budgets1/exactN; success first/last; exhaustion; reschedule; fatal before/during poll; nonfatal signal; fatal plus successful condition; release at poll→queue boundary and after enqueue; reader-tail contention/last-tail exit; competing writer CAS loss; gate cancellation; sleeping/IRQ-disabled-final reader; downgrade followed by another killable writer. Mutations must catch duplicated successful reserve, signal-first or no signal handling, missing tail guard, skipped fallback recheck, early reader entry and phase release before physical unlock. No fixture should turn a compile failure into a pass.

Run basic plus the new fixture, existing `tests/unit/mutex/test_rwsem_api.py`, `test_rwsem_read_admission.py`, `tests/unit/infrastructure/test_mmap_rwsem_generation.py`; generated headers/source and enabled object compilation remain separate checks. Existing `tests/kernel/rwsem/module.c:147–230,354–387,505–532` already covers fatal/nonfatal cancellation while queued, reader-drain cancellation, sleeping holders and downgrade. It does **not** establish cancellation during the new unpublished polling interval; add a narrowly controlled actual-helper race case rather than relabeling the old test.

Inspect exact compiled ordinary/prepared rwsem paths against their baseline, allowing only relocations/addresses, to confirm the new helper is confined to killable admission. A code-byte identity check is not performance parity. Do not run a broad nano suite merely for this localized helper; use the agreed directly affected regression gate and keep any subsequently requested nano measurements source-specific.

For attribution, first use an unscored mechanism probe of `down_write_killable → short update → downgrade → up_read`, with same-CPU sleeping-holder, reader and uncontended controls. Separately observe phase waiting, reader drainage and physical mutex waiting; a waitqueue publication alone is not proof of actual scheduling/parking. Default-off observations must not authorize any transition. Avoid wake_one, new fairness queues, gate bypass or batching changes. Polling adds CPU work for sleeping owners and can increase barging opportunities despite unchanged eligibility, especially cross-NUMA/oversubscribed/priority cases; check CPU time and adverse cases as well as ops/s.

Only after correctness and the local experiment should a distinct generated kernel/image be considered. Preserve the initial same-image Native/KD mmap1 baseline; compare the same frozen upstream binaries, exact thread/process models, topology and uninstrumented settings in the separate candidate. Threads share the mm/admission word, whereas processes are a distinct-mm control. Keep original syscall bodies and per-VMA sequence/downgrade boundaries unchanged. The new mmap1/identity runner is still subject to its own VM validation; no module result substitutes for it.

## Exact input hashes

Paths below are read-only evidence, not scripts executed in this review.

| Input | SHA256 |
|---|---|
| `kernel_module/kd_rwsem.c` | `9911761bdc89c4cb5cfa9f7cbeba05eaa133eef4e65d7d168855dfed30da8e24` |
| `kernel_module/kd_mutex_local.c` | `be9b83cd9ab54a94386875615bcbeadcbd0f570b3ae25999f0a765590f6eae65` |
| `kernel_integration/mmap_lock/prepare.py` | `109e28b1dc02fc2f09c0747950cf15c9520bf8496922734e13d51aa1375505cb` |
| captured Ubuntu `source/kernel/locking/rwsem.c` | `5d030b8ab20d775f3e3cf92d307b56e8309d0a6d9c9a4d626af91a3ccd53ea65` |
| captured Ubuntu `source/mm/util.c` | `dcd21ee1618380902d7217afc844dd810ec98213d2c71a225e3049993d551826` |
| captured Ubuntu `source/mm/vma.c` | `8dea0340f92be7b964b2d424459155f04447fb0b69075d02f4b64b58291f7f05` |
| authenticated pristine `include/linux/wait.h` | `26f762288b8a5992eb895f00427f02eebf275081cb7f869889b789e597b76971` |
| authenticated pristine `kernel/sched/wait.c` | `53061f82571cd55f20dfde25156a4347cbe9a8326416814d0cae58201252e514` |

Captured source root: `/tmp/kdlock-semantic-source-20261030/source`, with its `capture.json` and captured build config. Pristine wait sources: `/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/linux70-port-20261027/pristine-source`. Implementation and performance remain pending, not implicitly authorized by this review.
