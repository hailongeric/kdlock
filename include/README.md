# 接口与共享布局

这里放跨编译单元、内核与翻译器共享的接口，以及必须内联的热路径。
后端私有实现见 [kernel_module/README.md](../kernel_module/README.md)，
Demo ioctl 和数据布局见 [workload_modules/README.md](../workload_modules/README.md)。
头文件较短，按接口边界保留，避免将字段与其使用约束拆散。

| 职责 | 文件 | 关键约束 |
| --- | --- | --- |
| hook 与嵌套 CALL | [kd_lock.h](kd_lock.h) | 原生、已选择和合并 spin 入口不同 |
| spin 调度 | [kd_spinlock.h](kd_spinlock.h)、[qspinlock_i.h](qspinlock_i.h) | 调度节点/私有队列字与 Linux 原锁 L 分离 |
| spin gate/引用 | [kd_spin_gate.h](kd_spin_gate.h)、[kd_spin_entry.h](kd_spin_entry.h) | physical owner、ticket、logical origin 各有生命周期 |
| 原生快路径 | [kd_spin_fast.h](kd_spin_fast.h)、[kd_spin_select.h](kd_spin_select.h)、[kd_comm.h](kd_comm.h) | 可关闭的原生站点缓存、无竞争 S/L hold 和在途 owner；缓存键不重复回填 |
| mutex 调度 | [kd_mutex.h](kd_mutex.h) | 原 mutex owner 保留，原 waiter 可继续后缀 |
| frame/控制事务 | [kd_exec.h](kd_exec.h)、[kd_call.h](kd_call.h) | physical parent、logical resume_target、锁记录、最后 ACK |
| 注册/执行 | [exe.h](exe.h)、[exe_info.h](exe_info.h) | 注册槽、entry_abi 身份与 packet_state；NORMAL 不证明正文执行 |
| 热锁 | [kd_hotlock.h](kd_hotlock.h) | 固定窗口频率晋升；sticky IGNORE/DELEGATE，无自适应降级 |
| 来源生命周期 | [kd_source.h](kd_source.h)、[kd_source_api.h](kd_source_api.h) | 内部 pin 接口与设备 ABI；retire 不可撤销 |
| 设备/诊断 | [sys.h](sys.h)、[utils.h](utils.h) | 设备注册和既有日志，benchmark quiet 仅在专用 provider |
| 批次调用边界 | [kd_jit_batch.h](kd_jit_batch.h) | 新旧 wrapper 的版本目录和编译器 clobber；旧批次入口只额外保护物理 RBP，args 仍为两个元素 |
| wrapper 布局 | [wrapper.S](wrapper.S)、[asm_head.h](asm_head.h) | x86-64 保存现场、pt_regs 偏移与两元素参数 |
| 服务/段语义 | [kd_hostcall.h](kd_hostcall.h)、[kd_hostcalls.def](kd_hostcalls.def)、[kd_segment.h](kd_segment.h) | 有界服务能力与既有 GS 输入 |

修改布局时同时检查 C、生成汇编与 Python 解析器，不能只改变一侧结构体。
寄存器约定见 [JIT_REGISTER_ABI.md](../docs/JIT_REGISTER_ABI.md)。frame 锁记录
只描述实际获取/释放，本身不取得原锁；完成事件、owner ACK、frame pop 和
source pin 释放是不同边界。
