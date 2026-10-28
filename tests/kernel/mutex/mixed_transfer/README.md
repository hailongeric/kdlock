# Public mutex to spin ownership-transfer check

Run only in the recovery guest under [VM operations](../../../../docs/operations/VM.md).
This is a correctness mechanism test with a control ioctl, not a real-world API
substitute or a performance benchmark. No kernel source or installed kernel is
changed. The runner freezes source, including private `.inc` files, and records
kernel identity, dependencies, CPU placement, source/binary hashes and the exact
observation overlay before loading modules.

After setting the verified snapshot variables and pinned Python environment:

```sh
timeout 900s python3 tests/kernel/mutex/mixed_transfer/run.py \
  --cpus 0-4 \
  --output /root/kdlock-evidence/10.176.26.71/tests/mixed-transfer-NEW
```

The five distinct CPUs have fixed roles, in argument order: delegation holder G,
spin B holder, combiner C, original waiter W, and predecessor/competing task T.
Reserve these CPUs for this probe. All five CPUs first contend through the actual
public mutex call site, with the eligible worker name, to warm production
admission before taking their fixed test roles. The test requires a real
JIT body witness during warmup and cached eligibility observations from G, C
and W's actual affine CPUs. A global returned-JIT count alone does not establish
any particular CPU's admission. Up to `--warmup-rounds` real rounds (default
four, each `--warmup-iterations` per CPU) run until all three report hot. The
test workers finish Python imports and bind their CPUs before warmup. G, C and
W query again immediately before their armed acquisition; a cold result fails
before entering the lock. These are cached observations, so actual gate/queue
publication remains the authority if the following acquisition resamples heat.
The probe never forces heat, changes eligibility counters or treats image
publication as execution. Every warm round has separate counts and receipts.

The runner prepares the public mutex entry and audits its compiled capture/CALL
bytes. C and W use literal `kd_mutex_lock/unlock`; the inner B acquisition uses
literal `kd_spin_lock/unlock` with the public unpinned clobber shell. The initial
predecessor T deliberately uses the callable local C mutex API to hold A without
creating a second prepared image. G uses the same prepared public entry as C/W.

1. T blocks A locally. The runner starts G and requires owner T with gate
   `ACQUIRING`, then releases T to become the trylock competitor. It requires
   owner G with gate `HELD` before starting C. C must publish its exact waiter
   record and queue tail; W then publishes the second record and a changed
   tail. Only then does G release. C must become the physical owner and execute
   W's prepared body. A local holder alone leaves the gate `FREE`: the first
   admitted request claims it without allocating a queue node. That setup
   cannot satisfy the required one-waiter queue observation.
2. W's delegated prefix increments exactly once and pauses at a bounded source
   barrier. B's independent holder requires the authoritative A owner to be C.
   A fifth task starts real `kd_mutex_trylock` attempts while A is held. Only
   then does B's holder release the prefix barrier; it continues holding B.
3. The runtime's single CAS on B must fail. B's holder observes A's physical
   owner become W, with its gate still occupied, prefix equal to one and suffix
   still zero. It releases B through its normal paired public unlock only after
   at least 10,000 competing trylock attempts. W acquires B natively, checks
   that W really owns A, completes the suffix once, and stops/joins the trylock
   loop before its legitimate A unlock.
4. W's A unlock must produce the retained executor's native ACK. C's own body
   must subsequently run exactly once with C again physically owning A. All
   five processes must return with balanced preemption/IRQ state. The runner
   requires one partial JIT body for the forced attempt, one matching transfer,
   one pending-B native continuation, one A ACK and one native completion.

This tests direct physical owner handoff followed by C's later reacquisition.
C keeps servicing the retained frame until W's unlock ACK; C does not immediately
publish a new request for W to execute as a combiner. The probe does not claim a
full queued role swap.

The benchmark observation provider suppresses ordinary warmup logging. A
separately recorded overlay preserves the existing native begin/complete/ACK
diagnostic sites by replacing only their quiet logging macro with `pr_info`.
The existing production transfer log remains intact. A second recorded overlay
adds only `EXPORT_SYMBOL_GPL(kd_hotlock_query_mutex)` to the prepared provider;
the query body is unchanged and updates no heat, sample count or clock. This
export is absent from the ordinary provider. Before/after hashes identify both
overlays. There are no changes to ownership decisions, queues, lifetime checks
or source trust.

Success requires zero successful thief acquisitions, observed C/W owner tokens,
exact prefix/suffix/C-body effects, unchanged prepared image, empty A owner,
gate, tail and waiter records, zero B word, explicit joined-object drain,
source retirement with zero frames/writers/modules, and final native totals
`started=1 completed=1 unlocks=1`. Sampling plus competing trylocks validates the
selected execution; it does not prove every memory-order interleaving. The
production owner-word CAS and focused mutation fixtures provide separate code
and deterministic protocol evidence.

The B holder waits at most eight seconds and releases only its own lock through
the normal pair. Other probe barriers are bounded too. A timeout or observation
failure writes the last observed snapshot and process states to
`<phase>.failed.json`, then retains active kernel callers, provider and payload
for diagnosis. An `abort-starts.json` file lets userspace workers still behind
their external start barriers return without issuing an ioctl; it never
interrupts an entered kernel call. The startup barrier is bounded at 360 seconds
to allow the real warm rounds. Failure does not authorize killing kernel users,
source retirement, forced unload or a claim of drain. Only a fully joined,
validated run follows the normal retirement and
unload sequence. Multiple-owner transfer chains, IRQ/BH nesting, fairness,
oversubscription and arbitrary kernel replacement remain outside this probe.

`tests/unit/infrastructure/test_mixed_transfer_runner.py` checks the real runner's
warm eligibility decisions, gate-before-queue staging, snapshot wire format,
export-only overlay and failure records using explicit substitutes. It does
not compile the payload or replace live validation.
