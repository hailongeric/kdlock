# Scope3 local writer queue recipe

This separate recipe starts at `8446f4ecb08816380a4c233197a8ce5e4d333aac`.
Its first change adds only explicit `kdscope3-native` and `kdscope3-kd` identity
profiles and their directly affected fixtures, using the same profile structure
as `f4ae82cfdf053c679c5d09ee8e503a7919764c9b`. It does not include that earlier
recipe's rwsem implementation or any new writer implementation yet.

The source/output pair is
`/mnt/kdlock-builds2/linux-7.0.0-38-kdscope3/{source,build}`. The distinct release
is `7.0.0-38-kdscope3`, with bundles
`/root/kdlock-kernel-baselines/linux70-kdscope3-{native,kd}-20261031`.
Existing scope1 source, output, installed images and bundles remain unchanged.

After the candidate's production files and exact writer-chain classifier are
reviewed, copy their exact bytes into this recipe and record the source delta
before composing/building on the VM. The paired MM harness must be identical
for scope1 and scope3, including its explicitly selected eligibility policy.
No profile name supplies a functional or performance pass. Builds, fixtures,
boot checks and fresh one-round comparisons remain pending.
