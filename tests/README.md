# Tests

本目录维护测试的运行入口、场景说明和验收记录入口。根 README 不记录用例表、
测试命令或测试成绩。Demo 临界区模块集中在
[`workload_modules/lock_scenarios/`](../workload_modules/lock_scenarios/)，
生产 provider 的专用协议观察器在 `tests/kernel/`。
性能对比使用 [bench/README.md](../bench/README.md) 的独立入口。

## 当前验证范围

默认内核为 `6.1.159-kdclobber2`，普通 spin/mutex 使用 ABI 1/2，legacy 为 ABI 0。
当前热锁依次检查 CPU 频率、本 CPU 的锁频率和目标进程；共享发布或旧的
12000 次准备都不能代替每个新 CPU 的本地达标。最新完整冻结 live 范围仅为
`mode-0`、`mode-3`、`mode-2`、`mode-7`、`mixed-mutex`、`registers-3-1`。
其他协议脚本仍保留原断言，其中部分准备量和 CPU 放置尚未适配新准入；其
历史通过不表示当前可直接通过。按改动选择并核对准备，不能放宽 JIT oracle。

## 2026-09-19：按职责拆分与文档重组

在 `33026fa799b79b73339665df5d2d1dfa9fcf6095` 之后整理源码：准入分析拆为符号、
值传播和 CFG 策略；daemon 拆出工作区、编译、发布；内核拆出 wrapper 入口检查、
frame 生命周期及复杂 spin 出口。C 私有 `.inc` 保持原编译单元与声明顺序。
单条指令的薄分派合并进 `special_inst.py`；spin/mutex wrapper 测试合并为
`codegen/test_clobber_abi.py --entry-abi spin|mutex|both`，默认两种 ABI。
大型准入、双 frame 协议和回归基础设施测试拆出 case/fixture，入口不重复收集。

静态核对确认四个 C 编译单元展开 `.inc` 后 token 顺序一致，准入分析及双 frame
协议函数体 AST 一致；三个拆分测试组的函数体/断言保持不变，仅更新 mock 的
模块路径。合并后的分派函数与每种 ABI 的执行函数体也保持不变。
Python `test_*` 方法仍为 **524**；总入口从 49 减至 **48（2 C + 46 Python）**，
少一个是消除了独立 mutex 转发程序，不是删除 ABI 2 检查。

recovery guest `6.1.159-kdclobber2` 核对内核身份后，两个基础 C 程序及以下
11 个相关 Python 入口通过，合计 **13 passed / 0 failed**：

- admission：context_policy、context_memory、context_guards、clobber_entry。
- codegen：clobber_abi（两种 ABI）、jit_diagnostics。
- execution：jit_entry_scope、exec_capacity；spin：spin_outer_progress。
- mutex：mutex_parallel_protocol；infrastructure：regression。

首轮因拆分漏保留 `context_policy.context_memory` 接口和 mock 的旧模块路径而
失败，日志已保留；修复导出及 mock 定位后取得上述通过。最后去除拆分测试的
未使用导入，又运行两个基础 C 与 mutex_parallel_protocol、regression，
**4 passed / 0 failed**。没有修改或放宽协议 oracle。

生产 provider `W=1`、daemon `-O2 -Wall -Wextra -Werror` 强制构建和 benchmark
专用 provider `W=1` 构建通过。观察补丁按移动后的文件重新定位，在 guest 严格
应用，无 fuzz/offset；保留原观测内容。provider 仍有既有换栈/恢复 objtool 告警，
环境另有 Perl locale 回退提示，不能称为零告警构建。

构建及 13 个入口冻结 **405** 个输入；导入清理后定向复验冻结 **406** 个输入，
生产输入未变，两轮结束均核验哈希一致和 guest 空闲。本文最后的记录及一个旧测试名
注释另存最终清单。本轮没有加载模块、运行 live、完整单元或 benchmark，不能将
旧六项 live 和此次单元拼成当前全量通过，也没有新的吞吐结论。

文档按设计、测试协议、计量方法和文件地图分开维护，旧章节保留导航锚点；
性能任务集中在 [PERFORMANCE_PLAN](../docs/PERFORMANCE_PLAN.md)。静态核对
50 份 Markdown 的本地链接/锚点及 132 个固定 Git 文件引用，126 个 Python 和
25 个 shell 文件语法通过；23 个非文档内核基线/实验及 TCLock 文件保持原字节。

证据：guest `/root/kdlock-evidence/code-organization-20260919/`，宿主
`/tmp/kd-code-organization-20260919/`。包含整理前备份、结构核对、每轮冻结输入、
首轮失败及最终通过日志、构建日志、内核身份和最终源码归档。

## 2026-09-19：默认化后的旧代码清理验证

清理无消费者的 spin 适配函数、mutex 初始化宏、未使用返回分类和旧
socket/count 位域定义；此前已删除的旧内核安装分支及专用审计/夹具一起纳入提交。
legacy caller、FULL 恢复、owner ACK 和恢复基线继续保留。
历史验收及旧 benchmark 命令压缩为固定 Git 版本索引，当前操作说明修正
Build ID、本地频率准备、counter 及测试库存。

在 recovery guest `6.1.159-kdclobber2` 核验 source/config/build/live 身份后，
两个基础 C 程序及下列五个相关入口全部通过：
`test_hotlock_sampling.py`、`test_mutex_resources.py`、
`test_spin_batch.py`、`test_exe_registry.py`，合计 **7 passed / 0 failed**。
provider `W=1` 构建及 daemon `-O2 -Wall -Wextra -Werror` 强制重建通过；
provider 保留既有换栈/恢复的 objtool 告警。377 个冻结输入核验一致，最终 guest 空闲。
本次没有加载模块，没有重跑 live、benchmark 或全量单元；上面的六项 live
仍是本地发现改造时的独立冻结记录。

静态核对 39 份 Markdown 的本地链接/锚点、固定 Git 引用及历史锚点；
114 个 Python 文件和 25 个 shell 文件语法通过，TCLock 四个上游文件的哈希保持不变。
证据位于 guest `/root/kdlock-evidence/repository-cleanup-20260919/`，宿主
`/tmp/kd-repository-cleanup-20260919/`，包含整理前备份、输入清单和全部验证日志。
最后新增的文档记录另存最终清单，不冒充构建运行时输入。

## 目录

| 子目录 | 内容 |
| --- | --- |
| `live/` | kernel live 场景脚本，由顶层 `run_all.sh` 选择 |
| `protocols/` | 协议结果校验、CPU 放置与 source 生命周期辅助代码 |
| `clients/` | 用户态测试客户端 |
| `tools/` | 独立审计和成对 benchmark 工具 |
| `kernel/{spin,mutex,execution}/` | provider 的观察器与组件自测 |
| `kernel/hotlock_record/` | 独立采样组件微基准，由 bench/hotlock_record 运行 |
| `unit/basic/` | 两个默认基础 C 测试 |
| `unit/{codegen,admission,spin,mutex,execution,infrastructure}/` | 按功能分组的 Python 测试和配套 C 夹具 |

顶层保留公共 shell 库、live 选择器及证据读写入口；Python 单元测试通过
`unit/run.py` 运行，统一处理跨组夹具导入。当前库存为 2 个 C 和 46 个 Python
入口；`*_cases.py`/共享 fixture 由对应驱动显式加载，不重复收集。保留有独立协议覆盖的用例，已被生产夹具替代的模型和旧内核审计已删除。

## 环境与单元测试

构建、单元测试和 kernel live 只在 recovery guest `/root/host_fs/kdlock`
进行。先按 [环境与恢复流程](../docs/AGENTS.md) 核对源码、实际内核身份、
依赖及空闲状态。使用 [固定 Python 依赖](../disassem/requirements.txt)，
venv 的 `bin` 必须位于 PATH 首位，以供 daemon 翻译子进程继承。
原内核的身份检查与独立实验内核的检查不能混用，具体见
[捕获基线](../kernel_baseline/README.md) 和
[当前 mutex/spin clobber 内核](../kernel_experiments/mutex_clobber/README.md)。

按 2026-09-16 的开发约定，每次修改只验证基础简单功能和直接受影响的功能，
不自动运行完整单元套件或 live 矩阵。默认入口只运行两个基础 C 程序：

```sh
cd /root/host_fs/kdlock
timeout 60s make -C tests/unit run
```

在基础检查上增加相关测试，例如修改测试选择器时：

```sh
timeout 120s make -C tests/unit run PY_TESTS='infrastructure/test_regression.py'
```

`PY_TESTS` 支持分组路径及唯一的旧文件名；指定 `TESTS=` 可只运行所选 Python
测试。单独运行、列出库存及显式全量入口如下；最后一条仅在明确要求全量时使用：

```sh
python3 tests/unit/run.py codegen/test_segment_codegen.py
# 共用 wrapper 检查：默认 both，也可明确选择 spin 或 mutex
python3 tests/unit/run.py codegen/test_clobber_abi.py --entry-abi both
make -C tests/unit list
make -C tests/unit run-all
```

分析器改动按需要选择相关 admission 测试和 `tests/tools/audit_context_spills.py`。
目录、文档或选择器调整只检查相关入口与路径，不因此扩大到 kernel live。

单元夹具、只读证据检查和真实内核 JIT 分别判定；依赖缺失、SKIP 或编译失败
不能计作通过。这里只列入口，各协议的增量选择继续见
[测试选择](../docs/JIT_EXECUTION.md#7-分层与增量回归)。

`spin/test_hash_relink.py` 提取实际哈希表正文和 guest 内核的 hlist 原语，使用
ASAN/UBSAN 对照原毒化摘链与当前立即重插写法，核对操作分类、独立键集合及
完整链表。`admission/test_clobber_entry.py` 同时覆盖零扩展/符号扩展后的逐位
依赖：已定义低位可用，未捕获高位或符号位影响地址、存储和分支时仍拒绝。
实际哈希表 JIT 和三方性能结果维护在 [锁对比](../bench/tclock_compare/README.md)。

提取生产 C 函数的夹具通过 [source_text.py](unit/infrastructure/source_text.py) 读取源码。
它按原声明顺序递归展开私有 `.inc`，保留普通头文件和条件编译文本，供夹具
继续使用原有替代原语；不复制函数实现，也不放宽协议断言。冻结源码和
benchmark 专用 provider 的复制清单同样包含 `.inc`。

`infrastructure/test_hotlock_sampling.py` 提取实际生产采样器，验证每 10240 次
共用一次时钟、CPU 独立门槛、本地单锁窗口、冷却/重新开启、本地过期重测、
直接映射冲突丢样、共享集合重复发布/容量与分配失败。访问计数证明未达标及
缓存正向命中不访问共享集合；稀疏地址流不会逐地址读 TSC。四个 producer 和
两个查询线程验证不可逆共享身份发布，不把 pthread 模型写成内核 IRQ/NMI 覆盖。
spin 路由和 mutex 资源夹具保留先采样后看进程、冷却/改名/关闭 source 后仍按
原 owner 解锁的断言。

## 选择 kernel live 用例

```sh
# 列出范围或预览；尚不执行负载。
bash tests/run_all.sh
bash tests/run_all.sh --case mode-0 --dry-run

# 从宿主机 monitor 确认可恢复快照、核对空闲状态后，在 guest 执行。
KDLOCK_RECOVERY_CONFIRMED=1 timeout 360s \
  bash tests/run_all.sh --case mode-0 --timeout 300 \
  --output /tmp/kdlock-selected-case-new
```

宿主机发起 SSH 时还须设置覆盖整条远端命令的外层 timeout。
`--suite` 选择套件，`--case` 选择单项，交叉选择按用例身份去重；无参数只列出
范围。失败立即停止，已被复杂用例覆盖的诊断保持显式选用，不追加基础或稀有
场景矩阵。`--suite mutex` 选择 mode 4/5，并显式启用 `mutex_jit=1`。
完整模块/daemon 启动、逐用例协议和清理顺序见
[执行流](../docs/JIT_EXECUTION.md#3-环境与操作)。

验证 spin 的发布/栈恢复改动时，可在 guest 将生产汇编测试加入基础检查：

```sh
timeout 120s make -C tests/unit run PY_TESTS='spin/test_spin_wait.py'
```

IRQ-off task 入口复用 `mode-0`，在同样的 recovery 准备完成后显式运行：

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KD_SPIN_IRQ_OFF=1 timeout 360s \
  bash tests/live/test_04_spinlock.sh 0
```

直接脚本保留此开关；标准选择器会清除外部 `KD_*` 环境变量。
该开关只支持 mode 0：负载在 spin lock/unlock 对外层关闭 IRQ，并检查状态保持。
普通 `mode-0` 使用 IRQ-on 入口；这两个变体均为 task 上下文，不能当作
hardirq/softirq 代理测试。以上为按改动选用的命令，不扩大默认测试范围。

## Demo 模式

以下是场景映射，不是本轮执行或通过清单；同一模式还可能包含多个受检阶段。
完整用例库存、覆盖关系和参数见 [TEST_EXAMPLES](../docs/TEST_EXAMPLES.md)。

| Mode | 后端 | 场景 |
| --- | --- | --- |
| 0 | Spin | 单锁竞争 |
| 1 | Spin | A/B 嵌套 |
| 2 | Spin | allowlisted service 后返回 JIT |
| 3 | Mutex | 单锁竞争，`mutex_jit=1` |
| 4 | Mutex | A/B 嵌套及共享 B，`mutex_jit=1` |
| 5 | Mutex | service 与受检续跑，`mutex_jit=1` |
| 6 | Spin | A/B/C 深层嵌套 |
| 7 | Spin | 先释放 A 再释放 B |
| 8 | Spin | 独立队列及显式远端链 |
| 9 | Spin | 恢复拓扑；旧合成 post-entry fault 为 fail-stop |
| 10 | Spin | GS 读/写/RMW/current 的实际 JIT 正例 |
| 11 | Mutex | GS 读/写/RMW/current 的实际 JIT 正例，`mutex_jit=1` |

`test_24_gs_jit.sh 10/11` 使用各自独占 origin CPU 的四个 worker，要求翻译/发布、
wrapper body witness、12129 次 probe 全部成功、数据完整性和排空。统一入口仍为
`--case context-spin --case context-mutex`。`test_12` 仅保留 mode 3 的拒绝负例。
spinlock 和 mutex 的显式 GS 支持均为默认行为，测试模式只选择验证负载，
不充当 GS 功能开关。spinlock 被代理者原本就保持禁止抢占并 PAUSE 轮询；
mutex 的排队等待也遵循同一规则，两者等待结果期间均不睡眠或调度。
`test_segment_codegen.py` 通过真实 wrapper 在 guest 用户态验证 GS read/write/RMW
及不同 GS/task 输入；`test_mutex_resources.py` 检查 reschedule pending 时仍持续
禁止抢占轮询到结果发布。这些单元测试不代替内核并发验证。

等待代理结果的线程现在禁止抢占，不调度或睡眠。依赖 waiter 让出同一 CPU
才能推进的旧用例（例如同 CPU 的依赖环）需要按新 CPU 放置重新设计，
不应直接复用旧通过记录。单锁 mode 3 已改为每个 waiter 独立 CPU；不要将
sleeping owner 和 busy waiter 固定在同一 CPU。

daemon 的 `--mode flat/per-tgid` 选择 workspace 布局，不是上表的 Demo 模式。

## 证据与结果

实际 JIT 正例必须同时满足有效生成/发布、wrapper 返回后的正文见证、完整数据
和 owner/ACK 校验。已发布但未执行正文不能算实际 JIT 通过。原生负例与协议探针
单列；benchmark 的 NO_JIT 分类见其 README。

运行器在源码树外保留冻结源码、内核/依赖信息、命令、日志、生成物和排空记录。
只读核对已有目录：

```sh
python3 tests/verify_evidence.py /tmp/kdlock-selected-case-new
```

这不重新执行 JIT，也不认证当前源码。停止新 workload 后，先等待调用者、请求、
frame 排空，再结束 daemon/翻译者、retire，最后卸载；不强制卸载。超时或未排空
时保留现场并停止后续用例。

<a id="local-hotlock-validation"></a>

2026-09-19 本地发现版本在 `6.1.159-kdclobber2` 的 recovery guest 验证通过：
两个基础程序、生产采样器 131164 项检查 / 9 种错误变异、spin 路由 15 场景 /
8858 项检查、mutex 资源 16910 项检查 / 19 种错误变异。`W=1` provider
构建通过，保留既有汇编/objtool 警告。benchmark 驱动检查 30 场景、配对观察器
113 项检查和 cacheline 驱动 15 项检查通过。

同一冻结 live 输入 `live-compile-fix` 的 `mode-0`、`mode-3`、`mode-2`、
`mode-7`、`mixed-mutex`、`registers-3-1` 全部通过，实际 JIT、状态副作用、
IRQ/preempt 和排空检查保留。mutex 记录 726 次 JIT 完成；4 次 spin hostcall
全部执行并恢复；寄存器用例 48009 个请求校验无误，8 份样本中有 1 份实际
JIT → native 续跑，验证 16 GPR、SP/BP、返回槽及 owner ACK，不宣称 flags 覆盖。
内核无故障，模块、调用者和 frame 均已排空。未运行全量或完整吞吐矩阵。

准备方式已变更：相关普通测试的连续 promotion 从 12000 增至 48000，精确
正文计数同步增加；短探针显式启用 `cpu_frequency_prepare` 和
`KD_TEST_LOCAL_PREPARE`，每线程在共同屏障前以非目标 comm 对实际锁执行
40960 次原生空临界区，再恢复 comm 并运行原正文。线程固定于准备 CPU，
原生准备不注册 JIT、不改正文或寄存器记录，且不进入计时。该选项默认关闭，
性能驱动不启用；其余专门协议用例未重跑，不继承旧全局识别版本的通过结论。

保留初始失败：并发夹具选择的地址同时产生本地碰撞，改为单独测试全局发布
与本地碰撞；首次 live 在测试模块链接阶段遇到未导出的改名函数，改用项目
已有测试函数后通过；benchmark 夹具的旧准备计数期望同步修正。未删除 JIT、
所有权或副作用断言。36 场采样组件对照与边界见
[组件报告](../bench/hotlock_record/results/20260919-local-discovery.md)。

证据在 guest `/root/kdlock-evidence/local-hotlock-20260919/`，包含各轮冻结
输入、失败日志和构建/运行结果；宿主归档
`/tmp/kd-local-hotlock-20260919/evidence.tar.gz`，SHA256
`12605e52f7bc13b2bdda1dc60b8cd047d4fdfb711a9c37f49b62b958f19fe750`。

<a id="mutex-clobber"></a>

## 2026-09-19：普通 mutex clobber 验证（本地发现改造前）

普通 spin/mutex 现在默认使用独立的 clobber 身份（分别为 1/2）。新内核
`6.1.159-kdclobber2` 从保留的 clobber1 派生，Build ID 为
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；配置只改变 LOCALVERSION，
保持帧指针和缓解配置。补丁、独立 build 和基线见
[mutex_clobber](../kernel_experiments/mutex_clobber/README.md)。

mutex 正常路径只捕获/恢复 IP/SP/BP，frame 借用 node 包，发布前先切 shadow 栈，
完成后放弃旧 hook C 帧。中途出口先物化 FULL，并在 C 控制处理前取得独立
frame 包；node 可复用后，物理 owner 的 frame 仍保留到最终 ACK。
保留旧 ABI、特殊 API 和两元素 wrapper 参数，没有删除必要的 FULL 续跑。

该阶段在 recovery guest 进行构建、单元和定向 live，未跑全量或性能测试：

- 基础两个 C 程序通过。生产 mutex 资源（16845 项）、入口消费者（3353 项）
  和 frame 容量（11133 项）检查通过；wrapper 覆盖 128 个 poisoned 入口及 16 个新旧混合交接。
- 直接编译并执行 `mutex/clobber.inc`：32 次未执行返回和 32 次主动毁掉旧
  hook 栈帧后的精简恢复通过，高寄存器压力下调用者活跃值保持正确。
- 默认 provider/workload/daemon 构建通过，仍有手写换栈/恢复的 objtool
  告警；新入口不是零告警构建。benchmark 默认参数的 15 项单元测试通过，
  default source/config/build/live 身份核验通过。
- 准入增量为 19 个 clobber 测试、51 个内存测试和 40 个 guard 测试通过。
  新范围谓词证明完整 spill 位于所有 native 检查窗口内；未知写入/callee
  和分支合并不能恢复已失效的入口身份。没有扩大 256B 检查窗口。
- `live-basic/mode-3`：732 次实际 JIT 完成，12934 次正文状态变化通过。
- `live-boundaries/mode-5`：463 次 JIT 正文，940 次 hostcall 执行/恢复，
  5 名 quota 调用者与最终 owner ACK 通过。
- `live-boundaries/registers-3-1`：12009 请求、8 个寄存器样本、1 个
  JIT/native frame；`live-final/registers-4-2`：12002 请求、双锁完整 GPR
  恢复及 owner ACK。均检查 16 个 GPR 与栈，不检查 flags。
- `live-window/native-mutex-stack-change`：真实 B 等待、共享栈变化、
  两个 owner 保留、一次原生后缀和两次 ACK 通过，正文不重放。
- `live-legacy/mode-3`：同一新内核以 `KCFLAGS=-DKD_MUTEX_LEGACY_CALLER`
  重编译调用者，732 次 legacy JIT 完成及排空通过；保留旧 ABI 生成物身份。
- `live-final/mixed-mutex` 和 `mode-0`：原生 mutex 互操作及普通 spin 回归通过，
  保留实际正文、准确副作用、原锁 owner 和退休/排空检查。

过程中保留了失败记录：嵌套用例最初因 RBP spill 无法证明属于 RSP 检查窗口
而拒绝准入，补入口范围验证后重跑通过；混合用例最初要求同 CPU 的八线程
必然耗尽四个 node，该假设不适用于禁止抢占轮询。脚本仍运行全部 18810 次
状态变化及同 CPU 压力，核对实际 JIT、原锁 owner、task 与 node 排空，不再由
线程数推断同时预约数。node 真正耗尽继续由已有跨队列资源用例负责，本轮
没有声称重跑其完整 live 压力。另一次重跑修正了基本正则的计数匹配错误。

不同增量的 source freeze 分别保存，不能合并为最终源码的一次全矩阵通过。
通过项均无检测到的内核 fault，已完成请求/source/module 排空。已知七角色/
两 CPU 的 pinned mode-4 调度限制没有在此解决，也未把其他用例作为该场景
通过；见 [TODO](../docs/TODO.md#current-checkpoint)。
证据目录：guest `/root/kdlock-evidence/mutex-clobber-20260919/`，host
`/tmp/kd-mutex-clobber-20260919/`。本轮结果不表示性能提升。

完整归档为 guest `/root/kdlock-evidence/mutex-clobber-20260919-evidence.tar.gz`，
宿主副本为 [evidence.tar.gz](/tmp/kd-mutex-clobber-20260919/evidence.tar.gz)，
SHA256：`4450e4b0c26845187edc1faeca0305214934d971f533cb7c840281ab6c4d0f75`。
两侧哈希一致；包内保留全部成功和失败记录、各次源码冻结、新内核捕获基线、
最终 376 文件源码快照及三份构建二进制。离线审计复核源码和二进制哈希，
并确认实际生成物分别采用 mutex ABI 2、spin ABI 1、legacy ABI 0。
最终源码快照早于本段归档索引，不将其冒充全部 live 使用的同一版本。

## 其他冻结增量

<a id="clobber-default"></a>

- **spin 默认化**：删除旧内核安装分支、无消费者的选后入口、旧 shared-word 审计
  及夹具；保留同内核 legacy/FULL 协议。该阶段 mutex node 缩为 256B，后续又接入 ABI 2。
  验证和失败记录随 [mutex 归档](#mutex-clobber)保留，不作为新的全矩阵结果。

<a id="spin-cacheline-isolation"></a>

- **node/gate 分行**：[隔离报告](../bench/spin_cacheline/results/20260919-cacheline-isolation.md)
  保留 7 个基础/相关单元、gate 协议探针和定向 live，以及 40 场交替测量。
  spin node 为 128B，next 与 locked/completed 分行；gate 步长为 64B。
- **先前 CPU 门槛版本**：64 次单锁时间检查及共享计数属于已替换实现。
  定向通过、准备失败与修复在 `/tmp/kd-cpu-hotlock-20260919/evidence.tar.gz`；SHA256
  `df72f0e198a7c954763b6e9c298c7660d242adda6e9b65c338f04ca5e573d31c`。
- **批量采样初版**：[组件及完整操作报告](../bench/hotlock_record/results/20260919-batched.md)
  属于全局发现时期；不能与本地发现的 phase 1 冷地址流直接比较。

<a id="mutex-pinned-mode4-failure"></a>

七角色/双 CPU mutex mode-4 于 2026-09-17 出现 soft lockup，未修复。
现场与禁止抢占忙等的依赖限制一致，未以旧版对照证明根因；其他 mutex 用例
不能替代该场景通过。原始串口/monitor 证据位于
`/tmp/kdlock-frame-fast-20260917/`；限制见 [TODO](../docs/TODO.md#current-checkpoint)。

## 历史验证索引

以下为整理前已提交的记录。运行输入已被后续改造替换；详细的旧命令和阶段性
实现说明移至固定 Git 版本，不再作为当前操作步骤。离线使用
`git show 17f146e52f9f52485b8211addb7dab7195e70452:tests/README.md`。当前测试仍按上面的目录和选择入口运行。

| 阶段 | 冻结记录 |
| --- | --- |
| <a id="spin-state-access"></a>2026-09-18：诊断引用、热字段与普通批次处理 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-state-access) |
| <a id="spin-prefetch-hints"></a>2026-09-18：发布前准备后继预取地址 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-prefetch-hints) |
| <a id="spin-entry-first-cas"></a>2026-09-18：先尝试获取 S，再准备竞争入口 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-entry-first-cas) |
| <a id="shared-register-bank"></a>2026-09-18：JIT 暂存直接复用寄存器包 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#shared-register-bank) |
| <a id="tclock-native-validation"></a>2026-09-18：独立 TCLock 原生栈切换 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#tclock-native-validation) |
| <a id="spin-wwjump-validation"></a>2026-09-17：单份 request、热状态和锁侧 WWJUMP | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-wwjump-validation) |
| <a id="spin-batch-validation"></a>2026-09-17：per-CPU 统计、批内 exe 复用与下一请求预取 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-batch-validation) |
| <a id="spin-nested-state-validation"></a>2026-09-17：嵌套锁记录直写与虚拟 waiter 空轮询 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-nested-state-validation) |
| <a id="spin-shadow-wait-validation"></a>2026-09-17：TCLock 式物理 waiter shadow 等待栈 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-shadow-wait-validation) |
| <a id="tclock-shared-validation"></a>2026-09-17：TCLock 式共享请求，保留 JIT | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#tclock-shared-validation) |
| <a id="waiter-packet-validation"></a>2026-09-17：Waiter 预备寄存器包与原子 frame lease | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#waiter-packet-validation) |
| <a id="frame-fast-validation"></a>2026-09-17：Frame 复用与单锁路径 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#frame-fast-validation) |
| <a id="spin-stackless-validation"></a>2026-09-17：Spin 无栈等待与 IRQ-off 入口 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-stackless-validation) |
| <a id="source-organization"></a>2026-09-15：代码组织回归 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#source-organization) |
| <a id="gs-polling-validation"></a>2026-09-16：GS 与禁止抢占轮询 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#gs-polling-validation) |
| <a id="test-directory-validation"></a>2026-09-16：测试目录分组 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#test-directory-validation) |
| <a id="registration-read-path"></a>2026-09-16：重复注册的读取路径 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#registration-read-path) |
| <a id="gate-request-reuse"></a>2026-09-16：gate 发布与请求内复用 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#gate-request-reuse) |
| <a id="execution-entry-reuse"></a>2026-09-16：执行条目复用 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#execution-entry-reuse) |
| <a id="spin-clobber-v1"></a>2026-09-18：普通 spin caller-clobber v1 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#spin-clobber-v1) |
| <a id="tclock-context-loop"></a>2026-09-18：对照 TCLock 统一 combiner 现场 | [详细证据](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/tests/README.md#tclock-context-loop) |
