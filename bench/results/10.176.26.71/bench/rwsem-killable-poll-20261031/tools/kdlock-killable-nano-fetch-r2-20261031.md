# Continue the completed nano fetch offline

The original f7 fetch completed its read-only remote tar with return code 0,
then refused eight symlinks in the separate basic fixture workspaces. No timing
or archive failed. The original failed transfer receipt and partial output are
retained unchanged.

Exact existing transport:
`/dev/shm/kdlock-killable-nano-f7a84065-20261031/transport.tar`, 149,094,400 bytes,
SHA-256 `59ce889bd150fb3a5092013026af02b5e8af14f2dcbcb94c4d600d90f5b6df2b`.
Original transfer receipt SHA-256:
`9f470eae9b59717cab36a2dfa8089e4b2f2f1ea782ef3920fa1b6217a6cb5e90`.

Revision 2 permits only the observed `workspace/disassem` and
`workspace/include` links in the exact basic spin/mutex/rwlock/rwsem session
directories. Each original target must be the same family's archived
`source/disassem` or `source/include`. Regular members are extracted first;
then these eight links are recreated as relative local links confined to that
family's copied source tree. Original target, mode, uid, gid and mtime remain in
`transport-links.json`; relative reconstruction is explicitly recorded.
All prior file/group/control/basic hash checks remain unchanged.

The explicit offline mode requires the existing transport, failed receipt and
its actual hash. It verifies return code 0, the original helper identity, exact
source/five input hashes and transport size/hash before extracting into a new
tmpfs directory. It contains no executed remote branch in this mode. It neither
copies nor deletes the original tar, receipt or failed partial tree. The new
successful transfer receipt names its exact prior failure and retained transport.

Root authorized one offline continuation on 380G10 in the actual elevated
`/dev/shm` namespace. Independent source review passed the frozen helper SHA-256
`04ac5dd5fb693b42d782c75dde39bb30d8247be6f717238de15f0470fbce8a17`.
The ordinary fetch path is retained for 22d and uses the same exact link rules;
it still requires finalized archive receipts and never starts timing/archiving.
Only its own successfully verified intermediate tar may be removed. A later
failure retains partials. No report commit or acceptance follows from fetching.

The authorized offline continuation completed with return code 0 in
`/dev/shm/kdlock-killable-nano-f7a84065-r2-20261031`. It retained 11 original
compressed groups, 2,326 regular transport files and the eight relative links.
The original failed receipt and transport tar were rehashed after completion
and remain unchanged. No remote branch or archived code was executed.

- New `transfer.json`: `83a35e53e0155d875133ed94062d6371e4523a95e7ebe31340b1d2fd6c1c4bbd`.
- `analysis-arm.json`: `969f33fd03393608edc436cf7782c7717cdbd92847b9a5e22b6104550867a420`.
- `transport-links.json`: `a3d405a39a084be84195f3c5df98fbc8be4c81e2338c17b424eac26bf9ca760b`.
- Local proof and small receipt copies:
  `/tmp/kdlock-killable-f7-fetch-offline-r2-20261031/`; `result.json`
  SHA-256 `142022133187ffd2c224497267094803209e619b47163ad2b636323734be0688`.

For the future candidate fetch, use this r2 helper with the original guide's
five actual hash arguments and `--arm 22d`, choosing a new destination; omit all
three offline arguments. Full archive-member and point analysis remains pending
both finalized arms. Fetch success never changes `performance_accepted=false`.
