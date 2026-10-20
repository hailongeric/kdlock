# Public mutex comparison harness validation

The VM basic tests and directly affected synthetic caller, real API plan/report,
and comparison driver checks passed. See `checks-1/results.json`. After the
executable-copy correction, all seven comparison driver tests passed again in
`checks-2/comparison.log`, including compilation of an executable and relocatable
object in the VM.

The first preparation built all seven groups, then stopped before loading
modules because archived executable copies had mode 0644. Its failure is retained
in `prepare-console.log`. The correction validates the ELF architecture and
executable type and adds owner execute permission only to new, hash-verified
evidence copies. It does not change the archived inputs or executable bytes.

The second preparation completed all seven groups. Its fresh public KD, Native
and TCLock builds and copied pre-unification KD OUTER inputs are frozen under
`/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2`.
`round-r2/prepare-commands.json` records every build command and exit status.
`round-r2/harness-inputs.json` identifies the tested collection source.

All 16 smoke sessions completed with correct business results, worker progress,
CPU placement and drain: c01 and pipebytes, one and eight workers, four arms.
The report accepted all 16 records. Their compact receipts are under
`round-r2/smoke`; full per-session evidence remains in the VM round above.
`host-smoke-before.json` records the actual recovery snapshot and host placement.
The unmodified aggregate records are also retained locally under
`bench/results/10.176.26.71/raw/tests/mutex-api-compare-harness-20261020/smoke-records.json`
with SHA-256
`85975f692bd3f7f162fd3474cdb37b3408707a8fb8950020c6a5a8a2114e0aee`.

These are harness and functional checks, not the three-repeat performance gate.
The report separates source identities, caller shells and JIT execution classes.
Synthetic entry witnesses do not prove a returned JIT body. Individual operation
latency is not measured, so p95 and overall performance acceptance remain open.
The kernel was not modified or rebooted.
