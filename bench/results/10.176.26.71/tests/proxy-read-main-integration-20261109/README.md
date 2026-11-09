# Proxy-read implementation integration into master

The integration combines prior master
`343439f5d433affa2bfe416d12d27cccb9a44f82` with evidence/documentation commit
`2c819210ee9f4e59a12f0291636e19a9167872a9`, including implementation
`adf4d268`, fixture alignment `3ceb7f00` and tested checkpoint `7e3c90b4`.
The merge was prepared in a clean checkout before advancing the actual master
worktree. Exact pre-integration and tested tips are retained by local refs
`archive/master-before-proxy-read-343439f5` and
`archive/proxy-read-tested-7e3c90b4`.

The [completed campaign](../../bench/mmap1-proxy-read-7e3c90b4-v3/README.md)
establishes one compile-excluded, counter-enabled eight-process point at
25,670.9 mmap/munmap pairs per nominal second. Whole-application returns were
398,610 mmap and 398,608 munmap, with zero completed handbacks. Exact retirement,
unload and normal-kernel recovery passed. Its two earlier failed campaigns and
large raw archives remain unchanged and outside Git.

Static comparison checks every retained runtime/tool/runner path against the
frozen tested-source map. All eight incoming runtime files match the tested
candidate exactly. The only runtime differences from that candidate are
`disassem/instruction_policy.py` and `disassem/special_inst.py`; both match prior
master byte-for-byte, preserving independent flags-stack lowering and its REX.W
fix. The completed benchmark did not execute this merged runtime combination.
No new build, unit test or VM campaign was run during integration.

The sole merge conflict was the JIT guide's introductory evidence paragraphs.
Resolution keeps both the new result and master's source-specific validation
boundary, including the historical rate. No runtime file was manually resolved.
Staged whitespace and unresolved-index checks passed. Compact JSON parses,
new report links resolve, all 154 indexed raw files and all 422 evidence members in the archive
match their hashes, and both prior campaign trees remain unchanged. One
pre-existing result-index link to missing `docs/PROJECT_GUIDE.md` remains outside
this change; no new broken link was introduced.

Before advancing master, exact byte hashes and dirty/untracked status confirm
that its AGENTS.md, old disk-cleanup README and independent redesign documents
are preserved. None of those paths is in the merge diff. No unrelated branch
was reset, discarded or overwritten. Nothing was pushed.

[validation.json](validation.json) records the runtime hashes and preservation
checks; [source-review.md](source-review.md), [static-checks.json](static-checks.json)
and [report-checks.json](report-checks.json) retain the independent review, static
Python syntax/JSON checks and report validation. This receipt is included in the merge commit; its identity is available
from Git history without embedding a self-referential commit hash.
