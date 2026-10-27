# Trusted ordinary translation — October 27, 2026

The latest affected VM checks passed: **22 unit drivers, zero failures**.
Five separate MM runner/orchestration drivers passed **34 methods**. The new
read-only taskname live control also passed: **1,600,000 correct reads and
1,592,658 matched JIT entries/completions, with complete drain**. These results
provide no throughput or live MM claim.

Production now trusts all selected kernel and module code. It skips semantic
context, loop/value, alias and entry-input proofs, assuming the compiler
clobber-entry contract. String routines use ordinary decoded code and generated
CALL/RET, with no string-specific service, summary or direct native bridge.
Generated dispatch, block budgets, RET checks and LEA lowering preserve
arithmetic flags. Leased text, supported decoding/lowering, actual CALL words,
return routing and runtime ownership remain required. The earlier checked
analyzer is explicitly selected with `trusted_source=False` in regression tests.

| Attempt | Passed drivers | Failed drivers | Outcome |
| --- | ---: | ---: | --- |
| affected-checks-01 | 20 | 3 | Retained failure: missing fixture clobber symbols and stale string-service expectations |
| affected-checks-02 | 2 | 1 | Retained failure: checked analysis widened the padding-loop destination |
| affected-checks-03 | 22 | 0 | Passed with trusted production routing and explicit checked regression cases |
| MM runner checks | 5 | 0 | Passed; 34 fixture/mocked methods |

The six-method ordinary-byte fixture executes the actual generated userspace
wrapper. It checks finite scans through 64 bytes, nested copy/padding with exact
output and untouched surrounding bytes, zero/truncated cases, and arithmetic
flags across entry, blocks, LEA, CALL and RET. It also verifies that trusted
routing does not select string shortcuts. These are synthetic machine-code
fixtures, not returned kernel JIT bodies.

The second attempt failed at `MOV BYTE PTR [RDI], 0` in the padding loop:
`RDI` widened after 217,470 analysis work units, below its 1,000,000 limit.
That precision problem was not repaired by raising a limit or changing the
source algorithm. The user subsequently required trusting all kernel/module
code without semantic analysis. The superseded edge-analysis candidate and both
failed attempts remain retained; the latest pass has a different policy identity.
Expected negative-fixture errors and Miasm deprecation warnings remain in the
logs and are not omitted from the record.

[evidence.json](evidence.json) binds the retained logs, helper-byte capture,
fresh host preflight and 5,019-file synchronized source manifest. Git HEAD alone
does not identify this working-tree version. The helper-byte capture is
read-only evidence from the final Linux 7 kernel; it is not itself a successful
translation or execution receipt. Later prose edits are outside the tested
snapshot. Detailed inputs are under
[the raw receipt directory](../../raw/tests/ordinary-string-translation-20261027/).

## Live taskname control

| Property | Observed result |
| --- | --- |
| Scope | KD spin taskname, ABI1, 0% writes, 16 workers on CPUs 0–15 |
| Work | 100,000 iterations per worker; 1,600,000 correct reads |
| Returned generated bodies | 1,592,658 entries and 1,592,658 completions (99.54%) |
| Execution / retirement | OK; drained; source state 2 with zero modules, frames and writers |
| Last publication | `publications/02`, 4,277-byte image, requirements 0; identical before/after the functional phase |
| Runtime helper routes | Zero hostcall exits and zero direct string-helper calls |
| Guest identity | `7.0.0-38-kdlock1`; boot `59172bf2-ccd2-49bd-bc1b-fea1d12056a7` |
| Host endpoints | All 64 policies fixed at 2.0 GHz, turbo disabled, pins and recovery snapshot verified |

The final assembly contains decoded `strnlen` at `0xffffffff826c4f80`,
`sized_strscpy` at `0xffffffff826c5650`, and the ITS return thunk at
`0xffffffff826f9e20`. Calls use ordinary virtual CALL/RET lowering. Its assembly
has no string-service or direct-native-call markers, and the runtime counters
confirm neither helper route executed. Three publications are preserved. The
first two learning waves each recorded one partial JIT entry and zero returned
bodies; those preparation observations are separate from the successful
functional phase above.

Offline inspection verified all **282 archived source files**, all **four
binary bindings**, all **23 captured kernel-bundle files**, 94 production and
96 prepared provider files, and all three publication hashes. The 282 source
hashes match the synchronized source manifest. The archive inventory records
581 regular files and two internal source symlinks without extracting or
executing them. Full kernel build/installed artifacts are identified by the
retained successful guest verifier receipt, not duplicated in this archive.
The [verification receipt](../../raw/tests/ordinary-string-translation-20261027/taskname-offline-verification.json)
and [evidence index](evidence.json) bind these observations to exact bytes.

After the run, independent health capture confirmed the same boot, no project
modules and idle workload state; observed taint was 12288. The session kernel
log recorded zero spin/execution invariant failures and no matched kernel fault.
This was an iteration-count functional control. A separate MM kernel build ran
concurrently, so elapsed time is unscored and no throughput comparison is made.
Taskname mutation, other workloads, actual shared-MM runtime and performance
remain separate validation scopes.
