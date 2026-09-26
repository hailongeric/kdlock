# 当前测试入口

构建、单元、模块和性能测试只在 recovery guest 执行，先读
[操作手册](../docs/AGENTS.md)。当前使用显式 KD 单锁字 API；普通 Linux 锁完成
不能作为 KD JIT 证据。按修改范围选择下面的单元、功能或性能入口。

## 最近验证与证据

结果按冻结源码分别记录，不合并为当前版本全量验收。

| 批次 | 已完成与范围 |
| --- | --- |
| [全链路优化与无锁ticket](../bench/tclock_compare/results/20260927-flow.md) | 第一阶段90场及相关测试单列；最终原子ticket版基础/entry/outer_progress/remote_outer共5组、两种构建、CPU0/20真实ticket selftest、完整135场及36线程nested原生续跑/early各360万操作通过，未跑全量 |
| [spin清理与内联验证](../bench/tclock_compare/results/20260926-cleanup.md) | 基础/entry/shadow/outer共5组，普通及SELFTEST构建、81场性能、36线程nested/early各180万操作及归档审计通过；未跑全量 |
| [最新c1复测至36线程](../bench/tclock_compare/results/20260926-c1-through36.md) | aef982b完整135场通过；runner34项、源码/ELF/峰值及排空审计通过，本次未重跑nested/early或全量 |
| [c1跨node有界批次优化](../bench/tclock_compare/results/20260926-cross-node.md) | 08497ab完整126场、32线程nested/early各160万操作；基础/shadow三组、runner34项、源码/ELF/峰值审计通过，未跑全量 |
| [前版c1预取/诊断/CPU热值优化](../bench/tclock_compare/results/20260926-prefetch-unlock.md) | 77eb9a2完整126场、32线程nested/early各160万操作；相关生产fixture、runner34项、源码/ELF/峰值离线审计通过，未跑全量 |
| [前版c1 NUMA-on优化](../bench/tclock_compare/results/20260926-numa-followup.md) | d439df8完整126场、32线程nested/early各160万操作通过；相关queue/native/entry-scope、runner33项、源码/ELF/峰值离线审计通过；各阶段范围单列 |
| [首轮c1 NUMA/有界批次](../bench/tclock_compare/results/20260926-numa.md) | 完整126场、32线程nested/early各160万操作通过；相关queue/batch/storage/clobber及runner检查通过，预取候选和fixture失败/修正保留在报告中 |
| [前版1/8 cacheline复测](../bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md) | 126场业务/context/排空通过；42场KD中18场实际JIT。基础2组、runner32项及CLI矩阵核对通过；没有新增复杂功能或mutex测试 |
| [捕获队尾准入](../bench/tclock_compare/results/20260924-warmed-peak.md#captured-tail五后继三方90场完成) | 基础及采样/原生MCS共4组、runner32项、SELFTEST两种构建和90场性能通过；20线程nested/early各200万操作，实际JIT1997259/640480次，独立排空及归档审计通过 |
| [per-CPU waiter诊断](../bench/tclock_compare/results/20260924-warmed-peak.md#per-cpu-waiter观察保留) | 基础及batch/storage共4组、两种SELFTEST构建、30场性能通过；保留live近似和即时下溢信号移除的限制 |

原始归档在本地忽略目录`bench/.tmp/`和guest `/root/kdlock-evidence/`，不随Git分发。
构建警告、失败、源码身份及未测项保留在对应报告或归档内。旧模式、被拒绝的
性能候选和旧fixture验收表统一从[历史索引](../bench/tclock_compare/results/HISTORY.md)追溯。
当前采样及ABI分别见[执行流](../docs/JIT_EXECUTION.md#21-热度与角色)和
[寄存器约定](../docs/JIT_REGISTER_ABI.md)。

## 单元检查

代码修改后可直接运行[默认三轮性能测试](../bench/tclock_compare/README.md#准备与运行)，
使用其内置业务、IRQ/preempt、JIT 和排空检查。独立单元、SELFTEST、`--functional`
及小矩阵按需选择，不作为性能测试的固定前置步骤。2026-09-23 用户提高性能测试
轮次用于观察波动；功能模式仍显式使用 `--repeats 1`，已有单轮证据保留原口径。

```sh
make -C tests/unit run
make -C tests/unit run PY_TESTS='spin/test_spin_direct.py spin/test_spin_entry.py infrastructure/test_hotlock_sampling.py'
```

默认只执行两个基础 C 程序，按修改选择直接相关驱动；`run-all` 仅在明确要求时使用。
`python3 tests/unit/run.py --list` 列出现存驱动，无隐式执行。

| 修改范围 | 相关驱动（位于 tests/unit） |
| --- | --- |
| 原生 pending/MCS 与 owner 配对 | `spin/test_spin_nondelegated.py`、`spin/test_spin_shadow.py` |
| 单锁字入口和 ticket | `spin/test_spin_direct.py`、`spin/test_spin_entry.py` |
| 入口抢占配对 | `spin/test_spin_preempt.py`、`infrastructure/test_hotlock_sampling.py` |
| continuation 分配、容量、回收与最终恢复 | `spin/test_spin_storage.py`、`execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `spin/test_spin_entry.py`检查实际ticket CAS；`execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py`检查路由/ACK |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热表、获取/MCS计数、频率/比例窗口及准入恢复 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| 冷热调用壳与通用解锁 ABI | `spin/test_spin_cold.py`、`codegen/test_spin_paired_jit.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py`、`execution/test_jit_entry_scope.py` |
| 范围选择与离线证据 | `infrastructure/test_regression.py` |

共享源码读取/头文件过滤位于 `unit/infrastructure/source_text.py`，不再依赖旧 gate
测试。保留的 mutex/remote 等日志 oracle 检查身份、owner、ACK、顺序和最终副作用；
合成日志通过不表示当前 live 覆盖。生产代码 fixture 同样不证明真实内核并发。

## Live 检查

`tests/run_all.sh` 无参数只列出现存范围；`--case module --dry-run` 只预览。
当前唯一基础 case 为 provider/device 生命周期，不加载旧 `klock_module`，JIT=0：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 timeout 240 tests/run_all.sh \
  --case module --output /root/kdlock-evidence/module-current
```

输出目录必须新建在仓库外；变量只在 monitor 已确认真实快照后设置。
运行器核对依赖、冻结源码、检测内核错误及残留调用者，失败保留证据并停止。
`tests/verify_evidence.py` 对这类已有归档做离线一致性校验，不执行归档代码。

实际 JIT 与业务互斥使用 [直接运行器](../bench/tclock_compare/README.md)。
`--scenario plain` 为普通单锁；`--scenario nested` 为 A/B 嵌套；`--scenario early`
为外锁提前释放，仅 KD cacheline 允许后两项。当前只保留adaptive，功能正例可显式使用
`--spin-contention-pct 0`关闭比例过滤，但原生队头资格及CPU/单锁热度仍生效，实际JIT检查不放宽；
未重跑的功能场景不记为通过。
性能中的原生完成须保留 NO_JIT 标记。少线程可经 MCS 升温，但不保证出现可代理后继；
不能只凭线程数判断是否执行 JIT。具体有效性规则见运行器文档。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 spin_entry_selftest=1`
检查热表碰撞及满容量时既有身份和真实 owner 仍保留、mutex 等待 CPU 迁移及 owner ACK；这不执行 JIT。
构建方式及控制参数见 [provider](../kernel_module/README.md)。保持 normal 与
SELFTEST 构建分开，不替换加载中的模块，完成后必须排空和正常卸载。

## 历史验证与尚未覆盖边界

各批实测范围以本页链接报告的冻结源码和原始结果为准。continuation 容量、最终恢复汇编、
节点先复用、共享根包及延迟 ACK 的历史 fixture 通过，不等于当前真实内核多 CPU
远端 native/无锁 relay 强制时序已覆盖。mutex JIT、极端容量/取消组合及访问时
动态 guard 的剩余限制见 [TODO](../docs/TODO.md)。

| 历史阶段 | 冻结记录 |
| --- | --- |
| continuation 交接、ELF 布局和退休检测 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#continuation-validation) |
| 四线程 ticket 和抢占配对 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#four-thread-ticket-validation) |
| 已撤回的 MCS 边界准入实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-admission-validation) |
| 已撤回的准入时间域实验 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#admission-clock-validation) |
| 回退后的单元与 plain/nested/early 功能 | [原始结果与失败记录](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/tests/README.md#mcs-recovery-validation) |

[性能阶段索引](../bench/spin_cacheline/results/HISTORY.md)保留原始报告入口；
更早测试见 [VALIDATION](../docs/VALIDATION.md)。旧 hook/gate 脚本只适用于匹配的
历史 checkout；历史操作命令不作为当前运行指令。
