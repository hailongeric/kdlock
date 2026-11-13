# Differences from the project goals and the GPT-era documents

This is a review of this implementation against the documents under
`docs/` (the maintained guides for the earlier kdlock, the design/contract
notes, and the `kdlock_redesign` proposal) and `AGENTS.md`. It lists where
the **goal or the effect differs**, what each difference does to correctness
and performance, and what should be checked or changed. It is a static
review: nothing here has been run.

## 0. How complete the review is

Read in full or in the parts that define behavior: `README`, `DESIGN`, `LOCKS`,
`ROADMAP`, `BENCHMARK_WORKLOADS`, `PERFORMANCE` (current sections), `TODO`,
`design/lock_protocols`, `design/kdlock_lock_replacement_contract`,
`design/kernel_cs_semantics`, `design/admission` (exits and reached calls),
`design/kd_only_mutex` (semantic limits), the introductions of
`rwlock_implementation` and `rwsem_implementation`, the opening of
`JIT_EXECUTION`, `operations/VM.md`, `AGENTS.md`, and, earlier in this work,
the `kdlock_redesign` notes 00-03.

Sampled by headings and targeted searches only: `lifetimes`, `frames`,
`unified_lock_queue`, `rwsem_delegated_protocol`, `mutex_implementation`,
`spin_implementation`, `killable_queue_execution`, `native_call_arguments`,
`mmap_fault`, `writer_recovery`, `lock_protocol_comparison`,
`JIT_REGISTER_ABI`, `VALIDATION`, `TERMINOLOGY`, `history/`. The 172 KB
`compiled_mm_continuations` (a dated work-order record for a retired MM
direction) was not read. Statements about those documents below rest on the
headings and on the other documents that summarize them; items marked
**(verify)** need a closer read before relying on them.

## 1. Where the goal is the same

* A lock holder runs waiters' critical sections from a relocated copy produced
  by a userspace translator; the origin resumes after the release.
* Delegation is optional and per call; anything unsupported goes back to the
  origin at the **exact** next instruction; nothing is replayed.
* Production trusts kernel source (no semantic proof); learning of missed
  CALL/indirect/RET targets is cumulative and never blocks the current call.
* Readers of rwlock/rwsem stay local; spin/mutex/rwlock-writer/rwsem-writer
  can delegate.
* Bounded batches (1024), NUMA-ordered sessions, mutex handoff against
  starvation; no claim of a starvation bound.
* Unsupported configurations are refused (RT, lock debugging, lockdep).
* Native MM bodies and the real syscall path stay unchanged; only lock calls
  and lock objects change.

## 2. Summary

| # | Topic | Documents say | Here | Effect |
| --- | --- | --- | --- | --- |
| D1 | Machine model | virtual SP/BP and mapped registers; executor keeps hardware RSP | real `rsp` on the origin's stack, no virtualization | faster, simpler; different failure modes (D3, D12) |
| D2 | Call-site contract | compiler clobber macros, `noipa`, explicit `prepare`, ABI1/2/3 | ordinary C calls; assembly stub saves state | unchanged kernel call sites; no preparation step |
| D3 | `%gs` / per-CPU | origin's saved GS rebases ordinary per-CPU accesses | only `current_task`, canary, stack top redirected | per-CPU effects land on the executor CPU |
| D4 | Interrupt/BH variants | explicit IRQ/BH pairs always local | `_irq`, `_irqsave`, `_bh` delegable, sections run with the entry's IF state | more delegation; needs an interrupt-handler test |
| D5 | Ownership/lifetime records | owners, ACKs, source leases, frame retirement are mandatory (`AGENTS.md` rule 4) | none; lifetimes by construction | simpler; **conflicts with a standing project rule** |
| D6 | Handback | exact, custody of every live owner, owner list | exact; ownership transfer by lock-word value | same intent, less machinery, fewer checks |
| D7 | Nested locks | not supported beyond one scoped path | general recursion (bounded) | superset; unvalidated |
| D8 | What may delegate | rwsem: prepared writers only; mutex: not killable/interruptible | all writers; killable/interruptible too | more coverage; cancellation semantics differ |
| D9 | Spinlock | qspinlock-style pending + MCS | the native algorithm itself in plain mode | plain mode at Native's rate (spin c01, 2-6 workers: 1.00-1.02) |
| D10 | Mutex waiting | published waiters poll pinned | spin only while owner runs, then park; first parked waiter spins for its handoff; release is one atomic, handoff retakes the lock | better under oversubscription; handoff is not strict |
| D11 | Rwsem | 320 B, phases, queued-reader admission, proxy downgrade | 40 B, count + mutex queue, readers spin (bounded) then sleep, downgrade always handed back | readers never delegate; **MM downgrade not delegated** |
| D12 | Image/translator | Miasm backend, entries/generations, ABI-specific wrapper | capstone, byte copy, one image per site | simpler; some GPT gaps closed, some opened |
| D13 | Exit set | manifest of native terminal calls incl. TLB, task-mm, user access, IRQ/BH | smaller frontier list | **TLB/mm helpers not yet handed back** |
| D14 | API surface | mutex/rwsem non-owner, nested, timeout, owner helpers, MM adapter | every Linux 7.0 operation of the six lock types, `ww_mutex` with wait-die only | no MM adapter; not yet compiled into a switched kernel |
| D15 | Evidence tooling | schema-2 identity, ownership probes, many runners | one nano module + runner | no evidence yet |
| D16 | Layout | rwlock 128 B, rwsem 320 B | 8 B and 40 B (native sizes) | better for embedding |
| D17 | When to delegate | every eligible contended caller is published; counted local cutoffs were removed | plain mode until the queue is deep, per lock; rwlock/rwsem writers always | no loss at low contention; thresholds are depth only, not section length |
| D18 | After a handback | owner handoff only; "queued role exchange remains unimplemented" (`AGENTS.md` rule 6) | the combiner becomes a delegable waiter and the origin's release takes the head role over (mutex, rwsem writer by default) | gains where the holder blocks, costs a few percent where it does not |
| D19 | Task state in a section | origin's GS lowered for ordinary accesses | `current` redirected; RCU read-side depth kept on the executor and carried over | other non-atomic task-field updates remain a hazard |

## 3. Details

### D1. Machine model

GPT docs: generated code keeps a virtual stack and mapped registers; hardware
`current`, IRQ/RCU state and the physical wrapper stack remain the
executor's. The `kdlock_redesign` notes go further (five reserved registers, a
virtual SP).

Here: `rsp` points at the origin's own stack (as in TCLocks); instructions are
copied byte for byte.

* **Effect (performance):** no per-instruction overhead, no register spills,
  `PAUSE`, fences and `LOCK` are untouched. This is the main reason the design
  can be fast.
* **Effect (correctness):** the origin's stack is live memory on the executor.
  Interrupts on the executor push frames on it; stack-bounds checks and
  unwinders see a stack that is not `current`'s (limit 7 in ARCHITECTURE).
  Stack use of the section plus any interrupt frame must fit the origin's
  stack: the same as native, since the section already ran there once.

### D2. Call-site contract

GPT docs: delegable calls must be written as macros that declare clobbers and
live in `noipa` functions; objects need `*_prepare()` with an ABI id; address-taken or indirect
lock calls stay local.

Here: any ordinary call to `kd_*` is delegable, including through function
pointers and from inline code, because the stub itself saves the state.

* **Effect:** transparent replacement of the kernel's lock API without
  touching call sites. Indirect calls need no special case. Cost: the stub
  must preserve callee-saved registers and flags the compiler assumes
  preserved across a call; this is what `kd_resume` restores (check it with a
  test that hands back mid-section **(verify at run time)**).

### D3. `%gs` and per-CPU data

GPT docs: "saved-origin GS lowering" for ordinary GS memory; stable reads
(canary) use ordinary lowering; GS mutation is a declared operation.

Here: three per-CPU variables are redirected to the origin's values; every
other per-CPU access addresses the **executor's** per-CPU area.

* **Effect:** a section that does `this_cpu_inc(x)` updates the executor's
  counter. That is correct for counters and caches whose consistency is
  provided by the lock or by preemption control, and it is what TCLocks does.
  It is wrong for code that **stores a per-CPU pointer** taken before the
  section and uses it after a handback, or that depends on `smp_processor_id()`
  being the origin's CPU (for example TLB shootdown masks, see D13).
* **Check:** list per-CPU symbols touched by the nano bodies and by mmap_lock
  critical sections; the translator could report `%gs` accesses to unknown
  symbols as a learnable event instead of copying them silently.
* **Cost of `current` in a section, measured** (build #39, two rounds, spin
  and mutex bodies with one read of `current->pid`, and with
  `rcu_read_lock(); rcu_read_unlock()`; `probes-20261112/cur39.jsonl`): the
  access itself is one redirected load and causes no exit. Delegated rates
  at 8/16/32 workers: spin 5.27/5.59/5.41 Mops without, 5.44/5.69/5.60 with
  the read, 5.89/6.43/6.28 with the RCU pair; mutex 3.93/4.26/3.51,
  3.60/3.75/3.33 and 3.85/3.81/3.51. The differences have both signs and
  changed sign between two boots (the bodies are separate call sites with
  separate images), so no cost of `current` is established, only a bound of
  roughly 10%. What it does cost is correctness care, see D19.

### D4. Interrupt-flag and BH variants

GPT docs: explicit `irq`/`irqsave`/`bh` pairs always execute locally.

Here: they are delegable. The executor installs the origin's logical IF and
runs the section with preemption off; it refuses an origin whose saved IF is
on if the executor itself runs with interrupts off.

* **Effect:** `spin_lock_irqsave` (the most common kernel form) can delegate,
  which matters for real kernel locks.
* **Checked in the source:** the irq entries execute `cli` *before* the
  continuation is captured, so the packet's saved flags already have IF off
  and the section runs with interrupts disabled on the executor, exactly as it
  would have on the origin. An interrupt handler on the executor therefore
  cannot take the held lock while the section runs. The saved IF is on only for
  plain `spin_lock`/`write_lock` entries; an interrupt-context user of such a
  lock would already deadlock natively. For `_bh` entries the origin's softirq
  state is carried in `bh_off`.
* **Remaining risk:** the executor installs the packet's flags with `popfq`,
  so any section that itself enables interrupts (for example `local_irq_enable`
  inside an `_irq` section) enables them on the executor while it holds the
  session lock; this is also what the section would do natively. It must be
  confirmed by a test that takes the same lock from an interrupt handler.

### D5. Ownership and lifetime records

GPT docs and `AGENTS.md` rule 4: "Keep exact physical owners, acquisitions,
source leases, unlock ACKs and frame retirement. Approximate counters cannot
replace ownership records." Rule 5: share packet/frame storage with explicit
lifetime transfer.

Here: none of those records exist. Lifetimes follow from construction:

| Object | Why it is safe |
| --- | --- |
| node, packet, wait stack | the waiter is non-preemptible on its wait stack until `RESUME` |
| image | RCU grace period after unpublish; waiters/combiners are non-preemptible from lookup to resume |
| lock ownership | the lock word itself (value-based), one owner at a time |

* **Effect:** much less code and no ACK round trips; but the project's own rule
  asks for explicit records for **evidence**: with no ACK there is no direct
  observation that a release happened exactly once. The counters in
  `kdlock_stats` are approximate by design.
* **Recommendation:** decide explicitly whether the standing rule applies to
  this rewrite. If it does, add *debug-only* ownership checks (an owner
  field set on acquire/cleared on release, asserted on every release, behind a
  config option) rather than the full ACK protocol; they give the evidence
  without costing the hot path.
* **Open lifetime items:** live text patching (module text is handled since
  2026-11-11: images are dropped when module text goes away), CPU hotplug during a session **(verify: waiters cannot
  go offline while non-preemptible, but executors?)**.

### D6. Handback

Same exactness. Difference: GPT docs keep **custody** records (which owner,
which gate, which phase) and route the origin's later releases through them.
Here the lock word is the only state: after a handback the origin owns the
lock and releases it with the ordinary call.

* **Effect:** cheaper and simpler. It relies on invariants that are easy to
  break: the executor must never release a lock it does not own; for rwlock
  and rwsem the combiner keeps the queue word/mutex while the origin owns the
  grant (`keeps_q`) and must reacquire the grant for the next section. A test
  that forces each exit kind per family is the only way to gain confidence.

### D7. Nesting

GPT docs: separate nested-image activation and mixed ownership are listed as
open work; one scoped KD-mutex-to-spin path is implemented.

Here: recursive delegation as in TCLocks (continuation published for the
inner lock; roots stack; released bitmask; bounded depth).

* **Effect:** wider coverage (any spin-class lock inside a section), but it is
  the most intricate code. Two-level nesting (spin in spin, spin in mutex)
  has run with exact data since 2026-11-11; deeper nesting and the depth and
  roots limits have not. It also needs the frontier list to be right about
  which inner calls can sleep.

### D8. What may delegate

| | GPT docs | Here |
| --- | --- | --- |
| rwsem writer | only after explicit quiescent preparation; unprepared writers local | every writer |
| mutex interruptible/killable | local | delegable |
| spin `irq/irqsave/bh` | local | delegable (D4) |
| rwlock writer | delegable | delegable |

* **Effect on semantics:** a delegated killable/interruptible mutex or rwsem
  acquisition does not observe a pending signal while it spins in the queue.
  Native returns `-EINTR`/`-EINTR` promptly; here the caller is delayed until
  its section is executed or it parks. The docs require cancellation before
  commitment with exact cleanup.
* **Recommendation:** either make the queue-spin loop check
  `signal_pending_state` and withdraw (`WAIT -> ABANDON` already exists for
  the sleepable class), or keep killable/interruptible local.

### D9. Spinlock protocol

Docs: pending-bit fast contention path plus MCS (native-like).

Here: in plain mode the lock *is* the native queued spinlock: same word
layout, the same pending and queue steps in the same order, the queue head
taking the lock with a plain store. In delegation mode waiters queue the
same way with their continuation published.

* **Effect:** plain mode runs at Native's rate (spin c01 at 2-6 workers
  1.00-1.02, build #35). Getting there took more than the algorithm; each
  step was measured (`bench/results/kdclaude/README.md`): no read of a
  predecessor's node before linking, per-CPU state in 128-byte blocks, the
  node count in the node's own line, and no store to that line by a freshly
  promoted head. The general rule behind the last two: a store that waits
  for its cache line holds up every later store of that CPU, the lock
  handover included.

### D10. Mutex waiting and handoff

Docs: published waiters poll **pinned** for the whole wait; physical owners
may sleep; NUMA boundary 1024; deferred handoff threshold 8 and a scan budget
of 64.

Here: spin only while the owner is running (`kd_mutex_can_spin`), withdraw and
park otherwise; one `HANDOFF` flag; batch = 1024 including passed-over
waiters; no separate scan budget.

Since `63f8de2a`, as in the native mutex, the first parked waiter spins on the
owner once it has been woken and has asked for `HANDOFF`, so a handoff
normally goes to a running task. The recorded owner is the task that runs
with the lock: the combiner during its session, and the origin from a
handback onwards. Queued waiters check it every 1024 iterations, not per
section; it shares its cache line with the queue tail.

Since build #34 the release is one locked subtraction that returns the
flags, with no read of the lock word before or after it. A handoff request
is therefore honoured after the release: the releasing task takes the lock
again for the first parked waiter unless somebody else was faster, in which
case the request stays for the next release. That is weaker than the native
mutex, where the lock is never free in between.

* **Effect:** better behaviour when the owner is descheduled or tasks
  outnumber CPUs (the docs list oversubscription as unvalidated and
  pinned polling as a problem). The handoff rule is simpler than the
  documented cohort handling, so tail behaviour will differ.
* **Measured failure of the earlier rule** (grid round 1): a handoff to a
  sleeping waiter made every queued spinner see an off-CPU owner, abandon and
  park; that convoy held mutex at 0.4–0.5 of Native from 8 workers up. The
  counters (`no_spin`, `abandon`, `parked`, `handoff`) show it directly.

### D11. Rwsem

Docs: 320-byte object (mutex, count, selected-writer phase, two condition
queues, reader OSQ); readers use eight short admission attempts and then an
**abortable queue whose head alone polls** the shared count (found to matter:
c01/20% writes at 16/32 workers went from 4.2/3.2 to 5.0/5.1 Mops/s); proxy
downgrade keeps the retained writer through the read tail.

Here: a reader that finds a writer present or waiting undoes its increment and
**sleeps on the queue mutex** (`kd_mutex_sleep`), then registers and waits for
the active writer to leave. Since `63f8de2a`, before that, the reader spins up
to `KD_RWSEM_SPIN` iterations for the writer bits to clear (every spinning
reader polls the count; there is no head-only queue). Downgrade is one
atomic, and inside a delegated section it is always handed back.

* **Effect (performance):** without the spin, each reader that met a writer
  slept behind the holder of `->m`, which itself slept on the count: one
  wakeup per reader in sequence. rwsem w20 was flat at about 0.88 Mops from
  4 to 12 workers (0.5 of Native). With the spin, the same points ran at
  1.6–1.8 of Native in a single round, with per-worker progress near
  Native's. Readers still never delegate, and the per-reader polling is not
  head-only; both remain open.
* **Measured against TCLock** (original `tclock_backend` rwsem, AQS reader
  gate): equal up to 16 workers, but across both NUMA nodes (20–32
  workers, 20% writes) kd is about a quarter of TCLock. Diagnosis: a
  reader whose spin runs out queues on `->m` and, holding it, sleeps on the
  count; every queued writer then sees an off-CPU owner and parks. Bounding
  the spins by time, a holder spin (kept; +16–33% at 20 workers only) and
  checking before adding did not change the regime. **Next step:** a reader
  admission path that does not hold `->m` while it waits (a reader queue of
  its own whose head alone polls, as TCLock's AQS and the GPT-era design
  do).
* **Effect (MM):** `mmap_write_downgrade` is used on common paths (munmap with
  downgrade); a delegated section that reaches it is handed back, so those
  sections lose delegation at that point. Not a correctness issue.

### D12. Translator and images

| | GPT docs | Here |
| --- | --- | --- |
| Backend | Miasm-based decoder, assembly-text emission, per-class lowering | capstone decode, raw byte copy with a small rewrite set |
| `PAUSE` (F3 90) | alias path drops the prefix (documented gap) | preserved (bytes copied) |
| Flags at an exit | arithmetic flags restored by a documented contract | exit stubs use `mov` only; flags are the origin's at that point |
| Return mitigation | call-depth tracking refused; full coverage unvalidated | `ret` replaced by compare chains in copied code, no thunks |
| Image granularity | entries, generations, immutable per mutex, in-place spin/rwlock generations | one immutable image per site, replaced whole |
| Learning | CALL and IJ records; daemon rebuild | same |
| Indirect branches | learnable; fresh near indirect CALL exit 11 | compare chain over learned targets, `MISS_IND` |

* **Effect:** simpler and faster; the risks are encodings written without
  execution, `call_depth`/`max_insns` limits, and flags assumed dead at
  call/ret/indirect branches (documented in ARCHITECTURE).

### D13. Exit set: native terminal calls

Docs' "native terminal" manifest names exact symbols whose effect must stay on
the original task: native lock APIs, scheduling, preemption, migration,
IRQ/BH transitions, **task-mm, user-access and TLB operations**.

Here: frontier = extable instructions, privileged instructions, scheduler
entry points, user-copy and get/put-user helpers, a few exit paths.

* **Missing relative to the docs (candidates to add):** TLB flush and
  `switch_mm`-style helpers (`flush_tlb_*`, `local_flush_tlb`, `__flush_tlb_*`,
  `switch_mm*`, `enter_lazy_tlb`, `leave_mm`), `migrate_disable/enable`
  helpers, `cond_resched` and friends (they can enter the scheduler),
  RCU quiescent-state and `rcu_note_context_switch` paths, `smp_call_function*`
  waits, and the native lock APIs (`mutex_lock`, `down_read`, `raw_spin_lock`
  on objects that are not kdlock; irrelevant once the API is fully replaced).
* **Effect:** without them, sections that call TLB code run it on the
  executor CPU, whose `smp_processor_id()` is not the origin's. A shootdown
  that skips "the local CPU" can then skip the wrong CPU. This blocks stage 2
  (mm locks) until resolved and is cheap to fix in the policy list.

### D14. API surface

Provided: every operation the Linux 7.0 headers declare for `spinlock_t`,
`raw_spinlock_t`, `rwlock_t`, `struct mutex`, `struct ww_mutex` and
`struct rw_semaphore` (LOCKS.md 1; mapping in `integration/kd_linux_map.h`),
including `mutex_lock_io`, the trylock/interrupt combinations, the `arch_`
level, the lockdep aliases, the reader `_non_owner` forms, `mutex_get_owner`
and `rwsem_is_contended`.

Not provided: `rwsem_owner` and the optimistic-spin tunables (no owner is
recorded for readers or write holders), lockdep annotations.
`mutex_trylock_recursive` and `down_timeout` on a rwsem do not exist in
Linux 7.0. `ww_mutex` uses wait-die for every class. `rt_mutex` is not
replaced.

### D15. Evidence and validation tooling

The old project has schema-2 identity bundles, hash-bound host evidence,
ownership/ACK probes, exact retirement checks and dozens of runners
(`tests/`, `bench/*`). Here: one benchmark module with a data oracle, and the
counters. This is enough for first bring-up; it is not enough to make a
performance claim that satisfies `AGENTS.md` (exact data, worker progress,
returned-body observations and drain, separately classified).

### D16. Object size

Docs: rwlock 128 B, rwsem 320 B, mutex 32 B. Here: 8 B, 40 B and 32 B, equal
to the native types. Embedded locks keep their layout; false sharing between
the lock word and neighbors is now the user's concern, as with native locks.

### D17. When to delegate

Docs: every eligible contended caller publishes; earlier counted cutoffs
("local" classes) were removed in favour of the 1024 batch.

Here: a spinlock or mutex is in plain mode until a queue head finds
`kd_deleg_enter` (5) or `kd_deleg_enter_sleep` (3) waiters behind it, and
leaves delegation mode when a session finds fewer than `kd_deleg_exit` (2).
rwlock and rwsem writers always publish. ARCHITECTURE 7a.

* **Effect:** with every caller published, kd lost to Native at 2-5 workers
  (round 4: spin c01 0.67-0.81, mutex c01 0.79-0.81). With plain mode those
  points are at Native's rate for the spinlock and within 0.93-1.0 for the
  mutex (build #35), and the gains at higher counts stay.
* **Limit:** the right depth depends on the section length (a 16-line mutex
  section gains from 5 workers, a 1-line one from 7), and only depth is
  measured. Around the threshold either mode can be the worse one by a few
  percent.

### D18. Role exchange after a handback

`AGENTS.md` (rule 6) records for the earlier implementation: an owner
handoff exists, "the former combiner is not immediately requeued/delegatable,
and the recipient does not start a new combiner loop", and "the requested
queued role exchange remains unimplemented".

Here it is implemented (ARCHITECTURE 5, "Role exchange"): on a handback the
combiner's node becomes a delegable waiter at the head of the queue at once,
and the recipient starts a session when it releases.

* **Effect (measured, LOCKS 6a):** rwsem writer +19% at 16 workers, mutex
  +10% at 32, mutex -4 to -5% at 8 and 16, spinlock 0 to -4%. It is on by
  default only for mutex and rwsem writer.
* **Not done:** a parked former combiner cannot be served (its packet is
  per-CPU and released when it parks), so an exchange ends when the holder
  blocks for long: the offer is withdrawn and the queue dissolves as before.

### D19. Task state in a delegated section

Docs: the origin's GS is used for ordinary accesses, so `current`-relative
state is the origin's by construction.

Here `current` is redirected, which makes reads right, but a **non-atomic
update** of an origin task field from the executor's CPU can race with
interrupt handlers on the origin's CPU, which run as the origin and update
the same fields. Found with the `spin_curw` body: delegated
`rcu_read_lock(); rcu_read_unlock()` sections left the RCU depth unbalanced
between tasks and the kernel warned (build #38, "Voluntary context switch
within RCU read-side critical section"). Fixed for RCU (ARCHITECTURE 6):
the executor counts for itself and the depth is carried over.

* **Open:** `pagefault_disable()`, `migrate_disable()` and other task-field
  updates inside a section are executed on the origin's task structure from
  the executor's CPU. No failure was observed; the same pattern as RCU
  would be needed if one is.

## 4. Effects expected on the known performance picture

From `PERFORMANCE.md` (old implementation, one round, different VM):

| Known result | What this design changes | Expectation (hypothesis, not a claim) |
| --- | --- | --- |
| Mutex c01/c16: KD beats native and TCLock at 60 workers | same delegation idea; cheaper machine model; NUMA order | at least comparable; low counts unknown |
| Rwlock: below TCLock at 60 workers, c16/1% below native | same reader-local design; smaller object; qrwlock-style count | similar; readers dominate |
| Rwsem: below TCLock; reader admission matters | readers sleep immediately (D11) | **worse** until a spinning admission stage exists |
| Spin c01/c08 | plain mode is the native algorithm (D9, D17) | measured since: at Native's rate at 2-6 workers, above it from 7 |
| Handback-heavy sites are switched off | same accounting | same |

## 5. Items to settle, in priority order

1. **D13** add TLB/mm/migrate/`cond_resched` helpers to the frontier policy
   (correctness for stage 2, cheap).
2. **D8** signal handling in the queue spin for killable/interruptible, or
   make them local (semantics).
3. **D11** reader spinning admission for rwsem (performance).
4. **D4** a test that takes an `irqsave` lock from an interrupt handler while
   it is being delegated.
5. **D5** decide on debug ownership checks.
6. **D3** report unknown per-CPU `%gs` symbols from the translator.
7. **D14** the missing API surface, driven by the first real kernel user
   (`mmap_lock`).
8. Unit/stress tests that force each exit kind and each family's handback
   (D6, D7).
