# Core-only symbol reuse: complete compilation comparison

Candidate `26337db1d722e3f7a239d703496197658bee05e8` reduces measured complete
cold-history compilation time by 41.94% for the selected mmap root and 42.10%
for munmap. All four generated artifacts match byte for byte in each pair.
This is compilation preparation evidence, not mmap1 throughput or returned-JIT
evidence. Nothing was published or executed. `master` remains unchanged at
`20fde062729703208ac54445f51fc0f21f24e0e8`.

## Contract and implementation

Design commits `c6e25aaa` and `4c4a6901` precede implementation. A fresh lazy
context exists for each `dis_assem()` call and is cleared on every exit. Direct
calls without a validated device lease use the original live resolver. Existing
fixtures replacing `get_kernel_symbol` still intercept every lookup.

Only positive values in the fixed core prefix through the first `_etext` row
are reused. The tentative prefix requires positive coherent `_stext < _etext`
and successful close. Module/dynamic names, misses, zero results and later core
rows use the unchanged live scan on each request. First raw tokens win and
non-marker hexadecimal conversion remains request-local. Observed fill errors
discard the prefix; the current and subsequent requests then use fresh live
scans. Errors and callers' defaults are never cached.

Ownerless rows alone do not prove core provenance: a module in COMING may
temporarily have an empty owner name. The matching Linux 7 generator retains
the built-in `_etext` marker, and core enumeration precedes the dynamic suffix.
Stopping there excludes those rows without a new ABI or a namespace monitor.
The earlier owner-prefix draft was never built or measured.

Value reuse assumes a fixed boot, translator credentials and symbol visibility.
A cache hit cannot reproduce an unobserved later file-read failure or visibility
change. A failed fill followed by live lookup also introduces an extra read
attempt. These limits are documented; this is not a full live-table snapshot.
Source leases, decoding, bounds, code generation, ownership and validation are
unchanged. WARN-frontier handling remains on hold.

## Focused correctness checks

All checks ran in the VM against immutable candidate inputs.

| Driver | Result |
| --- | --- |
| `admission/test_kernel_symbols.py` | 26 tests passed |
| `codegen/test_jit_diagnostics.py` | 13 tests passed |
| `admission/test_context_policy.py`, candidate | 108 tests run; four failures |
| Same context driver, unchanged baseline | Same four failures |

The new cases cover first matches, zeros/defaults, dynamic insertion,
replacement/removal, ownerless dynamic rows, generated owners, later core data,
invalid/missing markers, malformed tokens, open/read/close failures, no-lease
behavior, nested contexts, exit cleanup and the mocked lookup boundary.

The four context-policy failures are retained, not waived or called passes:

- `test_retained_balanced_child_loop_keeps_ordinary_image_contract`:
  `8320 != 128`.
- `test_retained_callee_owned_child_keeps_early_outer_release_tail`:
  `8576 != 384`.
- `test_retained_deep_scope_uses_explicit_image_requirement`, children 7:
  `8320 != 128`.
- The same method, children 8: `8576 != 384`.

The baseline and candidate logs are identical after normalizing their source
paths and elapsed-time line. The differing requirement bit is 8192,
`RETAINED_MISS_REQUIREMENT`. This establishes pre-existing failures for this
comparison, not their resolution. No checks or expectations were disabled.

## Matched compiler inputs and measurement

The compiler ran on `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`03a16047-d5fb-472a-980d-f6c98420a152`, with `kd_mmap=off`. Both arms used the
same loaded provider from `4506f6e46394133e439f68a04d6fde38aea0885f`, SHA256
`a9e121b1dfae464e3199b8d6cec07d7539f3aedac62d31a3affd680b1b629f65`.
Its binary and loaded source version were checked. It was reused, not rebuilt;
candidate kernel-module and include bytes match that baseline exactly.

Baseline compiler source: immutable `/root/kdlock-inputs/shape-4506f6e4`,
commit `4506f6e46394133e439f68a04d6fde38aea0885f`. Its production compiler bytes
also match `be0fd17bd7f10b49ae2776a9b7ccc37a797bdd45`. Candidate source:
`/root/kdlock-inputs/core-symbols-26337db1`, commit
`26337db1d722e3f7a239d703496197658bee05e8`. Frozen inputs were hash-verified
before and after. The pinned translation Python and its exact dependency
verification ran in each compiler child. Parent and compiler affinity was CPU
63 on the existing 64-vCPU, two-NUMA-node VM. The recovery snapshot, host pins
and fixed 2 GHz policy passed the retained preflight capture.

There was exactly one baseline-first pair per root. Each child started fresh,
imported the compiler, entered the validated device lease, decoded the selected
scope, lowered it, assembled with GCC and completed objcopy/objdump. `wait4`
supplied child user/system CPU and peak RSS; wall time spans launch through
exit. A measurement-only harness records one item per symbol lookup and counts
symbol-file opens. There are no per-line or instruction profiler hooks. Output
and lookup-record writes are included in the lifetime.

Both arms used empty CALL/IJ histories, PID 0, ABI2 mutex continuation and the
existing trusted-source setting. mmap entry `0xffffffff817b6f68` selected 43
instructions / 152 instruction bytes in eight blocks, with two decode passes.
munmap entry `0xffffffff8181c73b` selected 39 instructions / 165 bytes in eight
blocks, with one pass. Coverage diagnostics are identical across each pair.
Neither scope has an incomplete block. The earlier large learning histories
contain module addresses from another load and were deliberately not reused.

## Results

| Root / arm | Wall s | User s | System s | Peak RSS KiB | Lookups | Opens | Core hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mmap baseline | 13.374795081 | 6.037400 | 7.317070 | 54,432 | 137 | 137 | 0 |
| mmap candidate | 7.764953803 | 3.683156 | 4.062996 | 78,388 | 137 | 49 | 89 |
| munmap baseline | 13.323225949 | 6.112495 | 7.167918 | 54,248 | 137 | 137 | 0 |
| munmap candidate | 7.714694382 | 3.541020 | 4.160941 | 78,220 | 137 | 49 | 89 |

| Root | Wall reduction | Speed ratio | System CPU reduction | Peak RSS increase |
| --- | ---: | ---: | ---: | ---: |
| mmap | 41.94% | 1.722x | 44.47% | 23,956 KiB |
| munmap | 42.10% | 1.727x | 41.95% | 23,972 KiB |

Each actual compiler invocation makes 137 requests. The candidate serves 89
from the positive core prefix, leaving 48 live requests and one prefix-fill
open: 49 total opens. Thus the conservative implementation retains substantial
live-scan cost. The earlier full-snapshot helper's 56.89x metadata result is
not an expected or measured production gain.

All ordered name/default/address results are identical per pair. `jit.S`,
`jit.o`, `jit.bin` and `bin.txt` hashes and retained bytes match. mmap binary
SHA256 is `82f5e9763d9192bccdcd074d624fd117754b137396a0064fb5e878406ca86257`;
munmap binary SHA256 is
`d89406cb72eec20657d175ebe5aaafd5a8922126e81555c93097e779ebbc77db`.
Observed symbol-table hashes match before and after the comparison. This is
not continuous namespace monitoring.

Peak memory is higher by about 23.4 MiB. Per-child `ru_maxrss` is a process
high-water observation with reaped-child accounting, not the exact retained
dictionary size. No compiler-time regression appeared in these two pairs.
One ordered sample per root gives no variance estimate; filesystem, imports
and source-pin caches were not reset between arms. Larger learned scopes,
publication, runtime throughput, mmap1 correctness/delegation and Nano remain
unmeasured by this experiment. The candidate remains isolated.

## Retirement, restoration and retained files

No daemon or application ran; demand capture was disabled and the kernel used
Native MM routing. The registry remained empty. Each compiler exited with zero
active source writers/frames; exact retirement returned
`state=2, modules=0, frames=0, writers=0`, followed by ordinary provider unload
and idle. No generated image was published.

Normal `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored and verified on boot
`74106c59-6990-4d67-a479-8aadf4fcdbf0`. Final idle passed and GRUB had no pending
entry. Both private source trees remained unchanged.

`compiler-result.json` retains the complete measurement and exact artifact
identities. The four unit logs and baseline comparison retain all failures.
The as-run compiler helpers, controller, source receipts, boot verifications
and recovery capture are included. `retained-files.json` binds all 38 raw
compiler files under
`bench/results/10.176.26.71/raw/tests/core-symbols-26337db1/`.
`sha256.json` binds this compact evidence set. Offline hash and byte-comparison
checks passed on 380G10; these are archive checks, not additional VM runs.
