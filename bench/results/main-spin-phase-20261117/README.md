# Main spin phase re-observation on local 380G10

Only main source and documents were accessed for this work. The main-only
restriction, including read-only access, is recorded in main AGENTS.md at
7af9bc85. Candidate 5cd2e62bfdd015584e3ffbd7e81038ac90da92f0 uses the
existing clean-rewrite main baseline and changes only contended admission.
All VM access is to identity-verified local QEMU on 380G10. No remote VM
access or unrelated deletion was performed.

## Candidate

An empty holder byte with an existing tail can occur between owners. The
original main path immediately selects ordinary queuing in this window.
The candidate optionally re-reads only the lock word, up to 128 times,
stopping when the holder/pending bytes appear, the queue disappears or the
bound expires. Offering still requires an observed delegation mode and the
existing capture eligibility checks. Pending and queue-head operations,
not the observations, establish ownership. It retains no address history
or node pointers. Forced mode and raw paths retain their existing semantics.
The fast CAS and unlock assembly are unchanged. The default is zero while
same-image values 0, 8, 32 and 128 are compared.

See [review.md](review.md) for source reasoning and validation limits. A low-contention
queue can pay extra observations without obtaining delegation; do not accept
higher high-contention throughput without reporting that cost. Counter deltas
are not physical chain-length measurements or ownership proofs.

## Inputs and build

All 131 source inputs were hash-verified against main. The input checkout
was created from the earlier frozen main 4669a085 copy plus the main-only
overlay. Every KD source/header in the Linux build tree was replaced with
these verified inputs. The generic Linux environment and existing guest
GCC 12.3/binutils 2.38 toolchain were reused. A separate main-phase-source
and entirely fresh main-phase-out directory were used; no prior compiled
kernel objects were reused for this build. No new compiler/packages were
installed and no other branch's source or documentation was consulted.

Kernel: 7.0.0-38-kdlocalspin4 #1, image SHA256
90e13abd0a6b8f4bbbc1c68dcfe44a8b1fc2c34463d680930f6f830b19001ab1.
Config SHA256: 1395ae1ff15c215ab680dbb5a4a8af074044cc7de35be82004ddf2647f01ca64.
Fresh olddefconfig adds CONFIG_TOOLS_SUPPORT_RELR=y relative to the saved main
baseline config; the exact diff is retained. Earlier boot results are not
pooled. The benchmark and TCLock spin .text hashes match that main baseline
exactly ([build-review.json](build-review.json)). Kernel task stacks remain 16 KiB, preemption
full (lazy), legacy REBUILD and whole-kernel replacement disabled.

The image build succeeded, but the first external module target failed
because the fresh output lacked scripts/module.lds. modules_prepare produced
it; a module-only retry then completed all seven required modules. Failed
and successful logs remain separate. Locale/HOME environment warnings and
existing TCLock objtool naked-return/BP warnings are retained; these are not
claimed as clean mitigation coverage. The benchmark also reports its existing
missing MODULE_DESCRIPTION warning. All modules were signed; no signing keys
are included in these receipts. Only the new release's NLS module was
installed; comparison/check modules remain in the isolated task directory.

## Measurement method

All backend and policy comparisons share boot
7e85181e-c95d-43fa-82e6-611304550383. The VM has 40 vCPUs, two nodes of 20 CPUs
and 32 GiB, one vCPU per host CPU. The emulator and controller use CPUs 38–39.
Up to 16 workers start at CPU0; 32 workers use balanced CPUs4–35. Packed
CPUs0–31 is a separate control. Host frequency limits were recorded, not
changed. The existing two-disk snapshot
kdlock-kernel16-two-disk-smoke-20261116-01 was verified before live work.

Each standard cell has three backend-order rotations, a 250ms warmup and
1000ms timing, 100% writes, post=64, lines=1 or16. Post=0 controls are separate.
Policy values reverse order between repetitions. Option0 is a same-image
control, not the exact old binary: it retains changed code layout and the
inactive slow-path checks. Serial requests are excluded during measurement.
Every point validates operation/write sums, shared-data delta, no torn reads
and progress of every worker. Native/KD/TCLock have separate objects but
matched workload bodies and CPU placement. TCLock spin execution counters
are unavailable; KD zero counters on its points are not TCLock counts.

## Validation and results

Before timing, the signed six-entry fixture passed plain, IRQ, IRQ-save,
IRQ-save-already-off, BH and clobber: 60000 operations per case, 30000 per
worker, observed contention, zero exclusion/state errors and normal unload.
This fixture runs without delegation; the campaign adds nested/raw/handback,
phase-transition and bounded-policy cases. It does not establish arbitrary
mixed nesting, full stack bounds or whole-kernel support.

The completed campaign has **853 checked points, zero failures**, 65 API
checks with zero failures, no new kernel warning, daemon exit 0 and normal
unload of all five comparison modules. Operation/write sums, shared-data
deltas and per-worker progress were also checked again from the exported
records. The first image-plus-modules build returned 2 at the external-module
stage; the later module-only retry returned 0. Those are separate results.

**The polling candidate is not promoted.** With `kd_spin_phase_wait=128`,
32-worker short KD improves from 3.470 to 6.250 Mops/s in the matched policy
comparison, but five-worker short KD falls from 4.462 to 3.607 Mops/s while
still delegating zero bodies. The value remains zero by default and cleanup
restored it to zero. Values 8 and 32 also retain the five-worker regression.
The non-polling queue-phase candidate has since completed its
[separate policy comparison](../main-spin-queue-20261117/README.md), followed by
the completed [default-enabled kernel6 verification](../main-spin-final-20261117/README.md).
Each report retains its own source/image/boot identity; their measurements are
not pooled with this polling campaign.

### Three-way baseline in this boot

Values are median Mops/s with [minimum, maximum] across three measured
repetitions. All rows here use phase_wait=0. KD count columns sum those
three repetitions and exclude warmups. TCLock execution counts are unavailable.

| Lines | Workers | Native | KD | TCLock | KD delegated | KD handback |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9.451 [9.447, 9.451] | 9.451 [9.449, 9.452] | 9.450 [9.450, 9.451] | 0 | 0 |
| 1 | 5 | 4.478 [4.473, 4.478] | 4.459 [4.459, 4.464] | 3.228 [3.225, 3.248] | 0 | 0 |
| 1 | 8 | 4.552 [4.549, 4.559] | 4.612 [4.609, 4.616] | 5.154 [5.152, 5.168] | 35 | 0 |
| 1 | 16 | 4.587 [4.579, 4.590] | 4.627 [4.598, 4.630] | 5.664 [5.664, 5.668] | 21 | 0 |
| 1 | 32 | 3.554 [3.547, 3.584] | 3.536 [3.429, 3.566] | 5.499 [5.494, 5.500] | 45 | 0 |
| 16 | 1 | 8.957 [8.956, 8.959] | 9.064 [9.062, 9.065] | 8.895 [8.891, 8.905] | 0 | 0 |
| 16 | 5 | 2.382 [2.379, 2.389] | 2.380 [2.369, 2.381] | 2.508 [2.494, 2.511] | 0 | 0 |
| 16 | 8 | 2.402 [2.400, 2.406] | 2.423 [2.421, 2.431] | 3.223 [3.208, 3.230] | 29,161 | 0 |
| 16 | 16 | 2.384 [2.383, 2.387] | 2.407 [2.402, 2.412] | 3.273 [3.261, 3.286] | 29,485 | 0 |
| 16 | 32 | 1.847 [1.829, 1.848] | 1.865 [1.862, 1.867] | 3.246 [3.244, 3.250] | 13,195 | 0 |

### Phase-wait policy comparison

Each row is a matched three-way cell in the same boot; rates are medians
and count columns are KD totals across its three measured repetitions.
No ordinary spin policy cell handed back. The complete per-round rates and
all counter deltas are in [summary.json](evidence/summary.json) and
[rates-and-counts.csv](evidence/rates-and-counts.csv).

| Wait bound | Lines | Workers | Native | KD [min, max] | TCLock | KD delegated | KD handback | KD stop_plain |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 5 | 4.478 | 4.462 [4.461, 4.465] | 3.230 | 0 | 0 | 0 |
| 0 | 1 | 8 | 4.549 | 4.608 [4.605, 4.616] | 5.133 | 22 | 0 | 2,822 |
| 0 | 1 | 32 | 3.552 | 3.470 [3.415, 3.624] | 5.487 | 33 | 0 | 1,572 |
| 0 | 16 | 5 | 2.381 | 2.383 [2.379, 2.383] | 2.501 | 0 | 0 | 0 |
| 0 | 16 | 8 | 2.402 | 2.426 [2.426, 2.428] | 3.215 | 29,417 | 0 | 428,744 |
| 0 | 16 | 32 | 1.866 | 1.862 [1.862, 1.863] | 3.240 | 12,287 | 0 | 504,406 |
| 8 | 1 | 5 | 4.477 | 3.641 [3.633, 3.641] | 3.239 | 0 | 0 | 0 |
| 8 | 1 | 8 | 4.554 | 5.696 [5.679, 5.782] | 5.140 | 17,973,348 | 0 | 102 |
| 8 | 1 | 32 | 3.697 | 5.842 [5.828, 6.010] | 5.485 | 18,062,163 | 0 | 152 |
| 8 | 16 | 5 | 2.379 | 2.356 [2.343, 2.358] | 2.508 | 0 | 0 | 0 |
| 8 | 16 | 8 | 2.403 | 4.147 [4.140, 4.172] | 3.208 | 13,078,853 | 0 | 2 |
| 8 | 16 | 32 | 1.879 | 4.255 [4.226, 4.525] | 3.230 | 13,453,399 | 0 | 71 |
| 32 | 1 | 5 | 4.475 | 3.608 [3.599, 3.610] | 3.235 | 0 | 0 | 0 |
| 32 | 1 | 8 | 4.554 | 5.750 [5.712, 5.765] | 5.136 | 17,996,116 | 0 | 22 |
| 32 | 1 | 32 | 3.559 | 6.084 [5.787, 6.159] | 5.476 | 18,673,194 | 0 | 18 |
| 32 | 16 | 5 | 2.383 | 2.346 [2.336, 2.349] | 2.510 | 0 | 0 | 0 |
| 32 | 16 | 8 | 2.403 | 4.145 [4.109, 4.187] | 3.211 | 13,037,693 | 0 | 4 |
| 32 | 16 | 32 | 1.836 | 4.235 [4.178, 4.408] | 3.244 | 13,242,053 | 0 | 5 |
| 128 | 1 | 5 | 4.477 | 3.607 [3.606, 3.607] | 3.240 | 0 | 0 | 0 |
| 128 | 1 | 8 | 4.551 | 5.744 [5.625, 5.764] | 5.135 | 17,831,809 | 0 | 30 |
| 128 | 1 | 32 | 3.581 | 6.250 [5.743, 6.264] | 5.495 | 18,369,323 | 0 | 0 |
| 128 | 16 | 5 | 2.381 | 2.352 [2.344, 2.353] | 2.504 | 0 | 0 | 0 |
| 128 | 16 | 8 | 2.402 | 4.157 [4.119, 4.182] | 3.216 | 12,988,132 | 0 | 2 |
| 128 | 16 | 32 | 1.848 | 4.302 [4.182, 4.308] | 3.245 | 13,133,333 | 0 | 0 |

The largest short-section KD median among these policy cells is 6.250 Mops/s
at 32 workers, bound 128 (range 5.743–6.264 over three repetitions). This is
80.1% above bound 0, 74.6% above matched Native and
13.8% above matched TCLock. It is an observed three-repetition median, not a
qualified universal peak. Five-worker short throughput is -19.2% below bound 0,
with disjoint observed ranges (4.461–4.465 versus 3.606–3.607). That low-contention
cost rules out adopting 128 as a general default despite the high-contention gain.

At 32 workers, one line, bound 0 has 33 delegated events and 1,572 plain stops;
bound 128 has 18,369,323 delegated events, 4,548 sessions, zero plain stops and
72,720 NUMA deferrals. At 16 lines, delegated events rise from 12,287 to
13,133,333 and plain stops fall from 504,406 to zero. This directly demonstrates
that the admission-window intervention changes delegation availability. It does
not establish a measured physical batch length, exact per-cycle attribution or
an ownership proof. The five-worker cost with zero delegation is consistent
with extra observations on ordinary contention; no profile isolates its cycle share.

### Counts, controls and limits

All-phase totals include learning, checks and warmups and must not be divided
by a single cell's elapsed time:

| KD event | All-phase count |
|---|---:|
| offered | 264,417,119 |
| delegated | 259,335,288 |
| handback | 454,576 |
| sessions | 730,554 |
| stop_plain | 4,549,069 |
| numa_deferred | 3,243,600 |

All 454,576 handbacks are frontier events: spin_hb accounts for 227,357 and
spin_hb_cl for 227,219. Standard spin timing and spin_mixend have zero
handbacks; zero is retained rather than described as handback coverage.
Nested, raw and clobber families remain separate functional evidence.
Counters are approximate runtime events, not logical ownership records or
proof that every published image executed.

The post=0 and packed 32-worker controls remain in the raw archive, with
separate phase labels and CPU placement. They are not pooled with the
standard balanced-32 workload. No full suite, whole-kernel replacement,
arbitrary mixed nesting or complete stack-bound proof is claimed.

Cleanup restored adapt=Y, entry/exit=5/2, batch=4096, numa=Y, numa_after=32,
phase_wait=0. Only the NLS module remained loaded. The measurement boot and
configuration are exactly those recorded above. The completed queue-phase
candidate and default-enabled kernel6 reports retain their own source/image/boot
receipts. This campaign's historical measurements remain unchanged.

Archive SHA256:
`aca2f2b69fa698001b82c05fc97a368f79c04cb9a8da3629fb7fd29646c3c40e`.
The host extraction rejected absolute/parent-traversal paths and non-regular
members; 55 members were extracted under the task directory after hash verification.


## Evidence files

The report retains existing top-level receipts and organizes the complete
export without rewriting its bytes:

| Purpose | Files |
|---|---|
| Source and review | [main-phase-identity.json](main-phase-identity.json), [review.md](review.md) |
| Exact observations | [points.jsonl](evidence/points.jsonl), [rates and counts](evidence/rates-and-counts.csv), [summary](evidence/summary.json) |
| Build failure | [initial log](build/initial-build.log), [result rc=2](build/initial-result.json) |
| Module preparation and successful retry | [modules_prepare log](build/modules-prepare.log), [retry log](build/module-retry.log), [result rc=0](build/module-retry-result.json) |
| Module diagnostics | [bench](build/module-logs/bench-build.log), [TCLock spin](build/module-logs/tclock-spin.log), [entry fixture](build/module-logs/main-phase-entry-build.log) |
| Image/config/code review | [build-review.json](build-review.json), [config diff](config-diff.txt), [slow-path assembly](build/asm/kd_q_lock_slow.asm), [entry assembly](build/asm/kd_spin_lock.asm) |
| Entry check | [result](checks/entry-result.json), [kernel log](checks/entry-dmesg.txt) |
| Completed campaign | [run result](runtime/result.json), [run log](runtime/run.log), [preflight](runtime/preflight.json), [cleanup](evidence/cleanup.json) |
| Reproduction | [run.py](run.py), [summarize.py](summarize.py), [signed artifact hashes](signed-artifacts.json) |
| Provenance | [archive identity](archive.json), [report file hashes](SHA256.json) |

The archive and extracted files contain evidence, not VM disk files or signing
keys. Prior failed build receipts are retained and not relabeled as passes.
