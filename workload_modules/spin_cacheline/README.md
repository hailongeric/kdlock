# 显式 spin API 负载

`module.c` 管理 ioctl、工作者计数和快照；`payload.h` 按 1/2/4/8/16 cacheline
展开更新；`hash_payload.h` 是 RCUHT 锁内负载；`post_work.h` 保留锁外计算。
`direct.h` 按 `SC_BACKEND=native|tclock|kdlock` 选择 API；KD 使用独立四字节
`kd_spinlock_t`，不与普通 Linux 锁混用。

`SC_COLD_FASTPATH=1`编译内联CPU分流的clobber调用壳，默认仍为0（保留clobber壳）。
不手工push/pop，允许编译器在分支前保存活跃寄存器。所有body及锁
统一传`kd_spin_direct_cookie`：一个CPU一份，直接引用该CPU已有的`rate_hot`。
cookie仅代表CPU热度，不记录路径或嵌套深度；冷解锁由锁字低字节状态5决定。
本轮只接入外层，内层仍走原接口。冷获取仍是完整CAS/pending/MCS；
provider的`spin_hot_min_queue`可调冷态升温所需队列压力，0恢复旧MCS规则，默认4。

`scenario.h` 的默认 plain 不增加锁，nested/early 只对 KD cacheline 启用。
`SC_PREPARE` 显式登记对应锁后 RIP，`api.h` 定义客户端和模块共同使用的 ioctl。

三后端构建、预热、计数和排空由 [直接运行器](../../bench/tclock_compare/README.md)
负责。三种直接负载保持相同编译/UBSAN 设置，内核运行配置不随负载修改。
不要使用旧透明 hook 扫描入口，也不要单独换载源码模块后复用旧 JIT 会话。
