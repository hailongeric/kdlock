# 显式 spin API 负载

`module.c` 管理 ioctl、工作者计数和快照；`payload.h` 按 1/2/4/8/16 cacheline
展开更新；`hash_payload.h` 是 RCUHT 锁内负载；`post_work.h` 保留锁外计算。
`direct.h` 按 `SC_BACKEND=native|tclock|kdlock` 选择 API；KD 使用独立四字节
`kd_spinlock_t`，不与普通 Linux 锁混用。

`scenario.h` 的默认 plain 不增加锁，nested/early 只对 KD cacheline 启用。
`SC_PREPARE` 显式登记对应锁后 RIP，`api.h` 定义客户端和模块共同使用的 ioctl。

三后端构建、预热、计数和排空由 [直接运行器](../../bench/tclock_compare/README.md)
负责。三种直接负载保持相同编译/UBSAN 设置，内核运行配置不随负载修改。
不要使用旧透明 hook 扫描入口，也不要单独换载源码模块后复用旧 JIT 会话。
