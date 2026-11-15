# Offline compiler and kernel16 input assessment

The bounded local preflight is complete. An offline paired spin build is not ready with the inspected local inputs. No source disk was mounted, no remote machine was contacted, and no compiler/package/key/module action was performed.

## Concrete compiler provenance

The completed archived nano receipt has status NANO_MODULES_BUILT_SIGNED for release 7.0.0-38-kdrebuild16. It records /usr/bin/x86_64-linux-gnu-gcc resolving to /usr/bin/x86_64-linux-gnu-gcc-15, SHA256 b5f1b773a7c733738352000c92a077dc5852a1a2fc6d836b1e411be1e9ec5f88. The independent expected-kernel receipt agrees and records executable size 1,305,304 bytes. Retained kernel16.config identifies gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0, assembler/linker version 24600, and pahole version 131.

These are compiler binary/build provenance, not an authenticated Debian package receipt. No exact .deb, package digest, package dependency closure, or original installed-package record was established in the inspected local artifacts. No public package availability is asserted. Host GCC defaults to 11.4; installed command inventory includes GCC11/12 but no GCC15. /var/cache/apt/archives contains no .deb. No alternate GCC15 environment was found in the inspected /usr/local or /opt inventory.

## Exact kernel metadata located

The retained expected-kernel and completed nano receipts bind source 7338197a587fd84110fe710be63abafde270c02b and Build ID 40d0694cb395dfcc98f8275d033b96797d2e5cb2. They agree on:

- .config: 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483
- Module.symvers and vmlinux.symvers: de0efc1f0aedfe4b2f48fe2d01a4fa6dfa9082b9af71ed572f8844f5ac8781b8
- include/config/auto.conf: d731f7137d4af0af8468041db3b03292d174ed184d3916fa9162a29cb8f63243
- include/generated/autoconf.h: ba620d16cd34149765ecae7223c519826d89e1bd51ef996f25af495b7cf18314
- include/generated/utsrelease.h: 2f11a6341f8e8ee26c7592cf5d7ff1a72ed00c92a0837d5728ecc80047cb9406
- Full vmlinux: 3026a7a5b496833a10ea58c0cf7e7be3c60aa6ee5249e137f5506aca81579b1a. elf-copy.json records 511,688,152 bytes.

All tool and generated-file hashes are retained in result.json. The old build root is /mnt/kdlock-builds2/kdlock-main-kernel16-7338197a-01, with source/ and build/. Those paths are absent on this host. The filename inventory under local kdlock-evidence did not find actual Module.symvers, generated headers or full vmlinux. The known /tmp/kdlock-kernel16-prerequisite-20261114/vmlinux is the 71,026,728-byte boot-extracted stripped ELF, not the original full ELF. Local kernel16 image/config and the isolated KD source lane remain available, but they do not constitute the Linux source plus prepared Kbuild output.

The three recorded Super-Server image paths are absent on 380G10. The differently named local ubuntu22.04_mal.qcow2 was not treated as the source disk and was not opened. Remote access would exceed this turn's no-other-machine-work scope. Consequently current source-disk compiler/package/header contents were not inspected. No automatic approval rejection occurred in this turn.

## Build practicality and missing inputs

The historical successful module build invokes make -C <kernel source> O=<kernel output> M=<module source> MO=<separate output> KERNELRELEASE=7.0.0-38-kdrebuild16 modules, followed by a separate sign-file operation. This establishes that module compilation and signing are separate steps in this workflow. An unsigned offline artifact does not inherently require exporting a signing key. It is not load-ready evidence.

Before attempting that path, supply the exact GCC15 toolchain and its runtime dependencies, compatible recorded binutils, the exact Linux source/private KD headers, prepared generated headers/config, Module.symvers, and Kbuild helper programs including modpost/objtool as required by the target. Their actual availability and host executability remain unverified. CONFIG_DEBUG_INFO_BTF_MODULES=y also makes the exact full ELF and compatible BTF tooling relevant. The receipts are hash references, not replacement build inputs.

The existing isolated Python builder additionally requires a matching running kernel and signs automatically. A separately reviewed offline entry must validate the target files explicitly and preserve source/header checks while keeping unsigned output explicit. This preflight does not modify or bypass the existing builder. No full kernel rebuild is indicated by the available historical completed-build evidence, but a complete usable local prepared build environment has not been established.

No module compile, controller compile, symbol CRC/vermagic test, signature test, runtime admission or timing ran. Source, recovery, profiles, harness and disks were left unchanged. Fresh-process recovery remains untested.
