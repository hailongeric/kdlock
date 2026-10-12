# Direct spin workloads

| Component | Responsibility |
| --- | --- |
| [module.c](module.c), [runner.inc](runner.inc), [api.h](api.h) | Ioctls, worker lifecycle, fixed/timed loops and snapshots |
| [payload.h](payload.h) | Cacheline updates |
| [hash_payload.h](hash_payload.h) | Preallocated hash move/conflict/miss logic |
| [post_work.h](post_work.h) | Shared lock-outside arithmetic |
| [direct.h](direct.h) | Compile-time Native/TCLock/KD direct APIs |
| [scenario.h](scenario.h) | Plain operation and selected KD nested/early cases |

Each backend owns its own object and uses one protocol throughout the session.
KD uses `kd_spinlock_t` and paired direct macros; its per-CPU heat cookie selects
entry, while exact owner state selects unlock. The outer operation uses the pair;
nested translated controls retain ordinary direct clobber entries. Preparation
registers the named continuation before measurement. See
[execution flow](../../docs/JIT_EXECUTION.md) for adaptive/native/JIT details.

Timed workers publish progress and check deadlines every 256 complete operations.
Hash random streams and local result counts remain per worker; final static
snapshots validate table structure and exact operation totals independently of
approximate progress. Cacheline/hash business logic, compile and UBSAN policy
are matched across arms.

After every unlocked body, `sc_post_work` executes 64 dependent multiply/add
rounds (128 ALU instructions), up from four rounds. Spin and mutex share this
helper for cacheline and hash runs, including warmup. `SC_POST_WORK_ROUNDS`
permits compile-time values 1..256, for example
`KCFLAGS=-DSC_POST_WORK_ROUNDS=256`; rebuild every compared arm with the same
value. Post-work remains register-only and adds no clock reads or scheduling
points. Throughput includes this work; four-round historical results describe
a different workload.

[The direct runner](../../bench/tclock_compare/README.md) builds matching modules,
warms every worker and verifies data, ABI, actual JIT where required and drain.
Stop calls and retire sources before unloading; do not replace only the workload
and reuse old provider/JIT artifacts. Shared top-level build guidance is in
[workload_modules](../README.md).
