# Text-region fixture contract repair

Repair `ca28cbc7043724f088cc17e51f3dd0f28174461f`, on
`codex/mmap-reached-jit`, corrects all 14 failures and the one error retained
by the [provenance check](../provenance-chain-ec9436d6/README.md).
The full corrected driver passes 85 tests. Five directly affected drivers
pass another 61 tests, and both required basic C programs pass. There are no
failed, skipped or unrun checks in this selected unit-check set.

Only `tests/unit/admission/test_text_regions.py` changes in the repair commit.
No production defect was demonstrated by these failures. Production JIT/GS,
native MM bodies, capability/refusal rules, source/read/CFG limits,
publication, acknowledgment, transport and retry code remain unchanged.
Implementation `d7763767` and review/evidence `ef7e11d8` remain ancestors;
all 18 files recorded by the provenance implementation check still match their
recorded hashes. This is checked in [verification.json](verification.json).

## Exact causes and repairs

The earlier candidate and checkpoint-production-overlay runs reported the
same 15 failure/error headings. That comparison alone did not establish that
the fixtures were wrong. This repair also traced the actual reader/decoder
contracts and the commits that changed those contracts.

| Original result | Cause established from source | Repair and retained assertions |
| --- | --- | --- |
| Eight subtest failures in `test_known_versions_never_infer_an_unadvertised_module_arena` | Valid capability results already include `source_frontier_extensions`, `source_frontier_controls` and `source_frontier_direction`; the exact expected dictionary omitted them. | Add all three explicit `False` fields for versions 1--3. Keep full dictionary equality, unknown/invalid packet checks and refusal of old translation providers. |
| One error in `test_returning_calls_require_v14_and_provider_registry` | The mock returned a service declaration for every file, including `service_call_table_state`, which requires three numeric fields. The real paged reader correctly rejected it. | Supply distinct valid state and eight page responses through the actual reader. Check state-before/pages/state-after read order, the same capability FD, descriptor cookie/argument count, lease reset and version refusal. |
| Four retained CFG-profile failures | `f4df7734` introduced separate 32+32 transition budgets and 65 decodes. `ebae17c1b9c57eb6636a7016f5316e6a28ae01f8` deliberately disabled eager callee closure and restored 32 combined transitions/33 decodes, independently of retained-miss runtime support. These fixtures still expected the retired profile. | Assert the current profile, exact combined limit, work class, and retained-miss requirement. Preserve source-only/covered-only 32/33 boundaries and original 32/33-pair stress graphs. Add the complete 16-pair boundary and immediate 17-pair refusal. Keep no-late-read, no-partial-image and no-build-on-refusal checks. |
| One failure in `test_budget_retry_completes_reached_callee_before_emission` | The render helper defaults CALL depth to zero and the fixture supplied only the entry region. It provided neither a learned callee root nor enabled lookahead, so zero callee reads were correct. | Explicitly exercise compact budget planning with the learned root before rendering at depth one. Keep exact 1024/512-byte reads, all prior bytes/roots, fallback selection, complete coverage and actual decoded callee body/literal. Assert ordinary rendering still selects `DEFAULT_WINDOW_POLICY`. |
| One failure in `test_truncated_instruction_fetches_a_complete_compact_extension` | Production extends with the ordinary page-aligned policy even when the supplied cached prefix is compact. Expecting an entry-aligned, roughly 1 KiB extension contradicted the selected policy. | Assert exactly one page-aligned 8192-byte extension for this fixture, full coverage through the pending instruction's 15-byte span, emitted immediate and original root dispatch. |

The affected method names now describe the current contracts. Existing compact
planner utility coverage remains explicit; it does not imply that ordinary
translation selects that policy. The compact fallback diagnostic starts a new
fixture observation so source-site diagnostic coalescing cannot erase its plan.
No production profile was reenabled or limit increased to satisfy a fixture.

## Fresh VM evidence

[checks-result.json](checks-result.json) retains exact commands, test counts,
return codes, log hashes and initial/final guest state.
[source-state.json](source-state.json) binds parent
`ef7e11d806e931a77e9d9be72ebbda917956e21c` and the tested staged patch.
The repaired fixture in `ca28cbc7` matches its tested bytes exactly.

The fresh unit-only ext4 source copy is
`/mnt/kdlock-builds2/kdlock-text-regions-checks-ldn27n76/source`.
Its manifest has 1,082 files and 10,434,266 bytes; SHA256 is
`8537edd6a42450f941fe49b715c89b9fca6d06c1b9faa01ce14b826a594cddee`.
Canonical source, the earlier unit copies and frozen campaign inputs were not
modified. All builds and tests ran in the designated guest with the pinned
Python environment and bytecode output disabled.

| Selected check | Count | Return code |
| --- | ---: | ---: |
| Basic C programs | 2 passed | 0 |
| `admission/test_text_regions.py` | 85 passed | 0 |
| `codegen/test_returning_calls.py` | 21 passed | 0 |
| `codegen/test_direct_call_depth.py` | 4 passed | 0 |
| `codegen/test_source_frontier.py` | 11 passed | 0 |
| `infrastructure/test_compiler_manifest.py` | 12 passed | 0 |
| `bench/test_mmap1_provenance.py` | 13 passed | 0 |

The corrected driver ran in 5.487 seconds. Logs contain no compiler warnings
or errors. Missing dependencies, skips and compile failures were not counted
as passes. The full suite was not selected or run.

Before staging and running, inspection confirmed normal kernel
`7.0.0-38-kdlock1`, boot `6148a091-cca7-4258-8d0b-d75227134564`, no project
module or work process, and sufficient disk space. Final inspection confirmed
the same boot/kernel, no remaining test process/project module, and unchanged
hashes for every frozen input. No reboot or guest configuration change occurred.

## Preserved evidence and remaining limits

The original failed logs, checkpoint overlay, timeout and subsequent registry
check remain unchanged in the earlier report and its raw archive. Their
`checks.tar.gz` SHA256 remains
`8597dfc6365e2b2e31a64cb504d2e7bdb9ed59cb9e89feb6c95f4dc4e2d63005`.
Those executions remain failed evidence; this fresh passing run has separate
inputs and receipts.

New raw files are under
`bench/results/10.176.26.71/raw/tests/text-regions-ef7e11d8/`:
`inputs.tar.gz` retains tested source and the exact repair patch;
`checks.tar.gz` retains all fresh logs, source hashes and guest-state receipts.
[verification.json](verification.json) records archive sizes and hashes.
The isolated guest copies remain available; unrelated work was not removed.

No provider load, campaign launcher, live publication check, deferred learning
application or fixed mmap1 measurement ran. The prior platform restriction is
unresolved. This fixture repair does not establish kernel execution, a loaded
image digest, whole-kernel support or throughput. No push or merge occurred.
