# Captured kernel experiments

These directories retain the independently authorized kernel-interface chain.
They are provenance/reproduction inputs, not instructions to change the current
kernel during ordinary provider work. [kernel_baseline](../README.md)
and [VM operations](../../docs/operations/VM.md#kernel-identity) define identity checks.

Linux 6.1 development is retired. Ubuntu 26.04 / Linux 7.0 is the active
adaptation platform; its OS boot is recorded in the
[migration record](../../docs/history/vm-ubuntu2604-migration-20261027.md), while
KD compatibility remains unvalidated. The [retirement policy](../../docs/history/kernel-retirement-20261027.md)
keeps one legacy recovery version and all result evidence. The small patch and
capture sources here remain historical provenance and ABI fixtures.

| Directory | Release/role |
| --- | --- |
| [spin_static](spin_static/README.md) | Historical kdstatic1/2 static-call ancestor |
| [spin_clobber](spin_clobber/README.md) |kdclobber1 spin caller-clobber v1 |
| [mutex_clobber](mutex_clobber/README.md) |kdclobber2 ordinary mutex caller-clobber v1; retained legacy recovery baseline |

Keep each patch, capture script and embedded immutable parent/ancestor record in
the retained bundle. Separate ancestor build trees and duplicate bundles follow
the retirement inventory. The current
spin provider requires spin-clobber-v1 and does not support old static-only
installation branches. KD mutex now owns its object and clobber entry; the kernel
mutex-clobber patch remains part of the captured baseline chain. Historical experiment source is retained because the later
bundles verify their parent chain; obsolete performance narrative is indexed in Git.
Build/test execution remains guest-only, and a new kernel change needs its own
scope rather than being inferred from source cleanup.

Rwlock writer ABI3 is implemented in the provider, direct headers and translation
engine on this existing baseline. It reuses the spin execution backend and does
not add a guest-kernel patch or rwlock hook. See the
[entry identities](../../docs/JIT_REGISTER_ABI.md#entry-identities-and-packet-states).
