# 内核临界区负载

这里放测试与 benchmark 的 Demo 内核模块及共享 ioctl/数据布局。
客户端与运行器分别在 `bench/`、`tests/`，生产锁协议在 `kernel_module/`。

| 子目录 | 用途 | 模块与设备 |
| --- | --- | --- |
| [lock_scenarios](lock_scenarios/README.md) | spin/mutex 嵌套、服务、原生续跑和协议场景 | `klock_module.ko`、`/dev/lock_dev` |
| [spin_cacheline](spin_cacheline/README.md) | 同一 spinlock 的固定展开 cacheline 微基准 | `spin_cacheline.ko`、`/dev/spin_cacheline` |

顶层 Makefile 委托给子目录，既有模块名和设备 ABI 保持兼容。
构建、快照与排空遵循 [操作手册](../docs/AGENTS.md)，只在 recovery guest 运行。
