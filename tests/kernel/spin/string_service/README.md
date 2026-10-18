# Original strcmp service and native continuation

This probe checks the original kernel `strcmp` helper inside one delegated spin
critical section. A typed service is a specific helper call whose arguments,
return value and memory effects have an explicit contract. This service calls
the captured kernel implementation with the original pointers; it does not
replace comparison with another algorithm or a copied-string comparison.

The [runner](run.py) reuses the source freezing, worker placement, effect checks
and retirement machinery of the
[address-guard probe](../address_guard/README.md). Follow that guide and
[VM operations](../../../../docs/operations/VM.md) for the verified recovery
snapshot and pinned environment. Run in the guest with a new output directory:

```sh
timeout 900s python3 tests/kernel/spin/string_service/run.py \
  --cpus 0-15 --iterations 100000 --warmup-iterations 100000 \
  --output /root/kdlock-evidence/10.176.26.71/tests/string-service-NEW
```

The provider must advertise version 8 or 9 and feature bit 7 (string services).
The current provider is version 9. The image must use ABI1, the spin clobber
interface, with requirement value 4 and a positive immutable-image generation.
Version 9's separate bit 8 enables the bounded `strscpy_pad` writing service;
this probe does not exercise that service.

The [payload](../../../../workload_modules/jit_string_service/module.c) owns two
301-byte module arrays. They remain allocated and unchanged while workers run;
the control operation changes them only after all workers have joined.
Each protected operation increments a prefix counter, calls the actual
`strcmp`, records task identity and increments a suffix counter. The strings
are equal in both cases, so every call must return zero.

Four phases remain in one provider/source session:

1. `cold-warmup` uses strings with 15 nonzero bytes followed by a zero byte.
2. `cold-delegated` requires positive matching body-entry and completion counts.
   Successful service returns pass through the general dispatcher before the
   final unlock. The observation overlay counts each complete root invocation
   once, including this helper path.
3. `hot-escape` changes both strings to 300 nonzero bytes followed by a zero
   byte. They are still valid strings, but exceed the service's 256-byte
   preflight bound. Preflight is the bounded read check performed before the
   helper is invoked. Its refusal must preserve the pending CALL and earlier
   effects, resume the helper on the original waiter, and disable future
   delegation for this entry. The phase requires a body entry but no delegated
   completion, no address-guard event, and a refusal log naming the exact entry
   and helper.
4. `post-ban` repeats the long-string case with no further generated-code
   entries, completions or address-guard exits. The registry must remain
   `NATIVE_ONLY`, meaning local execution for later calls in this source session.

The pending CALL includes its already-pushed return address. Native continuation
must neither push it again nor repeat the prefix. Per-worker progress, exact
prefix/suffix counts, zero comparison results, original-task identity and lock
exclusion check the resulting behavior. Preemption and interrupt state must
also match the caller's original state. These checks complement the runtime's
exact source-CALL, helper-text, ownership and return-continuation validation.

The scope is one outer physical spin lock with audited, stable ordinary kernel
strings. A bounded no-fault read returns a failure for unreadable input; it does
not establish allocation lifetime or prevent concurrent changes. Generic
pointers, nested lock-control calls, unrelated helpers and whole-kernel string
calls remain outside this contract. An invocation permits 128 comparisons;
all other supported services and control continuations, including
`strscpy_pad(..., 64)`, share the existing limit of 16. See the
[comparison contract](../../../../docs/design/admission.md#bounded-original-strcmp-service)
and the separate
[writing-service contract](../../../../docs/design/admission.md#bounded-original-strscpy_pad-writing-service).

Acceptance requires workers to join, zero active execution records, source
retirement, ordinary unload and final idle inspection. Timeouts retain callers
and modules for diagnosis. This is a continuation correctness check, not a
throughput comparison; publication or unit success alone does not establish
live acceptance of taskname, xattr or the writing service.
