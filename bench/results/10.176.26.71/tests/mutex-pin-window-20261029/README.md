# Bounded mutex waiter selection: checks and performance rejection

The four-request selection candidate passed its scoped correctness checks but
failed the performance requirement. It remains isolated, outside `master`.
Source `6d95745d8e3c405a650e32efe04d54ffd2187cc7` ran on Linux
`7.0.0-38-kdlock1`, boot `677b7afa-5358-4ece-a650-5f4a4adecd55`.
The user approved a small immediately selected group after the earlier strict
one-request candidate lost throughput; that approval did not waive correctness
or performance acceptance.

## Source and focused checks

`e0db88766b8d227d6b91986470ed8e651deaeba7` implements the bounded window.
Unselected waiters retain migration exclusion but may schedule. Each selected
origin acknowledges preemption exclusion before its stack/GS can be used.
Exact node/generation descriptors are removed before wake/reuse; future pins
are settled before FULL service, native transfer or custody exchange. The
window follows a consecutive local execution prefix and preserves deferred
queue order and total/local limits 1024/1024.

The initial integrated source `dc8f3c1f79641cd76d52b0fb1c41a1e227ced0cf`
passed 18 checks and failed two compilations. The cap-one policy build exposed
a compiler array-bounds diagnostic; the custody fixture's macro captured a
production parameter with the same name. Correction `6d95745d` adds an explicit
bounds invariant before indexing and moves the fixture observation into a
properly bound helper. Assertions and warning-as-error checks remain enabled.
Two basic programs and all eight directly affected drivers then passed (10/10).
The original failed log remains preserved.

The [live verification](live-verification.json) records four-family basic,
queued scheduling, five local role cases and an additional mixed-node placement.
Basic completed 1,600,000 operations per family with returned JIT bodies:
spin 1,597,166; mutex 1,588,637; rwlock 24,106; rwsem 1,589,742.
The scheduling probe demonstrated an exactly published queued waiter allowing
a same-CPU witness to run; it intentionally prepared no JIT image.
All role cases passed, drained and retired exact source resources. The probe
adds original-task preemption, IRQ and migration-state checks, integrated from
`d8149cc140655734c8100d4978c1e2a694d095c0` at `39abf5b1`.

The case named `simple-cross-numa` used C32 and W33, both on node 1, while
other participants used node 0. Its name does not prove cross-node ownership
exchange. A separate [C2-to-W33 case](cross-node-result.json) then passed on
nodes 0 and 1: exact C-to-W physical ownership, C's body on W, 10,014 competing
trylocks, zero thefts, and final source retirement. Its five RUN and five
warmup context receipts are all zero before/after, in addition to the 60 clean
context receipts in the first six role runs. These are scoped mechanism tests,
not arbitrary nesting, long-chain or whole-kernel qualification.

## Performance gate

The [36-point comparison](nano-results.md) uses the same boot and arguments as
`1c86d6d1a15d96d75c09504f1041772247707804`: c01/c16, post256, two seconds,
one observation per point, workers 1/8/20/32/36/60, collector 63 and 1024/1024.
No real-world API benchmark ran. [All rates and identities](nano-comparison.json)
remain separate from the earlier strict-pin cohort.

All ten contended mutex points lost 19.75–39.25%; uncontended mutex was flat.
For c01 at twenty workers, throughput fell from 4.590029 to 2.788218 Mops/s.
Rwsem differences ranged from -10.11% to +8.42%. Correctness passes do not
permit promotion over this loss. One round supplies no repeat variance and
strict timing qualification remains failed.

Static inspection of the frozen provider found an external `memmove` for each
nonempty descriptor shift, plus out-of-line selection/addition helpers with
return thunks. Those are verified instruction costs, not a measured attribution
of the whole loss. A circular descriptor array and inline helpers are being
prepared separately; they have no execution or performance verdict yet.

## Preservation

Four completed evidence trees were archived after verified idle. The
[offline receipt](archive-verification.json) verifies eight compressed hashes
and all 9,659 inventory paths. Raw archives are under
`bench/results/10.176.26.71/raw/tests/mutex-pin-window-20261029/`.
Guest roots are `tests/pin-window-units-20261029`,
`tests/pin-window-live-20261029`, `tests/pin-window-role-cross-node-20261029`
and `bench/pin-window-nano-20261029` below
`/root/kdlock-evidence/10.176.26.71/`.
