# Spin nano artifact preflight

Stopped before compilation: the required Ubuntu GCC 15.2.0-16ubuntu1 is not available through the inspected host compiler commands. Host GCC is Ubuntu 11.4.0-1ubuntu1~22.04.3. No compiler installation, substitution, old guest boot, or toolchain transfer was attempted.

Passed: isolated patch SHA256 matches 5c3b54b4c2c0a77075f08f79b877738407a18a12fccce7f10ed65f8114110b2e. Retained kernel16 boot image and config hashes match the historical completed build receipt. The config identifies the required GCC version. The prior recovery receipt records live Build ID 40d0694cb395dfcc98f8275d033b96797d2e5cb2 and release 7.0.0-38-kdrebuild16; no new live verification occurred.

Historical evidence: the previously captured scene7 build receipt reports COMPLETED_AND_IDLE for source 7338197a587fd84110fe710be63abafde270c02b, with matching config/image hashes and Module.symvers de0efc1f0aedfe4b2f48fe2d01a4fa6dfa9082b9af71ed572f8844f5ac8781b8. This turn did not reopen the stopped source disk or freshly verify its generated headers, compiler binary hashes, full ELF, or output files. Provenance preflight is therefore partial.

The existing isolated build.py is VM-oriented: it checks the running kernel against the target release and signs modules using the old output directory's certs/signing_key.pem. It cannot be invoked unchanged on this host. No gate was weakened and no key was accessed or exported. CONFIG_MODULE_SIG_FORCE is unset, but that does not establish unsigned module admission; no unsigned artifact is described as load-ready.

Unrun: Native/KD module compilation, MODPOST, emitted routing review, symbol CRC/vermagic checks, signing, controller compilation, runtime loading, functional tests and timing. No new module artifacts exist. Prior isolated source checks remain historical source-only evidence.

Smallest prerequisite: an explicitly permitted offline build environment with the exact GCC toolchain and verified generated kernel16 inputs. The existing builder also needs a separately reviewed offline invocation that preserves target identity checks. Signing needs an authorized arrangement that does not export the old private key. This task expressly stops when the exact compiler is missing.

No shared checkout, VM, image, profile, recovery point, installed package or host setting was modified. Only this new /tmp evidence directory was written. Recovery verification remains limited to the same QEMU process/profile; fresh-process restore remains untested.
