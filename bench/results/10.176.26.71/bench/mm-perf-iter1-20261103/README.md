# Delegated mmap1 performance iteration

The current delegated candidate improves on its starting KD runtime, but remains
far below Native throughput. It is isolated on `codex/mmap-performance-iter1`;
`master` is unchanged. This is a two-worker result, not full-grid qualification.
The alternatives remain at `codex/archive-mm-dispatch-20261103` and
`codex/archive-mm-fetch-20261103`; the failed build remains at
`codex/archive-mm-build-481f1497`.

## Throughput

One untraced application lifetime per model and source, with no repeated scored
points. Units are completed mmap/munmap pairs per nominal second from the two
post-warmup upstream samples. The exact output, identities and final retirement
hashes are in [points.json](points.json).

| Runtime | Threads | Processes | Change from starting KD: threads / processes |
| --- | ---: | ---: | ---: |
| Starting KD, `d8d21f08c652df3f01f9c8ef2b1698ce9e9aa11d` | 132.0 | 183.0 | — |
| Dispatch, `c9a46aa5600c44d81c18c632ba387475c3b1bda5` | 170.0 | 229.5 | +28.79% / +25.41% |
| Dispatch + instruction window, `0997fd7d550aafde9446d419b3b77e5fd90321cf` | 161.5 | 274.5 | +22.35% / +50.00% |
| Native, same kernel image in Native mode | 257,231.5 | 671,651.5 | separate comparison arm |

The instruction window loses **5.00% for threads** relative to dispatch alone,
while gaining 19.61% for processes. Retain both outcomes. A single round gives
no confidence interval and does not establish a noise bound. Current KD is
1592.76 times slower than Native for threads and 2446.82 times slower for
processes. Neither candidate is promoted or accepted as meeting the performance
goal. Nano, larger worker counts and a controlled NUMA comparison are unrun.

## Identity and workload

The unchanged will-it-scale revision is
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`, invoked directly as
`mmap1_threads -t 2 -s 2 -m` and `mmap1_processes -t 2 -s 2 -m` through ordinary
system calls. The runner retains six warmup samples and two measurement samples.
It maps/unmaps 128 MiB anonymous regions without touching their data. This does
not establish demand-page-fault throughput.

The VM has 64 vCPUs and 24 GiB, two 32-CPU NUMA nodes, fixed corresponding host pins
and 2 GHz frequency. Workers use CPUs 0/1 on node 0, collector 63 and profiler 62.
The KD executor pool is 0–61, including both nodes; actual executor placement is
not fixed to node 0. That pool and the host/topology checks are unchanged across
KD arms. This is not a same-NUMA versus cross-NUMA experiment.

All throughput uses `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, kernel component source
`1ab7124abb6140752c1f0bb6e862144d426a3875`, lazy preemption and plain logging.
KD boot `0be9cfa1-bb77-486b-8888-835a2ad6471d` uses `kd_mmap=on`; Native boot
`3ab0a031-d6ee-4da6-8959-81c13876c419` uses `kd_mmap=off`. The explicit schema-2
bundles are `linux70-kdscope5-kd-20261103` and
`linux70-kdscope5-native-20261103`. Image, workload and topology are matched;
these are Native-mode measurements in the scoped integration image.

KD uses the resident reached interpreter with `service_reached=1`, tracing off,
completion probes off and no translator daemon or prewarming. Compiled Native
regions have not been implemented for this path. No MM body or mmap1-specific
kernel adapter was changed in this iteration.

## Profile and source findings

Separate system-wide kernel cycle profiles use 199 Hz flat samples with monotonic
timestamps. Reports include only the actual application lifetime, including its
warmup. They are diagnostics, excluded from the throughput table. Every completed
flat profile reports zero lost samples. The `kthreadd` report label also contains
executor instruction samples; recording began before those tasks were created. See the three `*-perf-report.txt` files; they trim trailing whitespace only.
Raw report and recording hashes are retained in [profiles.json](profiles.json).

* Worker-side `native_queued_spin_lock_slowpath` fell from 22.24% of sampled
  kernel cycles to 0.22% after dispatch changes. `kd_service.c` previously called
  `wake_up_all(&kd_service_work)` for every ready request; every awakened worker
  then claimed through the same dispatch guard. Source ordering is verified;
  assigning the entire sampled slowpath to that guard is an inference because
  flat samples do not retain callers. The candidate uses one exclusive
  wake, registers before testing the work sequence, and retains the claim guard.
* `kd_service_capture_internal()` now uses an acquire-read only to skip origin
  arbitration while custody is on the executor. Actual admission/cancellation
  and every ownership change still recheck under their guards. This avoids
  unnecessary guarded polling without authorizing an action from a hint.
* The two leading positions in `kd_service_shadow_wait()` sum to 30.95% of
  system-wide kernel samples; two positions in `kd_service_capture_internal()`
  sum to 8.10%. Another 15.74% samples origin IRQ-save locking. These
  include waiting costs. Flat samples do not split that locking cost precisely
  between dispatch and admission.
* The instruction window changes `kernel_module/execution/reached.inc` and
  `include/kd_reached_session.h`. It freshly retains/reads up to 15 bytes for
  the current instruction step, including same-IP loops and service reentry.
  Every existing frame/context check remains. Failed optional lookahead retains
  the previous exact cached-length/byte fallback; it cannot reject a valid
  shorter instruction. No successor is decoded in advance.
* Worker IRQ-save locking falls from 6.88% to 4.64% of the respective profile
  totals; worker `memcpy` appears at 1.54% in the window profile. This is consistent
  with fewer source lookup/copy calls, but does not establish the cause of the
  untraced thread loss. No cache or NUMA cause for that 5% loss is asserted.

Module addresses in the first report were unresolved because recording started
before module load. Later profiles retain actual module section addresses and
symbol tables; the exact provider ELF files resolve them in
`dispatch-profile-resolved.json` and `fetch-profile-resolved.json`. No initial
module base was assumed to establish a source attribution.

The remaining large Native gap is measured. Source inspection verifies repeated
scalar interpretation, per-instruction context/source checks and retained Native
instruction/API services. Their exact contributions to the entire gap have not
been isolated. The evidence supports prioritizing reached-path compiled spans
and pending-admission polling next; no speedup for either is claimed here.
Ownership/source/frame probes must remain intact.

## Functional and delegation evidence

[functional-checks.json](functional-checks.json) records the VM-only builds and
focused checks: 1493 Native arithmetic/addressing checks plus three mutations,
13 canonical admission cases plus four mutations,82 fetch checks, and all 11
actual killable/nesting/downgrade phases on each optimization candidate.
The earlier scalar build also passed 67,643 resident execution assertions.
Actual phases cover queued cancellation before holder release, selected reader
drain cancellation, nested cancellation preserving parent effects, delegated
read-tail exclusion, a fresh following writer, depth 9 and 128 child-node reuses.

The final two-model detailed check uses the same frozen runtime source
`0997fd7d550aafde9446d419b3b77e5fd90321cf`, on a separate `log_buf_len=16M`
boot `d106d3fc-97e7-45ff-a6bd-fda9c4a444e1`. Its numbers are not throughput
comparisons. It completed all original trace, binding, source retirement and
normal unload checks with zero dropped records or kernel diagnostics.

| Audited observation | Threads | Processes |
| --- | ---: | ---: |
| Returned other-task critical sections | 1528 | 3156 |
| Delegated downgraded read tails | 764 | 1577 |
| Later same-executor/object writer observations | 758 | 1515 |
| Individually joined syscall pairs | 16 | 16 |
| Retained Native API transactions | 29809 | 35458 |
| Retained instruction transactions | 55086 | 99703 |

The audit does **not** account for every application invocation or measure
physical batch length. Later writer observations alone do not prove fresh
reader drainage; that ordering is tested separately by the live continuation
fixture. No whole-kernel/API coverage is inferred from these checks.

If an episode is defined as entered request to returned request, the separate
trace run's mean envelopes are 4.194/6.393 ms for thread mmap/munmap and
4.676/5.209 ms for processes. They include interpreter time, services and read
tails; they are not pure critical-section CPU time or batch length. No
critical-section ratio is measured in this iteration.

The timed and detailed-check providers have different artifact hashes. Their
`.text`, `.rela.text`, `.rodata` and `.data` bytes match exactly; both artifacts
and comparisons remain separate in
[provider-code-comparison.json](provider-code-comparison.json). Full proof
hashes and coverage limits are in [delegation-summary.json](delegation-summary.json).
The resident log (512,713,929 bytes) and full joined ledgers remain on the VM, not copied
into Git.

## Retained failures and cleanup

* The initial setup at runtime `111170d5` stopped at source/family quiescence before
  launching mmap1. A later connection reached unsupported GS-source ADD at
  `ffffffff81828ca9`; it did not establish the setup failure's cause. Reached
  operation8 was added through the exact original-task instruction channel.
* The perf control-ack setup reported `Thread and evlist pollfd index mismatch`
  before provider/application start. Ordinary recorder workload readiness
  replaces that setup.
* The next application returned 130 pairs/s but triggered the call-chain
  unwinder's frame-pointer diagnostic. It is excluded. A later connection
  reached memory-destination GS ADD at `ffffffff81828d5f`. General reached
  operations 9/10 now support accounting ADD and compare with actual Native
  flags/ACKs. The new write cannot alter preempt-count ownership through an
  unimplemented transition. Image publication explicitly refuses these new
  reached-only operations.
* The first dispatch build at `481f1497` failed because `wait_event_exclusive()`
  does not exist in this kernel. The corrected candidate uses
  `prepare_to_wait_exclusive()`, a sequence recheck and `finish_wait()`.
* Launcher path/CPU-option setup mistakes stopped before a build or application;
  their original local logs remain. They are not test passes or measurements.
* Both starting KD points and the dispatch thread point initially observed
  residual bindings. Later exact checks observed zero and retired normally,
  without repeating applications. The cause is unidentified. Subsequent runs
  retain bounded ordinary CPU activity after factory deactivation; all original
  final zero-state checks remain. Counts dropped 3→0 and 1→0 in completed runs,
  but that observation alone does not isolate why the objects were retained.

Each live attempt used the verified recovery snapshot
`kdlock-builddisk-clean-20261031`. Failed attempts, raw recordings and original
receipts remain under guest `bench/mm-perf-iter1` and `tests/reached-mm-*`.
Two approved current log files were cleared only after diagnostic records were
retained. Historical logs, builds, recovery data and all benchmark results remain.
The VM returned to its maintained `7.0.0-38-kdlock1` kernel, idle with the normal
default boot unchanged; [vm-final.json](vm-final.json) records its separate
post-experiment identity and headroom.

No candidate is merged to master. The shared-mm thread tradeoff, Native gap,
Nano gate, larger-worker/NUMA coverage, unvalidated call-chain collection and
general unreached instruction/API combinations remain explicit limits.
