# Negative observations and attribution limits

Every negative baseline KD/TCLock observation, equal-worker KD NUMA observation, and full-grid candidate/baseline observation is listed below. Positive results remain in the complete point tables. This index links each affected path to the measured mechanism or marks it unresolved; it does not claim that every one-round difference has an isolated root cause. Negative component observations are included; their complete three-point tables are in COMPONENTS.md.

Source references for the main mechanisms use `1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`, except where another commit is stated. Withdrawn grouping is described in ANALYSIS.md at `822036777ae5731f24c56cbf50751d6e075ed1e1`.

## rwlock-admission

Native slow-reader gate transfer and globally updated reader count dominate sampled cycles; remote modified-line loads rise on split nodes. Exact per-point cost not isolated.

Source: `include/kd_rwlock.h:56; kernel_module/spin/nondelegated.inc:46; tclock_backend/komb_rwlock.c:808`.

## rwsem-entry

Verified unnecessary fast-success frame and final-reader context work; one-worker profiles support entry/release overhead. Candidate changes this path.

Source: `kernel_module/kd_rwsem.c:88,181,201 (1ba4cc6e); kd_down_read disassembly (87a3a41f)`.

## rwsem-phase

Reader OSQ handoff and exact writer phase/ACK coordination dominate contended samples; remote transfer/DRAM events increase. Individual protocol costs not isolated.

Source: `kernel_module/kd_rwsem.c:127,142,406,425,437; kernel_module/kd_mutex_osq.c:113; tclock_backend/aqs.c:131,397`.

## mutex-handoff

Metadata/notification transfer and bounded NUMA selection remain; split c16 remote modified-line loads increase. Small c01 penalty lacks address-level attribution.

Source: `kernel_module/mutex/waiter.inc; kernel_module/mutex/combiner.inc:478,510`.

## spin-handoff

Queue/notification/stack handoff is the sampled wait path. No object-level remote event attribution; small one-round differences remain uncertain.

Source: `kernel_module/spin/wait.inc; kernel_module/spin/queue.inc; kernel_module/spin/combiner.inc`.

## unresolved

No isolated causal attribution for this score; retain the negative value without inventing a code defect.

Source: `ANALYSIS.md: Attribution boundaries for individual regressions`.

## 87a3a41f KD/TCLock

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| mutex c01 w100 | contiguous/1 | -0.12% | unresolved |
| mutex c16 w100 | contiguous/1 | -0.06% | unresolved |
| rwlock c01 w001 | contiguous/36 | -2.05% | rwlock-admission |
| rwlock c01 w001 | contiguous/60 | -12.65% | rwlock-admission |
| rwlock c01 w020 | contiguous/60 | -18.81% | rwlock-admission |
| rwlock c01 w020 | split32/32 | -20.31% | rwlock-admission |
| rwlock c16 w001 | contiguous/1 | -0.09% | unresolved |
| rwlock c16 w001 | contiguous/32 | -8.16% | rwlock-admission |
| rwlock c16 w001 | contiguous/36 | -27.09% | rwlock-admission |
| rwlock c16 w001 | contiguous/60 | -22.61% | rwlock-admission |
| rwlock c16 w001 | split32/32 | -8.98% | rwlock-admission |
| rwlock c16 w020 | contiguous/36 | -16.32% | rwlock-admission |
| rwlock c16 w020 | contiguous/60 | -36.65% | rwlock-admission |
| rwlock c16 w020 | split20/20 | -33.00% | rwlock-admission |
| rwlock c16 w020 | split32/32 | -38.39% | rwlock-admission |
| rwsem c01 w001 | contiguous/1 | -6.67% | rwsem-entry |
| rwsem c01 w001 | contiguous/32 | -3.89% | rwsem-phase |
| rwsem c01 w001 | contiguous/60 | -5.04% | rwsem-phase |
| rwsem c01 w020 | contiguous/1 | -5.61% | rwsem-entry |
| rwsem c01 w020 | contiguous/20 | -3.84% | rwsem-phase |
| rwsem c01 w020 | contiguous/32 | -14.58% | rwsem-phase |
| rwsem c01 w020 | contiguous/36 | -16.41% | rwsem-phase |
| rwsem c01 w020 | contiguous/60 | -20.45% | rwsem-phase |
| rwsem c01 w020 | split20/20 | -15.20% | rwsem-phase |
| rwsem c01 w020 | split32/32 | -17.17% | rwsem-phase |
| rwsem c16 w001 | contiguous/1 | -7.00% | rwsem-entry |
| rwsem c16 w001 | contiguous/8 | -9.15% | unresolved |
| rwsem c16 w001 | contiguous/20 | -1.32% | rwsem-phase |
| rwsem c16 w001 | contiguous/32 | -1.58% | rwsem-phase |
| rwsem c16 w001 | contiguous/36 | -1.44% | rwsem-phase |
| rwsem c16 w001 | split20/20 | -1.31% | rwsem-phase |
| rwsem c16 w020 | contiguous/1 | -5.80% | rwsem-entry |
| rwsem c16 w020 | contiguous/60 | -5.89% | rwsem-phase |

## 87a3a41f split/same

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| mutex c01 w100 | split20/20 | -9.01% | mutex-handoff |
| mutex c01 w100 | split32/32 | -2.79% | mutex-handoff |
| mutex c16 w100 | split32/32 | -2.35% | mutex-handoff |
| rwlock c01 w001 | split20/20 | -15.51% | rwlock-admission |
| rwlock c01 w001 | split32/32 | -8.26% | rwlock-admission |
| rwlock c01 w020 | split20/20 | -32.52% | rwlock-admission |
| rwlock c01 w020 | split32/32 | -39.38% | rwlock-admission |
| rwlock c16 w001 | split20/20 | -18.99% | rwlock-admission |
| rwlock c16 w001 | split32/32 | -12.25% | rwlock-admission |
| rwlock c16 w020 | split20/20 | -40.38% | rwlock-admission |
| rwlock c16 w020 | split32/32 | -41.57% | rwlock-admission |
| rwsem c01 w001 | split20/20 | -18.45% | rwsem-phase |
| rwsem c01 w001 | split32/32 | -4.83% | rwsem-phase |
| rwsem c01 w020 | split20/20 | -35.93% | rwsem-phase |
| rwsem c01 w020 | split32/32 | -28.72% | rwsem-phase |
| rwsem c16 w001 | split20/20 | -15.96% | rwsem-phase |
| rwsem c16 w001 | split32/32 | -11.54% | rwsem-phase |
| rwsem c16 w020 | split20/20 | -31.14% | rwsem-phase |
| rwsem c16 w020 | split32/32 | -29.28% | rwsem-phase |
| spin c01 w100 | split20/20 | -4.75% | spin-handoff |
| spin c01 w100 | split32/32 | -3.26% | spin-handoff |
| spin c16 w100 | split20/20 | -4.22% | spin-handoff |
| spin c16 w100 | split32/32 | -3.51% | spin-handoff |

## 82203677 candidate/baseline

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| mutex c01 w100 | contiguous/1 | -0.03% | unresolved |
| mutex c01 w100 | contiguous/8 | -0.65% | unresolved |
| mutex c01 w100 | contiguous/32 | -1.59% | unresolved |
| mutex c01 w100 | contiguous/36 | -2.24% | unresolved |
| mutex c16 w100 | contiguous/1 | -0.00% | unresolved |
| mutex c16 w100 | contiguous/8 | -7.05% | unresolved |
| mutex c16 w100 | contiguous/32 | -2.08% | unresolved |
| mutex c16 w100 | split20/20 | -1.69% | unresolved |
| rwlock c01 w001 | contiguous/1 | -0.02% | unresolved |
| rwlock c01 w001 | contiguous/36 | -11.27% | rwlock-admission |
| rwlock c01 w001 | contiguous/60 | -5.69% | rwlock-admission |
| rwlock c01 w001 | split20/20 | -10.25% | rwlock-admission |
| rwlock c01 w001 | split32/32 | -11.31% | rwlock-admission |
| rwlock c01 w020 | contiguous/8 | -5.13% | rwlock-admission |
| rwlock c01 w020 | contiguous/20 | -2.16% | rwlock-admission |
| rwlock c01 w020 | contiguous/32 | -6.85% | rwlock-admission |
| rwlock c01 w020 | contiguous/36 | -10.09% | rwlock-admission |
| rwlock c01 w020 | contiguous/60 | -8.76% | rwlock-admission |
| rwlock c01 w020 | split20/20 | -6.65% | rwlock-admission |
| rwlock c16 w001 | contiguous/8 | -0.31% | rwlock-admission |
| rwlock c16 w001 | contiguous/20 | -7.86% | rwlock-admission |
| rwlock c16 w001 | contiguous/32 | -10.25% | rwlock-admission |
| rwlock c16 w001 | contiguous/36 | -12.40% | rwlock-admission |
| rwlock c16 w001 | contiguous/60 | -18.46% | rwlock-admission |
| rwlock c16 w001 | split20/20 | -17.11% | rwlock-admission |
| rwlock c16 w001 | split32/32 | -23.48% | rwlock-admission |
| rwlock c16 w020 | contiguous/1 | -0.07% | unresolved |
| rwlock c16 w020 | contiguous/8 | -10.15% | rwlock-admission |
| rwlock c16 w020 | contiguous/20 | -6.62% | rwlock-admission |
| rwlock c16 w020 | contiguous/32 | -7.15% | rwlock-admission |
| rwlock c16 w020 | contiguous/36 | -3.37% | rwlock-admission |
| rwsem c01 w001 | contiguous/8 | -28.88% | unresolved |
| rwsem c01 w001 | contiguous/20 | -0.28% | rwsem-phase |
| rwsem c01 w020 | contiguous/20 | -0.80% | rwsem-phase |
| rwsem c16 w001 | contiguous/60 | -1.69% | rwsem-phase |
| rwsem c16 w001 | split32/32 | -3.63% | rwsem-phase |
| spin c01 w100 | contiguous/1 | -0.02% | unresolved |
| spin c16 w100 | contiguous/1 | -0.01% | unresolved |
| spin c16 w100 | contiguous/32 | -0.33% | unresolved |
| spin c16 w100 | split20/20 | -0.44% | unresolved |
| spin c16 w100 | split32/32 | -0.13% | unresolved |

## 1ba4cc6e candidate/baseline

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| mutex c01 w100 | contiguous/1 | -0.05% | unresolved |
| mutex c01 w100 | contiguous/20 | -0.75% | unresolved |
| mutex c01 w100 | contiguous/32 | -0.52% | unresolved |
| mutex c01 w100 | contiguous/36 | -0.76% | unresolved |
| mutex c16 w100 | contiguous/8 | -1.18% | unresolved |
| mutex c16 w100 | contiguous/32 | -0.85% | unresolved |
| mutex c16 w100 | split20/20 | -4.10% | unresolved |
| mutex c16 w100 | split32/32 | -0.94% | unresolved |
| rwlock c01 w001 | contiguous/20 | -6.12% | unresolved |
| rwlock c01 w001 | contiguous/36 | -0.84% | unresolved |
| rwlock c01 w001 | split20/20 | -10.32% | unresolved |
| rwlock c01 w020 | contiguous/1 | -0.07% | unresolved |
| rwlock c01 w020 | contiguous/8 | -8.45% | unresolved |
| rwlock c01 w020 | contiguous/20 | -0.62% | unresolved |
| rwlock c01 w020 | contiguous/32 | -0.34% | unresolved |
| rwlock c01 w020 | split20/20 | -11.55% | unresolved |
| rwlock c16 w001 | contiguous/8 | -10.49% | unresolved |
| rwlock c16 w001 | contiguous/20 | -0.67% | unresolved |
| rwlock c16 w001 | contiguous/60 | -0.75% | unresolved |
| rwlock c16 w001 | split20/20 | -3.00% | unresolved |
| rwlock c16 w001 | split32/32 | -3.25% | unresolved |
| rwlock c16 w020 | contiguous/1 | -0.03% | unresolved |
| rwlock c16 w020 | contiguous/8 | -1.31% | unresolved |
| rwlock c16 w020 | contiguous/32 | -1.61% | unresolved |
| rwlock c16 w020 | contiguous/36 | -0.51% | unresolved |
| rwlock c16 w020 | contiguous/60 | -1.49% | unresolved |
| rwlock c16 w020 | split20/20 | -1.03% | unresolved |
| rwsem c01 w001 | contiguous/8 | -21.90% | unresolved |
| rwsem c01 w001 | split32/32 | -4.81% | rwsem-phase |
| rwsem c01 w020 | contiguous/20 | -2.63% | rwsem-phase |
| spin c01 w100 | contiguous/60 | -0.26% | unresolved |
| spin c16 w100 | contiguous/1 | -0.02% | unresolved |
| spin c16 w100 | contiguous/32 | -0.38% | unresolved |
| spin c16 w100 | contiguous/36 | -0.66% | unresolved |
| spin c16 w100 | contiguous/60 | -0.06% | unresolved |

## 4df80e5a component/baseline

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| rwsem c01 w001 | contiguous/1 | -0.17% | unresolved |
| rwsem c01 w001 | contiguous/8 | -29.63% | unresolved |

## 25282540 component/baseline

| Workload | Placement/workers | Change | Attribution |
|---|---|---:|---|
| rwsem c01 w001 | contiguous/8 | -30.76% | unresolved |
| rwsem c16 w020 | split20/20 | -7.98% | unresolved |
