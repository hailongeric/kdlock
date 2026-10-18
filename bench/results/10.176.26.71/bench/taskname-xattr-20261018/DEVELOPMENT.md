# Development and validation record

This record preserves unsuccessful admission attempts and focused checks for
the taskname/xattr work started from `d87193f`. None of the attempts below is a
performance result. Candidate numbers identify successive working-tree
snapshots; the runner directories contain their exact source hashes and bytes.
Do not combine their results as repetitions of one implementation.

The VM has 64 virtual CPUs on two NUMA nodes, CPUs 0–31 and 32–63. Workers use
the requested CPU prefix and the collector uses CPU 63. The captured kernel is
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The recovery snapshot
`before-mutex-kdonly-20261017T140354Z` was confirmed through the host monitor
before live tests. This is the same selected KD mutex protocol; no mutex queue
or physical-exclusion redesign is part of these changes.

## Admission attempts

| Input | Exact workload | Outcome |
| --- | --- | --- |
| `d87193f` baseline | Xattr tail, 16 attributes, 16 workers | Refused a list-pointer load because the address analysis lost a bounded description of RBX. No completed delegated body. |
| Candidate 1 | Taskname, 8 workers | Defining previously uncaptured helper registers removed the R13 refusal. Expanding `strscpy()` exposed an assertion instruction, `UD2`, on its count-greater-than-INT_MAX branch. No completed delegated body. |
| Candidate 1 | Xattr tail, 16 attributes, 16 workers | Retaining real caller/callee relationships alone did not resolve the list-pointer refusal. |
| Candidate 7 | Taskname, 8 workers | Source-defined count 64 proved three branches unnecessary, including the assertion path. The later address/return analysis still refused the body; the two learning rounds each entered once and completed zero bodies. |
| Candidate 7 | Xattr tail, 16 attributes, 16 workers | Checked list-pointer loads passed their original refusal. Analysis then lost a bounded description of the index in `strcmp()`. One learning round entered once and completed zero bodies. |
| Candidate 7, diagnostic capture | Taskname, 8 workers | Refused again. Captured leased source bytes and analysis states confirmed that the caller-aware retry did run. Earlier warnings had been deduplicated; the final visible ordinary-pass warning was not proof that the retry was skipped. |

All these live attempts completed teardown. A successful publication or entry
into generated code was not counted as a completed delegated body. Original
kernel helpers and workload semantics were retained.

## Focused checks through candidate 7

The candidate 7 address-check probe completed four phases of 16 workers and
100,000 operations per worker:

| Phase | Operations | Generated-body entries | Returned bodies | Checked-address exits |
| --- | ---: | ---: | ---: | ---: |
| Cold preparation | 1,600,000 | 1,187,155 | 1,187,155 | 0 |
| Cold delegation | 1,600,000 | 1,514,636 | 1,514,636 | 0 |
| Stack overlap | 1,600,000 | 1 | 0 | 1 |
| Calls after refusal | 1,600,000 | 0 | 0 | 0 |

The overlapping load resumed on the original waiter before executing the
source instruction. The probe checked the returned value and task identity,
exactly one prefix and suffix per operation, exclusion, permanent refusal of
that entry, source retirement and module unload. It passed. This establishes
the checked-address mechanism, not taskname or xattr acceptance.

Earlier focused test and build failures remain in the archive. They included
an inaccessible publication-gate reference in the first provider build,
outdated fixture expectations after adding an independent image pointer to
each frame, and inadequate incoming-flags examples. The provider and daemon
subsequently built successfully; ordinary assembly warnings are retained in
the logs. The frame size changed from 648 to 656 bytes and the context from
5,208 to 5,272 bytes. Existing padding absorbed that difference in the spin
continuation record, which remains 704 bytes.

A review also found that branch simplification could conceal a flag read in
the original waiter's continuation after an address check. The implementation
therefore refuses to combine actual branch simplification and checked loads in
one image. The original-graph negative case and unsimplified positive case
passed in candidate 7. No flag check was weakened to admit a workload.

Candidate 7 passed seven checked-address admission tests, 23 reader/writer
runner tests and ten syscall plan tests. Earlier passing checks cover the
basic C tests, source lifetime, publication and image binding, malformed exits,
storage geometry, helper-entry register handling, branch constants, source
flags and spin progress. These are directly affected checks, not a full suite.
Fresh checks are required for changes after this candidate.

## Subsequent helper-service work

Candidate 8 adds a narrowly checked call to the original kernel `strcmp()`.
The actual running helper was captured through the provider source lease:
boot-time patching replaced its return jumps with `RET` followed by four trap
padding bytes. Its 42-byte runtime capture has SHA-256
`ae13f1a9c66d699172b99ba37b77dfc935e2c2e99ebcf17dc2284bfbf32cd1bd`.
The captured `memcpy()` also selects the processor's repeated byte-copy path;
the on-disk kernel's alternative code cannot stand in for that live selection.
All capture leases retired with zero outstanding users and the provider unloaded.

The candidate 8 focused check batch passed 12 drivers/programs and failed two.
The string-service Python driver had two fixture assertions that assumed a
particular scratch register and a load requiring an address check; the generated
code used another valid scratch register and an adequate entry check. The C
entry fixture failed compilation because an intentional negative relative
displacement lacked an explicit signed conversion. These are recorded failures,
not passes. Corrections are being validated in the next source snapshot. The
candidate 8 provider and daemon built successfully, retaining their assembly
and locale warnings. No candidate 8 live helper acceptance or timing is claimed.

The taskname replay located its first lost return-stack fact at the word store
inside `strscpy()`: merging two valid frame-relative destination addresses had
discarded their precise identities. A later store then conservatively invalidated
saved return information. Increasing analysis budgets would not establish the
missing address or loop-bound proof. The proposed original `strscpy_pad()`
service instead gives its 64-byte destination an explicit write effect and
checks the exact caller frame and helper implementation before executing it.
Its validation remains separate from the candidate 7 guarded-load probe.

Candidate 9 passed 15 focused drivers/programs and failed one pad-service test
whose coordinator fixture lacked the outer lock symbols. Candidate 9b corrected
that fixture and passed all five pad-service cases. The entry/runtime fixture
passed 8,024 assertions, including its negative mutations. Provider and daemon
builds passed. This does not retroactively turn the earlier failed batches into
passes.

Candidate 9b's live string probe and exact workloads passed their result and
drain checks but failed delegation acceptance: the benchmark completion counter
covered the fast batch path only. It omitted invocations completing through the
general dispatcher after an original helper call. The string probe recorded
1,002,482 entries and zero completions in its second cold phase; taskname recorded
848,144 measured entries and zero completions. Xattr tail n16 learned the actual
kernel copy helper and reached 225,394 entries in its third preparation wave,
still with zero recorded completions. These remain failed acceptance attempts;
neither publication nor successful helper calls alone supplied the missing
completion evidence.

Candidate 10 extends the private observation overlay to count a witnessed root
invocation once after its validated outer unlock, including helper returns.
Native suffixes, errors, nested calls and resumed remote suffixes remain
excluded. The production locking protocol is unchanged. Basic tests, eight
strcmp admission cases, five pad admission cases, the original 8,024-assertion
runtime fixture and the overlay's 8,909-assertion fixture passed. Seven deliberate
completion-accounting mutations each failed as required. The new observer adds
an enabled per-CPU increment on completed dispatcher invocations, so timing
under it must not be pooled with the older observer.

The candidate 10 live string probe passed all four 1,600,000-operation phases.
The cold delegated phase recorded 1,292,047 entries and matching completions.
After switching to valid strings longer than the admitted bound, exactly one
entry returned to the original waiter before calling the helper; it recorded
zero completions. Subsequent calls had zero generated-code entries. Exact
prefix/suffix effects, original-task identity, result, exclusion, retirement and
unload all passed. This is functional evidence, not a throughput measurement.

Candidate 10's taskname read-only check completed 1,600,000 operations with
1,594,587 matching entries/completions. Its 20% mutation case completed correct
data and drained, but returned no delegated bodies and failed the strict JIT
requirement. Xattr tail n16 returned 132,086 complete bodies in its one-second
diagnostic measurement. The n128 preparation exhausted the deliberately limited
three rounds: one entry executed all 128 original comparisons and discovered
the copy helper, then the next published image saw no entry. There were no
service rejections, failures or quota exits. Both xattr sessions drained.

The eight-worker syscall preparation group was the minimum number that could
satisfy the existing queue-depth qualification. Work outside the critical
section could leave too few participants. The comparison therefore uses one
fixed 16-worker preparation group and up to eight rounds for every measured
worker count; it does not change production heat or queue thresholds. Candidate
11 also restores taskname's ordinary direct call shell, removing the now-unused
five-register initialization from the hot path. Its measurements must remain
separate from earlier shells. The mutation acceptance check explicitly disables
the optional entry-ratio filter, separately from the standard timed policy.

Candidate 11's ordinary taskname shell completed 3,200,000 read-only operations
with 3,194,222 matching entries/completions. Native and TCLock read-only controls
also passed. All three 20% mutation cases produced correct results and drained.
KD returned nine complete snapshots during its checked mutation preparation,
but zero during the later 2,560,000-read/640,000-write phase, so that strict
measured-delegation requirement remains failed. Preparation evidence is not
substituted for measured delegation or added to the timing score.

Candidate 11 completed all eight xattr controls at 16 workers. Each returned
the expected syscall result, recorded matching generated-code entry and
completion counts, and retired all sources before normal unload:

| Query | n16 complete bodies | n128 complete bodies |
| --- | ---: | ---: |
| Tail, real 64-byte copy | 133,378 | 18,985 |
| Front, real 64-byte copy | 1,162,941 | 1,175,071 |
| Missing name | 133,084 | 17,985 |
| Tail size without copy | 133,879 | 19,839 |

These one-second controls are correctness evidence and are excluded from the
three-repetition comparison. The n128 tail preparation required two rounds,
with one initial partial entry and then 740,921 complete bodies; its 128
comparisons did not exhaust the separate ordinary-continuation allowance.

The final checked-address probe repeated all four 1,600,000-operation phases.
Its cold phase returned 1,432,107 complete bodies; the aliasing-load phase had
one entry, zero completions and one validated address exit; the post-refusal
phase had no generated-code entries. The original mutex instruction-marker
probe likewise passed, with 1,395,014 cold completions, one checked native exit
and no subsequent entries. Both preserved exact effects, task identity and
drain; the mutex probe also checked arithmetic flags.

The initial ABI3 rwlock c08/80%-write regression produced correct data and
drained, but recorded no generated-code entry and failed strict JIT acceptance.
Its retained heat statistics show that the existing entry-to-queue ratio filter
did not admit execution. This remains separate from an all-writer functional
check with the optional ratio filter disabled; the main timing policy retains
its ordinary limit of two.

The separate all-writer ABI3 check passed: c08 and RCUHT each completed
3,200,000 writes, returning 2,411,562 and 2,461,265 delegated bodies respectively.
The 16-worker rwsem regression used 80% writes and ordinary ratio settings.
Native and KD c08/RCUHT all passed, each checking 320,000 reads and 1,280,000
writes; KD returned 413,784 and 164,848 writers respectively. Every count matched
its completion counter and all sessions drained. These remain functional checks,
not fresh performance results for the accepted rwlock/rwsem implementations.

## Evidence

The local raw archive
`../../raw/tests/taskname-xattr-20261018/exploration-through-candidate7.tar.gz`
contains the complete VM output tree through the diagnostic capture, including
frozen source, binaries, per-session records, build/unit logs, passing probe
receipts and failed admission logs. Its SHA-256 is:

```text
0295d1c08cdb2e32a5efc8baee44030d83022df094f0f340597f7c7f919e8f77
```

Raw evidence is stored outside Git according to the project's result-storage
policy. The final comparison must identify its own frozen source and validation
receipts separately from these exploratory attempts.

The complete follow-up archive, `exploration-through-candidate11.tar.gz` in the
same raw directory, has SHA-256:

```text
e662cb0f7bf9779df5a5ae25bbc98845abeeb5eb6e9c1ea530888bfb15e01569
```

The [independent archive audit](validation-archive-audit.json) verified 1,811
manifest entries, all 39 live-session drains and all 32 KD source retirements.
It retains 13 failed live acceptance attempts, seven failed unit batches and
the first provider-build failure. Relative to committed `c79d84f`, the final
runtime source differs only by the removal of a trailing blank line; other
snapshot differences are documentation. This integrity check neither changes
failed outcomes nor supplies performance evidence. The final benchmark-runner
checks passed 10 API-plan tests, 13 API-report tests and 23 reader/writer-runner
tests. A separate report preflight replayed the eight authentic xattr controls
and rejected diagnostic timing and an altered undrained receipt as main results.
