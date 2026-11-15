# Kernel16 spin preparation and retained evidence

This local branch starts at 7338197a587fd84110fe710be63abafde270c02b. It preserves benchmark-session work separately from the maintained implementation checkout and from the unrelated master worktree. Nothing here establishes support for a later source layout.

## Preserved code

- Earlier paired Native/KD Nano source preparation: bench/nano, workload_modules/nano and tests/test_nano_spin.py. This is the original isolated patch, SHA256 5c3b54b4c2c0a77075f08f79b877738407a18a12fccce7f10ed65f8114110b2e. Its historical focused checks report39 passes,0 failures and0 skips. It was not built or run in a kernel.
- The later requested minimal fixture: tests/kernel/spin_simple/payload/kd_spin_simple.c and Makefile. Its README explains why this pinned API also requires exported task/runtime provisioning. The fixture is a source candidate, not a runnable validated module.
- The fixture checker has only path changes for this worktree. Original checker, logs and result files remain under fixture/. These original records use the original scratch paths; they were not relabeled as new test execution.

## Validation boundaries

The fixture's four historical offline checks passed: mocked Linux/runtime C syntax; preprocessing of real pinned spin entry macros; source export/layout inspection; and all88 packaged KD files matching kernel16's receipt. The later read-only Module.symvers check found all11 source-expected KD exports with CRCs and no missing entries. The exact Module.symvers hash is de0efc1f0aedfe4b2f48fe2d01a4fa6dfa9082b9af71ed572f8844f5ac8781b8.

These are not emitted-module import/CRC verification, a kernel module build, a signature/admission pass, runtime exclusion/progress evidence or throughput evidence. GCC15 and exact prepared kernel16 inputs remained inside the stopped source guest at the latest inspection. No new toolchain environment was created. Full ELF identity matches recorded GNU Build ID40d0694cb395dfcc98f8275d033b96797d2e5cb2, release7.0.0-38-kdrebuild16.

The three preflight directories preserve both the earlier local missing-input finding and the later successful read-only source-disk hash/package inspection. The failed initial cc1-path lookup is retained, alongside its later correction. Do not replace those chronological records with a fabricated successful build.

Finalization checks: original fixture manifest matches; actual source files and archived records match their original hashes; Nano changed files match the isolated source lane; checker path changes pass Python AST and destination inspection; git diff whitespace review. No build, test-suite rerun, VM operation, module load or recovery test occurred during finalization.

## Scratch retention and cleanup boundary

Original scratch inputs remain at /tmp/kdlock-spin-simple-7338197a-20261114 and /tmp/kdlock-spin-nano-source-7338197a-20261114, plus the three recorded preflight directories. The Nano base/source exports are still named dependencies of prior checkers and other handoffs. They are not newly created backups. The original fixture README, generated mock include tree, Nano edit helpers and other scratch-only files have not all been archived here or established disposable. No unique scratch content was deleted. Deleting these trees needs a separate exact inventory/dependency disposition; a clean committed worktree is not proof that all external scratch files may be removed.

The unrelated master edits, source VM, migrated VM, recovery profile and kdlock-main checkout remain untouched. This branch is local only; no push or merge is part of this preservation.

Whitespace review retained the original preprocessor log trailing spaces and package-list final blank line as byte-exact evidence. Source and maintained documentation pass the scoped whitespace check. The full staged diff reports those preserved evidence-only diagnostics.
