# Rwlock gate-before-context candidate

Runtime source `99b02076dfeb75d978be4eb75d43344ccb2f9049` attempts the native
reader gate CAS before checking interrupt context. The tested tree is
`89aac759c5fc98ad15bb127658c40ddcfe4191a1`, which additionally corrects the
spin IRQ test's source-header path. This candidate remains isolated: correctness
checks passed, but the 24-point nano round does not establish no regression.

The reader first withdraws its speculative count and reserves an exact native
acquisition reference. A successful gate CAS needs no context lookup. A failed
IRQ/BH attempt cancels that reference, restores the reader count and waits only
for actual writer ownership, avoiding a queue behind the interrupted reader.
Ordinary spin composes the same reserve and completion operations as before.

The first unit attempt passed five checks and failed the IRQ driver because it
looked for `typecheck.h` in the separated build tree. The committed driver fix
uses the explicit kernel source path and retains the real header and negative
flags-type check. The corrected six checks passed, as did the live interrupted
reader IPI probe with exact drain. Two subsequent basic preflights stopped
before workloads: an expired host capture, then changed auxiliary QEMU task
identity. Fresh matched captures admitted the final basic run; no reboot or
kernel change was made. Both failures remain preserved.

[Basic spin and rwlock](basic-result.json) each completed 1,600,000 operations
with final idle. Returned JIT counts were 1,596,036 and 22,717. The completed
nano round ran c01/c16, 1%/20% writes, workers 1/8/20/32/36/60, two seconds,
post256 and collector63, once per point. All 24 data/drain checks completed;
JIT status labels match the earlier controls. No real-world API test ran.

Selected whole-run rates in Mops/s; the complete
[24-row comparison](comparison.json) and [raw summaries](nano-results.json)
retain exact rates and commands. c01/c16 mean one/sixteen cachelines.

| Workload | Workers | Rollback `1ad2ef7f` | Gate `89aac759` | Change |
| --- | ---: | ---: | ---: | ---: |
| c01, 1% writes | 8 | 9.800 | 9.335 | -4.75% |
| c01, 1% writes | 20 | 8.746 | 8.557 | -2.16% |
| c01, 1% writes | 36 | 7.341 | 7.555 | +2.91% |
| c01, 1% writes | 60 | 7.308 | 7.560 | +3.44% |
| c16, 1% writes | 8 | 11.115 | 9.889 | -11.03% |
| c16, 1% writes | 36 | 8.350 | 8.220 | -1.55% |

All arms used boot `677b7afa-5358-4ece-a650-5f4a4adecd55` and matching command
arguments apart from output paths. The candidate began 71.2 minutes after its
rollback control. One observation has no repeat variance and does not isolate
source effects from run order/time. The three-round summary criterion explains
`complete=false`; it does not mean the requested one-round execution failed.
Earlier `67361fee` is a performance reference predating the interrupt-reader
fix, not behavior to restore. The gate candidate is not promoted.

The [basic](basic-elf-comparison.json) and [nano](nano-elf-comparison.json) ELF
reviews verified all executable sections, relocations and rewrite metadata of
the respective providers and DIRECT spin payload against their preserved
parents: they match exactly. Timed rwlock writer bodies and entry offsets also
match. Reader bodies retain their uncontended work and have the intended CAS
before context lookup, without added spills. Timed loop and ioctl instruction
sequences are equivalent after resolving local branch/call targets and alignment
padding. Reader branch order and payload placement change; their contribution
to throughput is an inference, not a measured cause. Identical provider code
does not establish equal slowpath invocation frequency.

All three trees, including failed attempts, are preserved in six archives;
hashes and all 3,320 paths were [verified offline](archive-verification.json).
Raw copies are under
`bench/results/10.176.26.71/raw/tests/rwlock-gate-first-20261029/`. Guest roots
are `tests/rwlock-gate-first-20261029`, `tests/rwlock-gate-first-r2-20261029`
and `bench/rwlock-gate-first-20261029` below
`/root/kdlock-evidence/10.176.26.71/`.
