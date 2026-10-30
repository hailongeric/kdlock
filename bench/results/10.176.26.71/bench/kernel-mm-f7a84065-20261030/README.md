# Scoped MM comparison: f7a84065

**The final 126-point, 63-pair comparison is archive-validated; the candidate
fails the MM performance criterion and remains unaccepted.** Every point has
one measurement round. All four completed boot archives passed source, artifact,
ownership/retirement and original score-log validation.

| Workload | Native/KD pairs | KD gains / losses | Change at 20 workers | Change at 60 workers |
| --- | ---: | ---: | ---: | ---: |
| Localized shared-mm mapping | 21 | 0 / 21 | −85.241% | −95.843% |
| Unchanged `mmap1_threads` | 21 | 0 / 21 | −81.803% | −94.344% |
| Unchanged `mmap1_processes` | 21 | 11 / 10 | +0.730% | +28.427% |

There are no ties. The models remain separate: independent-process results do
not offset the shared-mm thread losses. The [full localized CSV](analysis/whole_ops_s.csv)
and [full mmap1 CSV](analysis/pairs_per_nominal_second.csv) retain every count.
The [final validation](analysis/validation.json) records 126 points, 63 pairs and
`performance_accepted=false`; [summary](analysis/summary.json) includes each
group and its exact prerequisites. One round provides no variability estimate.

The [nano comparison](../continuation-perf-nano-20261030/README.md) and
[actual syscall comparison](../kernel-api-f7a84065-20261030/README.md) retain their
separate losses and validation limits. The user authorized this isolated MM
comparison despite those losses. Continuing the measurements is not performance
acceptance, and none of the three campaigns is pooled with another.

## Source, kernel and execution scope

| Identity | Exact value |
| --- | --- |
| Project/test generation | `f7a84065e84474380faa37eeadfdf534abd72a68` |
| Kernel integration/build recipe | `8446f4ecb08816380a4c233197a8ce5e4d333aac` |
| Ubuntu source | `linux=7.0.0-38.38` |
| Kernel release | `7.0.0-38-kdscope1` |
| Kernel Build ID | `a17d565ee157601e030d1b3c77c13e63fa62c994` |
| Configuration SHA256 | `7131e48d4bb556e54f9fc287c04e6fab33a3de80eb923a215872a01a07609f4b` |
| Linked `vmlinux` SHA256 | `ea8b44b8f9cc9256c93228adfcb30f5535a1c841a67496b96946f24080240a42` |
| Original will-it-scale revision | `75f66e45697e6f5f49c33dd950c4e6b289198f8f` |

The same compiled kernel image supplies both modes: `kd_mmap=off` selects
Native and `kd_mmap=on` selects KD for dynamic mms. The later f7 project generation
does not relabel the already-built 8446 kernel's MM code as a newer build.
Kernel source/build maps, mode-specific bundles and actual boot IDs remain
separate evidence identities.

The [MM adapter](../../../../../kernel_integration/linux70/MMAP.md) changes the
lock backend and required API/ownership/lifetime routing. Native mapping and
fault bodies execute unchanged on their original tasks. Reads remain local;
this MM backend also runs writers locally, including killable acquisition and
downgrade. There is no MM-body delegation or prepared MM teardown. This result
therefore does not measure the typed instruction service or JIT execution of
MM bodies, and does not establish arbitrary replacement of page-table, per-VMA
or folio locking.

## Localized result

The localized client uses ordinary `mmap`/`munmap` syscalls against the retained
mapping payload. Workers share one mm and map then unmap an untouched 4 KiB
range with `PROT_READ` and `MAP_SHARED`. One operation below means that complete
mapping/unmapping pair; it is not a CPU cycle. The nominal duration is two
seconds, but the score denominator is the actual joined worker wall interval:
`completed * 1e9 / wall_ns`. Optional peak-window values are not the score.

Both grids reuse Native-A's identical client and payload, with input-manifest
SHA256 `add83fe67e4f20a95ddb36b97bdbe22576ff32c93216262f35f8e6e1fdd5690f`.
Worker counts are 1–8 and 12–60 in steps of four; workers use CPUs 0 through
N−1 and the collector uses CPU 63. The 64-vCPU topology places CPUs 0–31 on
node 0 and CPUs 32–63 on node 1.

| Workers | Native Mops/s | KD Mops/s | KD / Native | Change |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.371494 | 0.363390 | 0.978185× | −2.182% |
| 2 | 0.339972 | 0.269291 | 0.792097× | −20.790% |
| 3 | 0.322980 | 0.196594 | 0.608687× | −39.131% |
| 4 | 0.329726 | 0.133527 | 0.404964× | −59.504% |
| 5 | 0.326238 | 0.109948 | 0.337018× | −66.298% |
| 6 | 0.319013 | 0.095550 | 0.299519× | −70.048% |
| 7 | 0.315270 | 0.075305 | 0.238858× | −76.114% |
| 8 | 0.323544 | 0.061396 | 0.189762× | −81.024% |
| 12 | 0.318700 | 0.052315 | 0.164152× | −83.585% |
| 16 | 0.290209 | 0.044296 | 0.152636× | −84.736% |
| 20 | 0.269161 | 0.039725 | 0.147588× | −85.241% |
| 24 | 0.281677 | 0.035710 | 0.126776× | −87.322% |
| 28 | 0.290651 | 0.030789 | 0.105930× | −89.407% |
| 32 | 0.270475 | 0.026034 | 0.096253× | −90.375% |
| 36 | 0.206630 | 0.014700 | 0.071144× | −92.886% |
| 40 | 0.186097 | 0.011558 | 0.062109× | −93.789% |
| 44 | 0.174330 | 0.009532 | 0.054680× | −94.532% |
| 48 | 0.173671 | 0.008493 | 0.048902× | −95.110% |
| 52 | 0.171085 | 0.007652 | 0.044729× | −95.527% |
| 56 | 0.165341 | 0.007075 | 0.042793× | −95.721% |
| 60 | 0.160348 | 0.006666 | 0.041572× | −95.843% |

The archive review checks all 21 coordinates, original raw client records,
completed/drained owners, matching source/image/artifact maps, environment,
topology and endpoint receipt bindings. Both localized grids retain `exploratory=true` and
`strict_host_gate=FAILED`; unchanged 131-task host snapshots do not promote them
to strict qualification. One round supplies no variability estimate. These
receipts alone cannot assign the loss to scheduling, parking, cache traffic or
physical placement.

| Localized evidence | KD | Native-B |
| --- | --- | --- |
| Boot ID | `02c1396f-28f3-44a9-8d01-97374a0f221d` | `588ce982-d213-458b-a354-f065054ef6f1` |
| Runner result SHA256 | `44af8ca458574f52de48220fc21ca76abfc35441e6492b0a593e1be3ec3394bc` | `d08b2b953a3916d2762797dda44f6c46738b58b9c8c59a96e7f4254b5f5261df` |
| Controller owner SHA256 | `c7eb4084fd93f3cd06682bb21ceaa4e2e2e0dba6c0a07d9f7830a0cb63714793` | `8a05d0c8fba52bdc0ff92d336962bd5bc622f717cc47c4c5de432c30d459567c` |
| Immediate endpoint SHA256 | `f3aa4082cf569f80a336f3cb64981a6bd11e40e2b67a7acb431544e5da122087` | `118b695d38efcfc3c8b76003428f98cca1d8c0df3997cbc58a85fa0739f7d1c7` |

The preliminary output remains at
`/tmp/kdlock-scope-f7-localized-preliminary-review-result-20261030/`.
Its `review.json` SHA256 is
`d9dad42c981499e65def3ed99eeeb15826b262bcce4a0d66235934b2e87451dd`;
`pairs.csv` SHA256 is
`8218590b958566ac84f9b331f00a2c91e2f9641f95b428f2321376c486cfd709`.
That earlier review explicitly records `raw_client_validation=false`,
`endpoint_capture_replay=false`, `final_archive_validation=false` and
`performance_accepted=false`; those original flags remain unchanged.

The later archive validation is retained separately at
`/tmp/kdlock-scope-f7-mm-localized-offline-result-20261030/`. Its `validation.json`
SHA256 is `238d8864e697993e142db7939aaa21fcf0d8cd008959e9cf60c32bb7ef11886f`,
with `completed=true`, `validated=true`, 42 points, 21 pairs and
`performance_accepted=false`. The full `whole_ops_s.csv` SHA256 is
`c9eef7a4d8dbd3f0e1172e50bc4f05c3796ad95d8fba2ebfb7ccd9bfdc4f9176`.
All 21 scores, ratios and percentage changes exactly match the preliminary
CSV: zero gains, 21 losses, zero ties. This validates the archived data without
promoting exploratory host qualification or accepting the candidate. The final
63-pair analysis validated both workloads and exactly reproduced these values.

## Correctness prerequisites and retained failures

All four archives retain successful actual-MM prerequisites:

| Boot | API checks / errors | Mapping cases | Fault records / joined children / joined threads | `VM_FAULT_COMPLETED` entries / returns |
| --- | ---: | ---: | ---: | ---: |
| Native-A | 137 / 0 | 6 | 18 / 16 / 16 | 64 / 64 |
| KD | 161 / 0 | 6 | 18 / 16 / 16 | 64 / 64 |
| Native-B | 137 / 0 | 6 | 18 / 16 / 16 | 64 / 64 |
| KD-B | 161 / 0 | 6 | 18 / 16 / 16 | 64 / 64 |

All completed-fault observations have zero errors and missed events; each
boot's own owners and results are retained under [receipts](receipts/).
The API checks include cancellation, nested exact ownership, downgrade,
deferred read ownership transfer, IRQ-state preservation and destruction.
These bounded checks do not establish every kernel caller or BPF/NMI path.
Preparation's one- and sixteen-worker observations are unscored and distinct
from the subsequent single-round grids.

Two KD failures remain failures in the retained evidence:

- The first API reuse attempt stopped before starting the probe because the
  original snapshot contained 319 files while the tracked selection contained
  298. The extra 21 were historical, unused unit-source files retained by sync.
  External controller r5 binds that exact disjoint extra set and checks the
  original tracked bytes; it does not relax source matching or change f7.
  The failed transport owner is preserved under
  `kd/preservation-inputs/external-control/api-reuse-failure/`, SHA256
  `13a8994cb552ea3523fa98a4ab660ea4e32a5f81d43b7d1048dc21652862f5cd`.
- The first KD mapping attempt completed 80,000 operations and joined all 16
  workers with zero worker errors and zero remaining VMAs, but did not observe
  the required stable sleeping-writer/scheduler bracket. Its runner remains
  failed/undrained, SHA256
  `04c6f32cb5ba1fdc956f03d05a62b66093b01003571a9299be5100c09021b05e`.
  Normal unload and a separate idle check preceded exact preservation under
  `kd/failed-attempts/mapping-writer-observation-r5/`; the preservation receipt
  SHA256 is `c464d7f2e3076947beec27facf57ed3b3b1da667d4359a79be2ff11063b96e97`.
  One focused correctness follow-up passed the unchanged predicate. No timed
  MM grid had started before either failure, and neither failure was relabeled.

Native-A also retains the earlier controller-log self-open refusal and the
missing `hwloc.h` preparation failure. The log destination correction and
installation of eight required dependency packages preceded separate successful
attempts; no scored measurement was repeated to repair them.

Native-B's first `mmap1` identity attempt failed before observer loading or
application execution: its snapshot included stale generated
`kd_mmap1_identity.mod.c`, which Kbuild rewrote. The runner's existing input
check rejected the changed bytes. The failed runner SHA256 is
`30af5a3cd8c4a5222cb51c058b16bdd2ae4b32647e2eba4ba8f9ea6fc76ee1dc`;
its failed controller SHA256 is
`4470de8764bb2c5252c44dbac32f70ff278812c7326296edeaad66383f511170`.
Both retain their failed/undrained flags. A separate preservation step confirmed
the former runner was absent and both maintained idle checks passed, then moved
the exact tree and closed logs to
`native-b/failed-attempts/mmap1-identity-generated-input/`. No unload was needed.
The source-host preservation receipt SHA256 is
`63a9dafd47242a37ab0a47c158f1babfb9eef6148e04f0cb83af64372874aaa2`;
it records `FAILED_ATTEMPT_PRESERVED_IDLE` and unchanged failed flags. No scored
`mmap1` point had started. The separately bound diagnostic-runner snapshot fix
then passed its fresh Native-B identity attempt: result SHA256
`0a2bbbef2955021c43b25950382421ac9e66a80f4e35e1a90f17b52bdd0ad5bb`,
with completed controller SHA256
`1d632418c2bff7486e77d4b44bce56409d26b04ae0a535589751c75007437cc0`.
It observed one shared mm for two threads and two distinct mms for two
processes, with `use_kd=0`. This is an unscored diagnostic-lifetime observation;
frozen f7 and the prepared application binaries are unchanged. KD-B's separate
diagnostic passed the same two models with `use_kd=1`, one shared mm for the
threads and two distinct mms for the processes. Its [retained result](receipts/kd-b/mmap1-identity/result.json)
is separate from every scored process. The diagnostic snapshot fix is commit
`d22a36567de28c024ebb8d1c79997c0d39541bd2`, not a new measured f7 or kernel generation.

## Unchanged mmap1

The original will-it-scale source and Native-A prepared binaries are reused for
both modes. Native-B and KD-B have each completed all 42 points: threads and processes
separately, each at the same 21 worker counts and one round. All sessions report
passed/drained completion, round zero, two nominal seconds and no observer
instrumentation. The unchanged application uses its normal syscalls. The
separate unscored object identity observation is not attached to the scored
application process.

The fetched Native-B runner result SHA256 is
`62f8770f554182e1145f8c6c845c38b3ed6b66d68b2e4303481459a0f74fc68d`,
bound by completed owner
`12682d4ffd528132940df00350c49f75457c774854f55a2587296e76a3118570`.
Its immediate endpoint SHA256 is
`2a7d0cc0d08ae2285558320a9969214a252525a0497ffb9751769872321e1be7`.
That endpoint reports strict PASS, unchanged 131-task identity and a 6.228-second
delay from transport completion. This is separate from the earlier exploratory
localized endpoint; its qualification is not transferred between workloads.

KD-B's fetched result SHA256 is
`2a4e26dd14acd45ef3660736a8a69038ee16d438104582f22dffa374f4f5c3f1`,
bound by completed owner
`329389d9053f2e6121d3f287cfc609785af0876c4a315f6bb1f5dcd7f6ed0632`.
Its boot is `8c5259e3-0f93-493d-afa9-bd93d5358683`; the immediate endpoint
SHA256 is `47376836dd5cf90b2f7a602e6c4c9f75b700efb1570d6590af6b418228f70742`.
That endpoint also reports strict PASS and unchanged 131-task identity, with a
7.892-second capture delay. Both complete archives and every raw `upstream.log`
passed the final offline review. The strict endpoint receipts remain separate
from each runner's original generic `host_endpoint=PENDING` field.

The tables below use each raw log's two post-marker sample totals
divided by two nominal seconds. The integer printed upstream average is checked
against the floor of that value. Six warmup samples and whole-process elapsed
time are not score denominators. `Mpairs/s` means millions of complete
mmap/munmap pairs per nominal second. All 42 pairs are retained, with no pooling
between threads and processes and no variability estimate from this single round.

Receipt-derived comparison files remain at
`/tmp/kdlock-scope-f7-mmap1-receipt-comparison-20261030/`.
Its `summary.json` SHA256 is
`d7bae352b08ccf5397a48c0d52697a53c20542864000c38a02003dbd5956619e`;
the full `pairs.csv` SHA256 is
`fffd94e1f3bc18ef8a21d04eeb762d90379624b588c5e2ae503e29c1bab91cb9`.
That earlier record explicitly retains `preliminary=true`,
`raw_upstream_validation=false`, `final_archive_validation=false` and
`performance_accepted=false`. The final archive-backed CSV exactly reproduces
all 42 preliminary scores, ratios and percentage changes; its SHA256 is
`f526e89a51073f4b813e1cfd03947c819d5687ca94a08beed6edb94aabeca54a`.

### Threads

| Workers | Native Mpairs/s | KD Mpairs/s | KD / Native | Change |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.306616 | 0.287353 | 0.937175× | −6.282% |
| 2 | 0.255356 | 0.190786 | 0.747137× | −25.286% |
| 3 | 0.243674 | 0.164956 | 0.676950× | −32.305% |
| 4 | 0.253042 | 0.115780 | 0.457554× | −54.245% |
| 5 | 0.250078 | 0.094720 | 0.378763× | −62.124% |
| 6 | 0.243098 | 0.073290 | 0.301485× | −69.852% |
| 7 | 0.233187 | 0.064717 | 0.277533× | −72.247% |
| 8 | 0.231378 | 0.057278 | 0.247552× | −75.245% |
| 12 | 0.227669 | 0.047852 | 0.210182× | −78.982% |
| 16 | 0.223570 | 0.041665 | 0.186362× | −81.364% |
| 20 | 0.206543 | 0.037585 | 0.181972× | −81.803% |
| 24 | 0.209496 | 0.033526 | 0.160032× | −83.997% |
| 28 | 0.212216 | 0.030163 | 0.142136× | −85.786% |
| 32 | 0.198244 | 0.024973 | 0.125974× | −87.403% |
| 36 | 0.157827 | 0.014292 | 0.090552× | −90.945% |
| 40 | 0.142333 | 0.011296 | 0.079363× | −92.064% |
| 44 | 0.131064 | 0.009375 | 0.071530× | −92.847% |
| 48 | 0.125775 | 0.008625 | 0.068571× | −93.143% |
| 52 | 0.121442 | 0.007675 | 0.063199× | −93.680% |
| 56 | 0.119987 | 0.007187 | 0.059894× | −94.011% |
| 60 | 0.116210 | 0.006573 | 0.056561× | −94.344% |

### Processes

| Workers | Native Mpairs/s | KD Mpairs/s | KD / Native | Change |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.356305 | 0.350102 | 0.982591× | −1.741% |
| 2 | 0.662971 | 0.651028 | 0.981986× | −1.801% |
| 3 | 0.995205 | 0.957094 | 0.961705× | −3.829% |
| 4 | 1.304209 | 1.310581 | 1.004886× | +0.489% |
| 5 | 1.651227 | 1.571067 | 0.951454× | −4.855% |
| 6 | 1.881434 | 1.821724 | 0.968264× | −3.174% |
| 7 | 2.067363 | 2.055277 | 0.994154× | −0.585% |
| 8 | 1.845768 | 1.902897 | 1.030951× | +3.095% |
| 12 | 1.896197 | 1.903756 | 1.003987× | +0.399% |
| 16 | 1.889639 | 1.911161 | 1.011390× | +1.139% |
| 20 | 1.851543 | 1.865064 | 1.007303× | +0.730% |
| 24 | 1.855867 | 1.857951 | 1.001123× | +0.112% |
| 28 | 1.806332 | 1.825231 | 1.010463× | +1.046% |
| 32 | 1.793794 | 1.790994 | 0.998439× | −0.156% |
| 36 | 1.577797 | 1.572677 | 0.996755× | −0.324% |
| 40 | 1.455278 | 1.462491 | 1.004956× | +0.496% |
| 44 | 1.388634 | 1.388455 | 0.999871× | −0.013% |
| 48 | 1.337276 | 1.336933 | 0.999744× | −0.026% |
| 52 | 1.304305 | 1.304930 | 1.000479× | +0.048% |
| 56 | 1.279745 | 1.280808 | 1.000830× | +0.083% |
| 60 | 1.262692 | 1.621636 | 1.284268× | +28.427% |

## Interpretation and remaining work

The shared-mm results identify a substantial scalability problem: both the
localized writer workload and mmap1 threads lose progressively as worker count
rises. The independent-process control has much smaller mixed changes at most
counts, although its 60-worker gain is retained. This supports prioritizing
shared-mm admission and serialization. It is an inference from the contrasting
models, not proof of a parking, wakeup or cache-coherence cause. Untouched mmap1
does not deliberately fault in its payload pages, so the separate fault
correctness controls are not a measurement of its dominant cost.

A concrete source difference is the killable writer path used by mmap/munmap.
In [kd_rwsem.c:237–253](../../../../../kernel_module/kd_rwsem.c#L237),
`kd_down_write_killable` uses `wait_event_killable` to reserve the writer phase
before acquiring the embedded local mutex gate. It bypasses the ordinary
writer's 16,384-probe `kd_rwsem_poll` at
[kd_rwsem.c:18–36](../../../../../kernel_module/kd_rwsem.c#L18).
The gate has its own owner-aware/OSQ spinning, but a writer must first win
phase admission; gate spinning does not substitute for spinning at that earlier
point. The captured Linux 7 Native
[rwsem.c:1111–1119](tools/linux70-rwsem.c#L1111) attempts owner-aware optimistic
spinning before its blocking slow path, and
[lines 1169–1185](tools/linux70-rwsem.c#L1169) can spin after handoff.
These paths make killable admission a bounded optimization hypothesis.

The scored receipts do not count admission sleeps, failed wakeups, reader-drain
timeouts or physical cacheline placement. Neither a wait-event call nor the
one-jiffy reader-drain timeout means that every acquisition sleeps; ready
conditions can complete immediately. Mmap1 CPU and elapsed fields cover warmup
and shutdown as well as measurement, so they cannot supply a scored-window
parking fraction. See the retained [source-only interpretation](review/source-interpretation.md)
for the exact original-task call paths and additional limits. No optimization
gain is claimed, and no unbuilt candidate is substituted for this measured
8446 kernel/f7 project cohort.

The final acceptance criterion remains unchanged `mmap1` performance, together
with the unresolved nano no-regression requirement. The current archive-validated
localized losses and thread losses provide no basis for accepting
or promoting this candidate. The general CALL fallback still continues through
the native suffix; supported typed RDTSC/RDTSCP/CPUID services have a separate
same-invocation reentry contract. These measurements do not complete generic
branch-only CALL reentry, queued combiner/waiter role exchange, or the requested
replacement of queue-wide waiter pinning with bounded immediate selection.

## Evidence and reproduction

[Copy provenance](copy-manifest.json) binds every copied receipt, source map and
tool to its exact original bytes. The four [transfer records](provenance/)
retain distinct boot/archive identities; raw compressed archives and their
verified receipt caches remain under
`/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/tests/kdscope1-mm-f7a84065-20261030/`.
No ELF or full archive is copied into this report. The [source state](provenance/source-state.json),
[tracked source hashes](provenance/source-sha256.json),
[generation split](provenance/generation-record.json) and original preparation
inputs keep runtime, kernel recipe and diagnostic identities separate.

The final [analysis invocation](receipts/analysis-invocation.json) completed on
its first attempt with return code zero. Final `validation.json` SHA256 is
`a3237b709d915c9725cb7fa55f4dfdc6d39ef97cadc4b067a13fd1ef80463286`.
The [independent arithmetic review](review/independent-arithmetic.json) checks
all 63 ratios and reconstructs 18 original raw logs at 20, 32 and 60 workers.
Earlier preliminary receipts are preserved under [preliminary](preliminary/)
with their original flags; neither their bytes nor failed attempts are rewritten.

From this report directory, reproduce the offline analysis against the retained
archives and existing verified caches with a fresh output directory:

```sh
python3 tools/analyze.py --inputs analysis/inputs.json \
  --inputs-sha256 fa4327979593a39dfdb230b393cfdf4c94b225e6b9bd47f7fc3525fc36e851d0 \
  --scope all --source tools/frozen-source --output /tmp/kdlock-mm-review-new
```

This evaluates only the hash-bound pure score validators. It runs no guest
work, build, module, workload or test. Compiler/library and compiled kernel
files outside these archives retain their explicit runner-verified status;
source/binary hashes do not add unobserved runtime coverage.

After all grids, archives and transfers completed, the
[pool restoration receipt](receipts/pool-restoration/result.json) records
`thread-pool-min=0`, `thread-pool-max=64`, and `aio-max-batch=0`, confirmed by
readback. Its SHA256 is
`e5ae6ed6f607f2d0eaba308e2d49fc823827632ce646e1f7f1ab5dd47f50d6c6`.
The original task map and QOM-object absence were not restored: the object
remains and workers retire naturally. The [before](receipts/pool-restoration/before.host.json)
and [restored](receipts/pool-restoration/restored.host.json) captures retain that
distinction. This later policy restoration neither proves guest drain by itself
nor retroactively qualifies an earlier benchmark cohort.
