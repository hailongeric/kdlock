# Conservative queue-readiness bit: source-only feasibility

Recommendation: do not implement this as the next performance experiment. A
conservative certificate appears possible, but it is a new queue/gate protocol,
not a safe return to the historical ordinary service loop. Its narrow saving is
one or two READY observations/branches. Exact current-node, generation, physical
owner, frame, source, acquisition and CPU proofs remain. A mode branch and reset
protocol could offset the saving. No performance benefit is established.

Reviewed source: `2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7`, whose only runtime
change from `99f383624faa872a76521d1b5be7faea586591c1` is the result-wait helper.
Historical comparison: `1c86d6d1a15d96d75c09504f1041772247707804`.
This record is an independent static design review, with no repository edits,
builds, tests, VM operations or new measurements. The restricted reset argument
also received independent source review from `api_semantics_audit`; it is not a
formal proof or tested protocol.

## What the existing source establishes

- Ordinary successors publish complete metadata/count/debug work, READY and then
  their incoming release link, while already on the shadow stack and pinned:
  `kernel_module/mutex/waiter.inc:49–66`. A traversal must retain that acquired
  link/publication ordering; merely having an encoded tail is insufficient.
- An origin changes READY to WAIT only after a withdrawal reservation, then
  releases that reservation before unpinning: `kernel_module/mutex/queue.inc:120–155`.
  Active COMBINER excludes new withdrawal reservations through
  `include/kd_mutex_state.h:31–53`.
- Executor cancellation also publishes WAIT, independently of origin expiry:
  `kernel_module/mutex/pin_window.inc:82–105`. This is a mandatory dirty setter.
- Private first heads can be INIT/WAIT and schedule while acquiring the physical
  lock; they are excluded from their subsequent proxy candidate list by
  `kd_mutex_head_successor`: `kernel_module/mutex/waiter.inc:21–106`.
  Therefore “every queued node is READY” is false. The certificate must describe
  only the exact reachable proxy candidates, excluding the owner's private head,
  retired/woken nodes and detached retained frames.
- Role exchange republishes C as INIT before retiring the old frame, then publishes
  C READY only after source/frame retirement and before W's custody-ready barrier:
  `kernel_module/mutex/combiner.inc:315–353,758–770`. W cannot start its native
  suffix or new combiner until that barrier: `kernel_module/mutex/custody.inc:50–55`.
  This barrier must remain part of the proof; alternatively conservatively mark
  such transitions dirty. A linked INIT is not a READY proof by itself.

## Necessary rules for a conservative certificate

1. DIRTY means “some proxy candidate may no longer be READY/quiescent.” It is not
   an owner, waiter count, generation or execution record. False positives only
   select the existing checked fallback; false negatives are unsafe.
2. Set DIRTY **before publishing READY→WAIT**, not merely before the later
   `preempt_enable`. An origin could combine DIRTY with its existing successful
   WITHDRAW-reservation CAS, even when the following node CAS loses; this is a
   safe false positive. Executor cancellation must set it before its WAIT release.
   Otherwise a new epoch can cache “clean” after WAIT is visible but before the
   cancelled origin sets DIRTY and unpins.
3. Every full-word gate phase transition must preserve DIRTY, including FREE,
   ACQUIRING, HELD, COMBINER and RELEASING; WITHDRAW release clears only WITHDRAW.
   Current literal `FREE→ACQUIRING` and `HELD→COMBINER` CAS helpers would fail
   permanently on sticky `FREE|DIRTY` / `HELD|DIRTY` unless explicitly adapted:
   `include/kd_mutex_state.h:17–28,59–73`. Unknown-bit checks also need updating.
   No mixed-width gate accesses or unconditional phase stores are acceptable.
4. A successful epoch CAS must capture the dirty value atomically with closing
   withdrawal. A prior clean load followed by a mask-only CAS is insufficient.
   Clean proof also requires this exact physical owner, private live epoch and
   unreleased outer acquisition, not a later owner's COMBINER value.
5. An ordinary clean iteration can at most infer its candidate's pin/readiness
   from acquired publication plus that still-live epoch. Preserve the exact
   descriptor and generation/key re-read, different-CPU check, physical owner and
   PICKUP checks, frame ledger/routing, source lease, and retirement-before-wake.
   DIRTY cannot identify a recycled slot or authenticate a borrowed frame.
6. Any cold/FULL/native/early-outer transition ends the clean proof. A retained
   current still needs explicit READY→CLAIMED promotion before reopening withdrawal
   and strict CLAIMED checks afterward. A fresh epoch must choose its mode anew.
   Cancellation invalidates the private clean mode before any later candidate;
   no clean flag may survive role transfer, queue handoff or old frame callbacks.
7. Keep a single execution loop and every existing boundary. A private-mode branch
   in admission/completion is the likely cost. Two duplicated service loops or an
   indirect per-body helper introduce additional review/codegen costs, not free
   amortization. Compiler loop unswitching would also need inspection.

## Unsafe clear: exact ABA counterexample

Let an exact owner hold `HELD|DIRTY` after its old queue has drained. It reads
`delegation_tail==0` and intends to CAS away DIRTY. Before that CAS, a producer H
exchanges the empty tail and becomes a private head; producer W links behind H
as READY. W completes a legal withdrawal reservation, changes its node to WAIT,
and clears WITHDRAW. Because DIRTY was already set, the full gate word has
returned to exactly `HELD|DIRTY`. The owner's clearing CAS succeeds despite the
new withdrawn W. After handoff, H could admit a falsely clean epoch and proxy W
while W is schedulable. Even a full-word clearing CAS does not fix this ABA.
Clearing at FREE, unlock, a new head, a zero-tail observation, or a sampled
waiter count is therefore not justified. Detached NUMA prefixes make a tail-only
empty assertion still weaker.

A possible restricted reset is a **successful terminal tail CAS** while the same
exact owner/private COMBINER epoch still excludes withdrawals, with no deferred
prefix and with the current body/frame already safely retired. See the actual
terminal decision at `kernel_module/mutex/combiner.inc:176–196`. Reset must occur
before opening that epoch, with all queue/lifetime predicates checked. A racing
publisher that already owned the old predecessor link makes this tail CAS fail;
a later publisher becomes a new private head, whose followers cannot withdraw
until the old COMBINER opens. No old detached frame may subsequently introduce
an unready candidate into this queue. The old head/current exceptions and the
role-C barrier require explicit reasoning and adversarial fixtures.

This opportunity does not cover terminal retirement after cold epoch closure or
all-native queue drainage. Those paths need either another independently proven
freeze/reset protocol or continued dirty fallback. Never-clearing until explicit
caller quiescence is conservative, but one exceptional wait can then disable the
fast mode for the rest of a busy object's lifetime. It also conflicts with the
current raw-zero gate condition in `kd_mutex_is_idle` and drain assertions:
`kernel_module/kd_mutex_local.c:445–457`. Preserving those contracts is additional
work; silently masking the new bit in idle evidence is not sufficient.

## Cost and priority

The bit does not remove the new exact descriptor stores/clears, two-phase
key/generation proof, entry owner checks, frame retirement, terminal-link handling
or cold ownership checks. Conservatively it avoids only the admission notification
load and perhaps the ordinary READY completion load/branch. Every non-clean route
still needs the present checks. Normal epoch admission could carry its mode in
one existing CAS, and origin expiry could set DIRTY in the existing reservation,
but executor cancellation and safe reset require additional shared gate updates.

The preserved baseline/99 ELF inspection does **not** show a new outlined
`kd_mutex_batch_try_retire_current` call on each ordinary successful body: that
helper is inlined in the combiner. Added epoch begin/end calls are batch/cold
boundaries, not necessarily per-body costs. The most concrete remaining service
work is the exact descriptor/readiness proof and its branches/stores; no distinct
new dominant service call was established in this review. The prior sampled-IP
neighborhoods do not establish notification-load latency or a causal share of the
remaining throughput gap. The measured six-instruction waiter loop also did not
close that gap, so instruction-count arguments alone are insufficient.

Given the user's careful no-regression requirement, retain this as a design note
and prefer evidence that isolates a material service-side cost before adding a
sticky-bit/reset protocol. No implementation or promotion is recommended here.
