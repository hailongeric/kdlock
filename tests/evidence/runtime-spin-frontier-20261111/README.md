# Spin source-frontier attempt

This attempt returned `failed_or_incomplete` after 122.858 seconds. The first
warm recursive scene timed out waiting for a child request. Protected recursive
spin acceptance remains unmet.

## Identity

- Core source is `2d0ad60b`, fixture source is `0a07f678`, and the spin module SHA256 is `180d36459307576ff3c54b874186a058da710acf9c8c76ba28e5929efffe8b47`.
- The running release was `7.0.0-38-kdrebuild4`, Build ID `f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053`, boot `84e4ba94-b616-4b65-9efe-820921f36c16`. Entry taint was zero and module taint became 12288.
- Five spin roles used CPUs 0–4 and the userspace controller used CPU 5. The holder bound was 10 seconds and each runner operation had a 120-second deadline.

## Observed source frontier

The fixture exported three source regions totaling 5,113 bytes. Four compiler
cycles made three publications, with coverage ACK counts 0, 1, 1 and 0. All
22 wire attempts returned status zero through cached CLAIM_END sequence 21.
The native-local, native-nesting, no-image contended, cold body and warm-plain
counter checks completed before the recursive-scene timeout.

The final read-only buffer contains 4,949 twenty-word records and zero overflow.
The exact scene interval is rows 4827–4948, using zero-based row IDs. At row
4859 C_A selects W. Row 4866 records generated entry with the physical atomic
context flag. Row 4867 records COVERAGE_MISS, SOURCE_UNAVAILABLE and
JUMP_RESOLVED at helper IP `0xffffffffc000b0de`, with target and cursor
`0xffffffff8271be20`. Row 4868 forwards that continuation to W. W then enqueues
B on its own thread at row 4873. The fixture correctly retains `child=0`.

The original module relocation names `__x86_return_thunk`. The running target
is `its_return_thunk`, confirmed independently in the actual kernel ELF and
System.map. Its exact symbol span is two bytes, `c3 cc`, containing RET and
INT3. The bounded disassembly and source excerpts are retained. These ordinary
bytes were outside the three exported regions.

After the bounded holder timeout all five workers finished. The actual status
has five completed bodies, three helper effects, A=2, B=1 and clear physical
locks. It retains one worker error, zero pin errors, zero origin errors and
zero core errors. All five scene workers were parked. The captured dmesg has
the expected out-of-tree/unsigned module taint and no kernel BUG/WARN.

`scene1-diagnosis.json` and `scene-correlation.json` join the exact scene rows.
The older captured `scene1-rows.json` also contains historical rows with reused
task-pointer values, so its contents require the scene interval above.

## Follow-up and retained state

Reviewed commit `db7d7d6e` adds an optional caller-supplied built-in source span
to the fixture. The runner compares actual exported bytes with the pinned
executable kernel ELF before compilation. The next invocation supplies
`0xffffffff8271be20` with length 2. The existing compiler handles that ordinary
source span. The correction awaits module rebuilding and live verification.

Automatic approval review rejected execution of the reviewed recovery helper.
Its stated reason was missing trusted user authorization in the child
transcript for root feedback settlement and module unload. The rejection
occurred before SSH dispatch. Explicit user confirmation is pending. Runtime
controls, the published image and five parked workers remain retained.
The mutex regression and operational return remain pending.

## Retained files

The initial guest copy index independently verified 182 files, totaling
4,398,169 bytes. The complete runtime, wire, GNU construction, raw observation,
status and source records are retained under `captured/`. Supplemental exact
symbol evidence and source-host scene correlations have their own hashes.
`controller/` retains the exact live controller, reviewed recovery helpers and
approval rejection. `source/` identifies the immutable 103-file fixture snapshot.
`copy-index.json` and `SHA256SUMS` cover the retained local bytes.

The staged whitespace check reports 198 diagnostics across five raw capture
files, listed in `raw-whitespace-check.json`. Their captured bytes are retained.
Maintained prose and controller source have a separate clean whitespace check.
