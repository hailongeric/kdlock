# Isolated comparison generation

The user explicitly selected: "Complete comparisons; keep the candidate unaccepted."
After the active nano run, endpoint, archive and offline result review complete,
continue the syscall and mmap comparisons with the isolated provider at
`f7a84065e84474380faa37eeadfdf534abd72a68`. Retain every negative nano result;
neither running the later comparisons nor completing their functional checks
grants performance acceptance or promotes this branch.

This supersedes the earlier external sequencing note's requirement for nano
performance acceptance before staging. Correctness, completed retirement, idle
synchronization, recovery, exact identities and one measurement round per point
remain required. The running source and workload inputs remain frozen.

The compiled kernel project provenance remains
`8446f4ecb08816380a4c233197a8ce5e4d333aac`. Source-host Git inspection found all
56 kernel recipe paths and four shared API headers byte-identical between that
commit and f7. This supports reuse of the existing kernel build; it does not
establish current-provider CONFIG-on execution or actual syscall/MM behavior.
The VM controllers will verify both complete source generations and original
preparation inputs before each operation.

The adjacent JSON is the exact existing generation-record schema, using the
clean 5,922-file f7 synchronization and the retained original kernel provenance.
It selects a comparison candidate, not an accepted implementation. No guest
operation, build, test, installation or measurement is performed by creating it.
