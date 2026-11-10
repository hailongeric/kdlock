# Repeat helper dispatch — prepared, no execution

Helper: `/tmp/kdlock-kdrebuild2-repeat4.py`, SHA256
`236de120d2ecd6c3c96920b7ebb590360d55f91bb35789edb8c2487d00ca1056`.
This supersedes the broader first recipe. No complete-module inventory/signature
scan or old-file protection scan is repeated for the Python-only correction.

Before any invocation, root reviews actual corrected-source Python checks rc0,
completed live3 shutdown/unload, fresh HMP snapshot proof and actual host/guest headroom. Copy
the frozen helper to persistent receipt storage, assert its hash and perform VM
`ast.parse` there before dispatch (source-host review is not a syntax pass).

Create a separate immutable review JSON outside the fresh repeat directory, with
these exact required fields:

- `python_result`: absolute saved actual Python command-result JSON path;
  `python_result_sha256`: its actual hash. It must contain integer returncode0.
  Root separately binds those successful checks to the reviewed corrected frozen
  Python snapshot; this helper does not claim a test's source identity by rc0.
- `runner_ast_result`, `runner_ast_result_sha256`, `module_build_result`,
  `module_build_result_sha256`: actual module3 build-result receipt and pins,
  each with integer returncode0. Both labels may bind the same actual command
  receipt when that command also records runner_ast PASS and 106 verified source
  files; this is one command with two checks, not two executions. Root separately
  asserts source 9f and the 104 common unchanged files before dispatch. Existing
  common 18c 16+5 check receipts remain distinct; no AST or test is rerun solely
  to create a second label.
- `hmp_result`, `hmp_result_sha256`: actual fresh HMP receipt after recovery,
  format utc/status/snapshots/block, real shared snapshot on all three disks.
- `headroom_review`, `headroom_review_sha256`: actual saved root-reviewed host/
  guest free-space and live4 output budget receipt. The helper retains this
  reviewed input; it cannot measure host free space from within the guest.
- `minimum_root_free_bytes`: explicit reviewed value (existing reserve1GiB).
- `minimum_build_free_bytes`: explicit root-reviewed live4/output requirement.
- `max_proof_age_seconds`: explicit root-reviewed finite positive freshness bound.
- `max_command_bytes`: explicit tool-output bound (33554432 accommodates the
  existing postproof's full symbol table; smaller values may fail, not pass).

Hash that exact review JSON and keep its path/hash unchanged across phases.
The helper has no defaults for these bounds or external proofs. Example dispatch
structure (root supplies actual pinned paths/hash):

```
timeout 180s python3 /PERSISTENT/kdlock-kdrebuild2-repeat4.py preflight --review-inputs /PERSISTENT/review.json --review-sha256 ACTUAL_SHA256
```

Require actual outer return0 AND fresh
`.../receipts/repeat-kdrebuild2-live4-20261111-01/preflight-complete.json`.
Review actual fresh idle/GRUB/df and exact boot4/ELF/config/BID/source64/module3 bbd3ba41
identity results before invoking the separate mutation phase:

```
timeout 240s python3 /PERSISTENT/kdlock-kdrebuild2-repeat4.py arm --review-inputs /PERSISTENT/review.json --review-sha256 ACTUAL_SHA256
```

Require actual return0 AND arm-complete, exact candidate2 next_entry, unchanged
normal default/config/other environment fields. The helper never reboots. Root
separately records a bounded ordinary systemctl reboot command and complete
bounded reconnect attempts. Do not reboot on failure or infer drain from timeout.

After reconnect, source/kernel/build/module inputs remain frozen. Invoke the
read-only phase with fresh output directories only:

```
timeout 240s python3 /PERSISTENT/kdlock-kdrebuild2-repeat4.py postproof --review-inputs /PERSISTENT/review.json --review-sha256 ACTUAL_SHA256
```

Require outer return0 AND postproof-complete, pinned91d helper actual0 plus
POSTBOOT_IDENTITY_VERIFIED, new boot !=fb0601dd, taint0, exact ELF/config/BuildID/
GS and fresh repeat-arm→consumed-nextentry proof. The unchanged pinned helper
also retains its original first-arm inputs; the independent repeat binding keeps
that historical input distinct from this fresh arm. Only then root admits live4.
All phases preserve failure receipts and refuse repeat/partial namespace reuse.
