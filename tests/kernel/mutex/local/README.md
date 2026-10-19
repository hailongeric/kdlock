# Compact KD mutex ordinary API probe

Run this probe only in the verified recovery guest on `10.176.26.71`, following
[VM operations](../../../../docs/operations/VM.md). Confirm a real recovery
snapshot and set its recorded environment variables before running:

```sh
timeout 600s python3 tests/kernel/mutex/local/run.py \
  --output /root/kdlock-evidence/10.176.26.71/tests/mutex-local-<new-run>
```

The runner verifies the captured kernel, copies and hashes source inputs
(including private `.inc` files), and builds the provider and probe from that
frozen copy. It captures command records, module hashes, kernel messages and
`result.json` in a new external output directory. No translator or generated
image is used; `jit_bodies=0` describes the ordinary API scope.

The probe checks native 32-byte size, 8-byte alignment and matching embedding
offsets at compile time. Live checks cover 160,000 operations by eight workers,
exclusion, sleeping and nested owners, interruptible and killable cancellation,
I/O accounting and trylock. It initializes 2,048 independent objects twice at
the same addresses, then frees them without calling destroy. The exact auxiliary
index must stay empty during ordinary ownership and after drain.

Module initialization prints its exact PASS record only after the workers join
and the lock state drains. The runner requires all layout, address-reuse,
no-destroy and no-auxiliary fields before ordinary probe unload. It then retires
the source session, checks zero remaining source references, unloads the provider
and verifies final idle. A timeout, missing PASS record or kernel fault never
proves drain: the runner retains remaining modules and records the failure.

These checks do not demonstrate delegation or performance. The separate
[auxiliary unit fixture](../../../unit/mutex/test_mutex_aux.py) checks lazy
allocation, same-address retirement, allocation failures, exact owner/invocation
references and concurrent lookup/publication.
