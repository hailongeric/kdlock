# Captured kdclobber2 kernel provenance

The verified guest kernel is `6.1.159-kdclobber2`, derived from the preserved
[kdclobber1 spin experiment](../spin_clobber/README.md). This directory retains
[guest-kernel.patch](guest-kernel.patch) and [capture.py](capture.py) because the
captured kernel bundle verifies its source and parent chain. The current KD
mutex is provider-local and consumes no kernel mutex hooks. Its API and protocol
are documented in [mutex implementation](../../docs/design/mutex_implementation.md).

The guest source/build is `/root/linux-6.1.159-kdclobber2`, linked to
`/mnt/kdlock-builds/linux-6.1.159-kdclobber2`. Its captured bundle is
`/root/kdlock-kernel-baselines/mutex-clobber2-20260919`, with Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Verify source, configuration, build
files and the live Build ID using [the identity procedure](../../docs/PROJECT_GUIDE.md#kernel-identity).

Keep the captured source, configuration, boot files and parent bundles intact.
Ordinary provider work does not modify or rebuild this kernel. The original
interface description and build/install commands remain in the
[fixed experiment record](https://github.com/hailongeric/kdlock/blob/98118e91822847c37558655d07193c0c362c0bd8/kernel_experiments/mutex_clobber/README.md).
Reproduction requires a matching historical checkout and separately scoped
kernel work; those commands are not part of the current mutex build workflow.
