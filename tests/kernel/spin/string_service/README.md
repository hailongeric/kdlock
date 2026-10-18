# Original strcmp with audited caller inputs

This probe checks the original kernel `strcmp` helper inside one delegated spin
critical section. A typed service is a specific helper call whose arguments,
return value and memory effects have an explicit contract. The audited caller
provides valid, stable strings under the physical lock, just as the original
kernel call requires. KD invokes the kernel helper using its original API
contract. It performs no helper-specific code, string or buffer checks at
publication or execution.

The [runner](run.py) reuses source freezing, worker placement, exact-effect checks
and retirement from the [address-guard probe](../address_guard/README.md).
Follow [VM operations](../../../../docs/operations/VM.md) for the confirmed
recovery snapshot and pinned environment. Run only in the guest, with a new
output directory:

```sh
timeout 900s python3 tests/kernel/spin/string_service/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/string-service-NEW
```

The provider must advertise version 10 and feature bit 9, which identifies
the original-API contract without helper prechecks. The generated image uses
ABI1, the spin clobber calling agreement, and the read-only string-service
requirement. Its positive
generation identifies an immutable image. The separate writing-service
requirement enables `strscpy_pad`; this probe exercises `strcmp` only.

The [payload](../../../../workload_modules/jit_string_service/module.c) owns two
301-byte module arrays. They remain allocated and unchanged while workers run.
Only the control operation changes them, after every worker has joined. Each
protected operation increments a prefix counter, calls the actual `strcmp`,
records task identity and increments a suffix counter.

Four phases remain in one provider/source session:

1. `cold-warmup` uses equal strings with 15 characters and a terminating zero.
2. `cold-delegated` requires positive matching body-entry and completion counts,
   zero comparison results and zero failed address checks.
3. `long-delegated` changes both strings to 300 characters plus the terminating
   zero. They differ only at their last character: the original helper must return
   minus one. These valid inputs exceed the former 256-byte precheck bound.
   They must now complete delegated bodies with no failed address checks,
   permanent refusal or image replacement.
4. `long-repeat` repeats the long-string case and requires continued complete
   delegation from the same image.

Per-worker progress, exact prefix/suffix counts, comparison values, original-task
identity, lock exclusion and unchanged preemption/interrupt state check the
resulting behavior. The runtime still checks execution ownership and the pending
CALL return word, and consumes that word exactly once. The generated image and
its source references stay pinned through completion and retirement.

The former bounded-preflight probe and its native-return/disable results remain
in the [fixed development evidence](../../../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
for source `c79d84f`. This revised probe checks the removal of redundant helper
checks. It does not treat unreadable, expired or concurrently mutated strings
as valid input. General helper admission and checked-address refusal retain
separate probes.

The candidate 6 run passed all four phases with correct effects, complete
delegated bodies and normal retirement. The
[current validation record](../../../../docs/VALIDATION.md#taskname-and-xattr-helper-validation)
links the frozen source and raw receipts and preserves earlier failed attempts.
Performance measurements remain pending.

Acceptance requires workers to join, zero active execution records, source
retirement, ordinary module unload and final idle inspection. A timeout retains
callers and modules for diagnosis. This is a correctness check, separate from
throughput measurements and whole-kernel integration.
