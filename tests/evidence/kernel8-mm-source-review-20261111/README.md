# Kernel8 next MM source-step review

This is source/static investigation at `08454c4e2412a8821461ea596c04d5cbc1add45d`.
It runs no compiler, project import, test, build, provider, VM command or syscall.
It changes no execution code, native MM body, JIT/GS mapping, canonical state,
context frontier, cancellation, downgrade or lifetime policy.

The smallest next step is configuration-only admission of the linked
`do_mmap` span, `0xffffffff818321c0` plus 1,656 bytes. Five regions total 3,214
bytes, fitting the earlier 4,096-byte source capacity with 882 bytes remaining.
The host region bound must become five; SOURCE wire data grows by 1,672 bytes
before a version-length change. No dispatchable configuration or fresh live
callee bytes were created in this review.

The actual new capture decides whether fentry is a patched NOP or an earlier
ordinary callee miss. Conditional on entry progress, the existing typed query
at `0xffffffff81832246` returns at `0xffffffff8183224b`. The existing runner can
admit that exact observed reentry in a later image. The successful ordinary
anonymous path then reaches omitted `__get_unmapped_area` at
`0xffffffff81832349`; exact native continuation is at its callee entry,
`0xffffffff818313c0`, after the CALL word is staged once. Other paths may stop
earlier. Direct-CALL feedback cannot fetch omitted source into a fixed epoch.

The query-control branch has at most 16 total named KD source functions,
including the existing ten-function combiner prefix. Early helper error returns
can reach the outer typed UP_WRITE: the separate unlock/completion supplement
includes that branch, at most 19 functions for collection, and the existing
27-function terminal tail. No assumption excludes early errors. All relevant
compiled units fit the saved 392-byte grouped maximum and 16-byte whole-unit
alternative charge. Independent source and saved-weight peers closed the query
and unlock/completion paths. The fresh five-region conditional calculation
remains 44,024 bytes, leaving 21,512 bytes within 65,536 declared control bytes
and a 131,072-byte allocation. This retains the two unmeasured inclusive 16 KiB
native/IRQ experimental allowances. It proves neither complete AUX capacity nor
new runtime behavior. The historical four-region artifact remains unchanged.

Munmap's actual callee target is known, but no standalone linked span or fresh
live entry bytes were retained for `do_vmi_munmap`. Its native source describes
range validation, VMA lookup and aligned unmapping; no size or compiled next
helper is guessed. The broader source order includes VMA/tree operations,
allocation, downgrade, TLB gathering and notifier callbacks before the shown
normal-PTE RCU/PTL interval. That interval is not a globally first MM context.

AUX supplies stack separation and actual-RSP preservation, not scheduler/RCU,
preemption, lazy-MMU or TLB context transfer. If native service places a duty
on C, exact W handback needs W-local context, matching release/ACK routing and
legal progress while C retains it. Same-CPU W cannot run behind a PTL-pinned C.
Current translated RCU instead writes logical W while scheduler current is C;
that field update is not a valid context protocol. More source before the
frontier needs no new policy choice. Crossing it needs a proved context route;
CPU reservation, native-on-C continuation and delayed required handback remain
unselected. See the maintained [integration guide](../../../kernel/integration/RWSEM.md#native-rcu-and-page-table-context-boundary)
for the duties and alternatives, with their assumptions and costs.

`source-step-review.md` preserves the initial independent source/compiled query
review unchanged, including its then-pending second query-depth peer.
`unlock-completion-review.md` supplies the fresh early-return scope and later
independent source/weight closure; read both notes together. `scope.json` records
the proposed finite scope and false runtime/proof flags.
`input-index.json` hashes 58 existing Git-bound source/evidence inputs and
records raw hashes for compressed inputs. The historical proposal is retained
byte-for-byte as a non-dispatchable earlier input, not a new run configuration.
`SHA256SUMS` covers all six other files. Offline standard-library inspection
checked the listed bytes against the exact Git commit and checked the scope
arithmetic. This is archival/static verification, not a behavioral test.
