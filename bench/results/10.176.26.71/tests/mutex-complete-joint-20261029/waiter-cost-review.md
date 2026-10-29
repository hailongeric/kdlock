# Waiter cost review before joint COMPLETE validation

The joint candidate `3232d47ca4d9d90a4ec576d55ac028be3c9da7ba` leaves the waiter, queue and gate-state sources byte-identical to `99f383624faa872a76521d1b5be7faea586591c1`. It cannot directly remove the extra origin polling work introduced since `1c86d6d1a15d96d75c09504f1041772247707804`.

The preserved default-off record ELFs show a four-instruction steady nonzero poll at baseline `0x18ee2..0x18eee` (PAUSE/load/test/branch). Candidate READY with budget greater than one executes thirteen instructions along `0x199ae..0x199cc` then `0x199e0..0x199eb`: WAIT check, READY-or-CLAIMED validation, PAUSE, budget-zero check, decrement/check, then notification load/check. Both perform one PAUSE and one notification byte load per selected iteration. Candidate current-task GS loading occurs once before this loop.

Thus finishing within the initial budget still incurs state and budget work at every poll. Nine additional architectural instructions per selected iteration do not establish a cycle cost or explain the measured instruction delta without a poll-count or function-level instruction denominator. The all-within-budget observation also comes from separate instrumented sessions, not the default-off perf run itself.

Other concrete additions are a READY publication store/INIT guard per ordinary queued invocation, INIT-to-WAIT CAS for a private head, and full-word CAS phase transitions preserving WITHDRAW at head/epoch boundaries. Exact count/key/generation publication and retirement already existed in the baseline. Long observed diagnostic batches amortize head/epoch work; those observations do not price the CAS operations.

A bounded future hypothesis is to separate finite initial-budget polling from post-expiry polling while retaining every state-validity, zero, WAIT and expiry/withdrawal check. This may avoid the initial loop's redundant budget-zero test/branch. No source edit, emitted-code saving, timing benefit, or acceptance is claimed.
