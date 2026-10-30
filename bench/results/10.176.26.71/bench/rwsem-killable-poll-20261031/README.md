# Bounded killable-writer polling: completed comparison, candidate unaccepted

The isolated candidate is **not accepted**. Both fresh nano arms completed and
passed offline validation: 420 points, 210 matched pairs, strict host
qualification and zero unscored coordinates. The **no-regression evidence gate
failed**: 120 pairs lost whole-interval throughput, 120 lost peak throughput,
and 123 lost at least one metric. Every negative is retained. The completed `mmap1` comparison has **16 thread
gains and 5 thread losses**, and **2 process gains and 19 process losses**.
At 20 workers, threads changed by **+135.3946%** and processes by **−0.7062%**.
These are separate models under explicit prospective functional eligibility;
the original strict mapping failure remains failed. No Linux Native parity or
performance acceptance is claimed.

| Identity | Exact commit |
| --- | --- |
| Baseline provider | `f7a84065e84474380faa37eeadfdf534abd72a68` |
| Candidate provider | `22d62d5c13cad3c61c97dd47524da908769f1a52` |
| Candidate documentation before code | `2c4882f8cded1456fb6face980d717f3ee6c3ed1` |
| Baseline scope1 kernel recipe | `8446f4ecb08816380a4c233197a8ce5e4d333aac` |
| Candidate scope2 kernel recipe and common MM harness | `f4ae82cfdf053c679c5d09ee8e503a7919764c9b` |
| Separate signal-probe source | `43dd256e7e0eba7639d4db87c0eaa450f6d86d41` |

`kernel_module/kd_rwsem.c` adds at most **16,384 reservation probes** before the
existing killable writer admission wait. Each probe attempts reservation first.
After failure, `need_resched()` or any `signal_pending(current)` ends this
unpublished polling interval; otherwise it executes `cpu_relax()`. A successful
reservation returns immediately and is consumed exactly once. A false result
enters the unchanged `wait_event_killable`, including its condition recheck and
fatal-only cancellation semantics. Gate acquisition, reader drain, rollback and
release remain unchanged. The exact provider delta is retained in
[provider-rwsem.diff](source/provider-rwsem.diff).

The scope2 recipe applies that same rwsem C delta to the original scope1 recipe,
preserving its API/mutex headers and MM bodies. It adds explicit scope2 identity
profiles. Actual preparation recorded only
`kernel/locking/kd_mmap/kd_mmap_rwsem.c` changing among generated kernel sources,
and only `CONFIG_VERSION_SIGNATURE` changing in the configuration. This is a
local writer-admission optimization. MM readers and writers still execute the
native critical-section bodies on their originating task; no MM body delegation
is introduced.

| Recorded initial check | Outcome and scope |
| --- | --- |
| [Focused units](prerequisites/units/result.json) | Six selected checks passed; 25 deterministic scenarios and 10 assertion mutation controls. |
| [Live rwsem](prerequisites/live/result.json) | 17 API checks and 10 cancellation checks; zero errors, drained. |
| [Four-family basic](prerequisites/basic/result.json) | Spin, mutex, rwlock and rwsem each completed 1,600,000 operations with positive, equal JIT entry/completion counts; final idle. |
| [Real-kernel signal probe](prerequisites/live_signal_probe/result.json) | Four busy/free × SIGUSR1/SIGKILL cases passed; zero errors and inconclusive cases, drained. |

These initial checks ran on boot `8c5259e3-0f93-493d-afa9-bd93d5358683`,
`7.0.0-38-kdscope1`, with the candidate provider source. They do not constitute
scope2 runtime or fresh same-boot validation. Initial unit/live results remain
prior-boot functional prerequisites; fresh four-family basic checks are recorded
separately. The signal probe
extracts the actual helper bodies and uses real kernel atomics/signals with
observation wrappers; it does not prove the uninstrumented provider binary or
queued cancellation behavior. Its first upload failed before guest extraction
or build; the exact failure is retained under
[failed-signal-upload](prerequisites/failed-signal-upload/).

| Recorded scope2 step | Outcome and limit |
| --- | --- |
| [Preparation](prerequisites/preparation/result.json) | Five affected profile drivers passed; generated/config deltas verified; affected objects compiled. |
| [Full build](prerequisites/build/result.json) | `-j32` build completed, including 6,901 modules; source and configuration unchanged. |
| [Preinstall](prerequisites/preinstall/result.json) | Three linked API sites and four bridge shapes checked; a fresh candidate provider was built against scope2. Live ABI validation remains false. |
| [Module stage](prerequisites/stage/result.json) | All 6,901 stripped modules matched their loadable build identities and release. |
| [Installation](prerequisites/install/result.json) | New modules, boot files and initramfs installed; 1,188 initramfs modules. Old protected paths and normal boot default preserved. This receipt does not prove a scope2 boot or runtime behavior. |
| [Boot-entry append](prerequisites/append/result.json) | Separate entries appended; existing normal default preserved. This receipt neither arms nor proves a scope2 boot. |

The later MM preparation booted scope2 in Native mode, then returned to scope1
in KD mode. These are image/backend identity and view-restoration records,
**not MM functional or performance passes**:

| Boot preparation evidence | Exact recorded boundary |
| --- | --- |
| [Scope2 Native arm](mm-boot/scope2-native-arm/result.json) | Armed the separate entry; did not reboot. |
| [First scope2 request](mm-boot/scope2-native-reboot/result.json) | Failed the freshness check with `commands=[]` and `reboot_requested=false`; no boot mutation. The failed attempt remains unchanged. |
| [Successful scope2 request](mm-boot/scope1-observe/scope2-request.json) | Independently recovered durable request receipt: `REBOOT_REQUESTED_NOT_VERIFIED`. Its separate transport's empty result and small logs remain under `scope2-native-reboot-r2`. |
| [Scope2 Native postboot](mm-boot/scope2-native-postboot/result.json) | Verified `7.0.0-38-kdscope2`, Native MM mode, boot `6dcbd9dd-2d8c-4743-96f6-a43f70f8ab8e`. This is not KD MM execution evidence. |
| [Scope1 arm](mm-boot/scope1-arm/result.json) and [durable request](mm-boot/scope1-observe/request.json) | Separate return selection and successful request; the interrupted transport result read is retained under `scope1-request`. |
| [Scope1 output restoration](mm-boot/scope1-output-bind/result.json) and [postboot](mm-boot/scope1-postboot/result.json) | Restored the exact preserved build view and verified scope1 KD identity on boot `43101fa8-697a-46ad-99c9-be4b39cce0b3`. |
| [Read-only harness bind](mm-boot/baseline-source-bind/result.json) | Bound the exact f4ae harness view for the upcoming baseline MM steps; no MM check or score is inferred from this operation. |

The fresh nano cohort uses boot `760d4758-28b8-4903-b1d5-5bbb8938430d`,
`7.0.0-38-kdlock1`. The [normal postboot result](fresh-cohort/normal-postboot/result.json)
independently confirms the new boot and unchanged normal default. The reboot
command returned successfully; the transport's subsequent result fetch failed
during reboot and retained an empty result file.
[The reconnect observation](fresh-cohort/normal-request/reconnected-observation.json)
and postboot proof remain separate from that transport failure. This is an
ordinary-kernel transition, not a scope2 runtime validation.

[The new pool activation](fresh-cohort/pool/policy.json) records cohort
`kernel-killable-22d62d5c-20261031`, with min/max 64 workers and `aio-max-batch=0`.
Its [actual reference](fresh-cohort/pool/reference.json) contains 131 tasks,
including 64 workers. Earlier host qualification is not reused.

| Fresh nano evidence | Current retained outcome |
| --- | --- |
| [f7 basic controller](fresh-cohort/f7/basic/result.json) | Completed, return code 0, final idle; the [full runner result](fresh-cohort/f7/basic/runner-result.json) and four session receipts show returned JIT bodies. |
| [22d basic controller](fresh-cohort/22d/basic/result.json) | Completed, return code 0, final idle; the [full runner result](fresh-cohort/22d/basic/runner-result.json) and four session receipts show returned JIT bodies. |
| [f7 measured controller](nano-baseline/run/result.json) | Completed and idle; 210 one-round points also passed the source-host replay. |
| [f7 archive controller](nano-baseline/archive/result.json) | Completed and idle; 11 groups in the [archive index](nano-baseline/archive/archives.json). Immediate endpoint receipts and before/after captures are retained separately. |
| [f7 offline fetch continuation](nano-baseline/fetch-offline-r2/result.json) | Copied-byte checks passed for 11 compressed groups, 2,326 regular transport files and eight confined relative workspace links. This is not score validation. |
| [22d measured controller](nano-candidate/run/owner.json) | Completed and idle; 210 one-round points also passed the source-host replay. Its [archive receipt](nano-candidate/archive/owner.json) and [endpoint receipt](nano-candidate/endpoint/receipt.json) remain distinct. |
| [Paired offline audit](nano-comparison/validation.json) | Both complete source/provider/image/raw-point chains validated under the same kernel, topology, workload settings and fresh host cohort; no-regression gate failed. |

The [first fetch receipt](nano-baseline/fetch-failed/transfer.json) records a
successful remote tar followed by local refusal of eight expected basic fixture
symlinks. This was a local extraction failure, not a timing or archive failure.
The reviewed r2 continuation reused that exact tar without network or VM calls,
recreated only same-family source links as relative local links, and preserved
[their original metadata](nano-baseline/fetch-offline-r2/transport-links.json).
The original failed receipt, tar and partial tree remain unchanged. The full
separate basic/control trees and compressed archives remain in the actual
source-host tmpfs directory named by
[analysis-arm.json](nano-baseline/fetch-offline-r2/analysis-arm.json); this volatile
copy does not replace the original guest evidence.

The exact [210-pair CSV](nano-comparison/comparison/points.csv) and
[summary](nano-comparison/comparison/summary.json) are unchanged analyzer output.
[The workload table](nano-comparison/interpretation/README.md) includes the worst
whole/peak loss for every workload and all 20/32/60-worker changes;
[key-points.csv](nano-comparison/interpretation/key-points.csv) retains their exact
baseline and candidate rates. At 20, 32 and 60 workers, respectively, 4, 8 and 6
of the ten workloads lost each metric. Independent integer-arithmetic review is
retained [separately](nano-comparison/independent-arithmetic-review.json).

The largest whole-interval loss was `rwlock c01 w1` at 7 workers:
9.494959 million to 7.977512 million operations/s, **−15.9816%**; peak changed
by **−15.9976%**. Both arms were `NO_JIT`. Of 77 `NO_JIT`→`NO_JIT` pairs, 42
lost at least one metric; 78 of 127 returned-JIT→returned-JIT pairs did so.
The six remaining pairs changed execution class and remain scored and visible.
All 210 published `jit.bin` hashes match across arms. Full provider/workload
ELF hashes differ; that alone does not establish instruction differences or a
cause. Matching generated bytes do not prove identical data placement or context.

Verified in source, the new helper is confined to killable writer admission;
the ordinary/prepared nano paths do not call it directly. These nano results
therefore measure regression risk, not the proposed MM admission benefit.
The results do not establish a parking fraction or explain the observed losses.
One sequential round per point supplies neither variance estimates nor causal
evidence. No loss is dismissed or removed on that basis.

The baseline MM arm is now complete on scope1-KD boot
`43101fa8-697a-46ad-99c9-be4b39cce0b3`. The eight step controllers completed,
drained and reached final idle. Exact results and the limited meaning of each
check are retained in [functional-summary.json](mm-baseline/functional-summary.json):

| Baseline MM evidence | Recorded result |
| --- | --- |
| [Writer sites](mm-baseline/steps/sites/runner-result.json) | Exact writer-call return PCs captured; this capture is not a live contention or teardown pass. |
| [MM API check](mm-baseline/steps/api/runner-result.json) | 161 checks, including 8 API and 3 cancellation checks; zero errors and idle. |
| [Mapping/lifetime checks](mm-baseline/steps/mapping/runner-result.json) | Six cases passed; the 16-worker cycle completed 80,000 operations with all workers joined and nine rejected observation mutations. |
| [Fault/retry checks](mm-baseline/steps/faults/runner-result.json) | 596 checks, 16 retry/VMA-split rounds, 16 children and 16 fault threads joined. Separate callback coverage limits remain recorded. |
| [Completed-fault check](mm-baseline/steps/completed/runner-result.json) | 64 entries, returns and completed events; zero errors/misses; writer reacquisition observed. |
| [Application lock identity](mm-baseline/steps/mmap1-identity/runner-result.json) | Two diagnostic threads shared one mm; two diagnostic processes used two mms. This proves those diagnostic lifetimes only, not the timed mm addresses or delegation. |
| [Unchanged mmap1 grid](mm-baseline/steps/mmap1-measure/runner-result.json) | All 42 one-round sessions passed and drained: 21 thread counts and 21 process counts. All 42 pairs now passed offline score replay; see the separate final comparison below. |
| [Immediate endpoint](mm-baseline/steps/endpoint/runner-result.json) | Captured 3.1721 seconds after child exit; both strict comparisons passed with the same 131 tasks. Endpoint identity is not uninterrupted isolation or performance acceptance. |

The [archive receipt](mm-baseline/archive/owner.json) and
[offline continuation](mm-baseline/fetch-offline-r2/transfer.json) bind four
compressed groups and 1,779 regular members. The
[first fetch](mm-baseline/fetch-failed/transfer.json) completed transport, then
failed only during local module import (`fresh_controls` was not on the import
path). The r2 continuation verified the same retained tar without refetching,
VM calls or new timings; the original failed receipt, tar and partial tree remain
unchanged. The exact [source-view unbind](mm-baseline/source-unbind/result.json)
is separate from MM functional and timing evidence. This baseline evidence is distinct from the paired results below and does not grant acceptance.

The candidate MM mapping check **failed before any candidate MM timing** on
scope2-KD boot `fe7fa10a-13fb-4bb3-b730-eb99db9200cd`. Its
[original controller](mm-candidate-failure/transport/result.json) and
[runner result](mm-candidate-failure/observed/result.json) remain failed and
undrained, with the controller retaining `drain_unknown=true`. The
[16-worker log](mm-candidate-failure/observed/02-cycle-16.jsonl) records all workers
joined, 80,000 completed operations, zero worker errors and zero final VMAs,
but the required strict sleeping-writer stack witness was not observed.
Operation completion does not satisfy that missing oracle.

The [later health observation](mm-candidate-failure/observed/drain-observation.json)
records `files=0 mm_refs=0 destroyed=3 release_errors=0`, no candidate processes
and zero module users. That separate observation does not rewrite the original
failure or prove a later normal unload. Compact original receipts, the empty
kernel log and the complete 16-worker diagnostic log are retained. That failed attempt supplied neither an all-pass verdict nor paired MM
performance evidence; see the [failure summary](mm-candidate-failure/summary.json).

A subsequent [normal-unload/preservation receipt](mm-prospective/candidate-mapping-preserve/result.json)
records actual idle and a full archive of the failed arm using the executed
`8452a6ab` helper. Original failed flags and canonical paths remain unchanged;
the unexecuted `b42fc933` revision is not evidence of that action.

The separate prospective continuation uses explicit **`mmap-functional-v1`**:

| New evidence | Recorded result and limit |
| --- | --- |
| [Functional mapping controller](mm-prospective/candidate-mapping-functional/result.json) | Six fresh cases passed and drained. Only the 16-worker cycle used functional eligibility; its ordinary writer observation was `inconclusive`. The other five cases retained strict behavior. The exact runner result SHA is `666eea31f715ca523d86001bb8c2eb710ba5000a0b9b6672056b0e39e5170b48`; its [full result](mm-prospective/candidate-mapping-functional/runner-result.json) is now retained from the verified candidate archive. |
| [Separate strict-hold result](mm-prospective/candidate-strict-hold/result.json) | Actual mmap and munmap syscall witnesses passed, with nine rejected mutations each, exact holder retirement, normal unload and final idle. The controlled held interval is artificial and does not supply the missing observation in the free-running cycle. |
| [Baseline compatibility record](mm-prospective/baseline-compatibility.json) | Later source-host interpretation of the original six-case strict pass, actual witness and nine rejected mutations. Original baseline policy, receipts and timing remain unchanged; no baseline point was repeated. |

The new measurement controller runs the unchanged mmap1 binary and runner with
the new mapping-result path. A separate policy receipt binds the actual raw
measurement hash; raw results are not amended to claim another eligibility
policy. Both finalized archives and all 84 raw points passed the
[paired replay](mm-comparison/validation.json); the exact
[measurement policy](mm-candidate/measurement-policy.json) remains separate
from raw results. Host strict qualification passed, while strict/performance
qualification and acceptance remain false. Neither the prospective policy nor
the supplemental strict proof reverses the failed nano gate.

The [complete comparison](mm-comparison/README.md) retains all 42 rows and all
24 negative points, with exact [thread](mm-comparison/threads.csv) and
[process](mm-comparison/processes.csv) CSVs. The metric is completed mmap/munmap
pairs per nominal second, calculated from two post-marker integer samples
divided by 2. At 20/32/60 workers, threads changed by +135.3946%/+68.4958%/+88.4653%;
processes changed by −0.7062%/−1.6346%/−10.9973%. The worst thread loss was
2 workers, −44.4340%; the worst process loss was 60 workers, −10.9973%.

Improved contended thread points are consistent with avoiding some wait
transitions; no parking fraction or cause was measured. Uncontended independent-mm
admission exits on its first successful probe, so the 19 process losses cannot
be blamed on exhausting the spin budget. Their cause remains unresolved.
The first offline replay failed only on diagnostic/common README source-domain
classification; its [failure](mm-comparison/failed-replay/validation.json) and
[precise correction](mm-comparison/tools/README.md) are retained. No timing was repeated.

The fresh comparison retains **one round per point**, with no historical
Oct30 rates or qualification pooled into it:

- Nano: completed 210 KD points per provider, 210 matched pairs, on the ordinary
  `7.0.0-38-kdlock1` kernel with matching workload, topology and instrumentation.
  Whole-interval and peak rates, every loss and every `NO_JIT` classification
  remain separate. Workload prose uses c01/c16 and w1/w20/w100; captured
  identifiers remain unchanged.
- Unchanged upstream `mmap1`: 42 points per arm, comprising 21 thread counts and
  21 process counts. Baseline uses scope1-KD; candidate uses scope2-KD. Both use
  the same f4ae harness and original application binaries. Each arm needs its
  own actual boot, identity, functional prerequisites and endpoint evidence.
- The fresh cohort uses `kdlock-builddisk-clean-20261031`; earlier initial
  snapshot tags are retained as recorded and do not qualify future timings.
  Threads and processes are reported independently. No repetitions or
  significance threshold are inferred from this single-round design.

Source-identical ordinary/prepared rwsem paths do not prove identical compiled
layout or performance. The measured ELF identities and final archived point
records were retained and validated; source identity alone is insufficient. Broader replacement, generic CALL branch-only JIT
reentry, queued mutex role exchange and unsupported configurations remain outside
this change. No correctness check here resolves the earlier performance losses.

Final restoration is recorded separately: the [source view was unbound](restoration/candidate-source-unbind/result.json),
the [durable reboot request](restoration/final-normal-request-observed/result.json)
was recovered after the reboot command returned 0 but its
[subsequent result fetch did not complete](restoration/final-normal-request/owner.json).
The [normal postboot verification](restoration/final-normal-postboot/result.json)
confirmed `7.0.0-38-kdlock1` on new boot `fa97b9f8-fefc-49b9-abc1-636861e64fc0`.
The [pool restoration](restoration/final-pool-restore/result.json) restored
min/max 0/64 and `aio-max-batch=0`, with known policy state. It explicitly did
not restore original QOM absence or the original task map; no claim is made
that all dynamically created workers retired. These actions are not benchmark results.

[status.json](status.json) records both completed comparisons and failed acceptance gates.
[evidence-manifest.json](evidence-manifest.json) records each retained file's
original local path, size and SHA-256. Result/transport JSON and logs are copied
without rewriting. The [initial checkpoint](inputs/progress-at-scaffold.json)
is unchanged; the [baseline-complete capture](inputs/progress-f7-complete-candidate-running-20261031.json),
[nano-complete capture](inputs/progress-nano-complete-mm-pending-20261031.json)
[MM boot-preparation capture](inputs/progress-scope2-native-scope1-kd-boot-20261031.json)
[baseline MM completion capture](inputs/progress-baseline-mm-complete-candidate-pending-20261031.json)
[candidate mapping-failure capture](inputs/progress-candidate-mm-mapping-failed-20261031.json)
[prospective grid-start capture](inputs/progress-prospective-mm-grid-running-20261031.json)
and [final comparison/restoration capture](inputs/progress-final-comparisons-restored-20261031.json)
remain separate historical checkpoints, not live status services.
Selected final analyzer artifacts were copied without rewriting. All original
outputs, including full per-point and observed-loss JSON, remain in tmpfs and
are hash-indexed in [retained-artifacts.json](nano-comparison/retained-artifacts.json).
The complete CSV preserves every negative without duplicating those larger JSON
records. No placeholder measurements are generated. Large source/build/module
inventories and raw timing archives are not duplicated here. All preparation of this report was source-host
inspection and copying; builds and checks were executed by the recorded VM runs.
