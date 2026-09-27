# 接口与共享布局

`kd_hotlock.h`提供分类型per-CPU精确地址记录、spin获取/MCS近似计数及缓存CPU准入。
复用已有获取/MCS计数，MCS达到512时先以右移比较比例，清零两计数后采时；不再保存历史快照。
默认`spin_entry_ratio_limit=2`，即`(spin_entries >> 9) < 2`，在512次MCS时接受最多1023次获取。
IRQ统计允许近似；busy跳过时保留计数，下一次MCS重试，guard仍保护热表，小型pinned封装内联。
spin单锁达到512次检查12.5亿TSC窗口，mutex保持第1025次/25亿。
旧两低确认、冷却及热度保留已移除；当前策略与验证状态见[性能计划](../docs/PERFORMANCE_PLAN.md)。
完整语义与统计边界统一见[热度与角色](../docs/JIT_EXECUTION.md#21-热度与角色)。
热度接口仅返回自适应判断；原observe模式已移除，比例门槛0仍保留CPU/单锁热度要求。

这里放跨编译单元、内核与翻译器共享的接口，以及必须内联的热路径。
后端私有实现见 [kernel_module/README.md](../kernel_module/README.md)，
Demo ioctl 和数据布局见 [workload_modules/README.md](../workload_modules/README.md)。
头文件较短，按接口边界保留，避免将字段与其使用约束拆散。

| 职责 | 文件 | 关键约束 |
| --- | --- | --- |
| hook 与嵌套 CALL | [kd_lock.h](kd_lock.h) | mutex 路由和两类型嵌套控制 CALL |
| spin 调度 | [kd_spinlock.h](kd_spinlock.h)、[qspinlock_i.h](qspinlock_i.h) | 显式KD单锁字、128字节节点及704字节continuation；per-CPU节点数组显式128字节对齐，类型与通知偏移不变；禁止与Linux锁协议混用 |
| mutex 调度 | [kd_mutex.h](kd_mutex.h) | 原 mutex owner 保留，原 waiter 可继续后缀 |
| frame/控制事务 | [kd_exec.h](kd_exec.h)、[kd_call.h](kd_call.h) | physical parent、logical resume_target、锁记录；spin pop 后通知，native ACK 与退休分离 |
| 注册/执行 | [exe.h](exe.h)、[exe_info.h](exe_info.h) | 注册槽、entry_abi 身份与 packet_state；NORMAL 不证明正文执行 |
| 热锁 | [kd_hotlock.h](kd_hotlock.h) | 分类型 per-CPU 256 桶/256 精确地址记录，spin 竞争比例准入，无候选淘汰；热度不持有锁 |
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

## 显式 IRQ/BH spin 接口

包含`kd_spin_direct.h`，操作`kd_spinlock_t`；不能传入Linux的`spinlock_t/raw_spinlock_t`。
接口与对应Linux raw-spin变体的调用方式、IRQ/BH及抢占配对一致：

```c
DEFINE_KD_SPINLOCK(lock);
unsigned long flags;

kd_spin_lock_irqsave(&lock, flags);
/* IRQ关闭；flags保留此次获取前的状态。 */
kd_spin_unlock_irqrestore(&lock, flags);

kd_spin_lock_irq(&lock);
/* IRQ关闭；irq形式要求调用者原来允许中断。 */
kd_spin_unlock_irq(&lock); /* 无条件开启IRQ。 */

kd_spin_lock_bh(&lock);
/* 禁止本CPU软中断及抢占，保持硬IRQ原有状态。 */
kd_spin_unlock_bh(&lock);
```

嵌套获取不同锁时，每次irqsave使用独立的`unsigned long flags`；irqrestore恢复该次状态。
BH配对保留已有BH禁用层数，按目标内核普通task/softirq调用约束使用，不能用BH替代hard-IRQ保护。
所有变体先释放KD锁字/在途计数，再恢复IRQ/BH并允许抢占；解锁必须与获取形式配对。

这些变体固定在原CPU执行，共用现有KD锁字、pending/MCS队列和原生byte-5所有权，
无需`kd_spin_prepare`、continuation、cookie或daemon。IRQ/BH状态不传给远端combiner，
不可将它们当成已支持的JIT嵌套控制调用；翻译准入拒绝相应上下文符号。
普通`KD_SPIN_DIRECT_LOCK/UNLOCK`的自适应路径及默认IRQ/BH语义保持不变。
