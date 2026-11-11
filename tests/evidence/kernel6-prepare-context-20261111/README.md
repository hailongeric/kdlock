# Kernel6 exact-context refusal and preserved preparation

Attempt01 used core `532b68a6`, frozen installer/source `02ffa1ec` and fresh
candidate `/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-01`.
[The result](payload/focused/result.json) records independent source copy0 in
17.027s and exact integration inspect0, followed by integration plan1. The
[actual refusal](payload/focused/integration-plan.log) was the nonunique
`bool is_rwsem_reader_owned(...)` definition context: its substring also
occurred in the separate RT static-inline implementation. The controller
returned1. No target application, make, compiler, kernel link, module or live
behavior was dispatched. This attempt is a failure, not a compile pass.

The complete candidate source, seeded output, copied package and input/receipt
backing remain in the guest. Nothing was edited, resumed, removed or retried in
that tree. Exact collected payloads use the [copy index](copy-index.json);
[collection metadata](collection.json) binds before/copy/after identity for the
nine retained VM files. These are actual command logs/receipts, distinct from
the authored explanation here.

[Post-stop verification](post-stop-pins.json), a separate bounded read-only
command, returned0 and matched all eight normal source integration inputs,
all71 kernel5 package inputs and14 kernel5 output hashes, candidate original
integration inputs, and the77 copied package/input files. It also found no
integration-application directory or make dispatch. The guest remained normal
`7.0.0-38-kdlock1`, boot `51b49fa4-4d99-457e-a73e-632b690eb95e`, taint0 and idle.
Those exact checks do not claim a complete whole-kernel filesystem audit.

Source fix `3512f5dd` adds the leading newline to both before/after literals,
uniquely selecting the native external definition and excluding the RT helper.
Independent source review checked this fix and every other callable-definition
prefix. It changes no lock algorithm or MM body. A separately reviewed fresh
attempt02 is being prepared; no result for it is implied here.

The [refreshed approved read-only recovery output](recovery-for-next-attempt.json)
was captured UTC2026-11-11T11:49:19.224816Z, SHA
`83c72e703940ca7527e3c9989eac7b95ac383744ce6b91ec7254a6afc2d7e9d9`.
It records the all-three-disk recovery tag, running VM, no block jobs and host
available242,846,973,952B. Its freshness must be rechecked at dispatch.
