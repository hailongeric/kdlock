# Focused spin test checks

The designated VM (`7.0.0-38-kdrebuild16`) compiled the production excerpts with
`gcc -std=gnu11 -O2 -Wall -Wextra -Werror` and passed the extractor regression
plus all 18 cases. `build.json` and the per-case JSON files retain actual commands,
input hashes, exit codes and output. The extracted mutex source includes pending
rwsem diagnostic conditionals, with that configuration disabled in this fixture;
these are excerpt checks, not a candidate kernel build.

The first seven evidence-checker regressions passed. The final eight passed after
adding the different-object rejection. Both outputs are retained. The final tar
copy reported a roughly one-second clock skew; tests returned zero. Inputs are
hashed in `inputs.json`. All compilation and test execution occurred in the VM.

The focused live entry point is `tests/kernel/spin/run_spin_batch_fixture.py`.
It has not executed, and its kernel/module has not been built. Running kernel16
is not the spin candidate. No continuous two-foreign-JIT-body runtime result or
performance claim follows from these excerpt and synthetic-checker passes.
The spin candidate remains separate and unmerged.
