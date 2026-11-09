# Normal-kernel symbol lookup comparison

This focused metadata experiment compares the unchanged `get_kernel_symbol`
resolver with a helper-only, one-pass snapshot. It uses the restored normal
kernel without loading modules, publishing images, or running mmap1. Production
translation code is unchanged. Warning-frontier handling remains awaiting review.

The ordered lookup sequence uses the actual control and hostcall resolvers,
all 98 terminal specifications, ABI2 alias assignments extracted from
`dis_assem`, and the `current_task`/`__per_cpu_start` helper. Device-dependent
startup checks and the source-dependent preemption lookup are outside scope.
Extracting these assignments measures a constructed lookup sequence even when
missing controls would prevent normal compiler startup.

The original resolver runs first, then a fresh snapshot with construction and
all lookups inside its timed interval. There is one measurement per arm. Wall,
user and system CPU time, lookup/open counts, affinity, symbol/module table
identities and source hashes are retained. The snapshot keeps the first raw
address token for each name, defers integer conversion until that name is
requested, preserves each call's missing-name default and retries after read
failure. Focused fixtures cover duplicate names, zero addresses, malformed
tokens, partial reads and close errors before measurement.

Acceptance requires identical ordered requests/results, an unchanged observed
symbol/module table before, between and after the two arms, exact source/boot
identity, and final idle. These observations cannot establish table stability
between samples or attribute the earlier complete compiler job time.

## Identity and results

The VM ran normal `7.0.0-38-kdlock1`, boot
`1ed38b4b-301c-4c76-a2a1-eb4b9f1bd93e`, pinned to CPU 63. The prior running
verification binds that same boot to Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`; this helper checked the boot UUID
and release again rather than repeating full build verification. It verified
122 source hashes from immutable `/root/kdlock-inputs/shape-4506f6e4`, commit
`4506f6e46394133e439f68a04d6fde38aea0885f`. The production resolver is unchanged
at the parent evidence commit `a46ff2ec9c60bc20d501a55f82d19c7a8dc6aac7`.

| One measured invocation | Original resolver | Helper snapshot |
| --- | ---: | ---: |
| Wall time, seconds | 14.588067001 | 0.256441473 |
| User CPU, seconds | 6.391238 | 0.150246 |
| System CPU, seconds | 8.195089 | 0.106180 |
| Ordered lookups | 138 | 138 |
| Symbol-file opens | 138 | 1 |
| Present / missing requests | 84 / 54 | 84 / 54 |
| Zero-address requests | 0 | 0 |
| Minor / major faults | 4 / 0 | 9,170 / 0 |
| Voluntary / involuntary switches | 0 / 66 | 0 / 2 |

The snapshot was 56.89 times faster for this constructed metadata sequence,
reducing wall time by 98.24% and system CPU by 98.70%. Original system CPU was
56.18% of measured CPU time. This is one original-first pair, with no repeat
variance or uncertainty estimate. Identity reads warmed the table before each
arm; neither arm flushed caches. Imports, source checks, semantic fixtures and
identity reads were outside the measured intervals. Both arms included one
counter per symbol-file open and one record per requested name, with no
per-line instrumentation or profiler hooks.

The 138 requests comprise:

| Request group | Total | Present | Missing |
| --- | ---: | ---: | ---: |
| Controls | 2 | 2 | 0 |
| Scalar hostcalls | 3 | 2 | 1 |
| Manifest terminals | 98 | 76 | 22 |
| Aliases, services and per-CPU helper | 35 | 4 | 31 |

There were 133 unique requested names: 82 present and 51 missing. Five names
were each requested twice: `_raw_spin_lock`, `_raw_spin_unlock`,
`kd_api_pipe_unlock_clobber`, `kd_rwsem_down_write_clobber_v1` and
`kd_rwsem_up_write_clobber_v1`. Reusing results for those repeats alone would
still leave 133 separate scans. The measured prototype instead replaces all
per-name scans with one table pass plus dictionary lookups.

The table contained 264,794 lines and 12,311,030 bytes, producing 251,106 first
name entries in the snapshot. Its SHA256 and the loaded-module SHA256 matched
at all three observations. All 138 ordered name/default/address records were
identical. Duplicate first-match, missing defaults, zero distinction, deferred
integer conversion, malformed-token, partial-read, close-error and retry
fixtures passed in the VM. Errors were not cached for later calls. No symbol
addresses were executed or retained in a production cache.

Process peak RSS increased from 35,456 to 71,808 KiB during the snapshot arm,
an increase of 35.5 MiB. `ru_maxrss` is a cumulative process high-water mark;
these values are not the retained dictionary's exact allocation size. Snapshot
construction accounts for its observed allocation faults and is included in
its wall and CPU times.

## Interpretation and limits

`get_kernel_symbol()` opens and iterates `/proc/kallsyms` on every call, returning
the first matching third token. An absent name takes the full-table path.
The measured combination of 138 opens, 54 absent-name requests and substantial
system CPU demonstrates a large repeated-scan cost independently of generated
code or application execution. This is global symbol metadata enumeration,
not whole-kernel control-flow analysis.

The normal kernel has no loaded KD provider, so many control/service names are
absent and two fallback aliases add lookups. The old learning campaign used a
different enabled kernel, loaded provider and source/runtime context. Do not
subtract this 14.33-second difference from those compiler jobs or extrapolate
it into mmap1 throughput. This experiment does not time source decoding,
lowering, code generation, publication, or a successful complete compiler run.

The candidate for a later production change is a fresh resolver snapshot per
translation invocation, scoped to the existing source/runtime lifetime. It
must preserve the tested first-match/default/error behavior and must never
reuse addresses across module/source sessions. That change has not been made.
Warning-frontier and per-lock child-image work remain separate.

Final idle passed on the same normal boot, without modules, images, workloads
or a reboot. `master` is unchanged. `result.json` is the original guest output;
`helper-as-run.py`, `controller.py`, the request and normal verification receipt
retain the exact inputs. `sha256.json` binds this evidence set.
