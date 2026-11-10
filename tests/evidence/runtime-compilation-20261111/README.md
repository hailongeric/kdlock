# Runtime compilation attempt, 2026-11-11

Status: **FAILED during first-image host compilation, after native-local and
managed fork/exit checks completed.** No candidate image publication or JIT body
completion is established. The pending control session and loaded module were
retained at this checkpoint; runner return is not a drain/unload result.

The actual attempt ran 2026-11-10 17:22:51.342885–17:22:53.346105 UTC (local date
November 11), returning 1 after 2.0021836379999627 seconds. The exact
[controller command](controller/command.json), [result](controller/result.json)
and [complete traceback](controller/stdout.log) are retained. The observer records
`RETURNED`, not timeout/drain. The runner writes
[failed_or_incomplete](output/result.json), including completed checks and the
original error; [identity.json](output/identity.json) is its earlier incomplete
snapshot, not a contradictory later pass.

## Exact input and kernel identity

The frozen source snapshot is
`/mnt/kdlock-builds/kdlock-main-work/live2-2cc70fce-01a1bc4f/input`.
It uses the actual module SHA256
`378bf139407bf57de1b4d708db3c6548a5d25537219b8ce83c2232c89010267e` on
kernel `7.0.0-38-kdrebuild2`, boot `dea66234-7f70-4e5b-acb6-40a6f2884919`.
The kernel includes cold-allocation correction
`81feb2d749ebbca468c0ab2eb895dcdd82fe519e`; its
[build](../kernel-build2-20261111/README.md) and
[install/boot identity](../kernel-install2-20261111/README.md) are separate records.
The actual kernel ELF SHA256 is
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`,
BuildID `fd2262c047e130787ef669419111eba6eb9ebb2c`, config SHA256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.

The command explicitly supplies immutable-text and auxiliary-stack contracts,
verified full linked GS input `0xffffffff8440f018`, workers 4, iterations 8 and a
120-second runner deadline. The trusted-source/module contract is the selected
one; these declarations do not establish arbitrary code equivalence. Relevant
exact frozen [runner](source/tests/kernel/run_runtime_fixture.py.txt),
[fixture](source/tests/kernel/payload/runtime_fixture.c.txt) and
[lowerer](source/disassem/lowering.py.txt) are copied with hashes. Their `.txt`
suffixes change only evidence filenames. No live module binary is duplicated.

## What actually completed

Module construction and source-provider setup succeeded sufficiently to open the
fixture control, export its actual source and perform these checks. This differs
from [candidate 1's earlier initialization failure](../runtime-initialization-20261111/README.md);
it does not turn that failed attempt into a pass.

- `native-local`: one worker completed all 8 iterations, with completed/calls/A
  each 8, B 0, errors/core_errors/origin_errors 0 and locks_clear 1. The source
  executes the real ordinary lock/unlock pair through the fixture's native path.
  Its recorded label is native body completion, not JIT execution.
- Managed fork/exit: the runner recorded a distinct child own core/native binding,
  child wait status 0, unchanged exact parent root/core/binding before/after the
  child, and a detached parent afterward. The status is
  `child_exited_parent_detached`; no packet content copy is claimed.
- Actual source export: two retained regions, 116 and 833 bytes, with typed source
  operation sites. Raw bytes, metadata and exact disassemblies are retained under
  [output](output/source-metadata.json). The initial exported slot has old image
  identity 0. Ordinary indirect kernel learning remains `unverified`; compiler
  thunk symbols are retained rather than rewritten into an invented success.

These are kernel mechanism checks through a fixture control interface, not
real-world application/system-call validation or the complete T01-T56 matrix.

## First-image failure and retained state

The first compiler cycle retained [its claim reply](output/cycle-1/claim.bin),
then failed in `lower_compilation` → `emission.body()` at the exact frozen
`disassem/lowering.py:383`:

```
ValueError: entry is outside this fragment's canonical source labels
```

The full source stack is retained in the controller output. The failure occurs
while constructing the first candidate, before the runner can write an image,
manifest, commit or ACK receipt. There is no successful compiler-cycle row and
no JIT publication established. `returned_full_jit_body` remains
`not_established`. The later contended-local, nested and out-of-order JIT cases
were not reached. No skip, exception or declaration is counted as passing them.

The recorded controller taint is **12288**, the expected out-of-tree and unsigned
module bits, without the WARN bit present in candidate 1's 12800 failure. A
[later read-only diagnostic](diagnostic/read-only-output.json), timestamped
separately, observes the same boot/release/taint with `kd_runtime_fixture` still
loaded and retains the actual dmesg/module text. It is not an error-time memory
sample, a session query or a proof of drain. No unload, destroy, control mutation
or automatic retry was dispatched by this collector. Exact later ABORT/drain or
unload results must be recorded separately if performed.

## Retention and limits

[The copy index](copied-files.json) binds every copied live controller/output and
relevant frozen source file to raw and retained SHA256/size. The
[guest index](guest-copy-index.json) also indexes the separately retained
postboot copies; it is a copy-time inventory, not a fresh execution snapshot.
The diagnostic command/output hash is retained separately. No project imports,
compilation, tests, module operations or new code execution were performed to
collect this evidence; only saved-file reads/copies and the labelled read-only
kernel diagnostic were used.

The original lowering rejection remains a failure even if a later correction
passes a fresh run. This record establishes native/fork completion and the
specific compilation frontier only. It establishes no successful JIT execution,
full lock replacement, acceptance completion or performance result.
