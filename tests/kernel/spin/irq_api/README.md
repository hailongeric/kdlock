# IRQ/BH spin API 验证

这是普通 KD provider 的接口消费者，不需要 SELFTEST、daemon、JIT 注册或修改内核。
接口说明见 [include](../../../../include/README.md#显式-irqbh-spin-接口)。只在已核对
内核基线、空闲状态及 recovery 快照的 guest 执行，遵循[操作手册](../../../../docs/AGENTS.md)。

## 覆盖范围与运行

单线程检查 irqsave 的 IRQ-on/off 入口、独立 flags 的嵌套获取、irq 获取、BH
已有禁用层数及嵌套、IRQ-save 区间内的 plain-native 获取。每次检查 IRQ、BH、
preempt、per-CPU native 计数和已有 fast owner 在获取/释放前后的状态。

竞争检查使用四个绑定 CPU 的 worker，各执行 10,000 次；优先选择 CPU0/1/20/21，
不足时补充其他在线 CPU，至少需要三个。每个 worker 轮换 irqsave、irq、bh 和
plain-native，在同一 KD 锁下递增计数并核对上下文。plain-native 使用已有 byte-5
入口，不注册普通自适应入口。所有 worker 在 init 返回前退出并完成 join。

```sh
make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 -j8
make -C tests/kernel/spin/irq_api KDIR=/root/linux-6.1.159-kdclobber2 -j8
timeout 60 insmod kernel_module/kdlock_km.ko
timeout 60 insmod tests/kernel/spin/irq_api/kd_spin_irq_api_test.ko
# 核对本次 dmesg 的 PASS、精确计数和错误；命令超时不能视为已排空。
timeout 30 rmmod kd_spin_irq_api_test
timeout 30 rmmod kdlock_km
```

保留运行前后日志并匹配实际记录边界；日志环覆盖旧前缀时不能按整个旧日志的
`startswith` 判断失败，也不能按粗略 uptime 删除本次记录。模块加载超时须先
调查在途线程，不能按上述正常结束路径强制卸载。

本模块只证明原 CPU 执行的变体和 plain-native 共用锁；PASS 明确标注
`MCS=unobserved JIT=0`。临界区的短暂 pause 增加竞争机会，不是进入 MCS 的证据。
实际 pending/MCS 由相关生产代码 unit fixture 单独验证；本次没有测试与活动
combiner 的混合交接，也没有执行 IRQ handler/softirq callback 注入或 PREEMPT_RT。

## 2026-09-27 验证

起点为 `f4750dc`，只修改公共头文件及 context-symbol 准入；普通 provider 函数体
保持不变。guest 内核 `6.1.159-kdclobber2`，源码/build/running identity 与
`mutex-clobber2-20260919` 捕获基线一致，未修改或重建内核。

| 检查 | 结果 |
| --- | --- |
| 基础与相关 unit | 两个基础程序、native pending/MCS、preempt、context policy 101 项通过；IRQ/BH 和 cold/paired ABI 两组修正 fixture 后通过 |
| NORMAL provider / consumer 构建 | 均通过；provider 保留原有 objtool 汇编告警，consumer 的初次 1040-byte 栈告警已修正，重建无此告警；环境 Perl locale 告警仍存在 |
| 普通路径 ELF 对比 | 修改前后 provider 的全部5个可执行 section 的字节、大小、对齐及 relocation 目标相同，选定9个普通 spin 函数的地址/大小/指令也相同；这次 API 增加没有向原 provider 执行路径加入指令 |
| live | CPU0/1/20/21，跨 guest 两个 NUMA node；四种获取轮换，40,000 次计数正确，IRQ/BH/preempt/native-count/owner 恢复检查通过 |
| 退出 | 新日志无 kernel error，native/frame invariant 为 0，所有 worker 退出，两模块正常卸载，空闲核验通过 |

unit 命令为：

```sh
make -C tests/unit run PY_TESTS='spin/test_spin_irq.py spin/test_spin_cold.py spin/test_spin_nondelegated.py spin/test_spin_preempt.py admission/test_context_policy.py'
# 初次两个 fixture 编译失败后，仅重跑受影响两组：
make -C tests/unit run TESTS= PY_TESTS='spin/test_spin_irq.py spin/test_spin_cold.py'
```

初次 unit 的 IRQ flags 数组触发 `maybe-uninitialized`，以 poison 值初始化后仍
保留精确 flags 断言；cold fixture 缺少已有生产分支使用的 `likely` mock，已补齐。
初次 live 的模块检查 PASS 并正常排空，但收集器因旧 dmesg 前缀被环覆盖而报失败。
该失败完整保留；改用精确保留后缀匹配后，同一源码/模块重跑通过。

原始证据位于本地忽略目录 `bench/.tmp/irq-api-20260927/`：`unit.log`、
`unit-rerun.log`、`build.log`、`build-rerun.log`，以及 `live/` 与 `live-rerun/`
中的冻结源码、ELF、参数、命令/退出码和完整 dmesg。guest 对应目录为
`/root/kdlock-evidence/irq-api-20260927/` 和
`/root/kdlock-evidence/irq-api-rerun-20260927/`，归档 SHA256 记录在各自
`guest-archive-verified.json`。未重跑全量 unit、mutex、性能矩阵或实际 JIT；不将
此前性能数据记为这次新增接口的实测结果。

| 冻结材料 | SHA256 |
| --- | --- |
| 最终 live 归档 | `fd3ef435d874430aead15ed453327d73704867ac48a2e9c87fae01b91bd9f225` |
| 初次 live 归档（收集器报失败） | `6a41f95d55acbd8471f3093a0a9364e0e9875a51e65ad35d202968e1e66fabb8` |
| NORMAL provider | `0b0f61e15eb32d02cae09ca5f8e92888f5318a7de1271949da3ee28fe17f5b31` |
| IRQ/BH consumer | `fb461b77cfd488aac36b8e201aa66bed2fe585f029c574ee4685a88bc7ab6ead` |
| 本地 `elf-comparison.json` | `eeecd4ef4a21f546412fb65569920629ce3278e761ad71b3362dbb509604dc37` |
