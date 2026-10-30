# Staged module ELF correspondence diagnosis

This is a read-only, offline analysis of the fetched `amd-uncore.ko` pair on
380G10. It does not rerun staging, execute either module, validate the full
module set, or change the failed stage receipt.

The stage controller compares built and stripped module identities through
`loader_identity`. Its standalone symbol inventory retains every symbol whose
target is an allocated section. `modules_install` used `INSTALL_MOD_STRIP=1`.

The fetched pair has identical properties and contents for all 25 allocated
sections, including `.text`, and identical 1,041 decoded relocations targeting
allocated sections. The relevant symbol multiset differs only by 18 removed
unnamed local `STT_SECTION` records: `info=3`, `other=0`, `value=0`, and `size=0`.
None is referenced by those retained loader relocations. The built relevant
symbol count is 224 and the staged count is 206. There are no added or changed
relevant symbols. The companion JSON records every removed symbol and the
exact input hashes.

This pair demonstrates legitimate stripping of unused section symbols, not a
change to allocated code, data, or normalized loader linkage. The verifier's
standalone symbol inventory was too strict for this transformation.

The narrow correction is to omit only canonical unnamed local zero-valued,
zero-sized `STT_SECTION` records from the standalone relevant-symbol inventory
when they are unreferenced by retained loader relocations. Preserve named,
global, noncanonical, or referenced symbols; retain exact normalized symbols
within relocation records and exact allocated section properties/bytes.
No allocated relocation-section byte exemption is needed for this pair.

The existing failed stage remains failed. A separately recorded verification
must still compare every staged module before installation can proceed.
