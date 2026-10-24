# Retired VMA advice delegation

This operation-specific design was removed from the active implementation.
The [maintained scope](README.md) is the lock backend and minimal API/lifetime
wrappers. Native MM bodies execute on their original tasks without algorithm changes.

Historical guides and source remain in commit `806e9a855b97ded9c25a44d3e4b12e14c49b0c55`.
The `mm-*` result records preserve their measurements, failures and raw evidence,
and are explicitly marked retired. Do not run their old build or boot commands
against the current checkout.
