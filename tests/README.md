# 当前测试入口

构建和运行只在 recovery guest，先读 [操作手册](../docs/AGENTS.md)。当前版本是
显式 KD 单锁字 API；全局 spin 分发已删除、mutex hook 安装停用。旧 hook live
套件、gate 容量测试及其专用 workload 已删除，不能以普通 Linux 锁完成冒充 JIT。

<a id="hotlock-direct-validation"></a>

## 2026-09-21 去除候选，按锁字直接哈希计数

当前每 CPU/type 256 桶、256 条预分配精确地址记录，无 score/error、候选排名或淘汰。
CPU 每 1024 次检查；单锁 count **大于 1024（第 1025 次）** 才采时检查原有窗口，
刷新 hot、更新时间戳并清零计数。满表不覆盖已有记录，adaptive 未收录锁走原生。
CPU 冷热变化重置统计但保留映射，地址身份保持到模块卸载。
布局和流程见 [执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md#51-准备热度与快速获取)。

本轮 guest 单元 4/4 通过，11 个错误变体全部被拒绝，覆盖 CPU 1024/锁 1025
边界、256 个同桶地址的独立计数、满表拒绝插入且不覆盖、窗口/倒退/零时间、
query、CPU/type 隔离和重入/抢占配对。普通与 SELFTEST 的 W=1 构建通过，
ELF entry/table/cpu 为 24/6688/13376 字节，CPU 对齐 64。

真实 SELFTEST 探针验证 `retained=1 full=1`、解锁后 `word=0`，mutex 等待从
CPU 1 迁移到 CPU 2，`balanced=1 ret=0`，正常卸载且无内核错误。此探针
`mutex_jit=0`，不冒充 mutex JIT。首次脚本误要求 dmesg 全量前缀不变，因环形
日志换页失败；保存前后日志，按唯一的最后一条前置记录核对本次输出后通过，
没有修改/放宽协议检查。

adaptive/plain/c1/t4 实际功能检查完成 400000 次操作，其中 JIT 正文 210103 次；
业务、IRQ/preempt 和排空均通过，无内核错误。此功能会话使用默认 `mutex_jit=1`，
实际执行的是 spin JIT，不据此声称 mutex JIT 已验证。

本轮原始证据在 guest `/root/kdlock-evidence/hotlock-direct-20260921/`；
[归档](../bench/.tmp/hotlock_direct_20260921/hotlock-direct-20260921.tar.gz)
SHA256：`45589ecb9e19718db0e9cea74afab1e43b48e460366f70021f43841ce85e1e25`。
包含本轮开始时工作树、`this-turn.patch`、最终源码哈希、两种 ELF/布局、单元、
探针前后日志、functional 及 `audit.json`；宿主代码与已测输入一致。

本轮未覆盖真实 mutex JIT、嵌套/远端 native 续跑或更大多锁 live 负载，
预分配容量固定且不回收地址记录；没有解决锁地址复用的对象代际问题。
功能修改时未测性能；随后 [直接哈希同期对照](../bench/tclock_compare/results/20260921-hotlock-direct.md)
完成 120/120 场、1 亿次操作并全部排空，80/80 竞争会话有实际 JIT。本次只重测
性能会话内的功能 oracle，没有重复运行上述单元/满表探针；上一版两级候选性能
不能算作当前无候选版本成绩。
历史候选版只保留冻结报告入口。

<a id="hotlock-twolevel-validation"></a>

## 2026-09-21 两级热度采样（历史候选版）

该候选版已被当前精确哈希计数替代。单元 4/4、10 个错误变体、实际 adaptive
JIT 和 120 场性能对照的冻结结果见 [两级采样报告](../bench/tclock_compare/results/20260921-hotlock-twolevel.md)。
不将其 1024 次单锁阈值、候选替换或对象大小解释为当前行为。

## 单元检查

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
| continuation 容量、回收与最终恢复 | `execution/test_exec_capacity.py`、`spin/test_spin_wait.py` |
| native 借用退休、共享根包与延迟 ACK | `execution/test_remote_outer.py`、`execution/test_remote_depth_protocol.py`、`execution/test_remote_outer_protocol.py` |
| 嵌套、提前释放、队列、frame 退休 | `spin/test_spin_outer_progress.py`、`spin/test_spin_shadow.py`、`spin/test_spin_batch.py` |
| 本地热锁哈希和窗口 | `infrastructure/test_hotlock_sampling.py` |
| mutex 资源和续跑 | `mutex/test_mutex_resources.py`、`mutex/test_mutex_outer_progress.py` |
| source/注册生命周期 | `infrastructure/test_source_lifetime.py`、`execution/test_exe_registry.py` |
| ABI、寄存器和生成器 | `admission/test_clobber_entry.py`、`codegen/test_clobber_abi.py`、`execution/test_native_registers.py` |
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
为外锁提前释放，仅 KD cacheline 允许后两项。observe 竞争正例要求真实 JIT；
adaptive NO_JIT 只可作为明确标记的性能样本。

SELFTEST provider 可用 `hotlock_lifetime_selftest=1 hotlock_mode=observe spin_entry_selftest=1`
检查满表不覆盖真实持锁记录、mutex 等待 CPU 迁移及 owner ACK；这不执行 JIT。
构建方式及控制参数见 [provider](../kernel_module/README.md)。保持 normal 与
SELFTEST 构建分开，不替换加载中的模块，完成后必须排空和正常卸载。

## 历史验证与尚未覆盖边界

当前改动的实测范围以本页最新结果为准。continuation 容量、最终恢复汇编、
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
历史 checkout；本次文档整理没有重跑上述实验，也没有删除测试或原始证据。
