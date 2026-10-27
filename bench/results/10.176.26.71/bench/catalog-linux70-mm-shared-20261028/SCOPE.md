# Shared-MM campaign scope

`catalog-linux70-mm-shared-20261028` selects **42 actual shared-MM points only**:
21 Native-control and 21 KD-local coordinates, with workers 1–8 and 12–60 in
steps of four, one two-second plain round each. All 42 completed normally.
Independent-mmap and private-fault are **not selected**, rather than pending
work in this generation.

The [original private-MM campaign](../catalog-linux70-mm-trusted-20261027/README.md)
retains its 21 independent-mmap and 63 private-fault points on
`7.0.0-38-kdlock1`, with the global MM adapter disabled. Its own 42-point shared
grid was never measured. The present campaign does not change that historical
status or import its 84 timing points. Across the two separate campaign scopes,
all 126 selected MM coordinates are complete; their results are not pooled.

This generation binds 527 source files with source-manifest SHA256
`b9de6aa0bd35100498be794b515ff17756aebeb72d802242c508b71f7725e549`.
The enabled kernel is `7.0.0-38-kdmm1`, Build ID
`ac9ea2ec7f24be8b910547bdfdbfb071176677e6`. Native2 preparation on boot
`1672c452-0346-4703-8215-ddb1cec50915` created the frozen client/payload inputs;
KD2 preparation reused them byte for byte. Both measurement phases use identical
`inputs.json` bytes (SHA256
`075b1d12d21646a802c7eb04805d1d4a5ecd78c9b9f7538837523554f0980ef5`).

| Phase | Boot ID | Scope |
| --- | --- | --- |
| Native2 | `1672c452-0346-4703-8215-ddb1cec50915` | Four correctness prerequisites and preparation |
| KD2 | `f5a6f61b-b1a0-47ed-a2a2-ff73b79a13ac` | Four fresh correctness prerequisites, reused preparation and 21 measurements |
| Native3 | `ddec066b-7a80-4a75-8376-897365e8b848` | Four fresh correctness prerequisites and 21 measurements |

Every phase has a preserved raw archive, source verification and normal-drain
receipt. The [matched offline audit](../../raw/tests/linux70-kdmm1-20261027/shared-matched-comparison-offline-audit.json)
binds both final results and all 42 published rows. Native was higher at all
21 worker counts; these are single-round exploratory observations, without
variance estimates or causal attribution. Strict qualification remains false.
The [earlier mapping failure and diagnostic](../../tests/linux70-kdmm1-20261027/README.md#earlier-mapping-failure-and-separate-diagnostic)
remain separate records and are not rewritten as passes.
