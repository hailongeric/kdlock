# Independent live5 raw-event audit

IDs are zero-based payload row numbers after the 40-byte header. No project code or runner oracle was imported or executed.

| Case | Exact generated execution and return rows | Physical release and retirement rows |
| --- | --- | --- |
| Recursive 1 | CA enter 4495 → child enqueue 4500 → CB enter 4517 → child DONE 4522 (3) → CA returned 4536 → root DONE 4544 (3) | A callback 4558/4560, source drop 4563, retire/ready/free 4564/4565/4570; B callback 4531/4533, source drop 4538, retire/ready/free 4545/4546/4569 |
| Recursive 2 | CA enter 4612 → child enqueue 4617 → CB enter 4634 → child DONE 4644 (5) → CA returned 4661 → root DONE 4664 (3) | A callback 4678/4680, source drop 4683, retire/ready/free 4684/4685/4690; B callback 4655/4657, source drop 4663, retire/ready/free 4666/4667/4689 |

Warm plain: 2 exact proxy selections each have a positive protected DONE with actual fixed-image entry/exit and accepted unlock; no native forward in those intervals.

Mode 2 outer A: request 4636 → deferred marker 4637 → inner DONE 4644 → post-export unwind publication 4645 → release notifier membership drops 4646 → actual original owner handles 4660; return token drops 4662. The frozen source places unwind publication after common-drive binding export; row 4644 itself is the pre-export completion event. Physical A release follows later at 4678/4680; source user drops 4683, all three release users are zero at retirement 4684. Physical completion and final slot retirement are distinct observations.

READY records precede the final retirable store. FREE flags 0x86f independently observe acquired retirable, queue/result completion, no result user, empty pool users and idle controls; their three release-user fields are zero. OWNER_RETIRE is recorded separately. Scalar identities are joined within SLOT lifetimes, never treated as new references.

The four actual publication replies chain old/new/returned-old identities to the fixed fourth image. EPISODE_DONE intentionally has image 0; image association comes from its exact preceding JIT entry/exit/accepted-operation records.
