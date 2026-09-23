# 显式 spin API 负载

`module.c` 管理 ioctl、工作者计数和快照；`payload.h` 按 1/2/4/8/16 cacheline
展开更新；`hash_payload.h` 是 RCUHT 锁内负载；`post_work.h` 保留锁外计算。
`direct.h` 按 `SC_BACKEND=native|tclock|kdlock` 选择 API；KD 使用独立四字节
`kd_spinlock_t`，不与普通 Linux 锁混用。

KD 使用 `KD_SPIN_DIRECT_LOCK/UNLOCK` 热度分流壳。
observe/adaptive 均根据当前 CPU 热度选择入口：
冷 CPU 调用 `kd_spin_direct_native_lock`，热 CPU 调用 `kd_spin_lock_pinned_clobber_v1`。
不手工push/pop，允许编译器在分支前保存活跃寄存器。所有body及锁
统一传`kd_spin_direct_cookie`：一个CPU一份，直接引用该CPU已有的`rate_hot`。
cookie仅代表CPU热度，不记录路径或嵌套深度。解锁统一调用 broad-clobber 入口并传递
lock/SP/IP/BP；provider 检查低字节状态 5，先做短原生释放，否则进入通用解锁核心。
仅外层使用配对壳，内层仍走原接口。冷获取仍是完整CAS/pending/MCS；
两种准入模式均在实际 MCS 发布处采样 CPU 热度，不检查队列深度；2/3线程也可因入队升温。

`scenario.h` 的默认 plain 不增加锁，nested/early 只对 KD cacheline 启用。
`SC_PREPARE` 显式登记对应锁后 RIP，`api.h` 定义客户端和模块共同使用的 ioctl。

三后端构建、预热、计数和排空由 [直接运行器](../../bench/tclock_compare/README.md)
负责。三种直接负载保持相同编译/UBSAN 设置，内核运行配置不随负载修改。
不要使用旧透明 hook 扫描入口，也不要单独换载源码模块后复用旧 JIT 会话。
