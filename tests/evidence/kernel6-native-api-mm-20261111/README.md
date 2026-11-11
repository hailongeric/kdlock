# Kernel6 native rwsem APIs and real mmap/munmap

The actual controller returned 0 with `NATIVE_API_AND_MM_COMPLETE`. The twelve native API cases passed, followed by the four-thread real syscall workload. Both modules unloaded ordinarily and the final activity list was empty. These are native-local compatibility and syscall results. [Actual controller result](collection/payload/runtime/result.json), [source-host command and return](source-host/controller/live-command.json), [independent saved-record audit](audit/native-audit.json).

| Binding | Actual value |
| --- | --- |
| Fixture source | `80c272e5f134d9a499c03782f71064d04fae25c3` |
| Core source | `532b68a65bdf96504e2cede6c23a5bc1476d94e9` |
| Kernel package | `3512f5dd639701f3f9953cfc6add1e4bbdd85e88`, 77 exact files |
| Running release | `7.0.0-38-kdrebuild6` |
| Boot ID | `4400eea1-c8fc-40e1-b6b7-f7a99ecc1364` |
| GNU Build ID | `5ed6cd8cffed6960ce901261dfab3bb019a0442d` |
| Configuration SHA256 | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| Taint | 0 before the fixtures, 4096 after ordinary unload |

The controller is `4be5676b…`. The actual final configuration is `f5c4605f…`, with fresh recovery `d165ff5e…`. The preceding configuration `fc8c636d…` is preserved. The final dispatch changed only the recovery SHA. Both raw running-note streams decode to the same kernel6 Build ID. Fresh postboot return0, identity and GS bytes are retained here, with the complete boot proof in its separate evidence directory. [Actual argv](source-host/controller/actual-argv.json), [final configuration](collection/payload/inputs/live-config.json), [postboot return](collection/payload/inputs/postboot-return.json), [postboot identity](proof/result.json), [GS proof](proof/gs-proof.json), [complete boot evidence](../kernel6-boot-20261111/README.md).

The compatibility module used `native_capacity=3` and a 2,000 ms wait bound. RUN returned 0 with state PASS2, all twelve case results 0, 19 workers created and joined, an idle pool, no module hold and no remaining worker/nonowner reference. Its four exact try results were `1,1,0,0`. The turn-wait and turn-cleanup flags were both 1. [Actual case status](collection/payload/runtime/compat-after-run.json), [driver result and fd closure](collection/payload/runtime/compat-result.json), [frozen case source](source-host/fixture/files/tests/kernel/rwsem_api/payload/rwsem_api_fixture.c).

| Case | Checked native behavior | Result |
| --- | --- | --- |
| 0 | Concurrent reader credits and writer exclusion | 0 |
| 1 | Trylock success/failure, callable APIs and cleanup constructors | 0 |
| 2 | Real write-to-read downgrade and concurrent reader admission | 0 |
| 3 | Nonowner read release after the acquiring task exits | 0 |
| 4 | Blocked interruptible read with SIGUSR1 | `-EINTR`, no grant |
| 5 | Blocked killable read with SIGKILL | `-EINTR`, no grant |
| 6 | Queued killable writer with SIGKILL | `-EINTR`, no grant |
| 7 | Available interruptible read with signal pending | Granted, return 0 |
| 8 | Available killable read with signal pending | Granted, return 0 |
| 9 | Available killable write with signal pending | Granted, return 0 |
| 10 | Killable writer owns its MCS turn while draining a held reader | `-EINTR`, no write grant, turn cleanup proved |
| 11 | Final pool/object quiescence and counter overflow check | 0 |

Compatibility counters were read acquire/release `10/11`, write acquire/release `10/9`, one real downgrade, four cancellations, two try misses and twelve MCS enqueues. The canceled head's physical queue cleanup is separate from a successful WRITE grant. STOP was unnecessary on this passing run. The driver closed its fd before ordinary module removal. [Complete compatibility result](collection/payload/runtime/compat-result.json).

The userspace client ran four same-mm pthread workers with 64 iterations each and a 60,000 ms cooperative deadline. Each iteration used actual anonymous private two-page mappings, deterministic zero/write/readback checks, unmap and absent-page checks, and exact-address reuse within its own guarded slot. All 256 iterations completed with zero worker, deadline or arena-cleanup errors. [Actual client stdout](collection/payload/runtime/mmap-client.stdout), [structured syscall result](collection/payload/runtime/mmap-result.json), [frozen userspace source](source-host/fixture/files/tests/kernel/mmap_api/userspace.c).

| Worker workload | Each worker | Aggregate |
| --- | --- | --- |
| Successful mmap calls | 192 | 768 |
| Successful munmap calls | 128 | 512 |
| mincore absent-page checks | 256 | 1,024 |
| Exact-address reuses | 64 | 256 |
| Fresh-zero bytes | 1,048,576 | 4,194,304 |
| Written bytes | 1,048,576 | 4,194,304 |
| Readback bytes | 1,048,576 | 4,194,304 |

The parent separately reserved and unmapped one 65,536-byte guarded arena. Those two calls are additional to the worker counts. Selected-gate counters cover the whole bound lifetime and are not equated with worker syscall counts. No test ioctl performs an MM body. [Actual arena and worker records](collection/payload/runtime/mmap-result.json), [binding/provider source](source-host/fixture/files/tests/kernel/mmap_api/payload/provider.c).

The selected MM gate used `native_capacity=64` and `source_calls=0`. Owner PID/TGID 3107 and exact mm/object/gate identities remained unchanged. One END attempt returned 0 with state RETIRED2, pool idle, all gate locked/write-locked/contended fields 0, no cleanup requirement and no counter overflow. Native counts satisfy both conversion balances. [Final selected-gate record](collection/payload/runtime/mmap-result.json).

| Native observation | Actual count |
| --- | --- |
| READ acquire / release | 1,544 / 2,057 |
| WRITE acquire / release | 1,285 / 772 |
| Real WRITE-to-READ downgrade | 513 |
| Try miss / cancellation | 374 / 0 |
| Physical callback begin / end | 1,285 / 1,285 |

The balances are `1,285 = 772 + 513` and `2,057 = 1,544 + 513`. They corroborate the actual retired/idle gate predicates and exact binding identities. The configured lane executes native bodies on the original tasks. `jit_observation_available=0` means JIT observation is unavailable, and `jit_entries=0` is not a measured absence proof. Generated execution and performance remain unmeasured by this run. [Actual counters and verdict](collection/payload/runtime/mmap-result.json), [independent audit](audit/native-audit.json).

All twelve controller subprocesses returned 0, including both ordinary removals. Final modules contain only `nls_iso8859_1`, with no fixture controls or activity. The raw kernel-log difference is the 79-byte out-of-tree module notice. The object-wide ordinary IRQ-enabled task-context and caller-established quiescence contracts remain explicit. Thread counts and event totals do not prove those caller obligations or broader API/context support. [Final identity, modules and commands](collection/payload/runtime/result.json), [raw logs](collection/payload/runtime/dmesg-after.stdout), [actual scoped configuration](collection/payload/inputs/live-config.json).

The complete stable guest collection contains 37 files and 208,348 bytes, with before/copy/after identities and hashes retained. The original transport archive, complete source-host dispatch records, the 83-file source archive and manifests, four extracted source files, fresh identity/GS/note bytes and independent audit are included. Every copied member is mapped to its exact source in the top-level index. The full kernel build and boot evidence remain separate. [Original guest index](collection/copy-index.json), [copy provenance](copy-index.json), [preservation summary](preservation.json), [source snapshot](source-host/fixture/manifest.json), [checksums](SHA256SUMS), [build evidence](../kernel6-build-20261111/README.md).
