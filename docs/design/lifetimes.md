# Source, lock and hook lifetimes

Current implementation contract; start with the [design overview](../DESIGN.md).
Validation belongs to its frozen inputs in [tests](../../tests/README.md).

### 3.1 Source, Lock And Hook Lifetimes

These are separate contracts, not solved by preserving a mutex's physical
owner or by the deferred immutable-JIT work. The earlier capability audit is in
[VALIDATION](../VALIDATION.md#source-and-hook-lifetime-review).

| Object | Current identity and retention | What is not established |
| --- | --- | --- |
| JIT entry/source text | `(0, RIP)` key; root/read/ordinary-target pins retain up to 64 LIVE modules for the session; retirement invalidates every used entry before releasing dependencies | No concurrent code versions or in-session source replacement; init/unknown source is refused |
| Translation session | Daemon/cache/children share a writer open description; real kcore reads acquire source pins before inspection | The trusted publisher must follow this path; pins do not prove byte immutability or arbitrary pointer/resource lifetime |
| Hotlock / mutex shadow | Append-only address-keyed maps for the kdlock session | A reused address inherits sampling/metadata; no lock allocation/free notification or per-object retirement |
| Spin gate | Stable address-keyed gate; `generation` distinguishes physical ownership intervals | Not a lock allocation epoch or source-code version; an idle entry can serve the same address again |
| Active request | Tickets, task records, native registrations and owner ACKs; successful frame push retains a provider ref/source lease until actual pop | No containing lock-allocation pin or protection before entering the guest hook/after frame pop |
| Hook provider | Plain guest function pointers into kdlock; device fops has `.owner=THIS_MODULE` | A `/dev/kd_dev` reference is not protection for independent lock-hook readers |

See [registration](../../kernel_module/exe.c), [hook publication/removal](../../kernel_module/kd_main.c),
[mutex shadow lookup](../../kernel_module/kd_lock.c) and
[spin gate ownership](../../kernel_module/kd_spin_gate.c). An idle reused lock
address does not by itself establish broken exclusion: both backends still
acquire the newly initialized original lock. But the tables cannot tell old
and new object lifetimes apart, reset policy or prove safe reuse while any
old request/physical owner still exists. A logical final A ACK can precede
physical batch release; it is not permission to free a containing object
still used by another request or owner.

The preserved legacy hooks have four plain spin/mutex lock/unlock dispatch
sites; the current kernel adds distinct versioned spin and mutex bridges.
Each calls `is_kd_test()` or `is_kd()` before deciding whether the task is a
target, so non-target kernel tasks are readers too. `exc_int3` also reads the
shared spin predicate before checking the legacy `kd_do_int3` pointer, even
though kdlock does not install that trap callback. Clearing the six lock-hook
pointers and calling `synchronize_rcu()` does not provide these readers with a
matching acquisition/lifetime protocol. Stopping benchmark callers and draining
requests is necessary for current recovery experiments, not proof of generic
hot unload. `rcu_barrier()` for task records solves a different lifetime.

The current guest exports `try_module_get/put` and module notifier registration.
`__module_address/__module_text_address` are not exported in its Module.symvers;
the implementation resolves `__module_address` through existing kallsyms support.
A raw spinlock keeps preemption disabled through lookup and successful reference
acquisition. Such a reference
must span source inspection, publication and any execution/native return using
that source, including learned callees. A pointer lookup or text hash alone
does not pin code or module-owned data. The normal delete-module path sets
GOING, calls the module's `exit()`, then sends the GOING notifier. That notifier
cannot veto an exit that has already destroyed source-owned resources.

Blindly pinning every source module until kdlock exit is also insufficient:
the current `klock_module.ko` already depends on `kdlock_km`, so pinning it in
the reverse direction prevents either module being normally unloaded first.
A separate terminal retirement boundary now releases source pins before either
exit; force-unload is not a solution. The benchmark's own fops
reference and module dependency protect its controlled ioctl lifetime, not an
arbitrary module source or cached image after source reload.

The device-session prerequisite is now implemented in userspace: one daemon
descriptor spans requests, compilation and publication; only translator children
inherit it, and Python validates the device identity before real text reads.
An orphaned translator retains the same open description. The live cdev probe
checks normal unload refusal at each stage, not reader protection after the last
close. Detailed flow, control commands and direct-CLI restrictions live in
[the daemon guide](../../daemon/README.md#device-session). Wire structures and the
two-word wrapper ABI are unchanged; source controls are separate ioctls.

`kd_source.c` implements session-wide residency, not per-image reclamation:

1. Root registration pins LIVE module core text before installing metadata.
   Each real read pins its bounded range before kcore inspection, including
   learned/cold windows. Core kernel init and module init ranges are refused.
   Read windows can include resident data, but roots and ordinary native CALL
   targets must be text. Dependencies are deduplicated and retained even after
   partial refusal, because older images can still use them.
2. Writer admission uses the source lock. Frame admission uses a single atomic
   word containing a closed bit and a 32-bit live count. Retirement atomically
   sets the closed bit before checking the count: a racing frame either reserves
   a counted lease first or fails admission. Module-reference failure rolls the
   reservation back. Frame get/put take no source raw spinlock; snapshots read
   the atomic count. Closure remains terminal even when retirement returns busy.
   Frame leases cover native/remote continuation through actual pop, including failed-push
   rollback. Ordinary CALL miss pins the target before native transfer/learning;
   failed target residency after progress is non-continuable, never entry replay.
3. Retirement serializes against uploads, closes fresh selection/registration,
   and refuses while writers/frames or known queue/task/origin state remain.
   Existing task/origin routing survives closing for owner unlock notifications.
   Existing leased reads/targets can finish while DRAINING, not new publication.
4. With the external no-new-callers boundary and all holders drained, retirement
   publishes NATIVE_ONLY under the registry gate, then drops source references
   outside the raw lock. RETIRED is terminal; slots/images are not reused or
   reopened. All source/provider modules can then exit in dependency order.

Repeated `kd_exe_add()` calls use a read-only registration check: acquire the
published slot, match PID/RIP/backend and code storage, and observe source OPEN.
The initial UNINIT release publishes both immutable metadata and completed root
pinning. UNINIT, miss and terminal native-only entries need no new registration;
they do not become executable by passing this check. An UNUSED slot is only a
lookup candidate and must not count as registered, even if its key is visible.
Misses, backend conflicts and closed admission retain the registration gate and
source checks. A concurrent retire may follow the OPEN observation, but the fast
return only skips redundant work: it reads no source bytes, calls no code and
acquires no execution lease. Readiness and frame admission still gate execution;
pins are released only after invalidation and drain. Slots are never reused
within the session, and controlled module teardown still requires no callers.

The source limit is 64 distinct modules, with no hook-time allocation; each
read is limited to 256 KiB. Built-in resident ranges need no module ref. These
checks do not pin arbitrary dynamically freed objects or prove source bytes
unchanged. Idle observations are not a generic hook-reader barrier. A frame's
provider ref also cannot protect the earlier dispatch or code after its pop.

The dual-queue lifecycle gate also fills the actual 64-block executable pool
through real cold mutex CALL sites while both earlier native frames remain
live. An independent three-client queue then hits pre-wrapper not-ready refusal
and completes under each caller's own native ownership. Existing block identities
and images survive; the old frames subsequently complete all owner ACKs. This
does not compile the filler sites, exhaust all 511 registry slots, reclaim code
or authorize replay after progress. The same gate then tests a surviving
compiler-child writer and source replacement under terminal retirement. The
writer can inspect pinned
text while DRAINING but cannot publish, and it independently blocks retirement
after frames finish. Once fully retired, the same provider/registry remains
loaded while the test source is normally reloaded. ELF lock-CALL return sites,
module bytes and runtime code/lock addresses must match; both native mutex wait
lists must reach three callers. Six fresh records complete without JIT or owner
ACKs from kdlock. This is a quiescent, retired-session reuse test, not concurrent
source replacement or proof of arbitrary lock allocation lifetime. It does not
exercise multiple live source modules. The separate learned-depth gate now
executes a second module's translated seven-lock prefix and returns to its real
local helper before the eighth-child capacity exit. Root and learned text each
add one
source pin. The helper's native loader reference is observed separately:
1 before its CALL miss, 2 after pinning, 1 after retirement, 0 after the importing
module unloads. Both sources normally unload with the old registry terminal.
This is two-module coverage, not live saturation of the 64-module bound.

The two-frame gate also tests task routing independently of target comm:
both borrowed waiters rename in their native callees, then acquire/unlock
independent C mutexes as their own physical owners while A/B remain borrowed.
Both frames are live and source admission is still OPEN. The C unlock must
not consume A's active-task reference or become a borrowed-owner ACK. The
renamed identity remains through the later B/A ACKs and completion record.
This uses existing routing and physical ownership, not owner handoff.

Non-target callers then queue on both retained native B mutexes. Each actual
wait list must contain its identified peer; pidfd SIGUSR1 cancels each native
interruptible wait, returns EINTR to userspace and permits one explicit retry
by that same caller. Both wait lists must be observed again before retirement.
After the first frame's B release, its peer acquires/releases B as its own
Linux owner while the other frame's B still rejects trylock. That frame cannot
resume until this observation and the first original waiter's final ACK
complete. No peer enters JIT, borrows a lock or adds a kdlock task reference.
These are composed routing/native-peer checks, not arbitrary cancellation,
fairness, object lifetime or additional hook-reader protection. Execution
order, evidence and affected-only commands are maintained in
[usage 6.6](../testing/native_protocols.md#66-独立队列的并行-native-frame).

The same two drain orders now compose signals to the original borrowed waiters:
SIGKILL for the first, SIGUSR1 for the survivor, after native-peer requeue and
before source closing. Each waiter is one ioctl process. The first completes
its native record and real B/A owner ACKs before fatal syscall exit. A bounded
fixture gate keeps the second frame alive until the controller's retained
pidfd observes that exit and source reports one frame. The second then completes
under its unchanged physical owners and returns after one userspace signal.
This adds no task reference or production lock policy; it is pending-signal
completion, not permission to abandon a frame, call do_exit inside the suffix
or claim arbitrary task/RCU/hook-reader lifetime safety.

Capability assessment under the no-guest-edit default:

- Bounded source pins and terminal metadata retirement are implemented entirely
  in kdlock. They require a real external no-new-callers boundary and are not
  concurrent versioning or automatic subsystem lifetime integration.
- Generic lock allocation/free identity is absent from the lock hooks. An
  arbitrary `kfree()` or embedded-object reuse cannot be inferred from an
  unlock. It needs subsystem lifetime integration or separately approved
  allocation/free interfaces, not owner handoff or a guessed idle timer.
- Generic provider hot unload requires protection before a guest reader
  enters the predicate/callback, coherent hook publication, and draining of
  dispatches plus retained requests. A reference added inside the callback
  cannot protect the earlier jump into it. An unconditional put after the
  hook call is not enough either: `jump_to_saved_regs*()` may bypass that C
  return. Reference release must cover those nonlocal continuations too.
- A future kernel-side design must audit at least the four existing lock
  dispatch sites and the shared `exc_int3` reader, plus registration/drain and
  nonlocal-exit interfaces. That is more than an unverified extra condition;
  no implementation-backed line estimate or approval is claimed here. Actual
  guest-kernel changes for this review: **zero**.

Retain stable lock-allocation lifetimes during a session, retire source pins
explicitly, and use only the controlled recovery procedure in
[AGENTS](../AGENTS.md#验收与清理). Replacing a source module requires a fresh kdlock
and daemon session after draining, not merely a new TGID or clearing daemon
workspaces. This remains an experimental boundary, not safe hot-reload support.
