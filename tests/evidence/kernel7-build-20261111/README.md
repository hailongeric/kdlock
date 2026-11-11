# Kernel7 focused and full build evidence

Core `0c97cd34` built as `7.0.0-38-kdrebuild7` in the isolated
`/mnt/kdlock-builds2/kdlock-main-kernel7-0c97cd34-01/{source,build}`.
This image includes integer root killable capture, managed cancellation and
queue-only storage retirement. It does not include the later typed query
source `0d42063e`. No kernel7 boot, selected API, generated body, MM execution
or performance result is established by this directory.

The [successful focused receipt](collection/payload/receipts/focused-02/result.json)
records rc0 for exact installer verification, olddefconfig and all 33 core plus
8 affected Linux/MM object targets. The earlier
[precompile failure](collection/payload/receipts/focused-01/result.json) remains
unchanged: its controller omitted required fingerprint arguments from verify,
which refused before any compiler ran. The separate continuation supplied the
externally recorded pins and verified the already-applied source; it did not
reapply it or overwrite the failed attempt.

The [original full receipt](collection/payload/receipts/full-01/result.json)
retains all seven rc0 commands, including bzImage in 291.475 seconds and the
single required NLS module in 3.763 seconds using 16 jobs and ordinary flags.
ELF, symbol, module and actual GS readers also returned zero. Only the selected
NLS module was built, not the full configured modules target. The receipt still
reports failure because its final strict idle observation saw PID/TID 458 in
D state, with no active build command. Its earlier wait cause is unproven.

The separate [read-only finalization](collection/payload/receipts/full-finalize-01/result.json)
returned zero after checking every original command/log, all 16 outputs, source,
normal/kernel6 and installed-file pins, and two fresh strict idle observations
10 seconds apart. It performed no rebuild, installation, load or boot. The
original failure remains linked by exact hash; a later clear sample does not
explain the earlier worker state.

The [linked identity](collection/payload/receipts/full-finalize-01/final-identity.json)
records Build ID `6195c94ad20aa3548344f27416b350cfde14ad6e`, configuration SHA
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`,
full current_task/const_current_task VMA `0xffffffff84425018`, and percpu start
`0xffffffff8440d000`. The actual GS:RIP instruction at `0xffffffff8150e90b`
has bytes `65488b050567f102`. These are linked metadata, not running-kernel
proof, and must not be reused for a later image without verification.

Raw logs retain 22 kernel warning records: the unchanged maple-tree frame of
1088 bytes exceeding the 1024-byte threshold, the unchanged AppArmor unused
variable, and 20 fortify fixture diagnostics about missing expected compiler
warnings. None is removed or presented as a fortify, stack, mitigation or
context pass. The NLS log has no warning record. Actual full logs and
[diagnostic rows](collection/payload/receipts/full-finalize-01/result.json) remain
available for review.

Throughout this stage the guest stayed on normal `7.0.0-38-kdlock1`, boot
`afb0c5cd-96b7-488b-bcb4-4a31cbb4e50e`, taint 0, with the exact 54 normal
modules. All 77 package files, seven integrated files, top Makefile, native MM
bodies, normal/kernel6 inputs, /boot and module namespaces retained their pins.
[The offline audit](audit.json) checks all 141 saved files and 34,865,280 bytes
against the copied index. It is a saved-evidence check, not another VM test.
