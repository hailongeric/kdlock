# One post-settlement mmap1 process point

The single fixed-receipt point failed its learning-stability check. Its
provisional rate was **21,087.5 pairs/s**. Both applications drained; exact
retirement and normal-kernel recovery subsequently passed. Performance remains
unaccepted, and no application was repeated.

Runner commit: `276f26470e5094c9a81f4f2d977dc517dd4eb4b5`.
Runtime/provider/daemon remain `ec623366622d1784f7e819b4e9031ba0482bee9b`;
kernel component remains `9a5d606aee0249d0e566a1c9667375eb038bc9cd`, Build ID
`357a7115d21941960b90262ac1165bf70d1b398e`. No backend, context routing,
source body or lock protocol changed. Separate child images for selected KD
acquisitions remain pending; allocator and other Native locks retain their
existing instruction-service handling.

One fresh factory ran the unchanged will-it-scale process application at eight
workers. No old raw code, context address or execution receipt was reused.
The long preparation used 730 samples, including 720 before measurement, and
the existing 1,800-second learning/settlement bound. It passed and settled with
mmap g5 and munmap g7 NORMAL. With no compiler children and zero execution
frames, the controller created a fresh fixed receipt in that same live factory.
It then ran exactly one short application: six warmup samples and ten measured
samples, with a 30-second application bound. Online publication remained enabled.

| Application | Pre-window elapsed | Measured elapsed | Whole application |
| --- | ---: | ---: | ---: |
| Long preparation | 720.126345 s | 10.001644 s | 730.138728 s |
| Fixed-receipt point | 6.033990 s | 10.001325 s | 16.059085 s |

These are delivered sample boundaries, including transport/callback latency.
The rate uses 210,875 pairs and the nominal ten-second divisor. Application exit
was zero and its lifetime drained, but postrun execution-session verification
raised `LEARNING_ADVANCED`; its durable receipt remains `FAILED`, `passed=False`,
`drained=True`. The original campaign remains `LIVE_STATE_RETAINED` with both
its measurement error and its separate close error intact. Later cleanup does
not change those outcomes.

| Boundary | mmap | munmap | Superseded reports |
| --- | --- | --- | ---: |
| Before application | g5 NORMAL | g7 NORMAL | 0 |
| Measurement begin | g5 CALL | g7 IJ | 1 |
| Measurement end | g5 CALL | g7 IJ | 1 |
| After application | g5 CALL | g7 IJ | 1 |

Both code pointers and generations were unchanged across all four snapshots.
The new pending reports occurred during warmup, before the measured window;
the records show no image publication during that window. Completed compiler
records also stayed at 12 through the point, while a new compiler child was
active. This fails the fixed receipt's no-new-learning requirement even though
the same compiled images remained in use. The receipt was never renewed.

Whole-application counters, including six warmup samples:

| Root | Submitted / JIT entered | Retained returns | Completed handbacks | Local, no image |
| --- | ---: | ---: | ---: | ---: |
| mmap | 337,306 / 337,306 | 337,298 | 8 | 0 |
| munmap | 337,300 / 337,300 | 0 | 337,300 | 0 |

All drained conservation equations pass on these saved deltas. The runner
retained them from the durable failed application receipt without changing its
error or pass status. During the ten-second observer interval:

| Root | Submitted / JIT entered | Retained returns | Completed handbacks |
| --- | ---: | ---: | ---: |
| mmap | 210,866 / 210,867 | 210,870 | 0 |
| munmap | 210,864 / 210,865 | 0 | 210,866 |

Boundary counters are concurrent reads with requests in flight, explaining the
small differences. The positive mmap retained-return delta, unchanged g5/code,
and pending status at both boundaries now establish continued completed retained
execution while learning is pending. The earlier long-run record did not
establish that case. These counters still do not identify a delegated downgrade
read tail or the executor's subsequent fresh writer admission. Physical batch
length, whole critical-section ratio and individual service runtime shares
remain unmeasured.

The new mmap CALL target was `mas_wr_bnode`, `0xffffffff826c1df0`. The retained
g5 assembly has one matching static CALL site at `0xffffffff826c4f10` inside
`mas_wr_store_entry`; it pushes return word `0xffffffff826c4f15` and dispatches
to that target's missing-CALL control. The matching ELF verifies the original
CALL encoding. The runtime CALL report stores the target, not its instruction
address, so attribution to this source site uses the unique matching emitted
site rather than a per-request instruction trace.

The prospective replacement selected `STD`, opcode `fd`, at
`0xffffffff826f0777` (`__memmove+0xb7`, before backward `REP MOVSQ`).
`disassem/disassem.py:848` refuses that instruction boundary with retained-service
execution. Child 3138 ended after 195.512222 seconds with wait status 512,
decoded exit/result 2. This is translation evidence, not evidence that the
application executed `STD`. `kernel_module/sys.c:268` recorded Native-only state
without another image publication or generation increment: final mmap remained
g5, status -3. The earlier g5 artifact is preserved; no subsequent application
ran in that terminal state.

Munmap added the same IJ pair twice:
`0xffffffffc0000f28` -> `0xffffffffc0e32980`. The exact loaded-module map names
the target `kd_provider_assert_held`. Final assembly identifies the source
instruction at `0xffffffffc0000f26` as `JMP RDX`; `...0f28` is its dispatch key.
The containing source symbol remains unverified. Repeated table rows establish
duplicate processing, not distinct lost reports. Two later successful
translations produced g8 and g9; g9 NORMAL was published after the application
and remains untested. Across preparation and postrun work there were 15 compiler
jobs totaling 1,256.329495 child wall seconds, overlapping application execution
and settlement. This total is not an application CPU-time share.

The saved Native process rate, 1,554,416 pairs/s, is an exploratory reference.
The provisional KD rate is 98.64% lower. Native-before, KD-before and KD-after
host captures match the host boot, QEMU PID/start/arguments, all 67 persistent
QEMU task rows, configured frequency/turbo policy, NUMA topology and actual RAM
bindings. Auxiliary CPU-63 workers changed 14 -> 9 -> 5. Matching endpoint
settings do not prove effective frequency or equal intervening activity.
Native used a long pre-window interval; this KD point used six seconds.
There is no accepted stable performance result or measured code-change gain.

The focused runner checks passed: eight fixed-session fixtures, six existing
lifecycle fixtures and two sample-window fixtures. An initial fixture run at
`954393ca13e85e39dad0a15ed06c250442e04766` exposed decimal-string JSON counter keys
in failure recovery; `276f2647` fixes key normalization. The failed check remains
retained. Existing built provider/daemon bytes were hash-verified and reused;
no new provider/kernel build is claimed for this Python-runner change.

Campaign close's separate 40-second compiler wait expired. Recovery preserved
the original failed result SHA256
`dd8e1f4c611f1667d3ca5c5cdfdb9c265cdc4dbc01db495cb33d98c77b4b85e8`.
Three cleanup prechecks stopped before any retirement action: omitted snapshot
environment, missing pinned Python PATH, then checking sole-writer descriptors
before compiler inheritance drained. A fourth read-only operator waited for
all-NORMAL, an unnecessary cleanup condition that terminal mmap -3 could not
satisfy. Its exact PID/start identity and empty action list were verified before
normal termination. Those receipts and errors remain separate.

Final cleanup used the existing retirement requirements: no application or
compiler children, exact sole daemon descriptor and identity, inactive provider,
zero frames, normal daemon termination, zero writers and bindings, exact source
retirement, then ordinary unload. It passed with state 2 and zero
modules/frames/writers; the original failure remained unchanged. The normal
`7.0.0-38-kdlock1` kernel was restored, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`78a62f64-862a-4a19-89d5-7a0e2d5e8951`, verified idle.

The boot helper initially wrote the fresh KD verification over the older guest
`mmap1-long-kd-boot-20261107/result.json`. The fresh source-host capture and the
original historical receipt in the earlier report's indexed raw copies remain
preserved. Normal recovery used the corrected destination; those canonical raw
copies were not rewritten.

[summary.json](summary.json) retains the exact counters, boundaries, compiler
history and hashed references. All 73 selected guest files (53,576,553 bytes),
including both applications, image assembly, failed checks, cleanup and recovery,
plus source-host launch/host/identity records remain in both checkouts under
`bench/results/10.176.26.71/raw/bench/mmap1-settled-276f2647-20261107/`.
No selected file exceeded the transfer bound. The guest index SHA256 is
`0585c1eacc13c9880c36939976920fb5ca7f1c0f003ae0fb9bbc52d2920ec9f0`.
