# Flags-stack lowering: focused VM checks

Branch: `codex/flags-virtual-stack`. Baseline:
`7231ddf0963ff2cc730590c09cc81e7f96f93095`. Final tested source:
`111ac671df1de0d1c036ece2871072c84b08d981`.

Source `PUSHFQ`/`POPFQ` and 16-bit forms now transfer flag words through the
virtual source stack with balanced physical-stack operations. The requested
executor-flags behavior introduces no incoming-flags capture, context comparison,
flag-bit filtering or runtime instruction service. Opcodes `0x9C` and `0x9D`
are removed from the instruction-policy rejection. Other families retain their
existing policy. See the [register contract](../../../../../docs/JIT_REGISTER_ABI.md#source-pushf-and-popf-operations).

All compilation and execution ran in userspace on VM `10.176.26.71`, kernel
`7.0.0-38-kdlock1`, boot `b4c42511-d2fd-4ac7-b6b5-48650aae48b7`, using
`/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3`.
The real recovery snapshot `kdlock-builddisk-clean-20261031` was confirmed in
the host monitor. Each attempt used a new private committed-source archive under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/flags-stack-<commit>-rN`.
The shared source mirror and other candidate inputs were not modified. All
attempts verified their own frozen source remained unchanged. No kernel module,
daemon, benchmark or reboot was used for these checks.

| Attempt / source | Flags-stack fixture | Instruction-policy fixture | JIT diagnostics | Ordinary callee bytes |
| --- | --- | --- | --- | --- |
| r1 / `39e916c8c90a77ced2b1a936b29290ce1a06b1e2` | Import failed before execution | Failed: old POPFQ rejection expectation remained | 13 passed | 6 passed |
| r2 / `97acf02ced98491c86424856b002173643c06d20` | Failed: `66 48 9C` used two bytes while Native used eight | 13 passed | 13 passed | 6 passed |
| r3 / `111ac671df1de0d1c036ece2871072c84b08d981` | 6 passed | 13 passed | 13 passed | 6 passed |

r1 was corrected by initializing the existing translator test import path first
and replacing the obsolete POPFQ refusal assertion with an unchanged instruction
family's refusal assertion. r2 exposed a lowering bug: effective REX.W overrides
66 for these encodings. The final implementation preserves that precedence;
the fixture executes the original PUSHF bytes to measure their physical stack
width and compares the translated virtual width, then executes matching POPF
forms and checks the restored arithmetic flags.

The final 38 tests include actual generated-wrapper execution, virtual stack
contents and deltas, physical stack balance, six arithmetic-flag patterns,
live virtual GPR preservation, nested source CALL/RET, branch dispatch, and
checked-coordinator acceptance. These are userspace lowering results, not kernel
task-context, lock integration, API-equivalence or performance measurements.

Final source-archive SHA256:
`8e2f7ba626fa425c1245042d3de58a339c674404f91a97e704fd717a60e7ee0b`.
The raw attempts, including failures, are retained separately under
`bench/results/10.176.26.71/raw/tests/flags-stack-20261102/r1`, `r2` and `r3`.
[raw-sha256.json](raw-sha256.json) records their exact bytes. Results are not
combined across source versions.
