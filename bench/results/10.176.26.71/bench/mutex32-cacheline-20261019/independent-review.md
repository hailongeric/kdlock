# Independent source, archive and candidate code review

This source-host review passed. It read archives and Git objects as data and
used host `nm`/`objdump` to inspect selected ELF bytes. No archived source,
binary, test, module, workload or timing was executed. These receipts were
created after collection and are not represented as guest-collected evidence.

The bounded command in [FINALIZATION.md](FINALIZATION.md), with all four exact
arm expectations and `--extra-source placement=09ebd8f`, returned zero.
[archive-review.json](archive-review.json) and
[source-review.json](source-review.json) report 10,246 members, 8,849 regular
files, 20 source manifests, 106 binary-manifest entries and 90 JIT binaries.
Both report zero issues; there are no ancillary exceptions. The final idle
production is the checked candidate `76af844`, including 90 production files
and 40 private `.inc` files. The later `de30588` prefetch trial remains a
separate source identity.

[code-binding-review.json](code-binding-review.json) adds 25 passing checks
with zero issues. It independently hashes the four provider/workload ELF
members from the packed32 and candidate plain-run archives, matches their
archived build manifests and the four hashes in
[code-review.json](code-review.json), then replays the recorded `nm` and
`objdump` inspections. All replayed outputs match. Only the temporary input
filename in the `objdump` header is normalized to its recorded filename;
instruction text is unchanged. The candidate provider differs from the
prefetch provider, and its recorded abbreviated revision resolves exactly to
`76af84414bd4548e11f60c67ae7174ec63644496`.

Independent manual review confirms the five control-flow obligations in
[code-review-manual.md](code-review-manual.md) for those candidate bytes:

- The nonzero node-link path at `0x1284f` proceeds directly to COMBINER
  publication at `0x1285b`, bypassing both the tail read and retirement CAS.
- An empty link reads the tail at `0x128e0`. A foreign tail branches to the
  delayed-link loop at `0x128fa`. A matching tail reaches the retained locked
  CAS at `0x128eb`; only success reaches the no-successor exit at `0x12878`.
  CAS failure retains the delayed-link loop and PAUSE.
- The initial producer exchange at `0x12764` remains a full `xchg` before
  link publication. Source acquire loads preserve node initialization
  ordering when the later head decision omits a failed CAS.
- Entry and retirement retain fresh current-task identity, physical-owner,
  PICKUP and HELD/COMBINER checks, followed by separate physical-owner
  reloads. Retirement stores follow these checks. The external predicate
  remains available to separately compiled unlock routing.
- Reviewing the complete `rb_body` address range, including internal
  `rb_entry`, confirms that only the zero-owner CAS at `0x1d1` grants physical
  ownership. The phase comparison at `0x133` merely exits the bounded retry
  loop for COMBINER. CAS failure returns to that hint; other phases retain
  PAUSE and the eight-probe bound. The binding receipt retains this complete
  `.text` range without mixing similarly numbered `.init.text` addresses.

The lifetime argument still rests on the exact origin CPU/slot reservation,
not the diagnostic count records. Reservation persists through sleeping
physical acquisition and the head decision. A linked successor remains
unwoken and reserved; a foreign tail cannot ABA back to this head's encoded
slot before release. Successful tail retirement makes a later arrival an
independent head. The enclosing early-outer-release path reacquires through
the batch path without repeating this helper on its detached old node.

The additional binding helper had two bookkeeping errors during development:
its first invocation used `name` instead of the archive schema's `group` key;
its second compared an abbreviated matrix revision directly with a full
revision. The traceback and rejected receipt are preserved in
[code-binding-initial-attempt.log](code-binding-initial-attempt.log),
[code-binding-second-attempt.log](code-binding-second-attempt.log) and
[code-binding-review-first-receipt.json](code-binding-review-first-receipt.json).
The final helper reads the correct schema key and resolves the exact Git
object before comparison. It also confines the supplemental full-function
listing to `.text`. No archive, runtime, performance measurement or acceptance
condition was changed to repair these audit-tool errors.

Static inspection does not prove all concurrent interleavings or establish a
cache-transfer cost or performance benefit. The unchanged pinned published
waiters, absence of published-node cancellation, exact retirement and captured
x86 kernel remain scope boundaries. Live checks and the independent arithmetic
review are separate evidence.
