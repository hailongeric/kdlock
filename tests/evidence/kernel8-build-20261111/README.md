# Kernel8 focused and full build evidence

Core `0d42063ead37dc8fc1631fa56c8348890ede9c5f` built as
`7.0.0-38-kdrebuild8` in the isolated
`/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/{source,build}`.
Its 78-file v3 package adds the two typed physical rwsem predicates to the
integer-operation and cancellation source retained from kernel7. Native MM
bodies retain their original hashes. This directory establishes compilation
and linked identity. Candidate8 was not installed, booted or exercised by
these receipts, and meaningful delegated MM completion remains unproved.
[Package and exact inputs](collection/payload/input/package.json)

The focused controller returned zero after the fresh source copy, v3
inspection, plan, application and verification, olddefconfig, and all 33 core
plus 8 affected Linux/MM object targets. Plan, apply and verify carry the
same inspected source/configuration/package fingerprints. The 41 object
targets and their 41 command records are pinned. Olddefconfig took 8.024
seconds and the focused compilation took 57.598 seconds. All seven recorded
commands returned zero.
[Focused receipt](collection/payload/receipts/focused-01/result.json),
[outer return](collection/payload/input/driver-focused-01/result.json)

The full controller returned zero with status
`BUILT_AND_LINKED_IDENTITY_VERIFIED`. Using 16 jobs and ordinary build flags,
bzImage took 290.990 seconds and the single NLS module took 4.520 seconds.
The module metadata, ELF notes, symbols and GS disassembly readers also
returned zero. All seven commands completed successfully, with 321.199
seconds recorded for the full controller's build and verification work.
Only the declared NLS boot closure was built.
[Full receipt](collection/payload/receipts/full-01/result.json),
[outer return](collection/payload/receipts/full-driver-01/result.json)

The same full invocation preserves its first final-idle sample: PID/TID 479,
`kworker/48:1+events`, was in D state at
`drm_atomic_helper_wait_for_vblanks.part.0`, with no listed build or workload
activity. The bounded observer then recorded two samples with empty activity
and D-state lists, 10.091 seconds apart. The initial sample remains in the
successful receipt. These observations record the wait site and later clear
state, without establishing its underlying cause.
[All final-idle samples](collection/payload/receipts/full-01/result.json)

The fresh linked identity records 16 outputs and Build ID
`a33dd4d11d0f0c6649107507e685b6e86e716c1a`. The 511,421,424-byte ELF remains
at the guest build path with SHA256
`4441e45c27f9300a4cd19739c917458308581472604c3b75d8ffba9fec493be1`.
Configuration SHA256 is
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
Fresh ELF/System.map checks establish full current_task/const_current_task
VMA `0xffffffff84425018` and percpu start `0xffffffff8440d000`. The actual
GS:RIP instruction at `0xffffffff81510aab` has bytes `65488b056545f102`.
These are independent linked-image observations, not running-kernel proof.
[Linked identity](collection/payload/receipts/full-01/final-identity.json),
[GS metadata](collection/payload/receipts/full-01/gs-config.json)

The complete logs retain 22 kernel warning records: a maple-tree frame of
1088 bytes exceeding the 1024-byte threshold, an AppArmor unused variable,
and 20 fortify fixture diagnostics about missing expected compiler warnings.
The NLS log has no warning record. This is no fortify, stack, mitigation or
context-validation result.
[Kernel log](collection/payload/receipts/full-01/kernel.log),
[diagnostic rows](collection/payload/receipts/full-01/result.json)

The guest stayed on normal `7.0.0-38-kdlock1`, boot
`afb0c5cd-96b7-488b-bcb4-4a31cbb4e50e`, taint 0, with the exact 54 normal
modules. Saved before/after maps preserve normal source, kernel6 and kernel7
outputs/packages, kernel7 integrated source/MM bodies/input, the current
package and integrated source, boot files, GRUB inputs and module namespaces.
The offline audit verified all 57 payload files and 35,018,967 bytes against
the copied index, including all command-log hashes and the regular-only
78-member source archive. It also checked the original transport's matching
before/after inventories and 57-member archive. The hidden transport files
remain at the source-host paths and hashes recorded in the audit. The named
payload, copy index and collection result are retained here.
[Offline audit](audit.json), [copy index](collection/copy-index.json),
[collection result](collection/collection.json)
