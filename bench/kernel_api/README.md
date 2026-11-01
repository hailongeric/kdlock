# Original-body setfd and pipe comparison

This controller uses the scoped built-in binding from
`kernel_integration/real_api`. It invokes the unchanged syscall loops in
`bench/real_api/client.c` with an explicit final `native` or `kd` argument.
It never loads the copied-body ftrace adapters. The measured bodies remain
`set_close_on_exec`, `pipe_ioctl(FIONREAD)` and `pipe_fcntl(F_GETPIPE_SZ)`;
only their lock call shells and whole-object lock/lifetime routing differ.
Native and KD objects use the same enabled kernel image and layout. TCLock is
not included until an equivalent whole-object binding exists.

The frozen plan has three cases: descriptor flag toggling at descriptor stride
one, FIONREAD over sixteen filled pages, and F_GETPIPE_SZ over that same filled
pipe. Setfd performs F_SETFD plus its F_GETFD oracle per operation; each pipe
operation performs one syscall. Each arm runs workers 1–8 and 12–60 in steps of
four on CPU0..N-1, with collector63. Each point has one two-second measured
phase following bounded unscored preparation. The score is all completed
operations divided by the actual joined phase wall time; no best window or
repeat is selected. Source/kernel/topology/instrumentation identities remain
separate from nano and earlier copied-body results.

The provider is loaded with `api_bind=1` before object creation in both arms;
the controller records and requires its read-only `Y` readback. Ordinary module
loads default to binding off and do not prepare these three global entries.
The client proves
actual object/lock/provider identity through setup-only queries and keeps the
object alive until joined workers finish. Its backend cannot change after
publication. The controller stops the client normally before provider retirement
and unload; a timeout, missing reply, kernel warning or failed drain retains the
live state for diagnosis. It never forces unload or counts a timeout as drain.

A separate functional invocation uses completion observations and requires
positive returned KD bodies at sixteen workers, exact syscall results and final
source/frame/object drain. Scored invocation disables body/completion/timing and
heat observations; a stable NORMAL image alone is recorded as publication,
not proof of returned bodies. Both use one immutable prepared provider tree and
retain exact parameters. Setup, translation and queries are outside measurement.

All preparation, compilation, tests, modules and timings run only in the VM.
The controller requires an explicitly reviewed enabled-API schema-2 kernel
profile, real recovery snapshot, current fixed-frequency host capture, and a
new external output tree. New profiles and installation are separate gates;
this documentation is a candidate contract, not performance evidence.

The explicit `kdscope4-native` profile is also supported for the fresh master
campaign. It uses the same original syscall bodies and binding protocol as
`kdscope1-native`, with the restored reader-entry implementation in the MM
backend. Both syscall arms run on this single image with MM mode off; object
selection still distinguishes Native and KD syscall locks. Its schema-2 bundle
and exact build path are verified independently from the older scope1 image.

The [fresh master campaign](../results/10.176.26.71/bench/master-native-20261101/README.md)
records all 126 one-round Native/KD points and six functional arms on scope4.
Setfd and F_GETPIPE_SZ have positive geometric means; FIONREAD has a negative
geometric mean. All points and identity limits are retained in that report.
