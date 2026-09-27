# 显式 spin API 负载

`module.c` 管理 ioctl、工作者计数和快照；`payload.h` 按 1/2/4/8/16 cacheline
展开更新；`hash_payload.h` 是 RCUHT 锁内负载；`post_work.h` 保留锁外计算。
`direct.h` 按 `SC_BACKEND=native|tclock|kdlock` 选择 API；KD 使用独立四字节
`kd_spinlock_t`，不与普通 Linux 锁混用。

KD 使用 `KD_SPIN_DIRECT_LOCK/UNLOCK` 热度分流壳。
当前仅保留adaptive，根据当前CPU热度选择入口：冷CPU内联首次CAS，失败后调用
`kd_spin_direct_native_contended`；热CPU调用 `kd_spin_lock_pinned_clobber_v1`。
不手工push/pop，允许编译器在分支前保存活跃寄存器。所有body及锁
统一传`kd_spin_direct_cookie`：它是唯一的静态per-CPU unsigned-int热值，所有锁共享，
通过`this_cpu_read`直接读取，不再经指针访问动态表。cookie不记录路径或嵌套深度；
导出符号由指针改为标量，provider及直接调用者须一起重编译。解锁统一调用 broad-clobber 入口并传递
lock/SP/IP/BP；provider 检查低字节状态 5，先做短原生释放，否则进入通用解锁核心。
仅外层使用配对壳，内层仍走原接口。冷获取仍是完整CAS/pending/MCS；
实际MCS发布处采样CPU热度，不检查队列深度；2/3线程也可因入队升温。
`spin_entry_ratio_limit=0`只关闭比例过滤，不强制CPU/单锁变热，也不改变正文或调用ABI。

`scenario.h` 的默认 plain 不增加锁，nested/early 只对 KD cacheline 启用。
`SC_PREPARE` 显式登记对应锁后 RIP，`api.h` 定义客户端和模块共同使用的 ioctl。

三后端构建、预热、计数和排空由 [直接运行器](../../bench/tclock_compare/README.md)
负责。三种直接负载保持相同编译/UBSAN 设置，内核运行配置不随负载修改。
不要使用旧透明 hook 扫描入口，也不要单独换载源码模块后复用旧 JIT 会话。

cacheline与hash均支持固定迭代和连续计时。计时循环每256次完整操作发布worker进度并检查截止时间；
hash保持原随机键/锁内正文和worker-local结果计数，结束时才汇总三类结果。
计时外的静止快照验证完整hash结构与精确操作总数，不能用近似进度代替业务校验。
