# Native continuation validation

Continuation implementation `9a0fdd4`, with fixture-only corrections through
`a4eb4eb`, passed basic and directly affected checks in the recovery VM.
Live continuation probes are in progress. This is separate from the completed
[`d21a1e3` public-mutex performance matrix](../../bench/mutex-public-20261020/README.md).
No whole-kernel replacement, mmap/fault integration, RT/ww_mutex or lockdep
acceptance follows from this work.

The source host is the sole writer. Builds and tests use frozen, committed
source copies only in `root@10.176.26.71:2222`, under
`/root/kdlock-evidence/10.176.26.71/tests/native-continuation-20261020`.
The guest kernel has not been modified or rebooted.

## Attempts and corrections

| Attempt | Source | Outcome |
| --- | --- | --- |
| checks-1 | `9a0fdd4` | Dependencies, W=1 provider and Werror daemon passed. Unit aggregate: 28 passed, three drivers failed. Remaining benchmark checks did not run. |
| checks-2 | `390d04c` | Dependencies, provider, daemon, both basic programs and all 29 selected unit drivers passed. First benchmark driver failed compiling a stale observation fixture. |
| checks-3 | `d7d65c1` | Spin/cacheline, list-image audit and direct-comparison drivers passed. Rwlock/rwsem benchmark driver failed on missing fixture metadata. |
| checks-4 | `a4eb4eb` | All 26 rwlock/rwsem benchmark tests passed; final idle and source hashes verified. |

All failed attempts and original results remain under their numbered
directories. Each failed process exited; a separate `post-failure-health.json`
then established VM idle and unchanged current/frozen source hashes. The
original scripts leave `final_idle` and `source_unchanged` false on an early
failure because those final checks did not run; the later receipt supplies
the independent verification without changing that original result.

Corrections are confined to tests:

- `390d04c`: provide both clobber symbols in the expanded-text fixture; map
  paired ABI2 fixture calls to KD local control symbols; scope the unused-C-
  parameter warning exception to the unchanged assembly helper that reads its
  argument through `%rdi`. Exact control, restoration and refusal assertions
  remain. All 24 paired-JIT cases and both 320-case spin restore builds then
  executed successfully in checks-2.
- `d7d65c1`: model the observation sysfs parameter's actual argument and
  read-only completion-probe permission. Check disabled and wrong-lock behavior,
  distinct entry/completion counters and accumulation across CPU slots.
- `a4eb4eb`: include the ordinary image's `requirements=0` in the rwsem
  publication fixture. Production publication checks are unchanged.

The third and fourth attempts select only remaining affected benchmark
drivers. Passed provider, daemon and unit inputs are byte-identical to checks-2;
their validation is retained under that exact revision, not relabeled as a
new run. Skips, missing dependencies and compile failures are not passes.
The successful benchmark drivers contain 16, five, 58 and 26 tests respectively,
with no reported skips.

## Remaining live scope

After the selected benchmark checks pass, the serialized plan covers checked
native exits for mutex OUTER, public DIRECT, spin, rwlock and rwsem; address-
guard and string-service regressions; ordinary mutex and rwsem ownership
probes. Positive JIT probes must demonstrate returned cold bodies, the exact
hot native continuation, sticky refusal and final drain. Publication alone
does not satisfy them. Reader contention must remain visible in shared-lock
families. Caller timeouts do not prove drain and must retain unsafe state.

Resident-list functional and matched prefetch measurements remain separate
subsequent stages. The seven original mutex regressions, incomplete comparisons
and unmeasured p95 gap remain open; correctness progress is not performance
acceptance.
