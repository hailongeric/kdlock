# 锁协议场景模块

[klock_module.c](klock_module.c) 组织共享组件、分派 ioctl、初始化和清理。
普通 mode 的参数、数据语义和入口保持兼容；用户态驱动仍从
[bench/klock_test.c](../../bench/klock_test.c) 单文件编译。

`common/` 放原锁、角色状态、GS/native-resume 探针和完整性检查；`modes/`
按普通场景与参与者角色组织；`fragments/` 保留独立的 gate/ticket/routing、
信号、双 mutex 队列、深层远端续跑等协议场景。

| 所属入口 | 组件 | 职责 |
| --- | --- | --- |
| `klock_module.c` | [common/resume.inc](common/resume.inc) | Shared original locks and per-request native-resume oracle/probe state. |
| `klock_module.c` | [common/integrity.inc](common/integrity.inc) | Deterministic per-lock payload transitions and completion counters. |
| `klock_module.c` | [common/depth.inc](common/depth.inc) | Learned deep-mutex callee used by the bounded lock-depth workload. |
| `klock_module.c` | [common/roles.inc](common/roles.inc) | Role synchronization gates and stable mode numbers for the ioctl driver. |
| `klock_module.c` | [common/gs_probe.inc](common/gs_probe.inc) | GS/current oracle for native and delegated bodies, with origin CPU storage. |
| `klock_module.c` | [modes/spin_basic.inc](modes/spin_basic.inc) | Single, nested, deep and out-of-order spin critical sections (modes 0/1/6/7). |
| `klock_module.c` | [modes/spin_inner.inc](modes/spin_inner.inc) | Inner-B participants, pending-lock observations and native/JIT continuation. |
| `klock_module.c` | [modes/spin_outer.inc](modes/spin_outer.inc) | Holder/successor roles and mode-8 routing for independent A/B contention. |
| `klock_module.c` | [modes/spin_abort.inc](modes/spin_abort.inc) | Isolated mode-9 abort roles; fault diagnosis is not an ordinary benchmark. |
| `klock_module.c` | [modes/spin_service.inc](modes/spin_service.inc) | Mode-2 bounded service CALLs inside the original spin critical section. |
| `klock_module.c` | [modes/mutex_basic.inc](modes/mutex_basic.inc) | Mode-3 native/mixed admission and contention, including interruptible APIs. |
| `klock_module.c` | [modes/mutex_nested.inc](modes/mutex_nested.inc) | Nested mutex A/B bodies and GS roles; real owners are retained (mode 4/11). |
| `klock_module.c` | [modes/mutex_contenders.inc](modes/mutex_contenders.inc) | Independent mutex holder/waiter roles, queue observations and role dispatch. |
| `klock_module.c` | [modes/mutex_service.inc](modes/mutex_service.inc) | Mode-5 bounded services and the separate post-promotion CALL-quota phase. |
| `klock_module.c` | [common/validate.inc](common/validate.inc) | After-drain integrity oracle: recompute every active per-lock payload. |
| `remote_depth_workload.c` | [fragments/remote_depth/callee.inc](fragments/remote_depth/callee.inc) | Deep chained critical sections and per-request native suffix probes. |
| `remote_depth_workload.c` | [fragments/remote_depth/participants.inc](fragments/remote_depth/participants.inc) | Direct/holder/follower roles and observers for the remote chain. |
| `mutex_parallel_workload.c` | [fragments/mutex_parallel/native.inc](fragments/mutex_parallel/native.inc) | Independent lane validation and native CALL bodies retaining two real owners. |

`common/integrity.inc` 是实际临界区的状态变换，`common/validate.inc` 只在
排空后重算校验；`common/resume.inc` 保留每请求 before/called/after 记录，
防止重放被总计数掩盖。不能在工作期间重置记录来制造通过。

`.c` 片段和 `.inc` 仍在同一编译单元中，必须保持包含顺序、static 原锁/记录
和内联正文，不能单独加载。`fragments/remote_depth_workload.c` 与
`fragments/mutex_parallel_workload.c` 保留参数、分派和生命周期，具体参与者
和 native CALL 已分到各自子目录。`kd_depth_source.c/.h` 是可选独立来源模块，
仅在 `KDLOCK_SOURCE_HELPER=1` 时构建。角色时序、实际 JIT 与 owner/ACK 验收见
[tests/README.md](../../tests/README.md)，这里不复制测试成绩。
