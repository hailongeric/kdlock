# Stable mmap1 point after longer preparation at 7e3c90b4

One eight-process point passed with **25,670.9 mmap/munmap pairs per nominal
second**: 256,709 completed pairs in the final ten nominal-second samples.
Selected-service counters and sample callbacks were enabled. Compilation was
excluded from the entire fixed application, including its six warmup samples.
Both roots returned every JIT entry across that application's complete lifetime.
Exact retirement, ordinary unload and verified normal-kernel recovery passed.

This is one stable instrumented point, with no quiet-performance or strict-peak
qualification, Native comparison, measured gain, repeat estimate or broader
workload coverage. The runner's performance acceptance and scored fields remain
false. Full returned-body counters do not identify a particular consumed
proxy-downgrade branch, physical chain length or per-worker delegation identity.

## Scope and source identity

The unchanged upstream `mmap1_processes` executable invoked the actual mmap and
munmap system calls. Eight independent processes were pinned to CPUs 0–7,
collector CPU 63; service CPUs were 0–61. Upstream revision was
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`, input receipt SHA256
`beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0`.
Service tracing remained `N`; no targeted handback PC/reason/lock-state capture,
required-publication probe or identity-probe load was added.

Tested candidate: `7e3c90b469c1f824ba0e82773880c605f3fbcfe2`, branch
`codex/release-unit-boundaries`. Its runtime source equals the earlier checked
build at `3ceb7f002672e8e9a4b2a14de6660944338088e5`; that actual build identity
is retained for the reused binaries. The complete 1,099-file map matched SHA256
`844c67826d86501572611449f4cd06452975fb1f2a5a67c54ad47e60be11ce93`.
Current source, provider production, observation/prepared and daemon maps,
build receipt, upstream dependencies and fixed-session binary hashes all joined.
No runtime source, runner cap or kernel MM body changed for this campaign.
The earlier two basic and ten directly affected guest checks, daemon build and
enabled-MM provider build were reused; no tests or builds were repeated.
See the [focused-check record](../../tests/rwsem-proxy-read-20261109/README.md).

Master separately contains flags-stack lowering `39e916c8` and its REX.W fix
`111ac671`, absent from this candidate. Integrating the candidate preserves
those changes. This measurement validates the exact candidate above, not the
merged runtime combination; static integration checks are separate evidence.
The [integration receipt](../../tests/proxy-read-main-integration-20261109/README.md)
records exact source differences and preservation checks.

## Preparation, compilation, settlement and measurement

One supported 3,600-second shared learning/prewarm allowance covered a
730-sample initial application (800-second body cap), at most 16 short
continuations (30-second caps) and settlement. Six continuations ran; the sixth
was stable. Close allowed 600 seconds, controller 4,500, finalizer 90 and outer
wait 4,800. No deadline was renewed and no replacement campaign was launched.
All eight applications, including the fixed point, returned zero and drained.

| Interval | Seconds | Meaning |
| --- | ---: | --- |
| Campaign origin to fixed application | 2,358.837496171 | All preparation; excluded from throughput |
| Setup before first preparation body | 5.775654088 | Derived from shared deadline minus its 3,600-second allowance |
| Initial plus six continuation bodies | 778.432045337 | Body lifetimes; overlap compiler work |
| Between-body settlement/verification/startup gaps | 1,574.629796746 | Includes 1,540.142086373 seconds inside compiler intervals |
| All 19 compiler-child wall times | 2,308.547259746 | Overlap preparation; do not add to the preceding durations |
| Last compiler finish to fixed application | 16.768834281 | No compiler work in this gap or the fixed application |
| Entire fixed application | 16.060508973 | Six warmup plus ten measured samples and process completion |
| Delivered measured sample lines | 10.001279546 | Line-receipt interval; not the rate denominator |
| Throughput denominator | 10 nominal seconds | Final ten completed-pair samples only |

Setup + preparation bodies + between-body gaps equals total preparation.
The gaps include compiler settlement, export/copy, receipt verification and
application startup; 34.487710373 seconds lie outside compiler intervals.
Neither the gaps nor that residual is an isolated settlement-cost measurement.
[phase-timing.json](phase-timing.json) retains the exact monotonic intervals.

The last compiler finished at 2,430,308,687,434 monotonic ns. The fixed application
ran from 2,447,077,521,715 to 2,463,138,030,688 ns; the measured sample-line window
was 2,453,110,374,583 to 2,463,111,654,129 ns. Every compiler interval is disjoint
from the complete fixed application. All 19 compiler records succeeded and are
identical in the daemon log and before/after receipts. Exact image registry and
superseded history stayed unchanged before, at both sample boundaries and after
the application. Final images were mmap **g7** and munmap **g12**, both status 0.
[measurement-audit.json](measurement-audit.json) records the exclusion verdict.
The unchanged runner's fixed receipt rejects active children or changed image
history, and the independent timestamp audit additionally checks every interval.

## Returned bodies and measurement boundaries

Whole fixed application, including all six warmup and ten measured samples:

| Root | JIT entries | Returned bodies | Completed handbacks |
| --- | ---: | ---: | ---: |
| `vm_mmap_pgoff+0x118` | 398,610 | 398,610 | 0 |
| `__vm_munmap+0xbb` | 398,608 | 398,608 | 0 |

Both roots have zero local/no-image/cancellation deltas and passed the drained
whole-application conservation check. These counts cover more than the ten
samples used for throughput and are not the benchmark's 256,709 measured pairs.

The narrower, asynchronously sampled callback window preserves mmap
256,701 entries / 256,703 returns and munmap 256,701 / 256,704, with zero
completed handbacks. Selected/submitted deltas are 256,698 and 256,701.
Snapshot callbacks and benchmark samples do not form one atomic boundary;
these small differences are retained and do not assert measured-window equality.
The exact whole-application conservation result remains separate.

## Finalization and machine state

The original campaign receipt remains `MEASURED_RETIREMENT_PENDING`, with one
stable point and its initial generic passed/drained/accepted fields false.
Separate standard finalization and outer receipts pass campaign completion,
retirement, drain, ordinary `rmmod`, final idle and unchanged frozen inputs.
Finalization binds original receipt SHA256
`5adc7090edbcfda0ad6c759c137ad92f7c7d7c65ba2006cbaf37190ab314b9c4`;
the original bytes were not rewritten. Binding references fell 19→0; final
source state was 2 with modules/frames/writers all zero.

The generic application receipt says `scored=true` because tracing was off and
learning was false. The enclosing point/campaign/outer receipts explicitly say
`scored=false` with selected-service counters enabled; those qualified verdicts
govern this report. Quiet/performance acceptance remains false.

All stored application kernel logs have no match for the runner's fault pattern
and no log collection error. Trace-disabled output provides no continuous
collector completeness/overflow summary. This does not extend validation beyond
the captured logs and exact receipts.

The run used enabled kernel `7.0.0-38-kdscope5`, Build ID
`357a7115d21941960b90262ac1165bf70d1b398e`, boot
`cd136631-4cf1-4c43-9e87-a222810fb901`, with `kd_mmap=on` and full (lazy)
preemption. Host recovery snapshot, topology/pinning/frequency, idle and >2 GiB
headroom gates passed. Normal recovery then verified schema 2/runtime policy,
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`,
boot `3d32656f-6162-4a0a-9304-bf383d34298d`, unloaded and idle. The normal GRUB
default was preserved. No forced unload, source cleanup or rollback was used.
Guest frozen inputs and output receipts remain retained.

## Retained evidence and integrity

[validation.json](validation.json) records lifecycle/source/receipt joins;
[raw-index.json](raw-index.json) binds all retained host files by size and SHA256.
Independent reviews are retained in [lifecycle-review.md](lifecycle-review.md)
and [measurement-review.md](measurement-review.md). All 422 archived members,
including link metadata without following links, match the archive manifest.
Large archives remain outside Git under the ignored raw-evidence convention.

Raw host root:
`bench/results/10.176.26.71/raw/bench/rwsem-proxy-read-7e3c90b4-v3`.
Guest output:
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/kdlock-proxy-normal-7e3c90b469c1-v3/processes/kd`.
The raw root retains the complete archive, source/preparation and boot receipts,
commands, reviewed controllers, progress records, unchanged original result,
finalization, recovery and offline audits.

| Artifact | SHA256 | Bytes where applicable |
| --- | --- | ---: |
| Live archive `collection/evidence.tar` | `3f58be968edf403e45bfbc793a4b3f1a87915b9d2a074c22b0f2a6e3785c53e6` | 897,218,560 |
| Provider | `663cec836c9661cb744cd62cd64983d3f213e56cd3e6e7e4eac05902d6671c92` | |
| Daemon | `0a0db51b9c35dc894027d0e347a1be5abb68e7467c7c941717f7bcb39c73c9d2` | |
| Provider note | `5079462f965691f10d3b47f235000f70be6f5b9dbdb44e00b385d95ca2faa27a` | |
| Prepared provider manifest | `24340a78864ffd453809b9b306459ab5fab6b581e9ad9a84254a1c8ed02b03b8` | |
| Current preflight | `9fd22c5173efe0862ae56a41a5285fe8c19f8535ddf55ef4c7cd175317ed832b` | |
| Fixed-session receipt | `fe3886059105f54256e3222cdf9ad5120309587ae17ade369a3d5fe92a21c71f` | |
| Normal recovery capture | `7c2fc85476e2578915a3003c81d5f16ffc53e388a8fa2c905ecf5bc2a0e2a177` | |

The prior failed campaigns remain unchanged:

- `raw/bench/rwsem-proxy-read-3ceb7f00-v1`: short 180-second learning-boundary
  failure, archive `aa58fe4e05a3697dcc07525c8582c9d7029aedff7befb2b949b789517161d997`
  (102,144,000 bytes); [original record](../../tests/rwsem-proxy-read-20261109/README.md).
- `raw/bench/rwsem-proxy-read-7e3c90b4-v2`: 1,800-second allowance expired after
  continuation four, no fixed point; archive
  `ba318c0abc3e453c14f9bfd90e58845deb650e388b28dcce316bceccf4be1435`
  (613,908,480 bytes). Its original `LIVE_STATE_RETAINED` verdict, separate
  successful retirement/recovery and unscored learning data remain intact.

The present success neither rewrites those failures nor pools their rates with
this point. No new workload was run during reporting or integration.
