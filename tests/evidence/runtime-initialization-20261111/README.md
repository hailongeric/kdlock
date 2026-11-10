# Failed runtime initialization, local 2026-11-11

**Result: FAILED during module initialization, before fixture workers, managed
source tasks, generated images or source/JIT bodies were reached.** This is not a
returned body, successful runtime lane, drain test or performance result. The
attempt ran 2026-11-10 16:00:58-59 UTC, which is 2026-11-11 00:00:58-59 Asia/Shanghai;
the directory uses that local date.

## Exact attempted identities and failure

[The controller command](controller/command.json) requested four workers, eight
iterations and a 120-second bound. Those are requested settings, not observed
worker execution. Its inputs were:

| Input | Exact identity |
| --- | --- |
| Host compiler/runner snapshot | 9d06c4510d2f4c8f991187717671e813969e9961 |
| Module source snapshot | 15a257c00f976fa1e598cd7df53ab7bc2d74ee2d |
| Module SHA256 | 7b5baba594c6bb781dca30ea7b52bb685abc59e34f8a6d8bc419c0d2dab2511b |
| Kernel code overlay | 950ee6fc494af2db129911b57f567ac4c5e5d3b6 |
| Running kernel | 7.0.0-38-kdrebuild1 |
| Boot ID | 91f48b75-2d02-4de1-81cf-f99902f6e3c7 |
| Running BuildID | f34c6d56a0f0545790efd04c566dc390cae8d2ae |
| Kernel ELF SHA256 | 466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9 |
| Kernel config SHA256 | 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483 |

The existing [candidate boot record](../kernel-install-20261110/README.md)
establishes those kernel/GS inputs, not source execution. The saved
[runner identity](runner-output/identity.json) records `status: incomplete`, empty
`cases`, source spans 833/116 bytes and `returned_full_jit_body: not_established`.
Those spans are static module metadata, not executed coverage.

[The outer controller result](controller/result.json) returned 1 in
1.1934451659999468 seconds, ending 16:00:59.450511 UTC. The complete
[exception output](controller/stdout.log) retains the actual insmod arguments and
`Cannot allocate memory` error. The exception occurred at runner initialization
before its protected workflow/receipt block. The runner directory contains only
identity and disassembly; no runner final result was fabricated afterward. The
outer controller result is the actual failed-command receipt. Exact copied paths,
byte counts and SHA256 are in [the receipt index](guest-receipt-index.json) and
[copy index](copied-files.json).

## Allocation warning and source/layout attribution

[The complete saved kernel log](diagnostics/dmesg.txt) preserves the warning and
all surrounding output. It reports `__alloc_frozen_pages_noprof` at
`mm/page_alloc.c:5234`, with `kd_jit_runtime_create+0x2e8/0x7f0` called from
`fixture_init`. The recorded order argument is 12. The retained controller
[addr2line result](diagnostics/allocation-site.txt), command return 0, resolves
that call to `kernel/runtime.c:375`, the `runtime->items` kcalloc in the exact
[950ee6fc source](source/runtime-950ee6fc.c.txt).

The fixture supplies cycle capacity 32 and claim capacity 4096. The source
allocates three item banks: 32 * 4096 * 3 = 393,216 items. The actual
[pahole output](diagnostics/item-layout.txt), command return 0, reports a 24-byte
`kd_jit_feedback_claim_item`. The requested payload is therefore 9,437,184 bytes
(9 MiB), requiring an order-12 (16 MiB) buddy allocation with 4 KiB base pages.
The [target source excerpt](allocation-limit-source.json) records the
`order > MAX_PAGE_ORDER` warning/NULL return and the default maximum order 10.
The exact [retained config](../kernel-core-20261110/config-after), SHA256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`,
defines no ARCH_FORCE_MAX_ORDER override.
The exact [calculation inputs](allocation-calculation.json) distinguish object
payload size from rounded physical-allocation size. No allocator probe was run
by this collector.

This is an unsupported contiguous allocation size for the old cold allocator,
not evidence that reducing caller capacity is the correct fix. The later
[diagnostic memory dump](diagnostics/memory.txt) reports MemAvailable
23,735,868 KiB at the diagnostic capture, not a simultaneous failure-time sample.
Free memory does not make an above-maximum order acceptable. The complete buddy
information is retained separately. The corrective cold bulk allocation change
and a rebuilt kernel require their own source/build/initialization evidence;
this failed attempt is preserved unchanged and establishes no successful fix.

## Initialization unwind, absence observations and taint

[The saved diagnostic summary](diagnostics/summary.json), captured 16:13:45 UTC,
records `module_absent: true`, both fixture device paths absent and taint 12800.
The complete observed module list remains [in the record](diagnostics/modules.txt).
The warning log's module list includes the module while it was initializing;
that is distinct from the later absence observation and has not been removed.
Taint 12800 contains the warning, out-of-tree and unsigned-module bits. The prior
postboot proof's taint 0 remains a separate earlier observation; this record does
not silently reset or discard the warning state.

[The exact module source](source/runtime_fixture-15a257c0.c.txt) calls runtime
creation before registering the fixture control device. A creation failure
returns through its private cleanup path. Worker start and managed source entry
are later control operations, and the runner stopped at insmod before them.
Together with empty cases and the actual failure path, this attributes the
attempt to initialization rather than local/proxy/JIT body execution. The saved
absence/unwind observations are not a general proof that arbitrary admitted
source users drained; no timeout or estimated count is used as such proof.
No forced unload, fabricated unlock or body-result receipt was used.

## Retained old binary and return to normal kernel

Before updating the isolated output, the controller retained the old ELF,
public build metadata and 64 package source inputs on the guest under
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/receipts/retained-kdrebuild1-950ee6fc`.
The copied [manifest](retained-v1-artifacts.json) records
`V1_ARTIFACTS_RETAINED`, module absence and installed boot files unchanged, with
capture 16:18:20-22 UTC. The old vmlinux is **508,210,904 bytes**, SHA256
`466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9`.
That binary and module payloads are not duplicated into this evidence directory;
its exact guest path, hashes, source/public metadata and source snapshots remain
available independently of the later rebuilt output.

The controller reports an ordinary reboot back to the pinned normal default.
[The actual reconnect trace](return-normal-reconnect.json) observes
`7.0.0-38-kdlock1`, new boot `5dde9006-ad3c-44eb-81ed-213cd003f31c` and taint 0
at 16:21:00 UTC. This is a fresh boot, not an in-place taint reset or an admitted
runtime drain test. The failed candidate's installed payload and failure record
remain preserved; the new build can proceed while that candidate is offline.

## Evidence limits

The collector performed only guest reads/SCP and source-host metadata/source
copy/hash work. Existing controller diagnostics include addr2line and pahole;
they were copied rather than rerun. No guest build, module load/unload, allocator
probe, boot mutation or source/JIT execution was dispatched by the collector.
No complete mutex lane, T01-T56 acceptance or performance pass follows from
this failed initialization. Previous focused checks and candidate boot evidence
keep their original identities and limits; they are not pooled into a body pass.

Raw kernel/tool output and exact old source retain their original formatting and
hashes. Prose/JSON whitespace checks are separate from raw-output whitespace;
no warning, exception or ownership/lifetime check was removed to hide the failure.
