# Reader recovery MM recipe

Prepare a separate 7.0.0-38-kdscope4 kernel for the reader-only ablation
66c68c17457c0ae60d09ff1f3d89b5fff16a500c. Keep all four production provider
files byte-identical to that candidate; preserve native MM bodies and syscall
workloads. The existing scope1 and scope3 kernels remain separate reference
arms. Do not overwrite their sources, builds, bundles or measurements.

Reuse the scope3 integration recipe and the validated de5e4f06 return-site and
API queue observations. Add an explicit scope4 identity and configuration;
changing a release name must never imply matching runtime identity. Each arm
needs its own actual boot, full schema-2 binding and fresh correctness results.
The new variant retains local MM execution and never delegates reads.

The user-approved second build-disk growth to 160 GiB provides more than the
existing 50 GiB preparation reserve. Build only on the VM after Nano is idle.
Run one round per point of unchanged mmap1 threads and processes, keeping source,
topology and each kernel's receipts separate. The old -22.39% process loss is
unresolved. A different worker distribution alone does not identify its cause.
