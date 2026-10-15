# Captured kernel experiments

These directories retain the independently authorized kernel-interface chain.
They are provenance/reproduction inputs, not instructions to change the current
kernel during ordinary provider work. [kernel_baseline](../kernel_baseline/README.md)
and [the project guide](../docs/PROJECT_GUIDE.md#kernel-identity) define identity checks.

| Directory | Release/role |
| --- | --- |
| [spin_static](spin_static/README.md) | Historical kdstatic1/2 static-call ancestor |
| [spin_clobber](spin_clobber/README.md) | kdclobber1 spin caller-clobber v1 |
| [mutex_clobber](mutex_clobber/README.md) | kdclobber2 ordinary mutex caller-clobber v1; required kernel baseline |

Keep each patch, capture script and immutable captured parent bundle. The current
provider requires both clobber interfaces and does not support old static-only
installation branches. Historical experiment source is retained because the later
bundles verify their parent chain; obsolete performance narrative is indexed in Git.
Build/test execution remains guest-only, and a new kernel change needs its own
scope rather than being inferred from source cleanup.

Rwlock writer ABI3 is implemented in the provider, direct headers and translation
engine on this existing baseline. It reuses the spin execution backend and does
not add a guest-kernel patch or rwlock hook. See the
[entry identities](../docs/JIT_REGISTER_ABI.md#entry-identities-and-packet-states).
