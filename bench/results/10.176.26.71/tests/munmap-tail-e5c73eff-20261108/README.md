# Joined learned-tail return regression

The single generated-image regression passed on the designated VM's existing
normal boot. It joins the direct outer CALL, learned `JMP RDX`, callback inner
CALL, inner RET, shared RET and outer continuation in one executed synthetic
image. The negative control reaches the specific shared-RET miss; the corrected
image reaches the outer continuation with each source effect occurring once.

Test-only commit: `035546aa79409e9eaa95488e178f2acf6ff389ba`, based on clean
checkpoint `e5c73eff`. Production translator, wrapper and provider sources are
unchanged. The prior checkpoint remains on `codex/mmap-reached-jit`; this work
is isolated on `codex/munmap-tail-fixture`.

## New coverage

The earlier graph fixture covered the full nested motif without execution.
The earlier executed learned-tail fixture had no inner CALL or shared RET.
This method adds their joined generated-code execution; it does not replay
historical g9 or reuse its kernel/module addresses.

The normal decoder/emitter and actual userspace wrapper builder receive one
complete synthetic byte region with five explicit roots. The only learned
input is `0x2002 -> 0x3000` for `JMP RDX`; neither RET receives a seeded history
row. Both variants decode the same 34 source instructions in one pass, have
identical image requirements, and refuse any additional source read. The
control removes only the three learned-tail traversal lines from an isolated
in-memory copy of the actual return collector. No production file or published
image is patched. Each variant builds and executes a separate image.

Both images derive inner match `kd_ij_4022_3011`. Only the corrected image
derives outer/shared-RET match `kd_ij_5001_1014`.

| Observation | Traversal omitted | Corrected traversal |
| --- | --- | --- |
| Inner SP relative to entry | -16 | -16 |
| Simultaneous inner/outer CALL words | `0x3011`, `0x1014` | `0x3011`, `0x1014` |
| SP after inner RET | -8 | -8 |
| Source effects: prefix, callback, inner, callback suffix, outer continuation | `1,1,1,1,0` | `1,1,1,1,1` |
| Wrapper target / source next-PC | `0x1014` / `0x5001` | `0x4444` / `0x102e` |
| Final SP relative to entry | 0, after shared RET pop | +8, after root RET pop |
| Arithmetic flags | `0x890` | `0x890` |

The fixture records both CALL words while the inner call is active, before
either can be overwritten. It checks untouched adjacent stack words, an
unchanged source RAX, and the corrected continuation's SETO/SETS/SETZ results.
Counters use MOV/LEA/store so they preserve the source arithmetic flags.
The corrected image's final exit is deliberately retained miss 15 at root RET
sentinel `0x4444`; success here means the shared RET reached the real outer
continuation, not that a kernel root released a physical lock or returned.

## Exact focused check

Only this command ran, under the pinned interpreter:

```sh
taskset -c 63 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -u \
  /mnt/kdlock-builds2/kdlock-batch-checks-k209ht7m/work/tests/unit/run.py \
  codegen/test_returning_calls.py -v \
  ReturningCallTests.test_learned_tail_nested_call_returns_through_shared_ret
```

The log reports `Ran 1 test`, `OK`, exit zero, with no skips, warnings or
deprecations. The controller independently requires exactly one reported case.
No other unit method, daemon/basic check or provider build was selected. The
test assembles its synthetic source and wrapper through the existing helpers;
it opens no provider device and reads no live kernel source.

Execution stayed on `7.0.0-38-kdlock1`, boot
`6148a091-cca7-4258-8d0b-d75227134564`, in a new isolated ext4 source/work copy.
Initial/final idle, disk, source and original-manifest checks passed. All 1,095
frozen files match the test commit; comparison against `e5c73eff` differs only
in `tests/unit/codegen/test_returning_calls.py`. Existing source receipt roots,
manifest/state identities and the canonical host receipts remained unchanged.
Historical contents under the controller's declared exclusions were not
rehash-verified. No cleanup or recovery-state change occurred.

## Retained evidence and limits

[fixture-source.json](fixture-source.json) records source addresses and the
single learned edge; [fixture-result.json](fixture-result.json) records both
outcomes and exact source, assembly and binary hashes.
[selected-summary.json](selected-summary.json) retains the command and check
status. [source-verification.json](source-verification.json) binds the passing
bytes to the commit and unchanged production source.

The complete synthetic `source.bin`, both `jit.S` outputs, both actual
wrapper-built binaries, controller, frozen inputs, patches and check archive
are retained beneath
`bench/results/10.176.26.71/raw/tests/munmap-tail-e5c73eff-20261108/`.
[artifact-verification.json](artifact-verification.json) records their sizes
and hashes. The original local run is `/tmp/kdlock-batch-checks-0t6t62fb`; its
guest copy is `/mnt/kdlock-builds2/kdlock-batch-checks-k209ht7m`. Independent
offline review verified archive/result equality, the log, six generated-input
and output hashes, both RET tables and the production-source comparison.

Historical g9 still lacks complete original runtime-patched source captures and
attempt-level compiler inputs, so no corrected complete g9 translator build is
claimed. No provider load, kernel-image publication, boot change, mmap1 run or
performance measurement occurred. Dynamic indirect-CALL RET learning, the
32-record policy and all production contracts remain unchanged. The historical
stopped live launch was not attempted; this check supplies no new signal about
its present restriction or clearance status.
