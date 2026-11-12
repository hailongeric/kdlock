# Kernel8 actual mmap/munmap syscall and borrowed JIT prefix

The bounded actual userspace syscall run passed on `7.0.0-38-kdrebuild8`, boot
`2ae5991e-d024-48ac-9f86-24a0a8910172`. Three rounds of eight threads with eight
iterations per thread completed their mapping, unmapping, zero-page, write,
readback, address-reuse and `mincore` checks. The unchanged client returned zero;
all nine ordinary cleanup gates passed, including owner leave, provider
retirement, physical-gate drain, archive/settlement, channel close and module
unload.

This is actual syscall completion plus borrowed execution of the admitted JIT
prefix. Full protected-MM JIT completion remains **false**: the protected-body
completion counts are zero for both roots, and
`meaningful_returned_mm_body="not_established"`. Native MM bodies and surrounding
semantics remain unchanged. The omitted helpers execute natively after exact
handback on the original task. This record makes no performance or measured
physical-batch-chain claim and does not establish arbitrary native-context or
whole-kernel support.

## Execution and exact handback

The raw source-profile evidence contains 247 borrowed JIT entries. Each joins
the original request/grant, generated entry, staged CALL exit, native handback
and eventual request retirement by exact identities. Root-specific raw audit
and the final read-only post-run check are retained separately in this archive.

| Root lock-return site | Borrowed entries | Source CALL | Unexecuted native callee entry |
| --- | ---: | --- | --- |
| `vm_mmap_pgoff`, `0xffffffff817ef5ea` | 144 | `0xffffffff817ef4d3`, `e8e82c0400` | `do_mmap`, `0xffffffff818321c0` |
| `__vm_munmap`, `0xffffffff8185b00e` | 103 | `0xffffffff8185af54`, `e8d7d4ffff` | `do_vmi_munmap`, `0xffffffff81858430` |

Every first exit has phase 2 (`CALL_STAGED`) and detail 1. The source CALL stack
effect has already been applied once; `FORWARD.cursor` is the callee target.
Native continuation starts at that unexecuted callee entry. Describing the CALL
site itself as unexecuted would be incorrect. Producing assembly stages return
addresses `0xffffffff817ef4d8` and `0xffffffff8185af59`; actual `CALL_STAGED`,
cursor and `FORWARD` records agree. The raw stream does not independently sample
post-exit SP or return-word memory, or count individual instructions. The CALL is
not replayed. The admitted source spans only four regions and 1,558 bytes; the
two helper bodies are outside admission.

One image was published across two host cycles. No fact received a coverage
ACK. Shutdown archived and settled all 247 exact pending fact identities. The
merge dispositions are 124 `NON_OBSERVATION` and 123 `CLOSED_EPOCH_LATE`, without
ordinary compiler-observation credit or publication/ACK association. The
final saved profile has 28,743 events without overflow, and 994 physical begins
and ends. Those totals do not measure a physical batch-chain length. The coarse
native snapshot reports `jit_entries=0` and `jit_observation_available=0`; these
unavailable coarse counters do not replace the raw source-profile JIT evidence.

The 192 completed worker iterations include 576 successful worker `mmap` calls
and 384 successful worker `munmap` calls. Each round also reserves and cleans up
an arena; incidental runtime calls and arena operations are outside those worker
totals. Reported round durations are receipt data, not a comparative benchmark.

## Source, configuration and experimental premise

The frozen 143-file source transport is from
`0798c1abf422017cfc93647a2649be0e5a73c75a`, with a clean recorded source status and
1,614,072 source bytes. All 78 kernel-core file hashes match
`0d42063ead37dc8fc1631fa56c8348890ede9c5f`. The full transport, exact manifest,
export receipt, exporter and core package are retained under `source-export/`.

| Input or result | SHA-256 |
| --- | --- |
| Frozen source tar, 1,730,560 bytes | `3b2512060b7eb3cac27b3a794bb5f0dc833c6ff24cd9866218481b53832a8053` |
| Actual host configuration | `c38376355e1b34c5a7dd7c645c8666b8737c201aefe12c31b6d69ba38ba3ec54` |
| Outer supervisor result | `637457c3e5399fc91eac45d11b7bf0fc2407b70c905a4b97ea88fe758c27a89e` |
| Actual runner result | `08d9660d0d81faf2481c63eedacc8d1e382318fc7084e6895e09a2df701e6bb6` |
| Supervisor | `09dc900987cec70b89ea60620ddd07c1493fa6c7dd2b4649201421b33c238ebc` |
| Unchanged runner | `3f36ab1289a6bc8e1601a745d36615d96d4a4bb9600c13d4ce8d99e321744afa` |
| Signed provider module | `5eb94db883a0ddff654eb4dce92afd1c569a3fe7b46bd02b88f275dfcae22e06` |

The ABI2 configuration has flags 511, a 64 KiB declared control requirement,
128 KiB auxiliary storage and a proxy limit of two. The user accepted the normal
16 KiB native-helper stack allowance as an **experimental premise** for this
bounded run. Scheduler/wakeup and IRQ callback footprints remain unmeasured.
The conditional analysis is 44,024 bytes with a 21,512-byte margin within the
declared control requirement. It does not prove the complete auxiliary-stack
requirement. The original conditional artifact retains its false premise/AUX
flags; the separate admission records the user's experimental acceptance.

The [AUX source/compiled review](../kernel8-aux-context-review-20261111/README.md)
and [provider-only frame-reduction build](../kernel8-mm-ioctl-frame-build-20261111/README.md)
remain separate evidence records. Their source/compiled results are not
retroactively described as MM runtime validation. The exact conditional hash
`bdcab02965bc43fb2134e5ef13087a0ecec92ee9fbfaef98ae62b657a8bf35b2` and admission
hash `db233cd8ac3164d3170c071ecc7081c9e58141f93cbf0b147f700dab761f5a1b` bind this
run's declared experimental premise to those records.

## Fresh-boot preparation and preserved failure

The first repeat-boot preflight returned 1 before creating its phase receipt or
dispatching boot-selection changes. Its strict canonical-file check used the
`/lib/modules` alias before resolving the verified `/usr/lib/modules` root.
The failure, original helper `9543da61...`, diagnosis and all source-host controls
remain under `repeatboot/source-host-failed-01/` and
`repeatboot/helper-original-01/`. No namespace byte drift was observed. The
corrected helper `54c5c483...` and successful preflight, boot selection,
reconnection, post-boot GS proof and identity checks remain separate under
`repeatboot/` and `repeatboot-collection/`.

The actual MM launch used the fresh boot and GS proof, fresh runtime metadata
`e503f285...`, and the exact host recovery receipt `5e67b010...`. Before launch,
taint was zero, the provider and test devices were absent, and no workload actor
was active. The completed run retained the same boot, unloaded the provider and
returned to the ordinary NLS-only module state with taint 4096. A final read-only
post-run check and saved-record statistics are retained with the source-host
controls; no second MM run or forced cleanup was performed.

The runner's final kernel-log command preserves its earlier command output as
an exact byte prefix. Its 82-byte delta has SHA-256
`f4a8e80246dde1b460c89d1f2498f428aa92c6ec2df836d8ff9bbccdc266dec0` and contains
only the normal out-of-tree module taint message. The delta contains no
`WARNING`, `BUG`, `Oops`, `Call Trace`, general-protection or panic diagnostic.
The later read-only post-run log preserves eight additional routine audit
messages for `who`. One existing boot emoji is C-escaped in the runner logs and
UTF-8 in that later read; the saved statistics document the normalization used
to compare those representations. All original log bytes remain unchanged.

## Archive contents and verification

`mm-collection/` retains the complete 176-file, 51,325,789-byte guest selection,
its full copy index and transport tar. `repeatboot-collection/` retains the
complete 76-file, 14,869,902-byte selection and its full transport. No duplicate
transport tar was omitted. Exact regular tar membership, member hashes, payload
hashes and zero trailing padding are checked by the standard-library archival
script.

`configuration/actual-03/` is the dispatched configuration. Earlier plan and
geometry/admission directories are retained as preparation history.
`source-host-stage/`, `source-host-run/`, `fresh-recovery/` and
`fresh-runtime-metadata-02/` preserve command bytes, return codes, stderr,
transport metadata and saved receipts. `independent-audit/` contains the separate
read-only raw-evidence audit and its script.

`copy-index.json` records each original file's complete stat identity, raw size
and SHA-256, stored path, encoding, size and SHA-256. Files of at least 64 KiB
are losslessly gzip-compressed except GNU `.o`, `.elf` and `.ko` artifacts, which
remain byte-exact raw files. Every stored file is read back and decompressed
where needed. `audit.json` records transport, provenance and aggregate checks;
`SHA256SUMS` covers every archive file except itself. Archive preparation uses
only offline standard-library reads and copies; it performs no VM operation,
project import, test or build.
