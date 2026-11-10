# Live2 unpublished-build recovery assessment

This is a proposed sequence, not an execution receipt. Only QUERY and read-only
fixture status were executed. No recovery adoption, ABORT, END, SHUTDOWN,
settlement, destruction or unload has been executed by this assessment.

The actual QUERY returned BUILD_START op 2, sequence 3, status 0. Its request and
response match the saved cycle-1 claim and source export exactly. The claim has
zero rows. Actual identities:

- candidate: 18379471558775858176
- claim: 18379471558651707392
- holder: 4097 (0x1001)
- epoch: 18379471558810037824
- slot: 18379471558794443016
- expected old image: 0

The cached last successful BUILD_START and source ordering establish an
unpublished code reservation. Loaded=false, update_started=false and
committed=false are source-derived phase conclusions, not kernel-memory flag
reads. No STAGE_LOAD/PUBLISH command was sent. The failed compiler did not
produce a LoweredImage or receipt, and none is reconstructed here.

After explicit approval, reopen QUERY and require its cache remains byte-for-byte
identical to the retained assessment. Adopt that exact actual recovered exchange.
Send only these exact normal commands, checking status 0 and complete exact
reply before advancing:

1. Sequence 4, ABORT op 7: fixed words
   [18379471558775858176, 18379471558651707392, 4097], zero rows/blobs.
   Reply must contain the same three words.
2. Sequence 5, CLAIM_END op 6: fixed words
   [18379471558651707392, 4097], zero rows/blobs. Reply must match.
3. Sequence 6, SHUTDOWN op 9: no words/rows/blobs. Require actual success and
   returned epoch 18379471558810037824. Kernel success checks ended native users,
   no active control cycle, no published slot and released compiled controls.
4. Sequence 7, ARCHIVE_CLAIM op 10: fixed words
   [18379471558810037824, 8192, 4096], zero rows/blobs. Preserve actual returned
   claim. Require actual zero rows before choosing an empty-producer archive
   path. Stop for reconciliation if any facts are returned; do not fabricate
   producer/compiler mappings.
5. Write the exact actual archive using O_EXCL and file plus directory fsync;
   retain its SHA256 content identity. Source export and original compile
   failure remain distinct provenance, not a publication or coverage receipt.
6. Sequence 8, SETTLE op 11: fixed words [actual archival claim, 8192], actual
   archive keys (expected zero), and one exact 32-byte content-identity blob.
   Require actual settlement receipt identity, matching claim/holder and keys.
7. Sequence 9, CLAIM_END op 6: fixed words [actual archival claim, 8192].
   Require matching success before ending host observers.
8. Close channel normally; then write ordinary fixture control 'destroy'. Its
   success requires worker_count=0, locks_clear, runtime idle, channel unregister,
   executable/source holds released. Close fixture control, then normal rmmod.

Any status/error stops this plan at the retained phase. A syscall delivery error
permits only exact same-sequence cache redelivery; a completed -EBUSY/-EAGAIN is
not drain and needs explicit phase-aware retry. No reset, forced unload,
source replay, timeout-as-drain or new protocol is involved.

Source evidence is unchanged between frozen 2cc70fce and current main for
control.c, runtime.c, session.py, archive.py and wire.py:

- kernel/control.c:636-728: exact candidate cancellation; committed candidates
  refuse ABORT; unaccepted provider code hold is released once.
- kernel/control.c:731-782: END after ABORT closes exact claim/build and releases
  the cycle, with persistent ending gate for partial progress.
- kernel/runtime.c:547-609: SHUTDOWN closes admission, checks native_empty and
  compiled controls, drops BUILD only after those checks.
- kernel/runtime.c:612-717: closed-source archival claim and exact settlement.
- tests/kernel/run_runtime_fixture.py:425-433: normal close/destroy/unload order.

Raw assessment receipts are preserved in the VM under
live2-runtime-2cc70fce-20261111-01/recovery-assessment-01 and copied unchanged to
/tmp/kdlock-live2-recovery-assessment-01 on the source host.
