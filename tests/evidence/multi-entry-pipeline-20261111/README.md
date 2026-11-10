# Multi-entry pipeline checks, 2026-11-11

The initial focused run passed **4 multi-entry tests and 12 runtime-pipeline
tests**, then failed its GS setup with **zero GS tests run**. Its aggregate
result remains `failed_or_incomplete`. A separate GS-only follow-up corrected
the retained ELF hash pin and passed **5 tests**. The earlier 4 and 12 tests
were not rerun; these receipts are separate results, not an initial 21-test
aggregate pass.

| Attempt | Actual result | Receipt |
| --- | --- | --- |
| Initial multi-entry check | 4 tests, return 0, no skips | [log](vm/receipts/check-1.log) |
| Initial runtime-pipeline check | 12 tests, return 0, no skips | [log](vm/receipts/check-2.log) |
| Initial GS check | Setup error, 0 tests, return 1 | [log](vm/receipts/check-3.log) |
| GS-only follow-up | 5 tests, return 0, no skips | [log](vm/gs-kernel2-followup/unittest.log) |

The initial [aggregate result](vm/receipts/result.json),
[partial result](vm/receipts/partial-result.json),
[complete controller output](vm/controller-output.log) and
[controller source](vm/kdlock-main-focused3-controller.py) are unedited. The
controller returns 1 for this aggregate failure. The
[follow-up result](vm/gs-kernel2-followup/result.json) records its own return 0
and does not replace the failed aggregate.

The later [receipt reconciliation](vm/receipt-reconciliation.json), at
17:59:45 UTC, returned 0 after verifying the existing 4/12 and separate 5-test
receipts and unchanged source. It ran no tests. Its
`EXACT_RECEIPT_RECONCILIATION_COMPLETE` status does not change the initial
aggregate's failure. Its SHA256 is
`03a1b0897de0709c537808e6c2f4917f52a5c427a3162b53e09f0529bdc51910`.

## Exact source and environment

All checks used committed source
`18c8f2e499d5fb74972e92bad5748489b921035d`, including the multi-entry correction.
The [source state](vm/source-state.json) records a clean `main` worktree at
capture, 106 files and a 1,300,480-byte archive with SHA256
`761de7017fa8da3716adedf7f7afe9aa27dd0ae79dd7a650e3b14130326f2928`.
The initial controller verified all 106 files before and after; the GS follow-up
again verified all 106 against the same [manifest](vm/source-manifest.json).
The archive and extracted source remain in the VM and are not duplicated here.

The run root is
`/mnt/kdlock-builds/kdlock-main-work/focused3-18c8f2e4-01a1bc4f`.
The initial checks ran at 2026-11-10 17:54:24–17:54:26 UTC, and the GS-only
follow-up began at 17:56:35 UTC (November 11 local date). The recorded kernel is
`7.0.0-38-kdrebuild2`, boot `dea66234-7f70-4e5b-acb6-40a6f2884919`, with taint
12288 unchanged. Initial before/after module and activity snapshots are retained
in the command/result receipts; no fixture module was loaded by these checks.

The [exact selected filenames and counts](vm/test-patterns.json),
[argv/environment](vm/receipts/command.json),
[pipeline configuration](vm/receipts/pipeline-config.json) and
[preparation receipt](vm/preparation.json) are retained. The controller imposes
a 180-second bound per command and accepts only return 0, the exact positive
test count, standalone `OK` and no skips. Test dependencies/configuration are
required; missing inputs are failures. The
[source-host archive preparation helper](sourcehost/kdlock-main-prepare-focused3.py.txt)
was copied without execution by this collector. Its original bytes and the
source-host/VM controller match are recorded in [collection.json](collection.json).

## Initial GS failure and separate correction

The initial [GS configuration](vm/receipts/gs-config.json) names the shared
kernel build path but still pins kernel 1's old ELF SHA256
`466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9`.
That path now contains kernel 2's ELF. The test refused it in `setUpClass` with
`ValueError: actual retained target input differs: vmlinux`; no GS case ran.
This is a failed input-identity check, not a GS lowering pass or failure result.

The separate [GS follow-up configuration](vm/gs-kernel2-followup/gs-config.json)
pins the actual kernel 2 ELF SHA256
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`.
Its System.map SHA256 is
`47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f`, and its
config SHA256 is
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The [actual kernel 2 witness](vm/gs-kernel2-followup/actual-kernel2-witness.txt)
retains bytes `65 48 8b 05 fd 08 f0 02` at `0xffffffff8150e713`, addressing the
full linked `current_task` alias `0xffffffff8440f018`. The other affected cases
check nearby/address-width/LEA distinctions and the original direct GS form;
derived cases are not additional hardware execution evidence.

## What these checks establish

The four new tests use the retained 949-byte live2 source fixture and its six
post-operation entries through the actual learning/compiler/lowerer/exporter.
They retain the single-root rejection, shared discovery-resource boundaries and
the rule that an independently entered RET does not prove an unknown callee
returns. The 12 pipeline cases exercise the existing finite compiler/feedback
path, including a real GNU assemble/link/extract operation. The five later GS
cases decode and lower actual or explicitly derived instruction bytes.

These are offline VM mechanism checks. They execute no generated machine code,
kernel JIT image, lock body, module load, publication/ACK or timing workload.
They establish neither returned JIT-body completion nor real-world API,
performance or complete acceptance coverage. The earlier
[live2 compilation failure](../runtime-compilation-20261111/README.md) and its
[exact recovery](../runtime-recovery-20261111/README.md) remain separate evidence.

## Copy integrity

[copied-files.json](copied-files.json) maps each retained raw file to its original
path, size and SHA256. The [VM copy manifest](vm-copy-manifest.json) was computed
by read-only saved-file reads and matched the initial 19 copied VM files
(231,443 bytes) on the source host. The later reconciliation copy was checked
separately against its actual VM SHA256 and the two result hashes it names.
`SHA256SUMS` covers every retained file except itself.
No project import, test, build, parser, module operation or guest-state mutation
was performed to collect this record. GNU scratch/build outputs and bulk kernel
artifacts remain at their original VM paths.

Git's whitespace check reports a final blank line in the raw controller output
and trailing whitespace in the raw objdump witness. Both files retain their
original bytes and hashes; authored metadata and prose have no such diagnostics.
