# Main live queue phase review

This review covers the uncommitted main-only queue-phase candidate prepared
following phase re-observation commit 5cd2e62b. It is static reasoning, not
compilation, runtime coverage or a performance result. No VM, network or other
branch/source/documentation was accessed.

## Representation and invariant

Spin-class bit 8 remains the pending waiter; bit 9 (0x200) becomes a queue
phase hint. Holder bits are unchanged. The ownership wait mask contains only
the holder byte and bit 8; the phase cannot prevent a head taking the grant.
The invariant is **phase implies nonzero tail**. It holds initially because
lock initialization zeroes the word, and the only set operation belongs to
the sole spin-class queue head while its tail is live.

The hint never grants ownership. A nonzero holder byte is authoritative even
if it explicitly says plain while the old queue hint is still being cleared.
Only an empty holder byte can use phase plus a nonzero tail, and only with the
option enabled. Forced adaptation-off behavior is unchanged. There is no
per-address cache and no lookup through an arbitrary observed tail slot.

## Writer and retirement audit

* Head acquisition first waits for holder and pending to clear. If it is the
  last node, the existing whole-word CAS writes only the selected holder byte,
  clearing both tail and phase together. A failed last-node CAS retries the
  holder/pending wait and last-tail decision. A stale pending caller can undo
  P and use the no-node fallback when its per-CPU node slots are full; that
  caller will never publish a successor link. Treating any failed CAS as a
  successor was an inherited assumption, corrected here before validation.
  Only an observed different tail selects the queued-successor path. There
  it sets the holder byte and conditionally changes only the phase bit.
  Enqueue can change the tail,
  and a stale pending attempt can change bit 8, without being overwritten.
* Only this head can remove its live tail. The phase snapshot used to avoid a
  redundant update stays valid: enqueuers change only tail, pending undo now
  clears only bit 8, and no other head may change the phase concurrently.
* Detaching a final successor moves tail back to the current head, not zero;
  splicing a deferred list also keeps a live tail. Neither can orphan phase.
* Final spin `kd_q_pass` clears tail and phase in one whole-word CAS while
  preserving the observed holder and pending bits. A CAS failure with the
  same tail retries: it does not wait for a nonexistent successor merely
  because bit 8 or the holder byte changed. A different tail proves an append
  has reserved an edge, so the existing wait for successor publication applies.
  The CAS retains the prior full ordering of the tail cmpxchg operation.
* The sleepable `kd_q_pass` branch keeps its old tail-only operation. Bit 9
  means HANDOFF in that separate protocol and must not be cleared as phase.
* Mode exit in a spin session updates its holder byte, then clears the queue
  hint while this CPU remains the sole head. A no-tail case does not set it.
  Setting the option to zero still allows heads and final-tail removal to
  clear hints left by earlier enabled acquisitions.

## Pending acquisition races

A pending attempt first rejects a queue or phase. If a stale first observation
allows its bit-set to race a queue, it rejects the queue afterward and undoes
only bit 8 atomically. Zeroing the whole pending byte would erase phase and is
therefore removed.

The successful pending-to-locked 16-bit store remains safe: a real pending
owner excludes head acquisition until this store. A head cannot set phase
while that pending owner holds bit 8. If an empty-tail retirement races the
pending bit-set, the final-tail CAS preserves pending, removes phase and tail,
and the pending caller can legitimately succeed without a queue. If the queue
remains, the pending caller rejects it and performs the bit-only undo.

## Shared scope and context

These helpers are spin-class, not exclusively kd_spinlock: rwlock wait gates
and raw/internal queue locks also use them. Raw callers never publish a
continuation; their physical protocol still recognizes the new bit correctly.
Rwlock may inherit a delegating head state and therefore maintain the hint,
although writer eligibility has its own policy. Sleepable flags/mode changes
remain on their separate path.

The uncontended CAS assembly and byte-store unlock source paths are unchanged.
No node or packet layout, source lifetime, continuation state, IRQ/BH state or
preemption operation changes. The queue phase adds no polling. The separate
phase_wait option remains default zero and retains its explicit bound if used.

## Measurement and coverage limits

Both options default false/zero pending evidence. Low-depth plain heads whose
phase is already off perform no extra phase-update atomic operation. This is
not a claim of zero slow-path overhead: eligibility branches, phase tests,
pending undo and final-tail retirement compile differently even when disabled.
The 0/1 comparison in one image cannot measure all inactive overhead against
the pre-change binary. Inspect emitted code and retain low-depth, phase-drop,
raw/IRQ/BH, rwlock, nested and handback checks.

Important races to cover include last-node head CAS versus pending bit-set,
last-tail pass versus pending-only word changes and new tail publication,
option disable while a queue remains, and genuine drain followed by immediate
uncontended reuse. Exact ownership/lifetime rules remain the basis of safety;
approximate delegated, handback, plain-stop and NUMA counters accompany rates
but do not prove those races or a measured physical batch length.
