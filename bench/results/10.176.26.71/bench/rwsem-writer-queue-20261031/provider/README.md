# Measured provider instruction comparison

The reviewed offline inspector (`81039f0f107e45b9f8049b9946216b657ab952978dc4e2e4d4041e0d6c32d07e`) completed capture and comparison of the actual fresh nano providers: baseline `f7a84065e84474380faa37eeadfdf534abd72a68` and candidate `1b6f256b13e8743aa1fd7bdc958cc82ae7726463`. No guest operation, build, test, timing or artifact execution occurred in this inspection.

The baseline capture SHA is `850614716fb25ec1646214842818defcd8596cd4942c0dd2a317e6c37ab8f1c0`; candidate capture SHA is `5118834bb43898ce3e8cfda4a900e4a147c30744cd87dee537ab4f812c8510e8`. They live under `/dev/shm/kdlock-writer-queue-provider-{baseline,candidate}-20261031`. The completed pair receipt `/dev/shm/kdlock-writer-queue-provider-pair-20261031/comparison.json` has SHA `2ed7ec2afa76722b558364c7020b88fbab0a874fe78987c2c0064727ae2f5c2f`. Compact facts and exact ELF hashes are in `/tmp/kdlock-writer-queue-provider-pair-facts-20261031.json`, SHA `f873ce9af5333340f5fbab109974ccd0f61572fbaebc3c5fed60569f76e65bee`.

All ten provider profiles within each arm have identical function inventories and executable-section identities: 740 baseline functions and 753 candidate functions. This includes section, offset, size, bytes and relocation records, not whole-ELF identity. Each of the ten matched workload profiles has identical inventories for all 18 defined functions and executable sections across the two arms. The three representative providers have full objdump/selected-instruction records; their comparison is applicable to the identical provider code inventories in the remaining seven profiles.

| Function | Baseline bytes / instructions | Candidate bytes / instructions | Direct observation |
| --- | ---: | ---: | --- |
| `kd_down_read` | 820 / 194 | 84 / 24 | Candidate entry uses `LOCK INC`; failed acquisition calls outlined suffix. |
| `kd_rwsem_read_slowpath` | absent | 783 / 188 | Candidate suffix contains OSQ/wait paths and reader `LOCK INC`. |
| `kd_down_read_trylock` | 93 / 27 | 87 / 26 | `MOV 1` plus `LOCK XADD` becomes `LOCK INC`; rollback remains `LOCK DEC`. |
| `kd_up_read` | 36 / 11 | 36 / 11 | Exact bytes and relocation records match. |
| `kd_down_write` | 408 / 99 | 823 / 196 | Writer protocol branches are larger; no claim that every path executes the whole function. |
| `kd_down_write_killable` | 446 / 109 | 939 / 232 | Candidate calls scoped signal-aware gate and retains phase/drain wait paths. |
| `kd_local_lock_slow` | 1717 / 432 | 1504 / 389 | Actual ordinary slow body changes; candidate calls outlined waiter add/remove. |
| `kd_local_lock_slow_signal` | absent | 1569 / 405 | New scoped signal-aware local gate body. |
| `kd_mutex_local_lock` | 106 / 35 | 106 / 35 | Same normalized instructions and relocation targets; direct target addresses shift. |
| `kd_mutex_osq_lock` | 448 / 130 | 448 / 130 | One instruction has reversed CMP operands before JNE; it is not byte-identical. |
| `kd_mutex_osq_unlock` | 142 / 49 | 142 / 49 | Exact bytes and relocation records match; placement shifts. |
| `__kd_mutex_lock_slowpath` | 1145 / 254 | 1145 / 254 | Raw bytes and placement match; two cold-target relocation addends shift. |
| `run_combiner` | 5207 / 1069 | 5207 / 1069 | Raw bytes and placement match; three cold-target relocation addends shift. |

The reader observation is actual emitted code, not merely a source expectation. Candidate first-success entry retains the admission load/recheck and the reader atomic update while avoiding the baseline's large slow-path prologue. This does not imply that a contended acquisition executes fewer instructions: the new entry plus suffix total 867 bytes, and their executed paths differ by outcome.

The ordinary OSQ CMP change swaps `cmp %edx,%gs:cpu_number` with `cmp %gs:cpu_number,%edx`; its immediate branch is `JNE`, which uses the unchanged equality result. Raw and normalized comparisons deliberately retain this difference. This is a narrow inspection of that instruction pair, not a new runtime equivalence test.

The five changed section-relative relocations in delegation slowpath/combiner were separately resolved using the x86 PC-relative instruction-end adjustment. They still reach the same offsets in their respective `.cold` functions: slowpath +13/+0, combiner +36/+0/+79. Those cold functions have matching raw bytes and relocation records, but are placed 3,824 bytes later. The original comparison remains unchanged and records all addends; it does not silently erase these differences.

Other matched controls include `kd_mutex_local_lock_node` normalized instructions, exact local unlock/slow-unlock instructions, and exact `kd_spin_lock_nondelegated` / `kd_spin_unlock_nondelegated` bytes, offsets and relocation records. Try-write, downgrade and write-release preserve their observed normalized instruction sequences. This does not make the whole ordinary mutex path unchanged: its shared local slow body was compiled differently, as recorded above.

Provider `.text` grows from 134,694 to 138,542 bytes (+3,848), aligned to 64 bytes in both arms. Physical allocation, instruction/data cache residency, actual branch frequencies, scheduling, parking and NUMA ownership cannot be inferred from ELF bytes. This note neither explains any timing difference causally nor accepts the candidate. Use the separate single-round performance comparison and retained correctness evidence for those decisions.
