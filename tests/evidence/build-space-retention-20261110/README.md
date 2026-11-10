# Exact inactive temporary-output retention, 2026-11-10 UTC

The authorized action returned **0**, retaining an independent verified copy and
then unlinking exactly one inactive temporary link output. Guest root free space
increased by **118,382,592 bytes**, from 1,983,664,128 to 2,102,046,720 bytes.
This is an operational space receipt, not a build or runtime validation result.

The only removed path was
`/root/kdlock-build-output/linux-7.0.0-38-kdscope1/.tmp_vmlinux2`,
device 2049, inode 357757, one link, 131,727,800 logical bytes and
118,382,592 allocated bytes. Its SHA256 was
`66a22524252fb3c33d202879b022be9a5f616fc4b55eca7aba82996375b1da29`.
The independent retained file remains at
`/mnt/kdlock-builds2/root-tmp-retention-kdscope1-20261111-01/tmp_vmlinux2.retained`,
device 2080, inode 1179656, with the same logical bytes and SHA256. The directory's
original date suffix is preserved; the actual operation was November 10 UTC.

The [controller](controller.json) records return 0 and 3.677 seconds. The
[helper](helper.py.txt), [reviewed scope](reviewed-plan.md), [raw output](stdout.log)
and five [guest receipt identities](guest/vm-copy-index.json) are retained.
The helper copied, fsynced, reopened and checked bytes/metadata before unlinking
the single literal source path. It checked idle state and absence of other open
users; its own retained source descriptor was explicit. Eight protected final
artifacts and the recorded baseline manifest were unchanged. No other output,
base disk, snapshot or debug cache was removed, and this action ran no trim,
build, module or JIT work.

The guest remained on `7.0.0-38-kdlock1`, boot
`ca0b717b-c19d-4027-b598-6a1cf58b93d2`, taint 0, with no fixture devices or workers.
This narrow root-space action is separate from the earlier guest cleanup and
user-approved discard/trim, and from later kernel2 witness retention.

Collection read saved receipts only. The binary retained on the guest is not
duplicated into Git. `SHA256SUMS` covers all retained files except itself.
