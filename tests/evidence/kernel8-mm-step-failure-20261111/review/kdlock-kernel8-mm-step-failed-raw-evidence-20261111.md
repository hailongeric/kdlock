# Recovered failed five-region MM run: raw evidence

The single run remains **failed_retained**, with a client phase timeout and no
client return code. This offline standard-library audit issues no VM command,
test, project import, replay or cleanup and edits no repository source.

The recovered collection is
`/tmp/kdlock-kernel8-mm-step-collection-20261111-02`. All 224 selected files,
30,666,498 raw bytes, match their copy-index hashes and exact decoded base64
transport bytes. Copy-source identities are equal before and after capture.
The failed run boot is `4a98638f-c01c-4fc9-8de8-69a74346aa0f`; the collection
was copied after the preserved-failure reset on recovery boot
`f1442f01-e060-46fa-a480-da508d7ce8a9`. These are different evidence stages.

## Completed syscall work

Only rounds 1 and 2 have actual completed phase/stdout receipts. Each has eight
distinct worker TIDs completing eight iterations and all recorded syscall,
zero/write/readback, absence and address-reuse checks.

| Retained completed worker total | Count |
| --- | ---: |
| Iterations | 128 |
| Successful mmap calls | 384 |
| Successful munmap calls | 256 |
| mincore / unmapped-page checks | 512 each |
| Successful address reuse | 128 |
| Fresh-zero, written, readback bytes | 2,097,152 each |

Each completed round separately reserves and cleans up one parent arena.
Incidental runtime/syscall activity is not included in these worker counts.
There is no third-round completion receipt. Some third-round work may have
occurred; its amount and correctness cannot be inferred from the retained
prefix.

## What the added do_mmap source actually reached

Five cumulative binary snapshots end at 19,248 events with no recorded overflow.
Their prefixes agree exactly; all 3,595 embedded event dictionaries used by the
saved host result and completion reports match their raw event rows.

The actual five-region SOURCE export has 3,214 bytes. Its `do_mmap` entry is
the live five-byte NOP `0f1f440000`, rather than the saved linked fentry CALL.
The raw query CALL is `0xffffffff81832246`, bytes `e8c5d5cfff`, targeting
`kd_linux_rwsem_is_write_locked_entry_asm`, `0xffffffff8152f810`.

The latest saved prefix contains:

- 81 executed mmap-root entries at `0xffffffff817ef5ea`, each exiting before
  that typed query with LOCK_OPERATION / TARGET_READY / query detail.
- 81 exact query operations and QUERY_RESULT rows, each predicate one,
  RESUMABLE phase, canonical return cursor `0xffffffff8183224b`, and the same
  source/grant/physical executor. The query is applied once.
- 81 subsequent JIT_ENTER **attempts** at that post-query cursor on image 1.
  None has an executed JIT_EXIT; all hand back with exact `-ENOENT` at the
  post-query cursor. These are entry lookup refusals, not 81 executions after
  the query. Each complete query lifetime joins original-task native unlock
  and source drop, physical callback begin/end, release/owner retirement and
  its matching slot free.
- 45 executed munmap-root prefixes, ending at source CALL
  `0xffffffff8185af54`, CALL_STAGED phase 2. Their unexecuted native callee
  entry is `do_vmi_munmap`, `0xffffffff81858430`; the source CALL is not replayed.

There are therefore 207 entry attempts and 126 matching executed-entry exits
in the saved prefix, not 207 proved generated executions. The raw query-return
records support 81 accepted host reentry candidates, of which one adds the new
entry. Two GNU builds and two exact publications are retained; image 2's actual
manifest includes `0xffffffff8183224b`.

**No saved JIT_ENTER/JIT_EXIT uses image 2.** No saved handback reaches
`__get_unmapped_area`, `0xffffffff818313c0`. The ordinary source CALL at
`0xffffffff81832349` has exact exported bytes `e872f0ffff`, but source bytes
and publication do not establish that execution reached it. The snapshots
end after round 2, before the failed third-round observation could be taken.

## Facts and lifetime limits

All 14 saved channel attempts returned success. They include the two
construction/publication/ACK/end cycles; both ACK replies contain **zero
coverage keys**. Cycle 2 claimed 45 distinct exact direct-CALL fact keys from
the first image's munmap frontier, without ordinary observation credit.
No shutdown, archive-claim or SETTLE command exists in this transport. No
archival settlement or final ordinary cleanup result is inferred.

The completed round-2 scalar snapshot reports 664 physical begins and 664
ends and pool_idle one. This is a snapshot of that completed phase, not a
failed-run drain receipt or physical batch-chain measurement. The raw final
prefix still contains one more SLOT_RESERVE than SLOT_FREE and lacks final
owner leave/channel close/unload gates. Matching retirement for the 81
observed query episodes does not prove that every actor later drained.

## First-fault node evidence

The preserved first diagnostic confirms `jit.c:855`,
`kd_jit_acquire+0x45d/0x4b0`, EAX/EDX `-EBUSY`. Its source-state address from
RBX, `0xff11000113ce5c00`, appears in **zero** retained event rows.

The node address `0xff11000109f80068` and acquisition address
`0xff11000109f80329` do occur in 28 earlier rows, across two different
source-state/origin reserve/free incarnations. Their latest matching free is
event 9600. Those reused addresses cannot be joined to the faulting source
state or used to claim its owner/queue scheduling order. The source-proved
post-publication initialized-batch race remains a supported explanation, not
a captured first-fault queue interleaving.

Protected-MM generated completion is not established. No full MM, AUX, native
callback-stack, performance, successful cancellation or final cleanup claim is
added by these records. The failed runtime, first fault, panic, recovery
snapshot/reset and any future corrected-kernel validation must remain separate.

## Audit artifacts and pins

- Machine findings:
  `/tmp/kdlock-kernel8-mm-step-failed-raw-audit-20261111.json`, SHA-256
  `15f89197cef0708c1063473e330fd545d4fc6130140271633c5b544647429e25`.
- Standard-library audit script:
  `/tmp/kdlock-kernel8-mm-step-failed-raw-audit-20261111.py`, SHA-256
  `9a89052807a763b51c23cd1c37e0bcf5720a83995c5aca35fc4567eee171129f`.
- Recovered collection copy index:
  `67d00a8ad3f909a7d7bd0ae4c0c649499993bf212d9775e68d8ad5c9a76cc001`.
- Failed runner result:
  `fd06287ab267b6ef682c623140dbd2735c20a4dfe6f83c5e574bf4fe8cbe99e6`.
- Activated configuration:
  `3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1`.
- The machine findings retain size/SHA-256 pins for every read input and exact
  event-index witnesses for all 81 query lifetimes.
