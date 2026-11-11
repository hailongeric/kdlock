# Kernel6 API module builds and NLS staging

These are VM build and read-only source receipts for the linked kernel6
[candidate](../kernel6-build-20261111/README.md). The guest remained on normal
`7.0.0-38-kdlock1`, boot `51b49fa4-4d99-457e-a73e-632b690eb95e`, with taint 0.
No module was loaded and no selected API or MM body was executed in this stage.

The [NLS staging receipt](nls-stage/payload/result.json), SHA
`054ea3702187da1e24f9990b4f9bd10349952f839ff661fe89cbaca782d385a6`,
records ordinary off-root strip/sign staging of only `nls_iso8859-1.ko`.
Its signed bytes have SHA
`b00f793a4a39e3378beef5651bf6489ffa7b86985627529297a404384f769a4b`.
No real installed module namespace or boot file changed.

The [failed API-module receipt](failed-module-build/payload/receipts/result.json),
SHA `74820c075be566754f7e367cdc22a75526e80faf76ce79a4791796cc61274d67`,
retains the actual compile failure from fixture commit `0d0b52c0`: Linux 7
removed `no_llseek`. No signing, mmap-provider build or module load followed
that failed compiler invocation. Earlier attempt 01 stopped before compilation
at an idle observation; a later sample found its worker idle but does not
identify the original wait site.

The exact [VFS open source](vfs-open/payload/fs/open.c) clears `FMODE_LSEEK`
when the file operations have no seek callback. The exact
[seek source](vfs-seek/payload/fs/read_write.c) then returns `-ESPIPE`.
Fixture fix `80c272e5` therefore removes only `.llseek = no_llseek`; status
controllers already use a fresh fd for each read. `noop_llseek` would return a
successful unchanged position and was not used. Both exported source audits
retain their before/copy/after hashes and actual read-only commands.

A fresh 83-file snapshot changes only that fixture C file. All 77 kernel inputs
remain identical to source/installer `3512f5dd`, core `532b68a6`. The
[successful module receipt](module-build/payload/receipts/result.json), SHA
`293aabf920da108861ce7bc0f218cd3dc7ad639cc952ed2b58f9626e5f72a183`,
records rwsem build 0 in 2.266 s, mmap-provider build 0 in 2.013 s and both
ordinary sign commands returning 0. The failed output remains untouched.

| Signed module | SHA-256 |
| --- | --- |
| `kd_rwsem_api_fixture.ko` | `ef7090e53222f0b9de925ac5ad32937f3c2b7ddc3e8347564f239279703fc32e` |
| `kd_mmap_api_provider.ko` | `2d409ad3514d5b57678dc0ba772232dcd7a55e657f3c9c77e2da5218c89ab482` |

Both have release `7.0.0-38-kdrebuild6`, matching MODVERSIONS metadata, empty
module dependencies and the same SHA-512 signing identity as the staged NLS
module. Unsigned originals remain separate. Private key bytes are not collected.
The already built client, SHA
`0622af43f5ccdff2d181fdf6d68f9aa882837d830310e5b9667083e0f3de22d3`,
was reused after exact source/ABI matching; it was not rerun in this stage.

Actual kernel artifacts, protected namespaces, source and boot hashes remained
unchanged, with strict idle checks before and after. Installation, new boot
identity, twelve-case native compatibility, selected real syscalls and private
JIT regressions require separate receipts. This stage supplies no performance
or generated-execution result.
