# Checked spin pointer-load continuation

This is an explicit checked-analysis regression fixture. Production trusted
translation bypasses this analysis; its old string-service/direct-call evidence
below is historical. [Translation policy](../../../../docs/design/admission.md)
defines the present production and optional regression scopes.


This focused check uses the [address-guard payload](fixture/module.c)
to verify a delegated spin critical section that encounters a checked pointer
load. JIT means the generated machine code that a lock holder runs on behalf of
a waiting task. The check compares the load's address with recorded stack writes;
it is not a general test that a pointer is safe to dereference.

Run only in the verified recovery guest, following
[VM operations](../../../../docs/operations/VM.md). Confirm the actual recovery
snapshot, set its recorded environment variables and use the pinned Python
environment before running. Choose 4–60 distinct available worker CPUs and a
new evidence directory outside the checkout:

```sh
timeout 900s python3 tests/kernel/spin/address_guard/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/address-guard-NEW
```

The runner freezes source files, including private `.inc` components, builds a
private provider with the benchmark observation overlay, and records source,
prepared-provider and binary hashes. It also records kernel identity, CPU
placement and dependency versions. These inputs must remain unchanged until
the session ends.

The provider must advertise capability version 7 through 12 with feature bit 6
(address guards). The current provider is version 12. The published entry must
use the spin clobber interface, called ABI1, and image requirement value 2.
That requirement selects an immutable generated image: active frames retain the
same code and guard-site records until retirement. The runner checks a positive
image-generation identifier as well as the registry's ready state.

The payload stores a valid pointer in a local stack slot. A second pointer
selects either a separate pointer cell or that stack slot; both contain the
same valid address. Four phases use one provider/source session:

1. `cold-warmup` uses the separate cell and permits translation to settle.
2. `cold-delegated` repeats that case and requires positive, equal generated-body
   entry and completed-body counts. A completion requires the matching outer
   unlock; ready publication alone does not qualify.
3. `hot-escape` selects the live stack slot after all earlier workers join. The
   address check must return before the original load, identify the exact
   source instruction, image generation and worker, then resume that load on
   the original waiter. The entry must become `NATIVE_ONLY`, meaning later
   invocations use local execution for this source session.
4. `post-ban` repeats the aliasing case after the hot workers join. Operations
   must remain correct with no additional generated-body entries, completions
   or address-guard exits.

Every operation increments a counter before the load and another afterward.
The runner requires each increment exactly once, the expected loaded value,
original-task identity, mutual exclusion and unchanged preemption/interrupt
state. The alias never targets a return address or lock cookie. An immediate
comparison overwrites arithmetic condition flags before their next use, so this
probe does not require the spin continuation to restore incoming arithmetic
flags. The production guard count records validated exits, not completion of
the remaining native code; the operation checks supply that separate evidence.

This contract covers a reviewed eight-byte `MOV` load in a single outer ABI1
spin critical section. It does not authorize nested ownership, ABI3 rwlock,
arbitrary loads/stores, task-sensitive objects, fault recovery or general
processor-flag restoration. See the
[admission contract](../../../../docs/design/admission.md#checked-spin-pointer-loads)
for the exact source and flag-proof restrictions.

The payload uses an explicit ordinary store, so the separate analysis rule for
original CALL-word aliases does not remove this check. The
[string-service probe](../string_service/README.md) separately requires both
short and valid 300-character strings to complete through the original `strcmp`
API without helper prechecks. Neither contract removes this pointer-load probe.
That string probe now requires the optional version 11
[direct-call route](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md#direct-original-helper-calls).
Direct-call images cannot also contain address guards; the two probes test
separate execution paths. This address-guard probe passed and drained in
[candidate 2](../../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-2-checks).
The final bridge's [candidate 3 checks](../../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
passed separately; they did not rerun this unchanged guard path. The separate
[direct-route comparison](../../../../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed 567 validated sessions for read-only taskname and xattr tail with 16
and 128 entries. Those images contain no address guards and do not measure this
guard path.

A successful run additionally requires all workers to join, zero active
execution records, source retirement, ordinary module unload and a final idle
check. A timeout preserves callers and modules for diagnosis; it does not prove
drain or authorize forced unload. Keep failure records and separate unit,
live-functional and performance evidence. This guide describes the check,
not a measured performance result.
