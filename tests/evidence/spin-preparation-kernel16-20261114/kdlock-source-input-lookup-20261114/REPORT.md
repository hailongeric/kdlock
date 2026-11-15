# Stopped source input lookup

Read-only inspection on Super-Server completed through the established eric@10.176.26.71 SSH route. The original source guest stayed off. No processes held its three image paths open at the final lsof check. The unrelated kdclaude VM uses different disks and was left untouched. No native approval rejection occurred.

Both inspected disks were opened with guestfish --ro; ext4 mounts explicitly used ro,noload. Only file hashes, source/compiler metadata, directory inventories and package records were returned. No executable payloads, private keys or credentials were read/copied, and no build, package change, monitor or snapshot operation ran.

## Current compiler inputs

Present on the source system disk:

- /usr/bin/x86_64-linux-gnu-gcc-15: SHA256 b5f1b773a7c733738352000c92a077dc5852a1a2fc6d836b1e411be1e9ec5f88, exactly matching the historical compiler receipt.
- /usr/libexec/gcc/x86_64-linux-gnu/15/cc1: SHA256 30510b346885152c4fce41d2b501751c95d3690b1c34eaa04ebb970e70eae620. Its installed ownership list is cpp-15-x86-64-linux-gnu. No historical frontend hash was available for comparison.
- Package database: gcc-15, gcc-15-base, gcc-15-x86-64-linux-gnu, cpp-15, cpp-15-x86-64-linux-gnu and libgcc-15-dev all report install ok installed, version 15.2.0-16ubuntu1, amd64.
- binutils packages report 2.46-3ubuntu2; pahole reports 1.31-2ubuntu1. GCC, assembler, linker and make executable hashes all match the historical receipt.

packages.json records selected installed-package versions and dependency declarations, including libc6 2.43-2ubuntu2.4, GMP, ISL, MPC, MPFR, zstd, zlib and ELF/DWARF libraries. This is installed-package provenance, not a newly authenticated repository/.deb chain or a complete verified runtime dependency closure. The compiler package declares libc6 >=2.38, so copying only the compiler driver does not establish host executability.

The top-level apt archive cache contains no gcc-15 or cpp-15 compiler .deb. It has libobjc-15-dev 15.2.0-16ubuntu1, which is not a substitute. The compiler is available as installed files; no complete cached compiler package set was found.

The first bulk command completed all receipt comparisons and two helper hashes, then stopped at absent /usr/lib/gcc/x86_64-linux-gnu/15/cc1. That error is retained in stderr.txt and incomplete-metadata.txt. A separate bounded metadata lookup located and hashed the real libexec path. No failed build or missing actual frontend is implied by that initial path error.

## Current kernel16 inputs

Retained source/build root:
/mnt/kdlock-builds2/kdlock-main-kernel16-7338197a-01

All 126 recorded file comparisons matched: 15 build artifacts, 107 recorded source files, and four tools. The source comparisons cover the receipt's integration8, native_mm11 and package88 groups; they are not a whole Linux-tree inventory. Exact source identity remains bound to the recorded 7338197a587fd84110fe710be63abafde270c02b input.

Key current hashes:

- build/.config: 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483
- build/Module.symvers and vmlinux.symvers: de0efc1f0aedfe4b2f48fe2d01a4fa6dfa9082b9af71ed572f8844f5ac8781b8
- build/include/config/auto.conf: d731f7137d4af0af8468041db3b03292d174ed184d3916fa9162a29cb8f63243
- build/include/generated/autoconf.h: ba620d16cd34149765ecae7223c519826d89e1bd51ef996f25af495b7cf18314
- build/include/generated/utsrelease.h: 2f11a6341f8e8ee26c7592cf5d7ff1a72ed00c92a0837d5728ecc80047cb9406
- build/vmlinux: 3026a7a5b496833a10ea58c0cf7e7be3c60aa6ee5249e137f5506aca81579b1a, matching the original full ELF receipt, not the stripped boot extraction.
- build/scripts/mod/modpost: 667cd803c1315e228d7e7f0b44f150b0223bba70fcbb42b00589eae89ccf687a
- build/tools/objtool/objtool: 8000462015e9e63f7cf7da93685471adc96b80da2edb6c677622674e01db1ca1

kernel.release reads 7.0.0-38-kdrebuild16. compile.h records GCC15.2.0-16ubuntu1 and GNU binutils2.46. Matching the full ELF hash binds it to recorded Build ID 40d0694cb395dfcc98f8275d033b96797d2e5cb2; this turn did not execute readelf against a transferred ELF or perform a live check. All detailed comparisons are in result.json.

## Practical boundary

The exact installed compiler and the inspected prepared kernel16 inputs currently survive on the stopped source disks. They are not missing there. Standard unsigned external-module preparation can be considered without a signing-key export, but no build environment has been materialized or exercised on 380G10. A compatible userspace/tool dependency set, access to the prepared source/output files, and a reviewed offline invocation remain necessary. Full source completeness, helper executability, dynamic dependency closure, compilation, MODPOST, BTF generation, signing and runtime compatibility remain untested by this lookup.

No claim is made that an unsigned artifact is load-ready. The original VM and new recovery VM were not booted; recovery verification remains same-process only.
