# Approximate diagnostic cadence: offline validation

After the first live diagnostic stopped on a 504.396027 ms gap, the user clarified
that 500 ms is an approximate target. The correction preserves that nominal
period and the 60-second phase/stimulus list. It treats a scan or start gap above
**five seconds**, the shortest phase window, as substantial observation loss.
Ordinary jitter is retained in the receipt. No benchmark admission rule changes.

The final path also rejects an excessive gap after the last scan and requires
task-observation evidence in every phase. Otherwise a final scheduling stall
could end the loop after successful stimuli without observing the tail.
Identity/access/new-task failures, missing phase evidence, pending-command
deadlines, partial receipts and uncertain completion remain fail-closed. Coarse
sampling cannot exclude short-lived tasks or establish exact causal timing.

**48 focused mocked tests passed in 3.300 seconds** in the recovery VM. Five
fixtures were added to the existing 43-test module; two old exact-period fixtures
were updated for the clarified contract. The additions exercise 6.7 ms scans
plus variable 0/1/3/7 ms oversleep, phase-scale gap/stall boundaries, a final
stall with no later scan, and a missing tail observation despite successful
stimuli. All use virtual time and mocked I/O; no live observer/controller ran.

The first test run is retained as **47 passes and one failure** in 2.977 seconds.
Its missing-phase fixture accidentally also exceeded the five-second gap bound
(5.42 s); the observer correctly refused completion. The fixture now completes
the mock monitor in one step, keeping its extra scan on the nominal grid so
the intended under-five-second missing-tail path is isolated. Production code
was unchanged between these two runs. No failed result is counted as a pass.

Exact command in the final frozen VM source tree:

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  tests/unit/bench/test_mmap_diagnostic.py -v
```

Raw source/patch snapshots and both test/transport receipts are retained at
`bench/results/10.176.26.71/raw/tests/mmap-diagnostic-cadence-20261026/` on 380G10.
`source-3.tar.gz` belongs to the failed fixture run (`checks-1`);
`source-4.tar.gz` belongs to the passing run (`checks-2`). Earlier source-1/2
snapshots were offline drafts, not test runs. Guest evidence is under
`/root/kdlock-evidence/10.176.26.71/tests/mmap-diagnostic-cadence-20261026/`.

The passing snapshot has five files / **94,053 source bytes**, compressed to
**23,422 bytes**, archive SHA-256
`961b2de7ca31ac7ab973e02e63c66e10a85048ca607285f1e3349b432d229ab7`.
Observer SHA-256:
`f1c5c14d6bf91720a04f0251eff0be8158ac5a8e43de3047859883facefd3940`.
Fixture SHA-256:
`661c9f40a3965b08ee0cbf5f1f9c56fd6158fb48c54a5ea9cd5a83b8d275571a`.
Controller, host parser and kdmm31 identity profile retain their `0771ae6` bytes.
The correction and fixtures are committed at
`39ad0be00c1e6120be29fc83710f7a3c1a68f66c`.

Independent read-only review found no material blockers. It matched the final
archive, passing receipt, post-test source hashes and health records, and
checked the separate approximate cadence/loss limit and missing-phase/final-gap
rejections. That reviewer ran no additional tests. The user's separately
authorized corrected live attempt uses these exact reviewed source bytes.

Both runs confirmed unchanged source hashes and before/after recovery health:
`6.1.159-kdclobber2`, boot `d32e2e18-c340-4a98-8105-335bccec0b5d`, exact original
73 modules, taint 12288, no pending boot or detected competing project work.
No source synchronization, build, module operation, reboot or benchmark ran.
The [first failed live receipt](../../bench/mmap-diagnostic-20261026/README.md)
is preserved unchanged in its raw directory and is not reclassified.
