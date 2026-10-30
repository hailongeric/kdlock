# Resume the completed MM transfer offline

The baseline transfer completed with exit status zero and retained a full
11,878,400-byte tar. Host verification then stopped at importing `fresh_controls`.
The original helper, failed receipt, tar and extracted partial files remain
unchanged. This is a host packaging failure; no measurement or guest archive is
repeated.

The new `kdlock-killable-mm-fetch-r2-20261031.py` is a copy of the frozen fetch
helper with two bounded changes. Its optional offline continuation requires the
actual failed receipt/hash and its exact original tar; it extracts into a new
tmpfs directory and repeats the unchanged byte/member checks. It never reaches
the subprocess transport branch in this mode. On success it removes only its
new derived receipt cache and retains the original tar and failed attempt.

The reader now uses its normal `nano_core` module name, registers that exact
module before execution, and adds the fixed reader directory to `sys.path`.
This supports the intentional `nano_core`/`fresh_controls` import relationship
without loading a second core. Both source hashes are checked. `PYTHONPATH`
alone would leave the original alias/circular-import problem unresolved.

Actual failed inputs:

- Receipt: `/dev/shm/kdlock-killable-mm-baseline-20261031/transfer.json`,
  `5ee7cbe9c0095b1337427c5c441bb9bc233b7207ec6c2bea6264429b9085c1cd`.
- Tar: the same directory's `transport.tar`,
  `9246e2e285f3d9d944008cccc4f725642e980a99697ab6c923196fb0ece84e15`.
- Original helper:
  `19e73578e919af0d0e50248ddca647f976062f3786944ba955afaf0ec0541e53`.

After source review, root may run this source-host-only command in the actual
tmpfs namespace:

```sh
python3 /tmp/kdlock-killable-mm-fetch-r2-20261031.py \
  --arm baseline-f7-scope1-kd \
  --boot-id 43101fa8-697a-46ad-99c9-be4b39cce0b3 \
  --destination /dev/shm/kdlock-killable-mm-baseline-r2-20261031 \
  --offline-transport /dev/shm/kdlock-killable-mm-baseline-20261031/transport.tar \
  --offline-receipt /dev/shm/kdlock-killable-mm-baseline-20261031/transfer.json \
  --offline-receipt-sha256 5ee7cbe9c0095b1337427c5c441bb9bc233b7207ec6c2bea6264429b9085c1cd \
  --archive-owner-sha256 f658a47eef9c317ab218d72ba3a492bde14fc0fb9c45943a5f7acdf476d4f12b \
  --archive-sha256 4fa34c365caad5c5288dfef9fce5cd8d95273153c144697014a75fa565c91e92 \
  --inventory-sha256 f7351486d7fbd1d4135c769c97ff119124679078f77792772518266ad3510404 \
  --aliases-sha256 9c28bb416b4ed49b8a3a6bf755422d65cfa5c61e6889c8299647bf9f16b9c283 \
  --preservation-map-sha256 bc239c1aff8e0099434835fa09549e1c8c8b4c0a2f64456ace3a8597aded7bf8
```

For the candidate, use r2's original normal-fetch arguments without the three
offline options. The guest transport body and archive verification remain
unchanged. There is no automatic retry, reboot, timing, endpoint recapture or
guest archive command. A successful fetch proves archive bytes only; scored
comparison and acceptance remain separate. This preparation performs only
source inspection and AST parsing, not reader imports or execution.

Frozen r2 script SHA-256:
`590181521849eede167c2ba6e6ffd3d72c5fbe883f330f79d6e492020695962d`.
The sibling `.py.diff` has SHA-256
`a7e50fca96b67b0f46623c67149ceccb6dda406e9894c8eda814a2eeb6311580`.
Outer and embedded Python parse statically; the guest transport string is
byte-identical to the original. Independent review is separate from executing
the continuation on the actual retained archives.
