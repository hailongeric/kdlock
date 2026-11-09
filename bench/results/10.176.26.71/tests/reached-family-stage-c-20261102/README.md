# Reached-path Stage (c): family, cache and returning services

Tested implementation: `b75d82ab7cc066763a659d3fe9f2b6811b98f664`, on
`codex/reached-path-translation`, starting from
`961550afdc1429cfd86cff138046d3f6eebacdf8`. This implements the Stage (c)
image-free joins and passes the focused checks below. The candidate remains
isolated; `master` was not changed. No actual mmap1 or performance comparison
was run. Directory dates identify this staged campaign; final checks completed
on November 3, 2026.

## Implementation

The design was updated before implementation in
[`reached_path_execution.md`](../../../../../docs/design/reached_path_execution.md#stage-c-image-free-family-cache-and-service-joins).
Load the provider with `service_reached=1` to select reached execution for
eligible captures. The default remains the existing image mode. The reached
fixture uses `tests/kernel/jit_continuation/run.py --execution-mode reached`;
it does not launch the translator, prewarm callees or require a complete
application image. Ordinary nonselected callers and calls inside a registered
Native helper retain their conventional API route. A published reached body
does not switch to an origin suffix.

| Join | Mechanism and source |
| --- | --- |
| Capture | `kernel_module/kd_service.c`: capture lease and stable root family are established before admission publication; actual execution still waits for acquisition commitment. No image lookup in selected reached mode. |
| Family and lifetime | `include/kd_family.h`, `kernel_module/kd_family.c`: exact list-backed references keyed by request identity/generation, source epoch and entry ABI; ACTIVE/DRAINING/RETIRED lifecycle. A count alone grants no ownership. |
| Service | `kernel_module/execution/reached_dispatch.inc`: retain the complete current instruction and its exact artifact sequence before publishing KD, Native or GS work; release its independent reference only after the actual completion ACK. Resume the same canonical packet on E. |
| Ordinary callee | Execute the actual source CALL/RET words and decode the reached callee on E. Registered Native operations use the returning origin service, rather than routing an unknown callee wholesale to origin. |
| Cache | Sixteen immutable instruction-byte records per root, not compiled native code. Admit after a PC repeats within a 32-PC recent window. The recent history is only a cache hint. `kernel_module/execution/reached.inc` freshly pins, reads and compares the complete current source instruction before using a candidate. |
| Bounds | At most 64 instructions per local dispatch; a persistent 16-million-instruction scheduling window survives services and nested waits. Runtime refills the window, honoring scheduling only where Native pin state allows. Cache exhaustion continues cold without allocation or a public error. |
| Scalar effects | `kernel_module/kd_reached.c`, `kd_reached_atomic.c`: Native-width shifts/rotates, IMUL and register bit operations; locked ADD/SUB/INC/DEC/XADD/CMPXCHG and implicit memory XCHG use a single actual CPU operation, not split load/store or retry emulation. |

There is no upfront CFG traversal or transitive callee expansion. Only the
reached instruction is decoded and supplemented. Future small native regions
may be cached without making a complete MM CFG an admission prerequisite.

The CALL join was also corrected to resolve a registered Native target before
validating its inherited CALL word. An ordinary intra-function JMP does not
imply a new CALL word. Unknown targets proceed through reached decoding;
known targets still require their exact source return contract.

## Preserved protocol behavior and focused proof

The public API and two-word wrapper ABI are unchanged. This stage joins
execution to the existing unified admission/ownership protocol; it does not
substitute a new cancellation or downgrade rule.

| Behavior | Mechanism and evidence |
| --- | --- |
| Killable acquisition | `kd_admission_step_locked` tests real grant readiness before origin-signal cancellation. Capture holds its lease before publication; no body executes for a canceled acquisition and no late signal converts committed effects into `-EINTR`. Reached fixtures passed success, three queued cancellations while the holder remained locked, and selected reader-drain cancellation. |
| Exact retirement | Cancellation uses the existing terminal guard transfer and ACK, then continuation retirement. Family retirement additionally requires no live artifact and an empty exact reference list before root reuse. All final fixtures reported drained and `active=0`. |
| Nesting | Existing per-owner identity, generation, parent and depth records remain authoritative. Family artifacts independently retain lifetime through nested waits. Nested origin-signal cancellation, mixed depth nine, early outer release, 128 repeated children and true nested control all passed in reached mode. |
| Non-LIFO completion | Releasing one exact owner does not retire another. Family component checks include independent reference retirement, and reached helper phases passed blocked/non-LIFO Native writer release and final Native release. |
| Downgrade | Existing selected writer phase becomes a read credit; the tail remains delegated on E. On read release, the next writer takes the ordinary fresh phase and drains readers. No implicit upgrade or overwrite of a live prepared cohort is added. |
| Native service return | Exact family generation, source instruction, artifact sequence and service/resume coordinates match; helper effects occur once on O and resume on the same E. Sleeping, mapped allocation, spin/RCU ownership and GS preempt-count service phases passed. |

In the final reached downgrade fixture, O `13435` ran on E `13378` through
`downgrade`, `read_release` and `returned`. Only then did O `13436` enter its
fresh writer phase on E `13378`. The full event ledger is retained in
[the reached reply](b75d-reached-checks.json). This proves that observed
fixture sequence; it does not promise executor affinity for every request or
establish actual MM execution.

Nested lock owners use separate `kd_service_owner` records while sharing the
root's canonical packet, family and current service artifact. This does not
allocate a family reference for every held lock. Their exact ownership records
and the independent active-artifact reference have separate retirement duties.

## Environment and provenance

All edits, Git and offline evidence inspection ran on 380G10. All builds,
unit drivers and live checks ran only on the VM. Final successful checks used:

| Identity | Value |
| --- | --- |
| Kernel | `7.0.0-38-kdscope5` |
| Build ID | `5f2fce72a33480f6e79a79b374b21a0db377ecd1` |
| Boot | `17478c05-2012-4095-ada6-977c32222817` |
| Runtime | `kd_mmap=on`, `preempt=lazy`, `full (lazy)`; schema-2 `kdscope5-kd` verified |
| Kernel bundle | `/root/kdlock-kernel-baselines/linux70-kdscope5-kd-20261103` |
| Build root | `/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build` |
| Private input | `/root/kdlock-inputs/stage-c-b75d-b75d82ab-20261102` |
| Source manifest | `76184c0a0d9a5b59d78d00d22aff29d9ab892110cc6b2a913635254b2f732d94` |
| Source state | `4f8674f6238cb9277c6d74bae53362b46eac5a6d76e74592497716102da3fe41` |
| Input size | 6,841 files; 413,023,898 bytes |
| Recovery snapshot | `kdlock-builddisk-clean-20261031`, confirmed before live checks |

Host receipts retain 64 vCPUs, two NUMA nodes (0–31 and 32–63), CPU pins,
collector CPU 63 and the fixed 2 GHz policy. These correctness fixtures use
CPUs 0–3; there is no cross-NUMA performance result. Private transfers were
idle-only, with unchanged files hardlinked and changed files given separate
inodes. The canonical guest source and all older frozen inputs were preserved.

Final verification found all 6,841 source hashes unchanged, no provider or
fixture loaded and an idle guest. Free space was 3,514,503,168 bytes on root,
15,129,886,720 on the first build disk and 23,269,277,696 on the second. This is
the final focused-run state, not admission for a future full-kernel build.

## Retained attempts and fixes

Results below remain attached to their exact commits and boots.

| Commit | Result and change |
| --- | --- |
| `bf3cb1fc4ab356190f1c68a694d00d7edaa68d87` | Initial joins. Family fixture failed compilation under `-Werror=restrict`: `pthread_create` reused its output address as its argument. Eight other selected drivers passed. No provider/live run was launched by that attempt. |
| `a7935391b1d7fffe121473da9382aa2e0e7b5de8` | Separate fixture identity storage. Nine drivers, provider build and 47,658 resident assertions passed. Seven reached helper phases passed; the eighth stopped at a missing BTR instruction. Later phases and killable suite were unrun on this commit. |
| `96d58adb8c70a05f2edb99f7e0f46b61091d616f` | Exact register BT/BTS/BTR/BTC support. Nine drivers, 52,854 resident assertions, reached helper 11/11 and killable 11/11 passed; separate image compatibility 11/11 plus 11/11 passed. Cache hits remained zero. |
| `b75d82ab7cc066763a659d3fe9f2b6811b98f664` | Repeat-PC cache admission and freshly checked cached fetch. Ten drivers, 52,854 resident assertions, reached 11/11 plus 11/11 and separate image 11/11 plus 11/11 passed. Cache hits and full-cache cold progress were observed. |

The missing instruction on `a7935391` was `48 0f ba f2 1f`,
`btr $0x1f,%rdx`, at `ffffffffc09edee5` (entry
`ffffffffc09ed944`, relative `+0x5a1`). It implements the mandatory preempt-count
predicate in `tests/kernel/jit_continuation/payload/helper_memory.inc:80`.
Three GS transactions had completed before that stop. E `42542` stopped and
O `42593` remained waiting; the existing service error path produced a kernel
BUG and a later soft lockup. This was an undrained failure, not successful
retirement or a local suffix.

Serial, frozen ELF diagnosis, session and kernel logs were preserved before
recovery. One QEMU reset recovered the guest, followed by a one-time boot into
the existing scope5 KD entry. Default GRUB selection was unchanged. The reset
does not establish clean retirement. The failed boot and final successful boot
are separate; their results are not pooled. See [diagnosis](a793-diagnosis.json),
[archive inventory](a793-archive.json), [session](a793-session.json),
[kernel log](a793-kernel.log), [serial identity](a793-serial-identity.json) and
[boot record](a793-grub.json). The full 12,557,478-byte serial log is retained
on the QEMU host with SHA256
`1fa7437c9bda3ed321c54616968a6cfd5c01888c59179c1c6aea80670cdc211e`.

## Final candidate checks

| Check on `b75d82ab` | Result |
| --- | --- |
| Production cached-fetch fixture | 67 assertions, zero failures |
| Production exact family/cache fixture | 4,402 assertions, zero failures; bounded 16-record cache |
| Reached service ledger validator | 14 cases passed |
| GS decoder | 172 assertions and three expected negative variants passed |
| Retained-frame adapter | 144 assertions, zero failures |
| Existing runner/helper/memory/mapped/Native writer validators | 7 / 6 / 6 / 4 / 4 cases passed |
| Ordinary provider and resident fixture builds | Passed, warnings retained below |
| Resident engine | 52,854 assertions; E `10648`, O `10647`; 47,657 source fetches |
| Image-free helper | 11/11 phases passed and drained; translator not started |
| Image-free killable/nesting/downgrade | 11/11 phases passed and drained; translator not started |
| Existing image compatibility | Helper 11/11 and killable 11/11 passed and drained |
| Final state | Idle, no project modules; all frozen input hashes unchanged |
| Actual mmap1 / Nano / timing | Not run |

The resident count is assertions, not distinct instruction encodings. It
includes 12,544 Native arithmetic tuples, 1,400 atomic cases, 1,400 shift/rotate
cases, 75 IMUL cases and 1,728 register bit-operation comparisons. The standalone
fixture executes exact engine sources on a separate task while O retains its
source stack. Public capture and returning-service evidence comes separately
from the reached helper and killable suites.

### Cache observations, not performance measurements

| Source / reached suite | Instructions/lookups | Hits | Misses | Full-cache publication attempts | Roots / completions |
| --- | ---: | ---: | ---: | ---: | ---: |
| `96d58adb` helper | 2,360 | 0 | 2,360 | 2,184 | 11 / 11 |
| `96d58adb` killable | 298,312 | 0 | 298,312 | 298,088 | 14 / 14 |
| `b75d82ab` helper | 2,360 | 826 | 1,534 | 520 | 11 / 11 |
| `b75d82ab` killable | 428,764 | 426,594 | 2,170 | 1,336 | 14 / 14 |

Before the policy correction, one-time entry instructions filled the cache
before the loops were reached. Repeated-PC admission retains loop instructions
instead. These are individually identified runs, not a pooled score or a speed
comparison: the downgrade fixture polls until the controller releases it, so
its instruction total changes with that interval. A hit means the freshly
observed current instruction matched a family record, not a compiled JIT hit.
Full cache continues through the uncached path.

Both final reached sessions ended with `unsupported=0`, `active=0` and exact
root/completion conservation. Helper service totals were 11 KD control, 43
Native primitive and eight GS transactions. Killable totals were 306 KD control
transactions. Canceled roots have no entered body or service transaction.

## Remaining limits

This slice does not activate the MM factory with reached mode or establish
actual mmap/munmap delegation. Broad MM path coverage and throughput require
their own candidate build/run. Native MM bodies and the integration layer were
not modified here. No Nano regression gate or performance gain is claimed.

Register bit operations are implemented; memory bit strings still stop before
effects. GS services cover the preempt-count load/test contract, not arbitrary
task/per-CPU reads. User-address accesses, faulting or cross-page ordinary
stores, cross-page atomics, other context
instructions and unsupported encodings require explicit instruction/service
contracts. Source-range retention and fresh-byte comparison do not add a
general concurrent text-modification contract. The resident scalar path and
its source cache are not a native compiled-region implementation.

An unsupported reached operation remains an explicit diagnostic failure; the
existing service error path can stop the executor and leave a live origin, as
the retained BTR failure demonstrates. Therefore this candidate must not be
described as a universal Native lock replacement. It neither reports public
API success for that interval nor silently executes a whole suffix on O.
Cancellation, nesting and downgrade passes establish the listed fixtures only,
not every API/configuration or arbitrary MM lifetime combination.

Build logs retain the compiler-identity warning, existing objtool warnings in
restoration/combiner/service bridges, fixture frame-size warnings and an
unreachable-instruction warning in the killable fixture. The separate image
daemon also logged disassembly retry warnings. Successful fixtures do not
resolve these limits; exact log hashes and warning lines are in the final
inventory.

## Receipts

| Artifact | SHA256 |
| --- | --- |
| [Final reached reply](b75d-reached-checks.json) | `f74095f9b925920eb150debb60cca6022e30ccb8938bf4784647f78499128932` |
| [Final image reply](b75d-image-checks.json) | `3c9e55c428eab4af05cff8c93209ef7ccf6bdc638943c517ccc864f6e613c055` |
| [Host before reached](b75d-reached-host.json) | `89a53f142a2091b5c07a714d2849f632dfbd0b3baef19269166bcf9075c0d1f9` |
| [Host before image](b75d-image-host.json) | `29994be3b699d1393a350a8dcca761942edb737be2c75ed43e37deb97e34eb29` |
| [Frozen input transfer](b75d-source-transfer.json) | `3450d9e7d1d9216de901f337675e5e81d0c5ef066c51292018f24071b266070f` |
| [Final idle/source/log inventory](b75d-final-state.json) | `75ee9973c4c800e27534674bab3db1706fd947b986a344a5f19a207a24d95e43` |

Earlier exact replies remain [initial units](bf3c-unit-attempt.json),
[first live attempt](a793-focused-attempt.json),
[BTR-corrected reached](96d5-reached-checks.json) and
[BTR-corrected image](96d5-image-checks.json). Their failures and zero-hit
observations are retained alongside the final results.

Full final VM outputs remain in
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/stage-c-b75d-checks-first-20261102`
and
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/stage-c-b75d-image-checks-20261102`.
