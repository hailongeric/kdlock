# 代码阅读与手动运行指南

本轮执行：[单锁字与本地哈希设计（待实施）](design/locking.md)。基线已提交为
`7e2460c`；先清理停用 spin 分发和缓存，保留正在使用的 gate/S、mutex 接入及生命周期检查。
下方旧架构描述保留为当前实现，待替代路径通过后更新。

本文面向第一次逐文件阅读、手动操作当前 checkout 的读者。协议细节仍以
[DESIGN](DESIGN.md)、[寄存器 ABI](JIT_REGISTER_ABI.md) 为准；每个复杂测试的
执行流和判定条件见 [JIT_EXECUTION](JIT_EXECUTION.md)，历史证据只维护在
[VALIDATION](VALIDATION.md)。逐文件定位见 [CODE_MAP](CODE_MAP.md)，
下一阶段性能实验见 [PERFORMANCE_PLAN](PERFORMANCE_PLAN.md)。不要把本文的操作示例当作新测试结果。

项目仅面向 **x86_64 机器**；代码、运行步骤、测试与任务清单均不包含其他架构
适配，也不将其列为延期任务。配对实验比较的是同一架构上的执行策略。

## 1. 当前进展

截至 **2026-09-19**，spinlock 和 mutex 默认均支持显式 GS 代理；被代理线程
等待结果时均保持禁止抢占并 PAUSE 轮询，不睡眠或调度。spin 接受 IRQ-off
task 入口，准备与 combiner 使用 task 内核栈；物理 waiter 在关本地 IRQ 后，
先切到每 CPU 预分配的 8KB shadow 等待栈再发布/轮询，完成时回到 task 栈
恢复原 IRQ 状态和上下文。虚拟 waiter 仍在执行者 C 栈上服务 owner/ACK。
frame 与锁记录按有效深度复用，push/pop 不再整块清零；普通单锁完成跳过
通用清理链。spin waiter 发布前在独立预分配 request 中准备 frame/寄存器，
combiner 按指针绑定；复杂/native/remote 路径共用逻辑包，物理 owner 状态独立。
诊断 slot 由批次/请求复用，计数与身份分行；普通请求元数据集中在前两条
缓存行，普通完成合并终态检查和解绑。source/provider lease 按批次持有，request 引用保留到最后读取与 owner ACK/pop。
默认要求 `kdclobber2` 的 caller-clobber v1 接口：普通 spin/mutex 由编译器保存活跃值，
正常请求只捕获/恢复 RIP/RSP/RBP，中途退出完整物化逻辑 GPR。新旧及混合
ABI 在同一个 combiner C 帧中连续执行；IRQ/BH/irqsave/trylock 及 mutex 特殊
调用契约保留。TCLock 对照、版本身份和状态边界见[寄存器 ABI](JIT_REGISTER_ABI.md#10-普通-spin-的-caller-clobber-v1)。
旧内核的三套安装分支已删除；同一内核上的旧调用者仍受支持。普通 mutex 已使用独立 ABI=2、最小入口及正常恢复；中途 FULL 包保留 owner ACK 所需的
独立生命周期，旧调用者兼容路径仍保留。见 [mutex ABI](JIT_REGISTER_ABI.md#mutex-clobber-assessment)。
测试代码按用途分组，默认仅验证基础简单功能和
直接相关功能。这是受控实验用的 x86_64 JIT 代理原型，尚未完成全部任务，
也不保证任意内核代码均可代理或已经取得性能收益。

### 1.1 版本与验收范围

- 当前实现以 `kdclobber2` 为默认，普通 spin/mutex clobber、缓存行隔离和
  per-CPU 本地热锁发现均已接入。源码提交身份与每轮测试冻结身份分别记录。
- 最近有 live 证据的本地发现版本完成六项定向 live 和相关单元；后续结构整理只重验相关单元和构建，完整 spinlock 吞吐未重测；
  见 [当前验证范围](../tests/README.md#当前验证范围)。
- 旧内核、旧采样器与各次优化结果只属于对应冻结版本，不拼接成全量通过；
  owner/ACK、两元素 args 和已明确延期的正确性边界保持原约定。

### 1.2 已完成

| 能力 | 当前实现与验收边界 |
| --- | --- |
| 主执行链 | 已有 hook 发现临界区，daemon 读取并翻译原机器码，上传发布后由 combiner 执行 JIT；不要求修改临界区源码，但依赖已有 guest hook。 |
| 单锁与嵌套代理 | mode 0/1/2 为 spin 单锁/嵌套/服务，mode 3/4/5 为 mutex 对应模式；mode 6/7/8 覆盖深层、提前释放 A、独立队列与远端关系。均有各自冻结版本的实际 JIT 证据，不表示本轮重跑全部模式。 |
| 原生互斥与完成协议 | spin/mutex 保留真实原锁，非目标线程仍受同一把原锁保护。native 后缀由 waiter 执行，原 owner 处理 unlock 并确认；没有 mutex owner handoff。 |
| 前进续跑 | 普通 CALL miss、CALL 次数额度及已有受检边界从当前寄存器/栈状态续跑，不从入口重放、不撤销既有写入；不是任意故障恢复。 |
| 服务退出和返回 | mode 2/5 的时钟和有界标量 `int_sqrt` 服务原生执行后返回 JIT；额度超限交回 waiter 完成后缀。通用可变参数 `printk` 未实现。 |
| GS 与等待策略 | spinlock/mutex 默认均支持显式 GS 读/写/RMW，使用 origin base；受支持的 current_task 读取使用 logical waiter。两种已发布请求的 waiter 都禁止抢占并轮询至结果或 native handoff，不睡眠或调度。spin 队列区间关闭本地 IRQ；NMI、mutex IRQ 并发及 native service 上下文仍有限制。 |
| Spin 栈与 IRQ | IRQ-on/off task 均可进入代理；combiner 使用 task 栈，物理 waiter 发布前切到每 CPU 8KB shadow 等待栈，完成/native 唤醒回 task 栈并从共享包恢复，保留原 IRQ 状态。shadow 锁记录和 wrapper 暂存独立，mutex 栈保留。 |
| 普通 spin/mutex 状态 ABI | `kdclobber2` 的新入口仅用 RIP/RSP/RBP，正常完成为独立 COMPLETE 分类；中途 FULL 出口与旧 ABI 保留完整状态。新旧混合批次用同一 C 循环，旧批次调用适配只额外保护 RBP，偏移 0 的普通 wrapper 仍满足 C ABI。 |
| Frame 与单锁路径 | 有效深度界定 frame/锁记录范围，spin 共用 waiter 预备的 request/frame，按指针绑定；首次正常 unlock 可直接完成，复杂分支保存独立 owner 状态并继续用共享包。source lease 按批次持有，pop 仍验证 LIFO、终态和 owner/ACK 依赖。 |
| 翻译准入 | 审查实际可能执行的 JIT 范围，已有入口谓词、受检 mutex 栈事实及静态 core/module per-CPU 筛查；动态地址的访问时保护不在其中。 |
| 测试与复现入口 | 按行为合并、显式选择测试，保留实际正文证据、完整负载状态、owner/ACK 和排空检查；已有源码/环境/生成物归档及离线校验。单元入口和 shell driver 按用途分组；默认两个基础 C，相关 Python 显式选择，全量仅按要求运行。 |
| 运行环境与可读性 | 固定四个 Python 运行依赖，提供 guest venv 安装、目录/文件索引、手动步骤及关键函数/协议操作的用途注释；不声称每个函数逐一完成审查。 |
| 测量基础 | 已有原生/JIT 配对、翻译 wall/CPU/RSS、负载计量和默认关闭的 `jit_timing`。当前十项边界包括 queue、owner wait 和新增 native handoff；翻译器符号匹配已做局部优化。 |
| TCLock 独立后端 | [tclock_backend](../tclock_backend/README.md) 保留上游完整 spin 队列、shadow 等待栈、六寄存器/RSP 切换及 WWJUMP，在同一 hook 下运行原生正文；本轮仅验收单锁全局计数器负载。 |

具体执行链见下一节；协议见 [DESIGN](DESIGN.md)，寄存器和输入约定见
[JIT_REGISTER_ABI](JIT_REGISTER_ABI.md)，逐项历史证据只维护在
[VALIDATION](VALIDATION.md)。

### 1.3 最近验证与历史结果

验证结果统一从以下入口查看，避免在多份当前说明中维护阶段计数：

| 范围 | 入口与解释 |
| --- | --- |
| 最近完整 spin 三方成绩 | [五档线程结果](../bench/tclock_compare/results/20260919-thread-scaling.md)：隔离前基线，clobber caller；不能与后续版本拼接倍率 |
| 历史批量采样优化 | [批量采样对照](../bench/hotlock_record/results/20260919-batched.md)：90 场组件成本与 40 场完整 spin 操作分开报告 |
| 当前实现的功能验证 | [默认化与 mutex 清理](../tests/README.md#clobber-default)，[mutex clobber](../tests/README.md#mutex-clobber)，以及按 clobber、共用寄存器、入口、预取和状态访问分别冻结的历史记录 |
| 运行与汇编查看 | [bench/README](../bench/README.md)：入口和统计口径；[执行路径](../bench/spin_cacheline/EXECUTION_PATHS.md)负责当前实现及 TCLock 对照 |
| 早期 benchmark | [历史索引](../bench/spin_cacheline/results/HISTORY.md)：已被替代的阶段报告、Git 版本和归档哈希 |
| 其他历史验收 | [VALIDATION](VALIDATION.md)：时间、源码身份、限制和失败记录 |

mutex 正例按 `mutex_jit=1` 验收；生成/发布日志本身不能作为 JIT PASS。
不同阶段的通过项不拼接成当前版本全量通过，也不证明任意上下文或通用提速。

### 1.4 未完成与明确延期

`record` 已采用每 CPU 批量计数和稀疏计时，仍仅按频率晋升；
原生/探测/代理切换尚未实现，见
[监测与准入待办](TODO.md#hotlock-monitoring-and-adaptive-admission)。

| 分类 | 事项与当前处理 |
| --- | --- |
| 当前未通过 | 2026-09-18 三方比较尝试中，kdlock 的 c16/t4/clobber 并发 promotion 超时并出现 RCU stall；正式计时尚未开始。根因未修复，后续完整稳态矩阵统一单 CPU 准备，见[故障及结果](../bench/tclock_compare/results/20260918-native-stack.md#失败记录与边界)。 |
| 当前未通过 | 2026-09-17 七角色/双 CPU mutex mode-4 出现 soft lockup；现场符合禁止抢占忙等的依赖可运行性限制，但没有旧版对照证明归因。保留 [失败证据](../tests/README.md#mutex-pinned-mode4-failure)，不以其他 mutex 用例替代该场景通过。 |
| 历史未通过 | 旧可调度轮询策略下，八线程/两 CPU 的短 mode 5 曾发布代码却没有执行 JIT。该失败点未重跑；当前禁止抢占轮询需要重新设计 CPU 放置，旧超额订阅记录不验证新策略。 |
| 当前使用限制 | 已发布请求的 waiter 保持禁止抢占轮询，sleep/parking 不属于当前设计。依赖 waiter 让出同一 CPU 的旧场景需要重新放置线程；不能直接沿用旧通过记录。 |
| 尚未完成 | 更多有明确契约的服务、通用 `printk`；真实未修改生产子系统负载；完整可复现系统/工具链与运行代码代际身份。 |
| 尚未完成 | 完整锁获取/观测成本的独立因果归因与摊销。诊断引用、缓存行布局、请求元数据及普通批次处理已有递进对照；共享计数原子更新、实际批长和 wrapper/正文重写成本仍待独立测量。原版 TCLock mutex 不是当前 guest 的可直接加载模块，不为此另改内核。 |
| 明确延期 | 访问时动态地址 guard、原指令处 waiter 续跑及必要的局部条件码保存；动态指针和并发改写仍可能绕过静态筛查。 |
| 明确延期 | 通用 flags、特殊指令及故障语义修复；INT-to-NOP、部分 warning-only 行为仍在。任意 JIT 故障、间接跳转 miss 和基本块预算不是已支持的恢复出口。 |
| 明确延期 | 不可变 JIT 代码版本、完整发布校验与按执行代际回收；当前仍原地覆盖，锁互斥不能排除跨锁并发风险。 |
| 不作为本阶段前置 | 极少发生的资源/取消/退出/远端交错和别名组合，不继续补实现或扩展矩阵；已有检查保留。通用热卸载、对象生命周期和任意 per-CPU/IRQ/RCU 上下文等价性不作保证。 |
| 不在项目范围 | 其他架构、用户态/futex、rwsem；不列为后续适配任务。 |

剩余项的契约与优先级见 [TODO](TODO.md#direction-and-priority)。这些条目是状态
记录，不是本轮继续自动启动的任务清单；下一阶段先由用户选择具体主目标，
不默认重跑历史矩阵或扩展稀有情况。

## 2. 先认识执行链

按职责拆分后的目录阅读地图分别维护在
[bench](../bench/README.md#代码组织)、[include](../include/README.md)、
[kernel_module](../kernel_module/README.md) 和
[workload_modules](../workload_modules/README.md)。下文保留公共入口及全项目索引；
各入口内部的私有 `.inc` 组件以对应目录 README 为准。

推荐先按这条链读代码，再查第 5 节的完整文件索引：

```text
bench/klock_test.c                      用户线程 -> ioctl
  -> workload_modules/lock_scenarios/klock_module.c
                                       按 mode 进入真实原生锁临界区
  -> guest 已有 hook                    不在本仓库重新实现 Linux 锁
  -> kernel_module/kd_main.c            安装 spin/mutex hook 与既有 owner 路由
  -> kernel_module/kd_lock.c            先 CPU/单锁频率，再目标进程、原锁与 entry 路由
  -> kd_spinlock.c / kd_mutex.c         排队、持有原锁、选择 combiner
  -> exe.c + kd_exec.c                  就绪检查、frame、寄存器与锁记录
  -> include/wrapper.S + asm/jit.S      执行翻译指令
  -> 控制调用 / hostcall / native 后缀  依据出口协议继续
  -> 真实 owner unlock + ACK            排空并恢复 waiter

翻译侧：sys.c /dev/kd_dev -> daemon/daemon.c
  -> disassem/device_session.py         同一设备 lease、source pins、CAPS
  -> memread.py + disassem.py           读取、解码、补齐 CFG、选择 JIT 范围
  -> context_policy.py                  上下文/地址/锁边界准入
  -> special_inst.py + normal.py        虚拟寄存器/栈到实际汇编
  -> wrapper.S + jit.S -> jit.bin       组装、上传，未来请求才可使用
```

阅读时区分四个身份：**waiter** 是原调用线程；**combiner/executor** 是实际执行
代理的线程；**physical owner** 是 Linux 原锁的持有者；**logical task** 是 frame
记录的 waiter。后两者不能混为同一 `current`。`kd_exec_frame.parent` 表示本 CPU
的物理 frame 嵌套，远端逻辑关系还要看 `resume_target`。

代码注释重点说明文件用途、入口/出口、引用和 ACK 的最后访问，已有充分注释不重复
添加。C/Python/汇编中的英文名称与符号保持一致，中文解释集中在本文和协议文档。
`tests/kernel/` 中的 C 多为 include 片段，不是可以单独 `insmod` 的模块。

## 3. 一步一步运行

### 3.1 确认宿主机与 guest

宿主机 checkout 是 `/home/eric/vm/vm-shared/kdlock`；guest checkout 是
`/root/host_fs/kdlock`。**模块编译、单元测试、daemon、benchmark 均只在 guest
执行**。不要因宿主机也能看到源码就在那里运行 `make` 或 `insmod`。

宿主机先执行：

```bash
cd /home/eric/vm/vm-shared/kdlock
ps -aux | grep '[q]emu-system-x86'
timeout --kill-after=5s 20s ssh -o BatchMode=yes -o ConnectTimeout=5 \
  -p 2222 root@127.0.0.1 'uname -r'
```

进程存在且 SSH 正常时使用现有 VM。确认没有旧 QEMU，才在另一个宿主机终端启动：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

该脚本确实支持 `recovery`，以前台方式运行 QEMU，使用相对磁盘路径；不要从其他
目录调用，不要同时启动两个实例。它不自动恢复某个快照。SSH 超时的日志保留、
强制关闭旧 VM 和重新启动步骤见 [VM 故障处理](AGENTS.md#虚拟机存活检查与重启)。
权限错误或宿主机沙箱看不到进程，不等于 guest 崩溃。

宿主机另开 monitor，或在 socket 为 root 所有时用 `sudo nc -U /tmp/qemu-monitor.sock`：

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh monitor
```

在 monitor 中输入 `info snapshots`，确认真实可用的 tag；没有快照时，在 guest
空闲、没有测试模块的状态下执行 `savevm pre_kdlock_manual`，再次查询确认成功。
使用 Ctrl-C 断开 monitor 客户端，**不要输入 `quit`**，否则会关闭 VM。

### 3.2 进入 guest 并检查基线

当前默认使用 `6.1.159-kdclobber2`；provider 不再支持旧内核安装接口，保留原
`6.1.159` 和 `kdstatic2` 作为可恢复基线。先检查实际运行内核，再选择对应的
source/build/baseline。不能用原基线核验新内核，也不能覆盖旧基线。

```bash
ssh -p 2222 root@127.0.0.1
bash
cd /root/host_fs/kdlock
findmnt -T /root/host_fs/kdlock
uname -r
export KDIR=/root/linux-6.1.159-kdclobber2
python3 bench/spin_cacheline/kernel_identity.py \
  --kernel-source "$KDIR" \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
cat /proc/cmdline
cat /sys/kernel/debug/sched/preempt
lscpu -e=CPU,NODE,ONLINE
```

后续 guest 示例使用 **Bash**。该实验的捕获 Build ID 为
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；命令同时核对 source/config/build
及实际运行身份，不能只看 release。启动参数保留 `nokaslr`，动态抢占为
`(voluntary)`，既有角色按 40 CPU、双 NUMA 布置。缺失或不匹配应停止排查，
不是 SKIP/PASS，也不应自动重建内核。实验构建历史见
[mutex_clobber](../kernel_experiments/mutex_clobber/README.md)。

仅在恢复或重现历史版本时启动原始 `6.1.159`，使用 `KDIR=/root/linux-6.1.159` 和
`python3 kernel_baseline/verify.py --source "$KDIR" --build --running`；其
Build ID 为 `6f9f2e9fec382e97f620553793aa90b527a30af5`。`kdstatic2` 按其
[独立基线](../kernel_experiments/spin_static/README.md)核验。旧内核必须使用对应
历史 provider 源码。benchmark 的 `--kernel-source/--kernel-baseline` 默认已经
指向上述 clobber 树与独立捕获目录；可显式指定匹配身份，不能绕过校验。

normal 的 9p 源码是共享的，不需要搬动。recovery 同名路径是 ext4，修改后要比较
两侧 SHA256，只传输变化文件。例如宿主机比较并按需同步一个文件：

```bash
cd /home/eric/vm/vm-shared/kdlock
sha256sum kernel_module/kd_main.c
timeout --kill-after=5s 20s ssh -o BatchMode=yes -o ConnectTimeout=5 \
  -p 2222 root@127.0.0.1 'sha256sum /root/host_fs/kdlock/kernel_module/kd_main.c'
# 仅在哈希不同且 guest 没有运行测试时执行：
scp -P 2222 kernel_module/kd_main.c root@127.0.0.1:/root/host_fs/kdlock/kernel_module/
```

不要递归覆盖/清空 `/root/host_fs`，也不要依赖旧 `/tmp` 辅助脚本才能操作项目。

### 3.3 检查依赖与空闲状态

翻译器只在 guest 安装。当前配方使用 CPython **3.10**，四个运行依赖及其版本
统一写在 [requirements.txt](../disassem/requirements.txt)，包括 miasm 的传递依赖；
不再以某台机器的全局 pip 状态作为安装说明。还需已有的 gcc/make/binutils 和
Python 3.10 开发头文件，以构建 miasm 的本机扩展。它不是 guest 内核构建。

在 guest 项目根目录先检查工具。若缺少 `venv` 支持，先模拟安装，确认不会升级
系统 Python 或修改内核后再安装；不要执行全局 `pip install --upgrade`：

```bash
command -v gcc make objcopy objdump readelf timeout taskset python3.10
apt-get --simulate --no-upgrade --no-remove --no-install-recommends install python3.10-venv
# 仅在已审查上条计划后执行；当前 guest 只新增三个 venv 支持包。
apt-get --yes --no-upgrade --no-remove --no-install-recommends install python3.10-venv
```

首次创建一个仓库外的新环境和 wheel 目录。以下命令从干净 venv 构建固定版本的
运行依赖，再从本地 wheels 安装；`wheel==0.37.1` 只是构建辅助，不属于四个
运行依赖。下载使用公共 PyPI，离线安装仍需先备齐匹配的 wheels。

```bash
VIRTUAL_ENV=$(mktemp -d /root/kdlock-venv.XXXXXX)
python3.10 -m venv "$VIRTUAL_ENV"
export VIRTUAL_ENV
export PATH="$VIRTUAL_ENV/bin:$PATH"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
WHEELS=$(mktemp -d /root/kdlock-wheels.XXXXXX)
python3 -m pip --isolated --disable-pip-version-check install --no-cache-dir --no-deps \
  --index-url https://pypi.org/simple wheel==0.37.1
python3 -m pip --isolated --disable-pip-version-check wheel --no-cache-dir --no-deps \
  --no-build-isolation --index-url https://pypi.org/simple --wheel-dir "$WHEELS" \
  -r disassem/requirements.txt
python3 -m pip --isolated --disable-pip-version-check install --no-index --no-deps \
  --find-links "$WHEELS" -r disassem/requirements.txt
python3 -m pip --isolated check
```

检查解释器、包位置和空闲状态：

```bash
command -v python3
python3 -c 'import sys; from importlib.metadata import distribution; print(sys.executable, sys.prefix); [print(n, (d := distribution(n)).version, d.locate_file("")) for n in ("miasm", "future", "pyparsing", "pyelftools")]'
python3 -c 'import sys; sys.path.insert(0, "tests"); import regression; regression.check_idle(); print("guest idle")'
bash tests/run_all.sh --list
```

解释器及四个包的位置应在所选 venv 内；`pip check` 必须成功。后续 make、测试、
手动 daemon 和翻译命令都从这个 Bash 会话启动。daemon 用 `execlp("python3")`
继承 PATH，**仅设置 `VIRTUAL_ENV` 不会选择解释器**。重新 SSH 后，先激活实际创建的
环境：`source /root/kdlock-venv.<实际后缀>/bin/activate`，并清除 `PYTHONHOME/PYTHONPATH`、
设置 `PYTHONNOUSERSITE=1`；不要原样执行占位路径，也不必每次重新安装。
本指南直接以 guest root 运行；另加 sudo 可能重置 PATH，不能假定它保留虚拟环境。

这里固定的是运行包版本，不是包字节、pip/setuptools、编译器或整个 guest 镜像。
源码归档包含配方，常规运行器记录选择的解释器和安装元数据，不自动打包 venv。
新环境首次按 3.4 验收；已有环境及基础路径未变时按改动选择测试，不反复全量运行。
`check_idle` 报错时先查已存在的进程/模块，不要直接强卸载。
无参数或 `--list` 只列清单，不会启动负载。测试脚本可能调整 guest 的
`kernel.randomize_va_space`、`kernel.numa_balancing` 并清理生成目录，因此只用实验 VM。

### 3.4 构建

```bash
make -C kernel_module W=1
make -C workload_modules/lock_scenarios W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
```

得到 `kernel_module/kdlock_km.ko`、`workload_modules/lock_scenarios/klock_module.ko`、`daemon/daemon`、
`bench/klock_test`。先构建 provider，再构建依赖它导出符号的 workload。
默认不启用 `KDLOCK_SELFTEST`、`KDLOCK_NUMA` 或第二源码模块；相关复杂驱动会自行
选择并在结束后恢复默认构建。不要任意沿用另一个实验的编译开关。
当前 `W=1` 构建仍有手写恢复/切栈汇编及测试 CLD 的 objtool warning，构建成功
不表示这些语义已经修复。若出现新的 error 或不同 warning，先保留日志排查。

默认只检查两个基础 C 程序；按改动用 `PY_TESTS` 增加相关功能，不自动全量运行：

```bash
make -C tests/unit run
# 测试选择器有改动时增加对应检查：
make -C tests/unit run TESTS= PY_TESTS=infrastructure/test_regression.py
```

只改某类代码时，按 [增量回归选择](JIT_EXECUTION.md#7-分层与增量回归) 选相关
unit，确有需要时再选择相关 live。单元测试中的用户态机器码执行也留在 guest，不计为内核 JIT。

### 3.5 按用例手动运行（推荐）

先预览，不执行：

```bash
bash tests/run_all.sh --suite core --dry-run
bash tests/run_all.sh --case mode-4 --dry-run
```

确认上面的恢复快照后，才在 guest 设置变量并一次运行一项：

```bash
export KDLOCK_RECOVERY_CONFIRMED=1
RUN_DIR="$(mktemp -d /tmp/kdlock-manual-case.XXXXXX)/run"
bash tests/run_all.sh --case mode-4 --timeout 300 --output "$RUN_DIR"
```

该命令执行真实的 mutex 嵌套竞争，显式启用并读回 `mutex_jit=1`，处理构建、模块、
daemon、角色启动、实际 JIT 判定和排空。退出非零就查看它打印的证据目录，先不要
接着运行下一项。不是只生成 `jit.bin` 就结束。

根据想看的机制，**选择**下列入口，不要求全部连续运行：

| 目的 | guest 命令参数，接在 `bash tests/run_all.sh` 后 |
| --- | --- |
| spin 的 service 出入 | `--case mode-2` |
| mutex 的 service 出入 | `--case mode-5` |
| 嵌套 B 的独立竞争及两个 A root 共享 B | `--case mode-8`，纯 JIT/混合完成见 [6.14](testing/spin_protocols.md#614-两个独立-root-共享-b-combiner) |
| mutex CALL miss 后寄存器续跑 | `--case registers-4-3` |
| 学习两层、跨模块 helper 后 JIT 及容量续跑 | `--case native-mutex-depth` |
| 两个 mutex native frame 同时存活 | `--suite mutex-parallel` |
| 上下文不适合代理时的原生拒绝 | `--suite admission` |
| 五个不重复的日常主用例 | `--suite core` |
| 特意观察单锁基本流程 | `--case mode-0` 或 `--case mode-3` |

`core` 是 mode 2/7/8/4/5，不是 0 到 8 的全模式扫描。mode 0/1/3 等被覆盖诊断
仍可显式点选，默认不会再附加；`extended` 也不重复这十一项已登记的被覆盖诊断。
mode 6 的单 frame 三锁等独立协议仍保留。不要直接运行 mode 9 故障路径来学习启动。

运行器输出目录内执行离线校验：

```bash
# 沿用上面设置的 RUN_DIR；换终端后需重新赋值为本次运行器目录。
python3 tests/verify_evidence.py "$RUN_DIR"
```

这是检查已保存证据，不会重跑 JIT，也不证明日志来源可信。原生负例、纯原生对照
和实际 JIT 正例是三类不同结果。

### 3.6 拆开观察模块、daemon 和负载（可选）

本节只用于理解组件，展示 **mode 3** 的一条简单人工流程，不替代上一节完整用例
的协议 oracle，也不是日常新增 smoke。不要与 `run_all.sh` 或其他实验同时运行。
所有命令在同一 guest Bash 会话中执行；开始前必须完成 3.1-3.4 的检查。
不要直接在交互 shell `source tests/common.sh`：它依赖驱动的 `$0` 并安装卸载 trap。

保存日志，确认全新会话后加载 provider 和 workload：

```bash
cd /root/host_fs/kdlock
RUN_DIR=$(mktemp -d /tmp/kdlock-manual.XXXXXX)
dmesg > "$RUN_DIR/dmesg.before.log"
dmesg -C
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
insmod kernel_module/kdlock_km.ko target_process=klock_test mutex_jit=1
insmod workload_modules/lock_scenarios/klock_module.ko
cat /sys/module/kdlock_km/parameters/mutex_jit
python3 disassem/device_session.py status
python3 disassem/device_session.py capabilities
```

应读到 `mutex_jit=1`、source `state=0`，能力包含 `mutex_stack_bytes=256` 和
`percpu_module_bytes=8192`。`state=1/2` 的旧会话不能重新启动 daemon 使用。
两条 `insmod` 应逐条执行并检查返回值；provider 加载失败时不要加载 workload。
这些值证明配置/能力，不证明执行。启动 daemon 会替换其管理的生成工作区，先保留旧证据。

```bash
cd daemon
set +m
KD_JIT_BODY_WITNESS=1 setsid ./daemon --mode per-tgid --verbose > "$RUN_DIR/daemon.log" 2>&1 &
DAEMON_PID=$!
cd ..
timeout --kill-after=5s 10s bench/klock_test 1 1 1 1 3
timeout --kill-after=5s 20s bench/klock_test 1 48000 10 1 3
```

`set +m` 关闭当前 Bash 的交互 job control，使后台 `setsid` 不因进程组首领身份
另行 fork，后面的 `$!` 才对应 daemon 的会话/进程组。第一波仅作负载准备；
当前没有 module-wide warmup，不再插入旧的一秒等待，以免消耗单锁窗口。连续调用
先打开执行 CPU 的门槛，各锁随后使用本 CPU 的独立窗口，只有达标地址才进入共享集合。周期单位及未晋升的排查见 [热锁准备](JIT_EXECUTION.md#32-热锁晋升与翻译准备)。
第二波是单线程采样/注册/翻译准备，不应作为 JIT
竞争验收。查看 daemon 日志，等待它完成本条目的翻译。随后选取唯一产物：

```bash
find daemon -type f -path '*/asm/jit.bin'
mapfile -t IMAGES < <(find daemon -type f -path '*/asm/jit.bin')
test "${#IMAGES[@]}" -eq 1
ASM_DIR=$(dirname "${IMAGES[0]}")
python3 tests/protocols/mutex_signal_protocol.py ready --artifact "$ASM_DIR" \
  --output "$RUN_DIR/published.json"
```

若还没有产物，先看日志并等待翻译完成后重新执行本段；若多个产物，不要任取第一项，
应排查旧会话或意外 workload。`test`、翻译或 `ready` 失败时不要进入下一步。
`ready` 有界等待对应 RIP/TGID 的 mutex NORMAL 状态，避免文件生成早于上传。

在负载之间的空闲边界停止 daemon 进程组并等待翻译子进程退出，再进行竞争，避免
本人工观察过程中并发重编译。先确认 PID/进程组确实属于刚启动的 daemon：

```bash
ps -p "$DAEMON_PID" -o pid,pgid,args
if test "$(ps -p "$DAEMON_PID" -o pgid= | tr -d ' ')" = "$DAEMON_PID"; then
    kill -TERM -- "-$DAEMON_PID"
    wait "$DAEMON_PID"
else
    printf 'STOP: inspect daemon identity before cleanup\n' >&2
fi
python3 disassem/device_session.py status
```

daemon 被 SIGTERM 结束时 `wait` 可返回 143；这与后续 benchmark 失败不同。
必须确认没有翻译子进程、status 的 `writers=0`；**此时不要 retire**，因为还要执行
已经发布的 JIT。随后运行已编译条目的竞争：

```bash
# 每个 worker 在自己的固定 CPU 上建立本地频率；空临界区不增加正文 counter。
printf '1\n' > /sys/module/klock_module/parameters/cpu_frequency_prepare
KD_TEST_LOCAL_PREPARE=1 timeout --kill-after=5s 30s bench/klock_test 8 1 1000000 1 3 > "$RUN_DIR/workload.log" 2>&1
dmesg > "$RUN_DIR/dmesg.execution.log"
grep 'JIT body witness:' "$RUN_DIR/dmesg.execution.log"
grep 'mutex JIT delegation ok' "$RUN_DIR/dmesg.execution.log"
cp -a "$ASM_DIR" "$RUN_DIR/asm"
```

必须核对 marker 的 entry/lock 是本次条目，且 `body=1`。没有 marker 就不能声称
动态翻译指令执行了；仅有 `begin delegate`、`install JIT chunk`、普通返回码也不够。
此观察仍需结合保护数据、失败计数和卸载时的最终统计；严谨验收使用 3.5 的驱动。

### 3.7 排空、保存和卸载

人工流程结束时，先等待所有自己启动的 benchmark 正常返回、daemon/翻译者退出。
检查 `pgrep -af 'klock_test|daemon|disassem.py'` 的真实身份，不能凭匹配字符串就杀掉
未知进程。停止一个持锁或借锁 waiter 可能使 owner 无法收到 ACK，不能以强杀代替排空。

```bash
python3 disassem/device_session.py status
(
    set -e
    python3 disassem/device_session.py retire
    rmmod klock_module
    rmmod kdlock_km
)
dmesg > "$RUN_DIR/dmesg.final.log"
grep -E 'final counter:|kd_exec|kd_native stats:|jit_success|cs_state' "$RUN_DIR/dmesg.final.log"
python3 -c 'import sys; sys.path.insert(0, "tests"); import regression; regression.check_idle(); print("guest idle")'
```

`retire` 失败（例如 EBUSY）就停在该步骤，继续查 writer/frame/队列持有者，不执行
后面的 `rmmod`。上面的子 shell 用 `set -e` 保证失败即停止卸载链，不退出当前
交互会话；不要去掉这个保护。retire 不可撤销；成功后新实验需要完整卸载/重新加载会话。
仅重启 daemon、只重载 workload 或删除生成物都不能重置旧 JIT 会话。
若通过复杂驱动加载了 `kd_depth_source`，卸载顺序是 workload、helper、provider；
用相应驱动完成清理，不在本 mode 3 示例里手工添加它。

核对 protected-state 完整性、owner/ACK、失败计数及 `BUG:`、panic、lockup 等错误。
上例在每条负载恰好运行一次的前提下，最终 counter 是 `1 + 48000 + 8 = 48009`；
它单独正确也不是 JIT 证据。当前卸载流程仅适用于可恢复、已排空的实验，不是通用
安全热卸载。人工目录没有自动运行器的完整 manifest，不要用离线 verifier 冒充完整归档。

## 4. 产物与参数怎么读

| 对象 | 含义和用法 |
| --- | --- |
| `/dev/lock_dev` | benchmark ioctl 入口，不接收 JIT 二进制。 |
| `/dev/kd_dev` | 注册表快照、代码上传、source/CAPS 控制；不要手写任意 payload。 |
| `target_process=klock_test` | 新目标按 task comm 匹配；改进程名可能使新请求不再代理。 |
| `mutex_jit=1` | 显式要求 mutex JIT，项目默认路径。 |
| `KD_JIT_BODY_WITNESS=1` | 翻译时加入返回后可观测的 body 标记；不能追溯修改旧产物。 |
| daemon `--mode flat|per-tgid` (`--mode 1|2|v1|v2` 为兼容) | 分别是 `daemon/<RIP>/`、`daemon/<RIP>/<tgid>/` 工作区布局。 |
| benchmark 参数 | `线程数 每次ioctl的CS循环数 CS工作量 每线程ioctl次数 mode [role-base]`。 |
| `KD_TEST_METRICS=1` | 可选 JSON ioctl 测量；排除创建/join，保留每 worker 完成数。计时、失败字段、日志和 JIT 关联见[测量流程](../bench/lock_scenarios/README.md#33-带观测的负载测量)，不是纯 CS 或三方性能基线。 |
| 回归/配对 `--jit-timing` | 显式选择只读装载参数 `jit_timing=1`，记录 JIT、native owner 等待、私有队列和 native 交接的十项区间；交接包含等待，不相加。直接 shell 使用 `KD_JIT_TIMING=1`，每次装载都核对；执行流及边界见[边界计时](../bench/lock_scenarios/README.md#可选的-jit-边界计时)。 |
| `callee_table.txt` / `ij_table.txt` | 学习的 CALL/IJ 目标；由 daemon 维护，不是随意开放的白名单。 |
| `asm/jit.S` / `jit.bin` / `bin.txt` | 生成汇编、机器码、反汇编；存在不等于已上传或执行。 |
| `.ko`、`.o`、`.mod*`、`Module.symvers`、`modules.order` | guest Kbuild 产物，不手工加注释或同步回宿主机覆盖源码。 |
| `daemon/daemon`、`bench/klock_test`、unit 可执行文件 | 本地构建产物，不是要修改的 C 源文件。 |
| `__pycache__`、`.ruff_cache` | 工具缓存；不是项目实现或验收证据。 |
| `/tmp/kdlock-*` | 每次运行的外部证据/临时目录；不要将其他 freeze 的 PASS 混入本次。 |

常见停点：找不到设备先检查加载；无翻译先查目标名、promotion、daemon、CAPS 和
source 错误；`CONTEXT_NATIVE_ONLY` 是拒绝，不是翻译成功；
`CONTEXT_SCREENING_ONLY` 是已知缺口告警，不是访问时保护；`in use`/EBUSY 先查引用，
不强卸载。手动直接调用翻译器的参数及设备 lease 边界见 [daemon 文档](../daemon/README.md)，
通常由 daemon 发起翻译，避免漏掉布局、lock kind 或 source session。

## 5. 完整目录与文件索引

详细说明见 [CODE_MAP](CODE_MAP.md#5-完整目录与文件索引)。

<a id="51-顶层与文档"></a>
<a id="52-生产模块-kernel_module"></a>
<a id="53-共享接口-include"></a>
<a id="54-翻译器-disassem"></a>
<a id="55-桥接负载与基线"></a>
<a id="56-测试入口-tests"></a>
<a id="57-测试控制器和-oracle"></a>
<a id="58-demo-临界区与内核测试片段"></a>
<a id="59-单元测试-testsunit"></a>

## 6. 阅读完以后改哪里

先从自己要改的行为回到第 2 节的执行链：JIT 范围改 analyzer，机器码 lowering 改
普通/特殊 lowerer，出口分类改 `exe.c`，锁/ACK 生命周期改 backend 与 `kd_exec.c`，
学习/发布改 daemon/device。不要在 workload 或 oracle 中放宽判定来绕过生产缺口。

新增功能必须注明目的和约束，选择覆盖该行为的复杂用例；基础已通过时不再默认重复。
涉及 flags 新出口、guest hook reader 或版本隔离时先查 TODO 的授权边界。
阅读与操作文档的完善不代表这些未完成功能已经实现。
