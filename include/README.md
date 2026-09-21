# 接口与共享布局

`kd_hotlock.h` 使用 `record_spin/record_mutex` 合并计数与热度判断，时钟按 10240 个样本批量更新；`query_*` 只读缓存热值。公共 spin 入口关闭代理时跳过记录。

这里放跨编译单元、内核与翻译器共享的接口，以及必须内联的热路径。
后端私有实现见 [kernel_module/README.md](../kernel_module/README.md)，
Demo ioctl 和数据布局见 [workload_modules/README.md](../workload_modules/README.md)。
头文件较短，按接口边界保留，避免将字段与其使用约束拆散。

| 职责 | 文件 | 关键约束 |
| --- | --- | --- |
| hook 与嵌套 CALL | [kd_lock.h](kd_lock.h) | mutex 路由和两类型嵌套控制 CALL |
| spin 调度 | [kd_spinlock.h](kd_spinlock.h)、[qspinlock_i.h](qspinlock_i.h) | 显式 KD 单锁字、128 字节节点及 768 字节 continuation；禁止与 Linux 锁协议混用 |
| mutex 调度 | [kd_mutex.h](kd_mutex.h) | 原 mutex owner 保留，原 waiter 可继续后缀 |
| frame/控制事务 | [kd_exec.h](kd_exec.h)、[kd_call.h](kd_call.h) | physical parent、logical resume_target、锁记录；spin pop 后通知，native ACK 与退休分离 |
| 注册/执行 | [exe.h](exe.h)、[exe_info.h](exe_info.h) | 注册槽、entry_abi 身份与 packet_state；NORMAL 不证明正文执行 |
| 热锁 | [kd_hotlock.h](kd_hotlock.h) | 分类型 per-CPU 16 桶/6 候选，score-error 保守阈值；无全局晋升集合 |
| 来源生命周期 | [kd_source.h](kd_source.h)、[kd_source_api.h](kd_source_api.h) | 内部 pin 接口与设备 ABI；retire 不可撤销 |
| 设备/诊断 | [sys.h](sys.h)、[utils.h](utils.h) | 设备注册和既有日志，benchmark quiet 仅在专用 provider |
| 批次调用边界 | [kd_jit_batch.h](kd_jit_batch.h) | 新旧 wrapper 的版本目录和编译器 clobber；clobber wrapper 保护物理 RBP；旧批次适配单独保护 RBP，偏移 0 普通入口保留 C ABI，args 仍为两个元素 |
| wrapper 布局 | [wrapper.S](wrapper.S)、[asm_head.h](asm_head.h) | x86-64 保存现场、pt_regs 偏移与两元素参数 |
| 服务/段语义 | [kd_hostcall.h](kd_hostcall.h)、[kd_hostcalls.def](kd_hostcalls.def)、[kd_segment.h](kd_segment.h) | 有界服务能力与既有 GS 输入 |

修改布局时同时检查 C、生成汇编与 Python 解析器，不能只改变一侧结构体。
寄存器约定见 [JIT_REGISTER_ABI.md](../docs/JIT_REGISTER_ABI.md)。frame 锁记录
只描述实际获取/释放，本身不取得原锁；完成事件、owner ACK、frame pop 和
continuation 存储回收和 source pin 释放是不同边界。
每 CPU 区域、字段偏移与数据流见 [EXECUTION_PATHS](../bench/spin_cacheline/EXECUTION_PATHS.md)，
这些内嵌对象尺寸不能重复计入总分配。

显式 KD 对象见 [kd_spin_type.h](kd_spin_type.h)，直接调用 ABI 见
[kd_spin_direct.h](kd_spin_direct.h)；稳定 ticket 见 [kd_spin_entry.h](kd_spin_entry.h)。
