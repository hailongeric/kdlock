# Native API revision: development and validation

This record covers the revision that removes `strcmp` and `strscpy_pad`
helper-specific checks. It starts from the historical `c79d84f` baseline but
has its own frozen candidates. Candidate numbers identify successive source
snapshots; a later correction does not turn an earlier failed check into a pass.
Candidate 6 passed the focused unit coverage and final live acceptance for
read-only taskname, all eight xattr controls and three provider probes. Its
20% mutation controls passed correctness with zero KD JIT entries/completions;
that is not mutation delegation acceptance. Earlier failures remain recorded
below. The full performance matrix remains pending; the historical baseline
does not establish this revision's performance.

## Candidate 1

The VM dependency check, provider build and daemon build passed. The focused
unit batch ran 20 selected programs/drivers, including the two basic C programs:
**16 passed and four failed**. This is a failed batch, not a full-suite pass.
The new CALL-alias driver passed all 16 cases. Here, CALL-alias analysis tracks
whether an ordinary memory access could overlap the return-address bytes
written by a source CALL instruction.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate1-checks/source`.
The copied `v10-candidate1-units.log` has SHA-256
`42840e893dc3715bf60348b51bc546695ae1d8ff4acf41e722b39334f97428f6`.
The complete build logs, source manifest and command receipts are retained in
`checks.tar.gz` in the [archive described below](#preserved-evidence).

Selected passing evidence from the unit log:

| Check | Recorded outcome |
| --- | --- |
| Basic CALL protocol | 56 phase/error combinations passed |
| Basic daemon policy | Passed, including intentional child-process and observation failures |
| New CALL-alias analysis | 16 tests passed |
| Provider capability/source-region driver | 36 tests passed |
| Generated-code diagnostics | 13 tests passed |
| Generated-body entry witness | 7 tests passed |
| Production entry/service fixture | 7,828 checks, zero failures |
| Fixture with benchmark completion observation | 8,713 checks, zero failures |
| Image registry fixture | 30,917 checks, zero failures |
| Source-lifetime fixture | 44,719 checks, zero failures |

The entry/service and completion fixtures detected all 42 deliberate mutations
listed in the log. A mutation deliberately breaks one implementation rule so
that the test must fail; detecting it is evidence that the check is meaningful.
The registry and source-lifetime fixtures detected 15 and 19 such mutations
respectively. Immutable mutex and guarded-spin image checks also passed.
These assertion counts are internal to their drivers and are not additional
programs in the 20-program batch.

### Four failed drivers

| Driver | Recorded failures | Diagnosis |
| --- | --- | --- |
| `admission/test_context_memory.py` | 51 tests: three failed assertions and one error | Three existing CALL/return cases were rejected; an old snapshot assertion expected three fields although the state now has a fourth field for CALL-word history. Formatting that mismatch also raised an error. |
| `admission/test_context_policy.py` | 104 tests: two errors | Independent helper-root cases reached an overbroad refusal: `partial CALL-word alias cannot select return control`. |
| `admission/test_context_guards.py` | 42 tests: one failed assertion | A previously valid CALL/return case was refused instead of producing an admitted image. |
| `admission/test_clobber_entry.py` | 30 tests: one failed assertion | The fixture expected the former `kd_entry_SPILL_` analysis identity after the new CALL-alias representation. |

The production regression is excessive refusal around RET, the machine
instruction that consumes a saved return address. A normal return word at an
independently analyzed helper entry must not be confused with a partially
overwritten data value. The correction must retain the source return-target
allowlist and reject a stack pointer constructed from a partial alias. An
allowlist is the set of source continuation addresses that generated return
dispatch can enter. Numeric alternatives from real CALL words and the existing
negative cases must remain represented. The snapshot and identity assertions
also required correction.

## Candidate 2

The focused follow-up passed **all 11 selected programs/drivers**: the two basic
C programs and nine Python drivers. The Python drivers ran 274 tests in total,
including all four previously failing drivers. Candidate 1 remains a failed
batch in this record.

| Python driver | Tests passed |
| --- | ---: |
| `admission/test_call_alias.py` | 16 |
| `admission/test_context_memory.py` | 51 |
| `admission/test_context_policy.py` | 104 |
| `admission/test_context_guards.py` | 43 |
| `admission/test_clobber_entry.py` | 30 |
| `admission/test_address_guards.py` | 7 |
| `admission/test_guard_flags.py` | 10 |
| `admission/test_strcmp_service.py` | 7 |
| `admission/test_strscpy_service.py` | 6 |

The production change is limited to `context_values.py`; the other changes in
this follow-up are tests. An uncertain return word loaded through an ordinary
stack pointer now keeps the complete source return-target allowlist. It does
not invent a balanced CALL/RET relationship or narrow the possible returns.
A stack pointer itself derived from a partial CALL-word alias remains refused.
The added generated-code regression checks allowed and unlisted return values,
including a source byte overwrite: an unlisted target must miss the dispatcher
instead of entering generated code. The outdated state and identity assertions
were corrected without removing their negative cases.

The runtime implementation is unchanged from candidate 1, whose provider/daemon
builds and C runtime fixtures passed. This follow-up did not repeat those builds
or fixtures. It exercised the changed analysis and directly affected admission
checks; it is not a full-suite run.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate2-checks/source`.
The copied `v10-candidate2-units.log` has SHA-256
`ff49e07ec1cbf7c9b2671224919f0389d9f23ad7e8d1abb6ccdc411aa4e30c0f`.

### Live functional checks

The following receipts are from candidate 2 on kernel
`6.1.159-kdclobber2`, boot ID `b65f0205-c8f9-4385-8b13-039cbce243a6`.
The provider reported capability version 10. These are focused correctness and
delegation checks, not the planned 1–60-worker performance comparison.
A generated-body entry counts an attempt; a completion counts a validated return
from that delegated body. A published `NORMAL` image only means translation
and publication succeeded.

The three provider probes each ran four phases of 16 workers × 100,000
operations, or 6,400,000 operations per probe. All phases completed and the
runners accepted their correctness, continuation, publication and drain checks.
The table lists each phase's counter changes, not cumulative totals.

| Probe | Phase | Body entries | Body completions | Native exits |
| --- | --- | ---: | ---: | ---: |
| `strcmp` | Short-string warmup | 420,608 | 420,608 | 0 |
| `strcmp` | Short-string delegation | 1,444,769 | 1,444,769 | 0 |
| `strcmp` | 300-character strings | 1,585,934 | 1,585,934 | 0 |
| `strcmp` | Repeat 300-character strings | 1,587,840 | 1,587,840 | 0 |
| Spin address guard | Cold warmup | 1,153,400 | 1,153,400 | 0 |
| Spin address guard | Cold delegation | 1,510,631 | 1,510,631 | 0 |
| Spin address guard | Trigger guard | 1 | 0 | 1 |
| Spin address guard | After delegation ban | 0 | 0 | 0 |
| Mutex instruction marker | Cold warmup | 1,400,742 | 1,400,742 | 0 |
| Mutex instruction marker | Cold delegation | 1,446,832 | 1,446,832 | 0 |
| Mutex instruction marker | Trigger marker | 1 | 0 | 1 |
| Mutex instruction marker | After delegation ban | 0 | 0 | 0 |

The `strcmp` probe compared valid zero-terminated strings containing 300
characters. They differ at character index 299 (`x` versus `y`), so the expected
result is −1; the short equal strings return zero. The original pointers reached
the original kernel helper, and the complete image-registry record remained
unchanged across all four phases: generation 1 and requirement value 4, which
identifies the read-only string API service. The runner also checked the
published code and its recorded hashes. No native exit occurred for the long
strings. This checks the revised API behavior beyond the former 256-byte scan
limit without reintroducing that scan.

The address guard checks a possible stack-address overlap. Its triggered phase
left generated code before the guarded access, resumed the waiting task in
native code and disabled later delegation for that entry. The mutex marker
similarly left generated code when a marked instruction was actually reached.
Each probe recorded one matching exit event, then no further generated-body
entries after the ban. The mutex probe exercises the existing version 2 entry
interface (ABI2); this revision does not replace that mutex protocol. Source-frame counts were
zero after every phase. Final retirement also recorded zero source modules,
frames and writers.

Receipt paths inside `live.tar.gz`, relative to its
`taskname-xattr-native-contract-20261019/` root, are
`candidate2-live/strcmp/session/session.json`,
`candidate2-live/address-guard/session/session.json` and
`candidate2-live/mutex-marker/session/session.json`.

### Exact taskname workload

The read-only taskname workload passed with Linux Native, TCLock and KD at
16 workers × 200,000 operations: **3,200,000 correct reads per backend**.
KD used the ordinary call shell and recorded **3,192,781 body entries and
3,192,781 completions** in the functional measurement phase. Its preparation
wave separately recorded 3,404,607 matching entries/completions. All three
sessions completed and drained. This exercises normal name copying and zero
padding with the original `strscpy_pad`; it does not test the helper's return
value or actual-kernel truncation behavior.

The 20% mutation control had a different outcome. Linux Native and TCLock each
completed 3,200,000 correct operations: 2,560,000 reads and 640,000 writes.
KD failed preparation with
`helper learning did not establish complete delegation within configured waves`.
All eight KD preparation waves completed correctly, each with 3,840,000
operations: 3,072,000 reads and 768,000 writes. Every worker had zero reported
errors, and the workload's active-worker count and gate were zero after each
wave. Nevertheless, every wave had **zero body entries and zero completions**,
reported as `NO_JIT`. The same published image remained `NORMAL` throughout.
These receipts establish the lack of delegation but not its cause.

KD therefore has **no measurement phase** for this mutation control. Correct
native execution and a published image do not satisfy the delegation check.
The session is retained as `PREPARATION_FAILED`, even though it drained and
retired all source ownership records normally. It is not a measured KD result
and must not be compared with the two successful controls as a performance
score.

The receipts are under `candidate2-live/taskname-read/` and
`candidate2-live/taskname-mutation/` in `live.tar.gz`. The mutation session's
`learning-0.json` through `learning-7.json` retain the individual correctness
and operation-count receipts. The combined live command batch returned failure
because of this preparation failure.

### Xattr refusal and diagnostic repeat

The intended xattr control set was front hit, tail hit, missing name and
size-only query, each at 16 and 128 list entries with 64-byte values and
16 workers. The batch stopped at its first case, the 16-entry front hit.
The other seven cases did not run in this candidate.

The first generated image entered once without completing a delegated body.
Helper learning then reached the original kernel `memcpy` implementation. Its
second translation attempt refused `REP MOVSB` at `0xffffffff81ed94fa` because
analysis had lost the destination-address facts in register RDI. `REP MOVSB`
repeats a byte copy; RDI holds its destination. The diagnostic reported
`kd_wide_RDI` and `memory_default_wide=true`: the analysis could not constrain
that address sufficiently. This is uncertainty in translation, not evidence
that a runtime invalid pointer was observed. The analysis used 3,080 work units
of its 1,000,000-unit limit, so this was not a work-budget exhaustion.

A separate diagnostic rerun with source/analysis capture reproduced the same
instruction, address uncertainty and work count. Both sessions ended
`PREPARATION_FAILED` with `JIT translation refused`, and both drained normally.

| Attempt | Preparation operations eligible for delegation | Body entries | Body completions |
| --- | ---: | ---: | ---: |
| Original front-hit control | 3,267,328 | 1 | 0 |
| Diagnostic repeat | 2,978,304 | 1 | 0 |

The preparation status `PARTIAL_JIT` here records one body entry without a
completion; neither row is a successful delegated measurement. There is
no accepted xattr performance result for this revision.

The original receipt is
`candidate2-xattr/xattr-controls/xattr-front-n16-t16-r0-kdlock/session.json`
in `live.tar.gz`. The repeat is at the corresponding
`candidate2-xattr-trace/xattr-controls/` path in `diagnostic.tar.gz`, together
with `candidate2-xattr-trace-data/` source bytes and analysis records. Neither
archived scripts nor captured code were executed during the host-side audit.

The next analysis change is under development: an explicit contract for the
reviewed C callers that their ordinary data accesses do not observe temporary
CALL return-address storage. That storage remains part of the actual source
CALL/return protocol. The proposed analysis treatment has not yet been
validated and is not included in candidate 2's passing evidence.

## Candidate 3

The focused unit batch ran 12 programs/drivers: two basic C programs and ten
Python drivers. **Eleven passed and one failed.** The Python drivers ran 284
tests: 283 passed and one failed. This remains a failed batch; no candidate 3
live or performance acceptance is recorded here.

The new `admission/test_audited_c_memory.py` driver passed nine of its ten tests.
Its coordinator test,
`test_coordinator_selects_typed_contract_without_pointer_guards`, failed before
reaching the intended analysis path: the fixture supplied the `strcmp` symbol
but omitted the spin clobber lock/unlock entry symbols. Translation correctly
refused with `clobber entry symbols unavailable`, returning status 2 where the
fixture expected status 0. The fixture setup must supply those required symbols;
this result is not evidence that the intended coordinator path passed.

The other nine Python drivers all passed, with the same counts listed for
candidate 2: CALL-alias 16, memory 51, context policy 104, context guards 43,
clobber entry 30, address guards 7, flag proof 10, `strcmp` 7 and `strscpy_pad` 6.
Both basic C programs passed, including the 56 CALL-protocol combinations and
the daemon's intentional error cases. This focused batch does not establish
that the previously refused xattr body can complete delegation.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate3-checks/source`.
The copied `v10-candidate3-units.log` has SHA-256
`6038451ecdb3a59a54405fe1d79310df2db4804e5b42a3dea08ff42a5b4289a2`.
This log is later evidence and is not part of the through-candidate-2 archives
listed below. A corrected fixture and further analysis changes still require
their own validation receipts.

## Candidate 4

The focused unit batch again ran 12 programs/drivers: two basic C programs and
ten Python drivers. **Eleven passed and one failed.** The Python drivers reported
287 test methods in total. The failing `admission/test_audited_c_memory.py`
driver ran 13 methods and reported two errors plus two failed subcases of one
method; these subcases are not additional test methods. The other nine Python
drivers passed all 274 tests, and both basic C programs passed. This is a failed
batch, with no candidate 4 live or performance acceptance.

| Case | Recorded failure |
| --- | --- |
| `test_captured_memcpy_preserves_ordinary_calls_and_all_copy_writes` | RET, the instruction that returns from a function, was treated as an ordinary data observer of temporary return storage and raised `audited C caller explicitly observes temporary CALL control scratch`. |
| `test_plain_ret_keeps_all_targets_across_may_token_joins` | The same observer refusal rejected an ordinary RET after possible return-storage states were joined. |
| `test_captured_graph_needs_actual_typed_api_and_resolved_copy_contract` | Two negative subcases returned translation status 0 instead of the expected refusal status 2: an actual string API call without the copy symbol, and the copy symbol without an actual string API call. |

The negative subcases admitted the tested graph without both declared
prerequisites, so they do not establish the intended restriction to the selected
C caller contract. The RET errors separately show
that normal control flow must not be classified as an ordinary data observer.
Neither failure is hidden by the passing lower-level cases.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate4-checks/source`.
The copied `v10-candidate4-units.log` has SHA-256
`002ef1b39b333d79439167486860d46b651f4a6de1a2ec3f2d5fdc5cba335d39`.
This later log is not part of the through-candidate-2 archives below.

### Archived alias experiment and next scope

The candidate 4 source checkpoint is preserved at commit
`66cccfab511866f095d9fbfb2ed33b909afd1d79` on
`archive/taskname-xattr-candidate4-alias-20261019`. Creating this archive branch
did not move `master`.

The generic CALL-alias mask experiment is no longer selected for the maintained
implementation. It tracked which parts of a loaded value could come from CALL
return-address bytes and which parts remained unknown. The earlier candidate
results above retain that experiment's source identity; its passing unit cases
are not evidence for the replacement.

The next revision removes that generic refinement and restores the conservative
ordinary-CALL memory behavior from `c79d84f`. This restores only the ordinary
alias-analysis behavior, not historical helper checks. The original string APIs
still run without helper-specific checks. The separate reviewed-C-caller rule
remains: temporary CALL return storage is tracked as control state, and the
selected caller promises not to inspect or overwrite it through ordinary data
accesses. Its decoded-copy scope, all copy effects and legitimate RET handling
must pass their own checks. The reworked implementation remains unvalidated;
see the [admission contract](../../../../../docs/design/admission.md#original-call-word-aliases).

### Follow-up diagnosis: the ordinary copy path is already emitted

A later review of the selected source and emitted assembly corrected the scope
interpretation above. The missing `__x86_return_thunk` warning concerned code
outside the selected critical section. It was not a missing return instruction
in the learned `memcpy` body.

The captured `candidate4-copy-False.S`, generated without special `memcpy`
classification, includes the actual `REP MOVSB` byte copy. It reads the source
CALL's return word, advances the logical stack pointer and dispatches through a
return-target allowlist to `0xffffffffc079616c`. An allowlist restricts the
continuation to recorded source addresses. That continuation contains the
terminal clobber unlock and its normal completion checks. Thus the copied body
and its return path were present; they were not omitted to obtain acceptance.

Both `candidate4-source-replay.log` and
`candidate4-source-replay-thunk.log` report status 0 and image requirement 4,
the original `strcmp` service, with the copy instruction present. Each log
records the same result with the optional copy classification disabled and
enabled. This is translation/emission evidence, not a live returned-body or
performance result.

The negative assertions that demanded refusal solely because the optional
`memcpy` classification prerequisites were absent were unjustified. An ordinary
copy that passes the existing analysis does not need such a classification.
The correction is to remove those assertions and retain checks for the actual
copy effects and return path, without relaxing admission policy. The original
candidate 4 batch still failed exactly as recorded above; this diagnosis changes
the interpretation of those subcases, not their receipts or the two RET errors.

This evidence supersedes the provisional decoded-copy plan above. The final
narrow revision will keep the original conservative ordinary-CALL analysis and
separate temporary control words only for the `strcmp` and `strscpy_pad`
services. It will add **no `memcpy` classification and no special RET
extension**. The generic CALL-alias mask experiment remains archived. The new
revision still requires its own unit and live validation.

The copied diagnosis files are under `/tmp/kdlock-taskname-xattr/` on the source
host and are later evidence than the through-candidate-2 archives:

| File | SHA-256 |
| --- | --- |
| `candidate4-source-replay.log` | `b9f93066f683469299bdd25628e3fc619b450ef451d06c068c274c4902030236` |
| `candidate4-source-replay-thunk.log` | `b9f93066f683469299bdd25628e3fc619b450ef451d06c068c274c4902030236` |
| `candidate4-copy-False.S` | `873847d627c605b4c73197c00a05ae3ebfbdbeb331b91bcee88aaa2fc1c38eca` |

## Candidate 5

The frozen simplified implementation keeps separate temporary control words only
for `strcmp` and `strscpy_pad`. Generic partial-CALL-alias machinery is removed;
ordinary CALL/RET analysis remains conservative. There is no `memcpy`
classification or special RET path.

The focused unit batch ran 12 programs/drivers: two basic C programs and ten
Python drivers. **Eleven passed and one failed.** The Python drivers ran 287
tests, with one failed assertion and no skipped tests. All 13 selected-C-caller
tests passed, as did all previously existing affected drivers. The sole failure
was in the revised 16-test conservative CALL-alias driver.

`test_stored_indirect_control_and_stack_reuse_keep_refusal` expected rejection
of `JMP [RBX]` (bytes `ff23`), although the fixture had made the unrelated
register RAX uncertain. The tested instruction did not use the uncertain
address, so that refusal expectation was incorrect. This is a test-operand
error, not a reason to reject an unrelated register or weaken admission. The
candidate 5 batch remains recorded as failed.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate5-checks/source`.
The copied `v10-candidate5-units.log` has SHA-256
`208c27ddb42b1144457ce70defa80883bb73fd6e82efa24189b745cefba433d6`.

## Candidate 6

The only change from candidate 5 was the test operand: `ff23` became `ff20`,
changing `JMP [RBX]` to `JMP [RAX]`. It now exercises the uncertain address that
the fixture actually creates. Production source bytes are identical to
candidate 5; no admission or runtime rule changed.

The rerun passed **all three selected programs/drivers**: both basic C programs
and all 16 conservative CALL-alias regression tests, with no skipped tests.
The basic CALL check again covered 56 phase/error combinations, and the daemon
basic check passed its intentional error cases.

Taken together, candidates 5 and 6 provide passing basic checks and all ten
affected Python drivers for the unchanged production implementation. The final
Python coverage comprises 287 tests: selected-C-caller 13, conservative CALL-alias
16, memory 51, context policy 104, context guards 43, clobber entry 30, address
guards 7, flag proof 10, `strcmp` 7 and `strscpy_pad` 6. This combined outcome
uses candidate 6 for the corrected driver and candidate 5 for the other nine;
it does not relabel the original candidate 5 batch or claim a full-suite run.

The frozen guest source was under
`/mnt/kdlock-builds/taskname-xattr-native-contract-20261019/candidate6-checks/source`.
The copied `v10-candidate6-units.log` has SHA-256
`4e332a3dd21d21225b5d6eee9b118d8b86310187e15dc2f52ae0952ebdc72eb6`.
These unit logs are included in the through-candidate-6 archives described below.
The final live receipts have now been audited. They establish the focused scopes
below, not a standard-grid performance result.

### Final live acceptance

The final command batch returned success and contains **17 new sessions**, all
with `execution_status=OK` and `drained=true`: three provider probes, three
read-only taskname runs, eight KD xattr controls and three taskname mutation
correctness controls. The [batch receipt](candidate6-live-result.json) records
the commands. These sessions use the simplified candidate 5 production code;
candidate 6 changed only the test operand described above.

All three provider probes passed their correctness, continuation, publication
and retirement checks. Each phase used 16 workers × 100,000 operations, giving
1,600,000 operations per phase and 6,400,000 per probe. Counter changes were:

| Probe | Phase | Body entries | Body completions | Native exits |
| --- | --- | ---: | ---: | ---: |
| `strcmp` | `cold-warmup` | 909,937 | 909,937 | 0 |
| `strcmp` | `cold-delegated` | 1,278,605 | 1,278,605 | 0 |
| `strcmp` | `long-delegated` | 1,587,740 | 1,587,740 | 0 |
| `strcmp` | `long-repeat` | 1,586,858 | 1,586,858 | 0 |
| Spin address guard | `cold-warmup` | 1,323,464 | 1,323,464 | 0 |
| Spin address guard | `cold-delegated` | 1,544,308 | 1,544,308 | 0 |
| Spin address guard | `hot-escape` | 1 | 0 | 1 |
| Spin address guard | `post-ban` | 0 | 0 | 0 |
| Mutex instruction marker | `cold-warmup` | 1,404,904 | 1,404,904 | 0 |
| Mutex instruction marker | `cold-delegated` | 1,423,921 | 1,423,921 | 0 |
| Mutex instruction marker | `hot-escape` | 1 | 0 | 1 |
| Mutex instruction marker | `post-ban` | 0 | 0 | 0 |

The `strcmp` probe completed both short equal strings and valid 300-character
strings, whose last character differs and whose comparison returns −1. Its full
image-registry record stayed unchanged through all four phases, with zero guard
exits. The spin guard and mutex marker each recorded one triggered native exit,
then no more generated-body entries after the entry was disabled. Every phase
finished with zero active source frames. Final retirement also reached zero
source modules and writers.

Read-only taskname passed on Linux Native, TCLock and KD at 16 workers × 200,000
operations: **3,200,000 correct reads per backend**. KD recorded **3,192,951
matching body entries and completions** in its functional measurement phase.
The separate preparation wave had 3,446,549 matching entries/completions; those
are not added to the measured count. The ordinary call shell and exact padded
copy remain unchanged. The payload still does not test the helper's return
value or actual-kernel truncation.

All eight KD xattr controls passed at 16 workers, with 64-byte values, correct
syscall results, zero worker errors, matching body-entry/completion counts and
full drain. Each measured control used a one-second target duration; these
focused acceptance runs are not the three-repetition performance matrix.

| Query | List entries | Completed operations | Matching body entries/completions |
| --- | ---: | ---: | ---: |
| front | 16 | 2,373,120 | 2,370,460 |
| front | 128 | 2,388,224 | 2,385,583 |
| tail | 16 | 557,312 | 556,535 |
| tail | 128 | 109,568 | 100,071 |
| miss | 16 | 590,336 | 589,664 |
| miss | 128 | 105,472 | 100,612 |
| size | 16 | 582,656 | 577,368 |
| size | 128 | 105,472 | 100,706 |

Front and tail hits learned the actual copy helper: their initial learning wave
entered once without completing, followed by a complete-delegation wave and a
successful measured phase. These preparation events do not pollute the measured
counts above. Miss and size-only queries required no copied value. The original
list traversal, `strcmp` calls and decoded `memcpy` remain the workload.

The final **20% mutation runs are correctness controls only**. They explicitly
set `helper_waves=0` and `require_jit=false`, allowing measurement without requiring
a returned delegated body. Linux Native, TCLock and KD each completed 3,200,000
correct operations: 2,560,000 reads and 640,000 writes. All drained. KD recorded
zero body entries and zero completions (`NO_JIT`). These runs establish correct
mutation behavior under that configuration; they do not accept mutation
delegation or erase candidate 2's strict preparation failure.

### Image and archive audit

The [captured API-image audit](candidate6-api-images.json) covers ten KD API
sessions: read-only taskname, the mutation correctness control and all eight
xattr cases. Their **14 published images** contain only requirement value 8 for
the padded-copy service or value 4 for the comparison service. None contains an
entry guard or address guard. The [host audit](candidate6-host-audit.json)
independently matched all image hashes, checked their ABI headers and requirement
bytes, inspected the emitted assembly for both guard types, and checked the
corresponding translator logs. This includes the mutation image with zero
execution; publication alone is not completion evidence. The separate guard
probe deliberately exercises guards and is outside this API-image count.

The [final archive manifest](candidate6-archives.json) points to the complete
through-candidate-6 archive set under
`raw/tests/taskname-xattr-native-api-20261019/taskname-xattr-native-contract-through-candidate6-archives/`.
The host audit recomputed all four sizes/hashes, the inventory hash and the health
receipt hash. All matched. It read captured data only; no archived script or
generated code was executed.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 9,091,436 | `31e16d407a4b0c82187a13a3b8dbb3a8958606f640d7c2d58174c997780e1cfb` |
| `live.tar.gz` | 52,703,465 | `fb726513e2b3ff7b63b26e47977f8eb1781601edd0b775c67967bb32e06b78e6` |
| `diagnostic.tar.gz` | 3,556,156 | `1f76339846f018657de9d112ee644996d7876c85f5a0a2776869f300ce238478` |
| `metadata.tar.gz` | 47,191 | `c288e00a566add4e9852f83ceebc05b62c476292498366951888f6240475d57d` |

The [final health receipt](health-through-candidate6.json) has SHA-256
`16c51247e7a55bdb5059ff90110f202516c2f3dcd36f216e8b1514c07bf36b15`.
It retains boot ID `b65f0205-c8f9-4385-8b13-039cbce243a6`, kernel
`6.1.159-kdclobber2`, an idle guest and 28 per-session kernel logs with no recorded
fault matches. All **28 archived live/diagnostic sessions drained**: the 17 new
successful sessions and the 11 earlier attempts, including three preparation
failures. The 13 current KD sessions, and all 20 archived KD sessions, retired
with state 2 and zero source modules, frames and writers. The eight other
sessions are Linux Native/TCLock controls and have no KD retirement record.

The host audit matched all 28 session status/drain/retirement records against the
health receipt. Passing the final focused checks does not relabel earlier failed
batches or establish performance parity, mutation delegation, whole-kernel
replacement or arbitrary caller safety.

## Preserved evidence through candidate 2

The [archive manifest](../../raw/tests/taskname-xattr-native-api-20261019/taskname-xattr-native-contract-through-candidate2-archives/archives.json)
and [input inventory](../../raw/tests/taskname-xattr-native-api-20261019/taskname-xattr-native-contract-through-candidate2-archives/input-inventory.json)
identify the completed attempts through candidate 2. All four copied archive
hashes were independently recomputed on the source host and matched the
manifest. The inventory records file metadata; it is not a claim that every
archived file has an independently verified content hash.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 4,876,076 | `0b5d57c7ad9b05f971ca3b3e9abb3f0190e7b1bd87233d6d9598c1d3ffd34e34` |
| `live.tar.gz` | 26,175,920 | `d9da7cde788b8588040505a0a71edb67e8a7958f513fe9341f10dcf26b695294` |
| `diagnostic.tar.gz` | 3,552,445 | `1cd8a351ed79eea511a4ac3c1724e39bcb613f5f5f4c1329278eb792798d7fd5` |
| `metadata.tar.gz` | 802 | `624880bd9bd166c13470ade50ced18999ffad47467dafda582930143d588f312` |

The health receipt, `health-through-candidate2.json` in `metadata.tar.gz`, has
SHA-256 `7792babf542dd4d9600bf15a7469cbb103eb3280cc4e5dd62960fbc5cd8f45e3`.
It records an idle guest, 381 matching frozen-source files and 11 per-session
kernel logs with no recorded kernel fault matches. All 11 session receipts
record `drained=true`: eight ended `OK` and three ended `PREPARATION_FAILED`.
All seven sessions using KD retired with state 2 and zero source modules,
frames and writers; the four Linux Native/TCLock controls have no KD retirement
record. These health and preservation facts include the failed attempts and
do not convert them into validation passes.
