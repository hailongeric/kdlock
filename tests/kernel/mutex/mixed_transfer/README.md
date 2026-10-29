# Public mutex to spin owner-handoff and queued-role-swap checks

Run only in the recovery guest under [VM operations](../../../../docs/operations/VM.md).
This is a correctness mechanism test with a control ioctl, not a real-world API
substitute or a performance benchmark. No kernel source or installed kernel is
changed. The runner freezes source, including private `.inc` files, and records
kernel identity, dependencies, CPU placement, source/binary hashes and the exact
observation overlay before loading modules.

After setting the verified snapshot variables and pinned Python environment:

```sh
timeout 900s python3 tests/kernel/mutex/mixed_transfer/run.py \
  --protocol owner-handoff --warmup-iterations 200000 \
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
Every warmup and test ioctl records `KD_MIXED_CONTEXT` on its original task,
with before/after preemption, IRQ and `migration_disabled` values. The runner
requires all six values and the error count to be zero for all five joined
roles. CPU affinity alone does not establish a balanced migration pin. A
queued role swap must retain the reservation's single pin until custody ends,
then return with migration enabled. These cold return observations leave the
ioctl layout and translated body unchanged; `result.json` includes test and
per-round warmup context receipts.
The original default remains `owner-handoff`, `simple`, and 50,000 warmup
iterations. The suggested commands use 200,000: a recorded live attempt exhausted
all four 50,000 rounds with G still cold; the larger real warmup then succeeded.
Neither setting guarantees eligibility, and failure retains its observations.

The runner prepares the public mutex entry and audits its compiled capture/CALL
bytes. C and W use literal `kd_mutex_lock/unlock`; the inner B acquisition uses
literal `kd_spin_lock/unlock` with the public unpinned clobber shell. The initial
predecessor T deliberately uses the callable local C mutex API to hold A without
creating a second prepared image. G uses the same prepared public entry as C/W.

1. T blocks A locally. The runner starts G and requires owner T with gate
   `ACQUIRING`, then releases T to become the trylock competitor. It requires
   owner G with gate `HELD` before starting C. C must publish its exact waiter
   record and queue tail; W then publishes the second record and a changed
   tail. Only then does G release. Its release control permits only the WITHDRAW
   bit beside HELD because C/W may now reserve withdrawal; the exact G owner,
   two waiter records and all ready-role bits remain mandatory. A real withdrawal
   may still prevent the required delegation and fail the case; the probe never
   rearms readiness. C must become the physical owner and execute W's prepared body. A local holder alone leaves the gate `FREE`: the first
   admitted request claims it without allocating a queue node. That setup
   cannot satisfy the required one-waiter queue observation.
2. W's delegated prefix increments exactly once and pauses at a bounded source
   barrier. B's independent holder requires the authoritative A owner to be C.
   A fifth task starts real `kd_mutex_trylock` attempts while A is held. Only
   then does B's holder release the prefix barrier; it continues holding B.
3. The runtime's single CAS on B must fail. B's holder observes A's physical
   owner become W, with gate `HELD`, prefix equal to one and suffix still zero.
   In this proxy-epoch candidate, only the legitimate `WITHDRAW` bit may accompany
   `HELD`; `COMBINER` and all unknown bits are rejected. The epoch must end before
   W's native suffix so unrelated READY origins can withdraw. This deliberately
   changes the earlier probe's COMBINER-phase expectation while preserving its
   exact owner, prefix/suffix, theft and context checks. It releases B through
   its normal paired public unlock only after
   at least 10,000 competing trylock attempts. W acquires B natively, checks
   that W really owns A, completes the suffix once, and stops/joins the trylock
   loop before its legitimate A unlock.
4. In `--protocol owner-handoff`, W's A unlock must produce the retained executor's native ACK. C's own body
   must subsequently run exactly once with C again physically owning A. All
   five processes must return with balanced preemption/IRQ/migration state. The runner
   requires one partial JIT body for the forced attempt, one matching transfer,
   one pending-B native continuation, one A ACK and one native completion.

The default tests direct physical owner handoff followed by C's later reacquisition.
C keeps servicing the retained frame until W's unlock ACK; C does not immediately
publish a new request for W to execute as a combiner. The probe does not claim a
full queued role swap. The explicit mode below has different requirements; the
runner never accepts the old handoff result as a successful role swap. These
flags select probe expectations; they do not switch the provider's protocol.
Use the corresponding frozen runtime source for each mode.

## Queued role swap

Integrate the reviewed runtime candidate before running `--protocol role-swap`.
The runner refuses this mode if the runtime's role-exchange implementation is
absent. That source check is a prerequisite, not evidence of live execution.
Run each selected case in a new output directory after the previous run has
joined and drained:

```sh
timeout 900s python3 tests/kernel/mutex/mixed_transfer/run.py \
  --protocol role-swap --case simple --warmup-iterations 200000 \
  --cpus 0-4 \
  --output /root/kdlock-evidence/10.176.26.71/tests/mixed-role-swap-simple-NEW
```

Select the other cases explicitly by changing `--case` and the output directory.
Each invocation still runs one forced attempt after genuine warmup.

| Case | Required C execution | JIT entries / returned completions | Native started / completed / unlocks |
| --- | --- | --- | --- |
| `simple` | W executes C's body while W physically owns A | 2 / 1 | 0 / 0 / 0 |
| `c-native` | C starts under W, then RDTSC resumes original C; A remains owned by W until C's ACK | 2 / 0 | 1 / 1 / 1, for C |
| `c-early-spin` | W executes C, which acquires B, releases A while B remains held, then releases B | 2 / 1 | 0 / 0 / 0 |
| `w-early-spin` | Native W releases A while holding B; C runs locally and observes B still held | 1 / 0 | 0 / 0 / 0 |
| `w-early-mutex` | Native W releases A while holding a separate KD mutex M; C runs locally and observes owner W on M | 1 / 0 | 0 / 0 / 0 |

All cases require one `kd_mutex role exchange` offer, no old `kd_mutex transfer`
record, exact once-only W prefix/suffix and C body effects, and zero successful
thief acquisitions before W reaches its legitimate A unlock. The simple case
additionally requires a returned C JIT completion and physical A owner W in C's
body. The exchange offer alone cannot establish that custody was accepted or
that C executed. The `c-native` case verifies the real C task after the safe
RDTSC marker, arithmetic flag mask `0x95`, a single suffix visit and the native
begin/ACK/completion on W's new executor frame. W's transferred prefix must not
retain the old native relay. Its validated RDTSC escape invokes
`kd_jit_native_escape`, which makes the source entry sticky `NATIVE_ONLY` (`-3`)
through `kd_image_disable`. Only `c-native` expects that status transition: it
requires exactly one escape count/event naming C, the marker and the existing
generation. Code address, ABI, requirements, generation, generated image/assembly/
disassembly hashes and source drain state must otherwise remain identical.
Every other case still requires the unchanged NORMAL publication and zero
instruction escapes. This follows the existing instruction-escape probe's
terminal-status contract; it changes no source trust or runtime policy.
`c-early-spin` requires the existing outer-release
trace naming logical C and physical W, followed by an unlocked A and still-held
B observation; W must finish without reacquiring A for another body.

The two `w-early-*` cases stop the thief before W releases A, then use a bounded
source barrier to keep W's inner lock held until C independently observes it.
They require C to execute locally after release, rather than under W's unrelated
inner lock. These cases cover tracked KD mutexes and spin state. Native Linux
sleeping locks, KD rwsem reads and locks already held before the root acquisition
are outside the role-swap context contract; these tests do not validate them.

The benchmark observation provider suppresses ordinary warmup logging. A
separately recorded overlay preserves the existing native begin/complete/ACK
diagnostic sites by replacing only their quiet logging macro with `pr_info`.
`outer-release-trace-overlay.json` independently records the same sink-only
replacement for the existing `kd_mutex outer release` site in
`kernel_module/mutex/combiner.inc`. This keeps the `c-early-spin` evidence visible
with `bench_quiet=1`; it changes no release operation or ordering.
The existing production transfer log remains intact. Another recorded overlay
adds only `EXPORT_SYMBOL_GPL(kd_hotlock_query_mutex)` to the prepared provider;
the query body is unchanged and updates no heat, sample count or clock. This
export is absent from the ordinary provider. Before/after hashes identify both
overlays. There are no changes to ownership decisions, queues, lifetime checks
or source trust.

Success requires zero successful thief acquisitions, observed C/W owner tokens,
exact prefix/suffix/C-body effects, unchanged prepared image, empty A owner,
gate, tail and waiter records, zero B word, explicit joined-object drain,
source retirement with zero frames/writers/modules, and final native totals
matching the selected protocol/case. The separate M object must also be idle.
The default owner-handoff totals remain `started=1 completed=1 unlocks=1`.
Sampling plus competing trylocks validates the
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
export-only overlay, protocol-specific returned-JIT/native/early-release
requirements, exact original-task context receipts and failure records using explicit substitutes. It does
not compile the payload or replace live validation.
