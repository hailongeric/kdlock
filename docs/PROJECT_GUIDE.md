# 代码阅读与手动运行指南

本文面向第一次逐文件阅读、手动操作当前 checkout 的读者。协议细节仍以
[DESIGN](DESIGN.md)、[寄存器 ABI](JIT_REGISTER_ABI.md) 为准；每个复杂测试的
执行流和判定条件见 [JIT_EXECUTION](JIT_EXECUTION.md)，历史证据只维护在
[VALIDATION](VALIDATION.md)。不要把本文的操作示例当作新测试结果。

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
- 最新本地发现版本已完成六项定向 live 和相关单元，完整 spinlock 吞吐未重测；
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
  -> translation.py + 各 lowerer        虚拟寄存器/栈到实际汇编
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
| 嵌套 B 的独立竞争及两个 A root 共享 B | `--case mode-8`，纯 JIT/混合完成见 [6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner) |
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
| `KD_TEST_METRICS=1` | 可选 JSON ioctl 测量；排除创建/join，保留每 worker 完成数。计时、失败字段、日志和 JIT 关联见[测量流程](JIT_EXECUTION.md#33-带观测的负载测量)，不是纯 CS 或三方性能基线。 |
| 回归/配对 `--jit-timing` | 显式选择只读装载参数 `jit_timing=1`，记录 JIT、native owner 等待、私有队列和 native 交接的十项区间；交接包含等待，不相加。直接 shell 使用 `KD_JIT_TIMING=1`，每次装载都核对；执行流及边界见[边界计时](JIT_EXECUTION.md#可选的-jit-边界计时)。 |
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

以下覆盖当前维护的源码、脚本、构建入口和基线材料。生成文件按第 4 节分类，不逐个
列入源码清单。脚本编号有空缺是整理后的结果，不要恢复旧的重复 smoke 文件。

### 5.1 顶层与文档

| 文件/目录 | 用途 |
| --- | --- |
| [README.md](../README.md) | 项目 idea、状态、快速入口和限制摘要。 |
| [.gitignore](../.gitignore) / [.gitattributes](../.gitattributes) | 生成物排除规则和基线证据的窄格式例外。 |
| `.git/` | Git 元数据，不手工清理；仅按用户要求提交。 |
| `.agents/`、`.codex/` | 工作区工具配置，非 guest 运行输入，不搬入 VM。 |
| [AGENTS.md](AGENTS.md) | 操作安全边界、恢复和验证约定。 |
| [DESIGN.md](DESIGN.md) | 原锁/队列、frame、source、hostcall、续跑协议。 |
| [JIT_REGISTER_ABI.md](JIT_REGISTER_ABI.md) | 两参数、GPR/栈槽、退出和待实现的访问时契约。 |
| [JIT_EXECUTION.md](JIT_EXECUTION.md) | JIT 范围、复杂测试执行流、增量选择。 |
| [TODO.md](TODO.md) | 当前待办、已知失败、可选扩展与明确延期；完成日志转查历史证据。 |
| [VALIDATION.md](VALIDATION.md) | 历史结果的时间、源码冻结与归档索引；新增测试/benchmark 结果维护在各自目录 README。 |
| [PROJECT_GUIDE.md](PROJECT_GUIDE.md) | 本文：逐步操作、阅读顺序和文件索引。 |

### 5.2 生产模块 `kernel_module/`

| 文件 | 阅读用途 |
| --- | --- |
| [Makefile](../kernel_module/Makefile) | provider 对象组成、SELFTEST/NUMA 开关、guest Kbuild。 |
| [kd_main.c](../kernel_module/kd_main.c) | 初始化/逆序退出，spin int3 selector、mutex 无条件分派与 hook 发布。 |
| [kd_lock.c](../kernel_module/kd_lock.c) | hook 路由、原生操作适配、mutex shadow 查找。 |
| [kd_hotlock.c](../kernel_module/kd_hotlock.c) | CPU 与单锁均本地识别，每 10240 次共用一次时间检查；仅达标地址进入共享集合，尚不代表 JIT 就绪。 |
| [sys.c](../kernel_module/sys.c) | 设备 open/read/write/ioctl、CAPS、退休协议。 |
| [exe.c](../kernel_module/exe.c) | RIP 注册、代码池、wrapper 退出分派、控制/服务处理；默认关闭的 `jit_timing` 只读装载开关及排空后边界统计。 |
| [kd_exec.c](../kernel_module/kd_exec.c) | frame/锁 ledger、远端关系、native 请求与 owner ACK；pop 拒绝未排空的 remote/native 引用。 |
| [kd_source.c](../kernel_module/kd_source.c) | source pin、writer/frame lease、终止式退休。 |
| [kd_spinlock.c](../kernel_module/kd_spinlock.c) | spin 排队、嵌套代理、IRQ 保存/恢复与非局部恢复桩；combiner 使用 task 栈，物理 waiter 使用每 CPU shadow 等待栈。 |
| [spin/request.inc](../kernel_module/spin/request.inc) | 独立于 node 的预分配 request 槽领取和最后用户归还。 |
| [spin/combiner.inc](../kernel_module/spin/combiner.inc) | 新旧及混合 ABI 的统一批次循环，完成/pop/发布、后继准入及复杂出口消费；保留原 owner/ACK。 |
| [spin/wait.inc](../kernel_module/spin/wait.inc) | 物理 waiter 连续汇编切入 shadow 栈再发布/轮询；未执行的队首恢复旧 RSP，完成或 native 唤醒放弃旧 C 帧并转入 task 栈的安全位置恢复。 |
| [kd_spin_gate.c](../kernel_module/kd_spin_gate.c) | 原锁 L 与私有调度 S 分离，真实 owner/hold。 |
| [kd_spin_entry.c](../kernel_module/kd_spin_entry.c) | origin ticket、代际、task/CPU 引用与借用生命周期。 |
| [kd_mutex.c](../kernel_module/kd_mutex.c) | mutex 节点池、combiner、原生 owner、waiter 续跑；正常 queue/JIT 日志保留为 INFO。 |
| [kd_mutex_tasks.c](../kernel_module/kd_mutex_tasks.c) | acquisition task 引用、rename 后路由及 RCU 回收。 |

### 5.3 共享接口 `include/`

| 文件 | 阅读用途 |
| --- | --- |
| [exe_info.h](../include/exe_info.h) | daemon/kernel 共用 entry、状态、代码块和上传布局。 |
| [exe.h](../include/exe.h) | C 执行器接口及返回值；区别于 wire/wrapper 状态。 |
| [kd_jit_batch.h](../include/kd_jit_batch.h) | 版本化 wrapper 目录、最小入口描述及新旧编译器 clobber 调用边界。 |
| [kd_exec.h](../include/kd_exec.h) | frame、ledger、远端状态及不变量辅助 API。 |
| [kd_call.h](../include/kd_call.h) | PENDING/已完成控制 CALL 的目标、SP、返回 token 校验。 |
| [kd_lock.h](../include/kd_lock.h) | hook 和原生锁辅助声明。 |
| [kd_hotlock.h](../include/kd_hotlock.h) | 本地采样准入与已晋升身份查询接口；计数/窗口不暴露为共享状态。 |
| [kd_mutex.h](../include/kd_mutex.h) | 私有 mutex gate/node 布局和容量。 |
| [kd_spinlock.h](../include/kd_spinlock.h) | spin node/队列与 JIT 上下文布局。 |
| [kd_spin_gate.h](../include/kd_spin_gate.h) | 原锁 gate 与物理 hold 的代际约束。 |
| [kd_spin_entry.h](../include/kd_spin_entry.h) | hook/virtual ticket 与 origin ref。 |
| [kd_spin_fast.h](../include/kd_spin_fast.h) | 可关闭的原生站点缓存与独立 S/L hold；匹配缓存不重复查询，保留解锁/退休约束。 |
| [kd_comm.h](../include/kd_comm.h) | 装载时准备的完整 task comm 掩码匹配，保留 NUL/超长名字语义。 |
| [kd_spin_select.h](../include/kd_spin_select.h) | spin 的共同目标/保留 owner 选择规则，供旧 selector 与合并入口的慢路径使用。 |
| [qspinlock_i.h](../include/qspinlock_i.h) | 私有调度字的 qspinlock 风格位布局/辅助宏。 |
| [kd_segment.h](../include/kd_segment.h) | 在 origin CPU 记录 kernel GS base。 |
| [kd_source.h](../include/kd_source.h) | source 生命周期内部接口。 |
| [kd_source_api.h](../include/kd_source_api.h) | source/CAPS ioctl 常量和固定布局。 |
| [kd_hostcall.h](../include/kd_hostcall.h) | 服务 ID 和安全属性定义。 |
| [kd_hostcalls.def](../include/kd_hostcalls.def) | 唯一服务清单：两个 ktime 服务及标量 int_sqrt，不支持任意 printk 或指针服务。 |
| [asm_head.h](../include/asm_head.h) | pt_regs 共享 GPR backing 与 wrapper 独立控制槽的汇编偏移；R11 为包基址。 |
| [wrapper.S](../include/wrapper.S) | 装载/回写寄存器，包含生成的 jit.S；flags 不持久化。 |
| [sys.h](../include/sys.h) | 设备初始化/退出接口。 |
| [utils.h](../include/utils.h) | 日志辅助，不是成功判定器。 |

### 5.4 翻译器 `disassem/`

| 文件 | 阅读用途 |
| --- | --- |
| [requirements.txt](../disassem/requirements.txt) | CPython 3.10 翻译器与证据读取器的固定运行包版本；3.3 维护唯一安装步骤，不锁定完整工具链。 |
| [disassem.py](../disassem/disassem.py) | CLI 和翻译总流程；解码、准入、发射、组装。 |
| [device_session.py](../disassem/device_session.py) | lease/source pin/CAPS；可直接执行 status/capabilities/retire。 |
| [memread.py](../disassem/memread.py) | 从 kcore 的 ELF 映射读取固定窗口和冷分支。 |
| [entry_abi.py](../disassem/entry_abi.py) | 普通 spin/mutex clobber 入口的有界未定义位分析，拒绝观察未捕获的初始 GPR。 |
| [context_policy.py](../disassem/context_policy.py) | 符号/静态 per-CPU 范围、数据流、JIT 范围与锁深度。 |
| [context_memory.py](../disassem/context_memory.py) | 有界顺序 byte/word 事实、别名、clobber；不是实时内存快照。 |
| [context_guards.py](../disassem/context_guards.py) | 正文前的入口 disjointness 条件，不是访问时 guard。 |
| [translation.py](../disassem/translation.py) | 单条指令在普通/特殊 lowerer 间分派。 |
| [normal.py](../disassem/normal.py) | 普通 operand、地址和寄存器映射。 |
| [special_inst.py](../disassem/special_inst.py) | CALL/RET/虚拟 PUSH/POP/控制指令。 |
| [conflict.py](../disassem/conflict.py) | 虚拟特殊寄存器到物理 scratch/spill 的映射。 |
| [indirect_jump.py](../disassem/indirect_jump.py) | 有界返回图与 learned IJ 分发表。 |
| [hostcall.py](../disassem/hostcall.py) | 读取共享清单并产生服务出口。 |
| [assist.py](../disassem/assist.py) | 指令名、branch 分类、operand/汇编格式辅助。 |
| [miasm_compat.py](../disassem/miasm_compat.py) | 已支持 miasm 表达式接口差异的适配。 |
| [solve_bug.py](../disassem/solve_bug.py) | LEA 解码和 LOCK 相关输出的局部修正，不是通用语义保证。 |
| [diagnostics.py](../disassem/diagnostics.py) | 每次翻译的定位、分级和去重日志。 |

### 5.5 桥接、负载与基线

`workload_modules/` 统一保存 test/bench 的 Demo 内核临界区模块。
`lock_scenarios/` 承接原 `klock_module/` 及其临界区片段，`spin_cacheline/`
保存 cacheline microbenchmark 驱动。模块名 `klock_module`、`kd_depth_source`、
`spin_cacheline` 以及设备/ioctl 接口保持原样；目录命名表达负载集合的职责。
用户态客户端和扫描入口仍在 `bench/`，协议与回归入口仍在 `tests/`。

```text
workload_modules/
  Makefile                          构建全部 Demo 模块
  lock_scenarios/
    Makefile, klock_module.c         多模式测试/benchmark 负载
    kd_depth_source.c, .h           可选第二源码模块
    fragments/                      被模块 include 的临界区片段
  spin_cacheline/
    Makefile, module.c               独立 spin cacheline 负载
    payload.h, api.h                 展开临界区及共享 ioctl 定义
```

在 recovery guest 构建生产 provider 后，可用 `make -C workload_modules W=1`
构建两组负载；只需一组时使用 `make -C workload_modules lock_scenarios`
或 `make -C workload_modules spin_cacheline`。后者不依赖 kdlock 符号。
原测试脚本通过 `KLOCK_DIR` 使用新的 `lock_scenarios/` 路径；cacheline 的
`make -C bench/spin_cacheline module` 会委托给新的负载目录。

| 文件 | 使用方式 |
| --- | --- |
| [daemon/daemon.c](../daemon/daemon.c) | 唯一常驻用户态桥接进程，维护目标学习和发布；`--metrics` 可选记录真实翻译子进程 wall/CPU/RSS，默认关闭。 |
| [daemon/Makefile](../daemon/Makefile) / [README](../daemon/README.md) | daemon 构建、参数、会话和诊断说明。 |
| [bench/klock_test.c](../bench/klock_test.c) | pthread ioctl 驱动及可选结构化测量，参数含义见第 4 节。 |
| [bench/README.md](../bench/README.md) | benchmark 总入口；具体伪代码、运行命令与结果维护在各负载的子目录 README。 |
| [tclock_backend/README.md](../tclock_backend/README.md) | 独立 TCLock 原生后端：上游来源、完整栈切换逻辑、hook 与验收边界。 |
| [tclock_compare/README.md](../bench/tclock_compare/README.md) | 同负载三方六臂交替矩阵、采样、计时外 allocator guard、冻结输入与结果。 |
| [spin_cacheline/README.md](../bench/spin_cacheline/README.md) / [Makefile](../bench/spin_cacheline/Makefile) | 独立 cacheline 对比的构建、参数化扫描、临界区与测试伪代码、结果解释、汇编查看及排空入口。 |
| [spin_cacheline/EXECUTION_PATHS.md](../bench/spin_cacheline/EXECUTION_PATHS.md) | 首次发现/注册、原生快路径、队列代理、JIT wrapper 与恢复的源码伪代码，以及按路径区分的性能检查点。 |
| [workload_modules/Makefile](../workload_modules/Makefile) | Demo 模块统一构建入口，可分别选择 lock_scenarios 或 spin_cacheline。 |
| [spin_cacheline/Makefile](../workload_modules/spin_cacheline/Makefile) / [module.c](../workload_modules/spin_cacheline/module.c) / [payload.h](../workload_modules/spin_cacheline/payload.h) / [api.h](../workload_modules/spin_cacheline/api.h) | 不依赖 kdlock 符号的外部模块，64B 数据槽、五种展开 CS、布局/run/排空计数 ioctl。 |
| [post_work.h](../workload_modules/spin_cacheline/post_work.h) / [post_work_fixture.c](../bench/spin_cacheline/post_work_fixture.c) | 正文返回后的固定寄存器乘加及其编译产物检查；负载定义见 benchmark README。 |
| [provider/prepare.py](../bench/spin_cacheline/provider/prepare.py) / [observation.patch](../bench/spin_cacheline/provider/observation.patch) | 在 bench 私有副本应用观测层并构建 kdlock；严格检查补丁上下文，冻结原始/最终输入哈希，主项目源码和产物不被覆盖。 |
| [provider/kd_bench.c](../bench/spin_cacheline/provider/kd_bench.c) / [kd_bench.h](../bench/spin_cacheline/provider/kd_bench.h) | 只加入 benchmark 专用 provider 的默认关闭 quiet 与锁地址选择，wrapper 返回后的 per-CPU 正文计数和只读排空查询。 |
| [client.c](../bench/spin_cacheline/client.c) | 逐线程绑核、原子 ready/go/abort 起跑、单 ioctl 循环、wall/线程 CPU 汇总及全部数据槽差值检查。 |
| [run.py](../bench/spin_cacheline/run.py) / [summarize.py](../bench/spin_cacheline/summarize.py) | 扫描入口、有效会话选择、kdlock 最佳吞吐/原生中位数及完整配对 CSV。 |
| [bench_runtime.py](../bench/spin_cacheline/bench_runtime.py) / [bench_session.py](../bench/spin_cacheline/bench_session.py) | 计划/环境/数据检查，以及单会话的准备、发布确认、测量和排空。 |
| [assembly.py](../bench/spin_cacheline/assembly.py) / [test_assembly.py](../bench/spin_cacheline/test_assembly.py) | 排空后按临界区及文件内容去重导出原生/JIT 汇编，生成查看索引并核对来源。 |
| [dispatch_floor/Makefile](../bench/spin_cacheline/dispatch_floor/Makefile) / [module.c](../bench/spin_cacheline/dispatch_floor/module.c) / [run.py](../bench/spin_cacheline/dispatch_floor/run.py) | 独立原生 selector/最小 callback 调用成本对照；复用实际负载和数据/排空检查，不计作 kdlock/JIT 成绩。 |
| [kernel_identity.py](../bench/spin_cacheline/kernel_identity.py) | 默认核验 clobber 独立基线；显式选择也须验证配置/源码/build/live 身份。 |
| [profile.py](../bench/spin_cacheline/profile.py) / [profile_summary.py](../bench/spin_cacheline/profile_summary.py) | 独立低频内核 IP 采样及只读离线 period 加权汇总；复用真实负载、JIT 差值和排空，不计为正式性能样本。 |
| [mutex_clobber/README.md](../kernel_experiments/mutex_clobber/README.md) / [guest-kernel.patch](../kernel_experiments/mutex_clobber/guest-kernel.patch) / [capture.py](../kernel_experiments/mutex_clobber/capture.py) | 独立 kdclobber2 普通 mutex 调用者 ABI、static-call 桥接与基线捕获。 |
| [spin_clobber/README.md](../kernel_experiments/spin_clobber/README.md) / [guest-kernel.patch](../kernel_experiments/spin_clobber/guest-kernel.patch) / [capture.py](../kernel_experiments/spin_clobber/capture.py) | 独立 kdclobber1 普通 spin 调用者 ABI、版本化桥接与基线捕获，保留原内核和缓解配置。 |
| [spin_static/README.md](../kernel_experiments/spin_static/README.md) / [guest-kernel.patch](../kernel_experiments/spin_static/guest-kernel.patch) / [capture.py](../kernel_experiments/spin_static/capture.py) | 经授权的独立 spin hook 直接调用内核实验与基线捕获；保留原内核和原基线。 |
| [test_spin_cacheline.py](../bench/spin_cacheline/test_spin_cacheline.py) / [client_fixture.c](../bench/spin_cacheline/client_fixture.c) | guest 定向布局/真实客户端/聚合/配对/正文计数检查，并核对增大批次不增加 ioctl/时钟调用；替代设备与 CPU 原语不算实际内核 JIT。 |
| [control_fixture.c](../bench/spin_cacheline/control_fixture.c) | 提取驱动实际原子准入函数，验证在途 writer 与独占计数快照相互排斥；客户端夹具另覆盖延迟 ready 和创建/绑核失败。 |
| [workload_modules/lock_scenarios/Makefile](../workload_modules/lock_scenarios/Makefile) | workload 构建与可选第二源码模块开关。 |
| [klock_module.c](../workload_modules/lock_scenarios/klock_module.c) | mode 分派、复杂 CS 记录、独立完整性检查和测试片段宿主；mode 4 分会话检查同 CPU 的 B 等待及两 A 共用原生 B。 |
| [kd_depth_source.c](../workload_modules/lock_scenarios/kd_depth_source.c) / [头文件](../workload_modules/lock_scenarios/kd_depth_source.h) | 两模块 learned-depth 实验的外部七锁 helper；普通启动不用加载。 |
| [hotlock_record/run.py](../bench/hotlock_record/run.py) / [组件驱动](../tests/kernel/hotlock_record/record_bench.c) | 冻结旧/新生产采样器，独立测发现延迟、冷地址流及正向命中成本；不装 hook 或执行 JIT。 |
| [kernel_baseline/README.md](../kernel_baseline/README.md) | 已捕获内核身份、已有 hook 差异和重建边界。 |
| [verify.py](../kernel_baseline/verify.py) | 只读检查 source/build/running；不是安装脚本。 |
| [manifest.json](../kernel_baseline/manifest.json) | 源码、构建文件和运行身份的基线哈希。 |
| [guest.config](../kernel_baseline/guest.config) | 捕获的内核配置，不是要求立即应用的新配置。 |
| [linux-6.1.159-guest.patch](../kernel_baseline/linux-6.1.159-guest.patch) | 已有改动证据；字节和旧注释保持原样，不作阅读性重写。 |

### 5.6 测试入口 `tests/`

文档入口为 [tests/README.md](../tests/README.md)，包含环境、用例选择、Demo
模式和证据解释；根 README 不维护测试命令或成绩。

测试入口通过 `run_all.sh --case/--suite` 选择，下面列原始驱动便于阅读。不要把
每个 `.sh` 都依次运行。复杂驱动管理角色和超时，直接以默认参数运行也可能加载模块。

| 文件 | 覆盖/用途 |
| --- | --- |
| [run_all.sh](../tests/run_all.sh) / [regression.py](../tests/regression.py) | 统一选择、去重、空闲门禁、执行和证据；`--jit-timing` 显式选择每个 case 的计量，不改变固定目录。 |
| [paired_benchmark.py](../tests/tools/paired_benchmark.py) / [benchmark_arm.sh](../tests/tools/benchmark_arm.sh) | 显式同负载原生锁/JIT 配对、交替重复及扫描；文件名中的 `arm` 指实验组，不是架构适配。shell 管理新会话，Python 校验准备/计时/发布/body，关联翻译资源和控制台设置；不进入固定回归目录。 |
| [common.sh](../tests/common.sh) | 驱动共享的构建、JIT 检查、daemon/清理函数；`load_kdlock` 统一各阶段装载/计量检查，保留可选 insmod 超时；start_daemon 透传显式选项，不交互 source。 |
| [regression_evidence.py](../tests/regression_evidence.py) / [verify_evidence.py](../tests/verify_evidence.py) | 捕获冻结输入与输出；离线一致性校验。 |
| [test_01_module_load.sh](../tests/live/test_01_module_load.sh) | 基础模块/设备显式诊断。 |
| [test_02_jit_engine.sh](../tests/live/test_02_jit_engine.sh) | promotion/翻译/上传管线诊断，不执行 JIT。 |
| [test_04_spinlock.sh](../tests/live/test_04_spinlock.sh) | spin 主模式、复杂记录及生成体证据；mode 8 追加独立双根阶段并保存前一阶段证据。 |
| [test_05_mutex.sh](../tests/live/test_05_mutex.sh) | mutex_jit=0 的原生互斥对照。 |
| [test_07_mutex_jit.sh](../tests/live/test_07_mutex_jit.sh) | mode 3 的发布门禁与独立 origin CPU 单锁竞争。 |
| [test_08_mutex_jit_modes.sh](../tests/live/test_08_mutex_jit_modes.sh) | mode 4 同 CPU 和共享原生 B 两阶段；OOO 只运行第一阶段。mode 5 服务返回和额度后缀。执行流见 [6.12](JIT_EXECUTION.md#612-同-cpu-的嵌套-mutex-jit)、[6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀)、[6.15](JIT_EXECUTION.md#615-两个-a-combiner-共享原生-mutex-b)。 |
| [test_09_jit_execution_modes.sh](../tests/live/test_09_jit_execution_modes.sh) | 显式 mode 兼容入口；无参只列清单。 |
| [test_10_native_resume.sh](../tests/live/test_10_native_resume.sh) | CALL/native 后缀、寄存器、资源、信号和受检边界的主驱动。 |
| [test_11_mutex_native_protocol.sh](../tests/live/test_11_mutex_native_protocol.sh) | 目标/非目标共享 Linux mutex。 |
| [test_12_context_native_only.sh](../tests/live/test_12_context_native_only.sh) | 上下文拒绝负例，必须没有实际 JIT。 |
| [test_13_spin_shadow_capacity.sh](../tests/live/test_13_spin_shadow_capacity.sh) | 显式 full-shadow 队首诊断。 |
| [test_14_spin_frame_depth.sh](../tests/live/test_14_spin_frame_depth.sh) | 自然物理 frame 链和继承的锁容量。 |
| [test_15_spin_native_gate.sh](../tests/live/test_15_spin_native_gate.sh) | 原锁 L/私有 S 内核组件检查。 |
| [test_16_spin_entry.sh](../tests/live/test_16_spin_entry.sh) | origin ticket/task/CPU 原生引用组件检查。 |
| [test_17_spin_native_protocol.sh](../tests/live/test_17_spin_native_protocol.sh) | spin 与非目标原生 API 的 Linux 互斥。 |
| [test_18_spin_routing.sh](../tests/live/test_18_spin_routing.sh) | 真实 hook 路由，刻意不执行 JIT。 |
| [test_19_mutex_signals.sh](../tests/live/test_19_mutex_signals.sh) | 非目标原生 mutex peer 的信号取消。 |
| [test_20_remote_outer.sh](../tests/live/test_20_remote_outer.sh) | 远端祖先提前释放和 owner 依赖；mode 8 调用 `multi` 纯 JIT 与 `multi quota` 混合完成两个变体。 |
| [test_21_remote_depth.sh](../tests/live/test_21_remote_depth.sh) | 四至八层、多请求、跨 NUMA/deferred 组合。 |
| [test_22_mutex_task_lifecycle.sh](../tests/live/test_22_mutex_task_lifecycle.sh) | 真实 task/RCU/final ACK，不计 JIT。 |
| [test_23_mutex_parallel_native.sh](../tests/live/test_23_mutex_parallel_native.sh) | 双队列 frame、资源压力、rename、peer、source 退休。 |
| [test_24_gs_jit.sh](../tests/live/test_24_gs_jit.sh) | mode 10/11 的 GS 读、写、RMW 和 current 代理正例。 |

### 5.7 测试控制器和 oracle

这组文件由驱动调用；部分会控制真实进程/sysfs，不应当作全部只读工具。名字带
`protocol` 表示检查器/协调器，而不是生产锁协议实现。

| 文件 | 用途 |
| --- | --- |
| [cpu_placement.py](../tests/protocols/cpu_placement.py) | 采集真实 CPU/NUMA 拓扑。 |
| [audit_context_spills.py](../tests/tools/audit_context_spills.py) | 独立静态准入 corpus，不执行危险指令。 |
| [mutex_signal_client.c](../tests/clients/mutex_signal_client.c) | pidfd/信号实验的单进程客户端；双 frame 原 waiter 只执行一次 ioctl，原生 peer 取消后显式重试。 |
| [mutex_signal_protocol.py](../tests/protocols/mutex_signal_protocol.py) | 就绪检查、mode 4 同 CPU 及两 A/共享原生 B 的身份/JIT/ACK、mode 5 超额度 CALL，以及 signal peer 控制/判定。 |
| [mutex_parallel_protocol.py](../tests/protocols/mutex_parallel_protocol.py) | 双 frame、原 waiter 的 pidfd 信号/退出、共享 CPU 和资源组合协调。 |
| [mutex_shadow_protocol.py](../tests/protocols/mutex_shadow_protocol.py) | 双 frame 内真实 shadow map 压力。 |
| [mutex_stack_protocol.py](../tests/protocols/mutex_stack_protocol.py) | 共享栈变化后的 post-control 续跑判定。 |
| [native_only_protocol.py](../tests/protocols/native_only_protocol.py) | 真实设备拒绝协议，不执行代码。 |
| [native_ooo_protocol.py](../tests/protocols/native_ooo_protocol.py) | 原 waiter 的 A-before-B 完成顺序。 |
| [native_register_protocol.py](../tests/protocols/native_register_protocol.py) | CALL-entry GPR/SP/IP 样本与 native frame 关联。 |
| [native_waiter_signal_protocol.py](../tests/protocols/native_waiter_signal_protocol.py) | 原 waiter 的信号、B 获取/取消和最终 A ACK。 |
| [native_waiter_signal_race.py](../tests/protocols/native_waiter_signal_race.py) | pidfd signal 与真实 B release 竞争。 |
| [readmission_protocol.py](../tests/protocols/readmission_protocol.py) | 两次尝试的真实队列重入契约。 |
| [remote_depth_protocol.py](../tests/protocols/remote_depth_protocol.py) | 深层远端 chain 和请求证据。 |
| [remote_outer_protocol.py](../tests/protocols/remote_outer_protocol.py) | 远端祖先/原生依赖及两个独立 root 共享 B 的逐请求证据；quota 阶段还关联首 waiter TID 退出与第二 root JIT。 |
| [spin_acquired_protocol.py](../tests/protocols/spin_acquired_protocol.py) | 本地已获取 B 的受检 post-CALL native。 |
| [spin_frame_protocol.py](../tests/protocols/spin_frame_protocol.py) | task 栈物理 frame 与 RSP 采样判定；兼容校验历史独立栈 watermark，区分两种指标。 |
| [spin_gate_protocol.py](../tests/protocols/spin_gate_protocol.py) | gate map 饱和、冷入口原生互斥，以及第二个 JIT 前缀的 PENDING ENOMEM/双 frame/最终 ACK。 |
| [spin_node_protocol.py](../tests/protocols/spin_node_protocol.py) | 排空后的节点 reservation 检查。 |
| [source_depth_protocol.py](../tests/protocols/source_depth_protocol.py) | 两层/两模块学习及 loader ref 与 source pin 区分。 |
| [source_retirement.py](../tests/protocols/source_retirement.py) | dual-frame 的 busy/finish/reuse source 阶段。 |
| [source_session_driver.c](../tests/clients/source_session_driver.c) / [source_session_child.py](../tests/clients/source_session_child.py) | 实际 fork/exec 设备 lease 存活探针，不是假装翻译成功。 |

### 5.8 Demo 临界区与内核测试片段

`workload_modules/lock_scenarios/fragments/` 的片段被 `klock_module.c` 或另一个
workload include；`tests/kernel/` 的观察器/组件自测在 `KDLOCK_SELFTEST` 下被
provider include。具体 include 点可用
`rg '#include.*(fragments|tests/kernel|workload)' workload_modules kernel_module` 查找。

| 文件 | 用途 |
| --- | --- |
| [context_lock_workload.c](../workload_modules/lock_scenarios/fragments/context_lock_workload.c) | IRQ/BH/per-CPU 原生拒绝源码。 |
| [native_register_probe.h](../workload_modules/lock_scenarios/fragments/native_register_probe.h) / [native_register_workload.c](../workload_modules/lock_scenarios/fragments/native_register_workload.c) | 无 C prologue 的 GPR 样本和可翻译前缀。 |
| [native_ooo_workload.c](../workload_modules/lock_scenarios/fragments/native_ooo_workload.c) | A 提前解锁的本地 native/JIT 场景。 |
| [native_waiter_signal_workload.c](../workload_modules/lock_scenarios/fragments/native_waiter_signal_workload.c) | 原 waiter 信号后仍保留副作用和 A ACK。 |
| [mutex_signal_workload.c](../workload_modules/lock_scenarios/fragments/mutex_signal_workload.c) | 原生 peer 的 interruptible/killable 等等待。 |
| [mutex_parallel_workload.c](../workload_modules/lock_scenarios/fragments/mutex_parallel_workload.c) | 两独立队列的真实 native frame；第二 frame 的有界门用于观察第一 waiter 退出。 |
| [mutex_shared_workload.c](../workload_modules/lock_scenarios/fragments/mutex_shared_workload.c) | 两个 A executor 与非目标 peer 共用原生 B；保留 owner 的普通 CALL 后缀与后继 JIT、真实 Linux 等待队列和精确记录。 |
| [mutex_parallel_peers.c](../workload_modules/lock_scenarios/fragments/mutex_parallel_peers.c) | 双 B 原生 peer 的取消/重排和 owner 观察。 |
| [mutex_code_pool_workload.c](../workload_modules/lock_scenarios/fragments/mutex_code_pool_workload.c) | 64 个真实 cold CALL site 消耗代码池，不计 JIT。 |
| [mutex_shadow_workload.c](../workload_modules/lock_scenarios/fragments/mutex_shadow_workload.c) | 原 hook 获取造成 shadow map 耗尽。 |
| [mutex_stack_workload.c](../workload_modules/lock_scenarios/fragments/mutex_stack_workload.c) | B owner 改写共享栈字，触发受检 native 后继。 |
| [spin_native_workload.c](../workload_modules/lock_scenarios/fragments/spin_native_workload.c) | 原生 L 排斥和 alternate API 数据 oracle。 |
| [spin_routing_workload.c](../workload_modules/lock_scenarios/fragments/spin_routing_workload.c) | 可控目标/非目标 hook 路由。 |
| [spin_chain_workload.c](../workload_modules/lock_scenarios/fragments/spin_chain_workload.c) | 八层物理 queue/combiner 链。 |
| [spin_multi_workload.c](../workload_modules/lock_scenarios/fragments/spin_multi_workload.c) | 两个独立 A root 共享 B；14 角色门禁、逐 root 副作用，quota 变体检查原 waiter 的单 origin pin、B 暂停及后继 JIT。 |
| [remote_depth_workload.c](../workload_modules/lock_scenarios/fragments/remote_depth_workload.c) | 一个 logical waiter 的多物理执行者和 deferred 请求。 |
| [remote_outer_workload.c](../workload_modules/lock_scenarios/fragments/remote_outer_workload.c) | 远端祖先解锁及独立 owner 依赖。 |
| [spin_ticket_workload.c](../workload_modules/lock_scenarios/fragments/spin_ticket_workload.c) | 真实获取填满 32 个 ticket。 |
| [spin_gate_workload.c](../workload_modules/lock_scenarios/fragments/spin_gate_workload.c) | 旧后缀存活时填满 gate map，再执行已发布 A2 JIT 并在无 gate 的 C 上原生续跑；角色和控制参数见使用指南 6.3。 |
| [spin_acquired_workload.c](../workload_modules/lock_scenarios/fragments/spin_acquired_workload.c) | B 私有队首、后继竞争者与已提交 A 前缀。 |
| [mutex_shadow_trace.c](../tests/kernel/mutex/mutex_shadow_trace.c) | 只观察真实 shadow 表，不填造成员。 |
| [spin_node_trace.c](../tests/kernel/spin/spin_node_trace.c) | node reservation 排空记录。 |
| [spin_frame_trace.c](../tests/kernel/spin/spin_frame_trace.c) | frame 深度与实际 task 栈边界/RSP 余量采样；不填色活栈，不在深栈上打印。 |
| [spin_refusal_trace.c](../tests/kernel/spin/spin_refusal_trace.c) | 拒绝包、owner/ledger 的只读快照。 |
| [spin_readmission_trace.c](../tests/kernel/spin/spin_readmission_trace.c) | bounded readmission 观察。 |
| [spin_deferred_trace.c](../tests/kernel/spin/spin_deferred_trace.c) | 真实 deferred 队列选择/接链观察。 |
| [exec_capacity_probe.c](../tests/kernel/execution/exec_capacity_probe.c) | 固定 frame 容量拒绝及包不变观察。 |
| [exec_relay_exit_probe.c](../tests/kernel/execution/exec_relay_exit_probe.c) | 无锁 root finish 或已发 ACK 的远端 B pop 等待原 waiter TID 脱离；仅持有 PID 身份，不加 task ref、不伪造 ACK。 |
| [spin_gate_selftest.c](../tests/kernel/spin/spin_gate_selftest.c) | hook 发布前的原生 L/私有 S 组件测试。 |
| [spin_entry_selftest.c](../tests/kernel/spin/spin_entry_selftest.c) | task/CPU pins、tickets 与原生锁组件。 |
| [spin_shadow_selftest.c](../tests/kernel/spin/spin_shadow_selftest.c) | full-shadow 队首路径。 |
| [spin_virtual_selftest.c](../tests/kernel/spin/spin_virtual_selftest.c) | virtual 请求资源拒绝/取消检查。 |
| [mutex_task_selftest.c](../tests/kernel/mutex/mutex_task_selftest.c) | task 路由删除、跨 reader RCU 与 final ACK。 |

### 5.9 单元测试 `tests/unit/`

`Makefile` 中的程序才是通常运行入口；`*_fixture.c` 多由对应 Python 程序生成
生产代码头后编译，不能脱离该驱动直接编译。模型、替代原语和 log mutation
不证明 Linux 并发正确；程序自身标明何处执行真实生成机器码。
默认仅运行 2 个基础 C；Python 入口通过 `unit/run.py`
按分组路径或唯一文件名选择，完整库存只供显式全量。逐项的覆盖重叠、模型
精简进展和保留理由见 [测试分析](TEST_EXAMPLES.md#4-单元入口逐项分析)；
本节保留源码与 fixture 的阅读索引。

| 文件 | 用途 |
| --- | --- |
| [run.py](../tests/unit/run.py) | 单项 Python 入口，统一配置跨组夹具导入；无参数只列出库存。 |
| [Makefile](../tests/unit/Makefile) | 默认 2 个基础 C 程序；PY_TESTS 按需增加，run-all 显式全量。 |
| [spin_gate_mock.h](../tests/unit/spin/spin_gate_mock.h) | 提取式 C fixture 共用的 CPU/lock/atomic 替代原语。 |
| [test_control_call.c](../tests/unit/basic/test_control_call.c) | 直接使用生产 kd_call 规则。 |
| [test_daemon_policy.c](../tests/unit/basic/test_daemon_policy.c) | 编译生产 daemon，测试结果缓存、真实子进程 lease/reap 和 wire；计量默认关闭、wait4 中断重试与时钟/资源失败。 |
| [test_clobber_entry.py](../tests/unit/admission/test_clobber_entry.py) | 新 ABI 未捕获寄存器、部分写、控制边界、入口栈槽与别名拒绝。 |
| [test_context_policy.py](../tests/unit/admission/test_context_policy.py) | 上下文/CFG/静态范围/有界分析 corpus。 |
| [test_context_memory.py](../tests/unit/admission/test_context_memory.py) | byte/word、alias、RMW、clobber 顺序事实。 |
| [test_context_guards.py](../tests/unit/admission/test_context_guards.py) | 实际运行入口谓词及有界 CALL/RET 生成体。 |
| [test_context_spill_audit.py](../tests/unit/admission/test_context_spill_audit.py) | 独立 spill audit 的错误分类。 |
| [test_hostcall_codegen.py](../tests/unit/codegen/test_hostcall_codegen.py) | manifest 与服务出口生成一致性。 |
| [test_segment_codegen.py](../tests/unit/codegen/test_segment_codegen.py) | segment lowering 与 wrapper 偏移。 |
| [test_text_regions.py](../tests/unit/admission/test_text_regions.py) | cold text、CFG 扩展、设备 session/CAPS。 |
| [test_jit_diagnostics.py](../tests/unit/codegen/test_jit_diagnostics.py) | 可复用 mocked-text harness 和定位/告警判定。 |
| [test_jit_body_witness.py](../tests/unit/codegen/test_jit_body_witness.py) | guest 用户态运行真实 wrapper 和生成体 marker。 |
| [test_shared_reg_bank.py](../tests/unit/codegen/test_shared_reg_bank.py) | 返回前验证 backing 双向共用，高寄存器压力、部分 R11、hostcall 续跑和 block 额度出口。 |
| [test_jit_entry_scope.py](../tests/unit/execution/test_jit_entry_scope.py) / [jit_entry_scope_fixture.c](../tests/unit/execution/jit_entry_scope_fixture.c) | 生产 JIT 入口/scope/拒绝包，typed hostcall 策略、完整 RDI/RAX 参数返回与共同额度；额度出口不弹 CALL 栈、不重放或触发学习。边界计时开关前后完整 frame/包一致；服务和计时原语为替代，实际执行需 live 验证。 |
| [test_exe_registry.py](../tests/unit/execution/test_exe_registry.py) / [exe_registry_fixture.c](../tests/unit/execution/exe_registry_fixture.c) | 生产 registry、代码池及上传边界、服务表编译契约和计量重置/卸载。服务 manifest/adapter 变化也须独立运行本入口。 |
| [test_exec_capacity.py](../tests/unit/execution/test_exec_capacity.py) / [exec_capacity_fixture.c](../tests/unit/execution/exec_capacity_fixture.c) | 生产 frame/ledger/完成状态、remote/native 未排空的回收拒绝、两后端清理和实际退出观察器；PID/RCU/time 等原语替代，不替代真实 ACK/退出。 |
| [test_hotlock_sampling.py](../tests/unit/infrastructure/test_hotlock_sampling.py) / [hotlock_sampling_fixture.c](../tests/unit/infrastructure/hotlock_sampling_fixture.c) | 替代 CPU/TSC 下的生产采样：批量门槛、独立窗口、碰撞、并发发布、重入、时间倒退与终态；不是实际 JIT。 |
| [test_mutex_resources.py](../tests/unit/mutex/test_mutex_resources.py) / [mutex_resources_fixture.c](../tests/unit/mutex/mutex_resources_fixture.c) | 生产 tail/node/shadow/hook、频率先于进程选择、hook 改名/降温/关闭路由及完整 packet；per-CPU 存储为替代原语。 |
| [test_mutex_clobber.py](../tests/unit/mutex/test_mutex_clobber.py) / [test_mutex_wait_clobber.py](../tests/unit/mutex/test_mutex_wait_clobber.py) | 真实 ABI 2 wrapper 与生产 shadow 切栈/毁栈恢复，检查精简完成、拒绝和 FULL 中间状态。 |
| [test_mutex_outer_progress.py](../tests/unit/mutex/test_mutex_outer_progress.py) / [mutex_outer_progress_fixture.c](../tests/unit/mutex/mutex_outer_progress_fixture.c) | 生产 mutex combiner/outer-event、原 owner/后继进度；编译真实日志宏，仅替代 printk sink，检查 INFO/格式/保留次数和两个日志变异，不模拟串口或调度耗时。 |
| [test_native_after_outer.py](../tests/unit/execution/test_native_after_outer.py) / [native_after_outer_fixture.c](../tests/unit/execution/native_after_outer_fixture.c) | 生产 native/control 边界和 mutex B 获取/解锁，原语为替代实现。 |
| [test_native_registers.py](../tests/unit/execution/test_native_registers.py) / [native_register_fixture.c](../tests/unit/execution/native_register_fixture.c) | 实际用户态汇编 probe 与 GPR oracle。 |
| [test_spin_gate.py](../tests/unit/spin/test_spin_gate.py) / [spin_gate_fixture.c](../tests/unit/spin/spin_gate_fixture.c) | 生产 gate/hold map 与过期代际；检出 PENDING ENOMEM、JIT/owner/副作用或双 frame 证据缺失。 |
| [test_spin_entry.py](../tests/unit/spin/test_spin_entry.py) / [spin_entry_fixture.c](../tests/unit/spin/spin_entry_fixture.c) | 生产 origin ticket/ref 生命周期。 |
| [test_spin_routing.py](../tests/unit/spin/test_spin_routing.py) / [spin_routing_fixture.c](../tests/unit/spin/spin_routing_fixture.c) | 生产 hook/selector 路由。 |
| [test_spin_clobber.py](../tests/unit/spin/test_spin_clobber.py) | guest 执行真实 caller clobber、精简/完整 wrapper 出口及新旧混合交接，检查 poisoned packet 和高寄存器压力。 |
| [test_tclock_context.py](../tests/unit/spin/test_tclock_context.py) | TCLock 六寄存器、RSP 与原生 lock/unlock 续点的真实汇编验证；不等于复杂内核场景覆盖。 |
| [test_spin_wwjump.py](../tests/unit/spin/test_spin_wwjump.py) / [legacy_batch.S](../tests/unit/spin/legacy_batch.S) | 当前旧入口 clobber 适配与历史外壳兼容对照；后者仅为测试夹具。 |
| [test_spin_batch.py](../tests/unit/spin/test_spin_batch.py) / [spin_batch_fixture.c](../tests/unit/spin/spin_batch_fixture.c) | 批内失效、三种预取策略、共享/独立包与栈边界；不可读页验证预取不追读 frame/包，另验 per-CPU 统计。 |
| [test_spin_shadow.py](../tests/unit/spin/test_spin_shadow.py) / [spin_shadow_fixture.c](../tests/unit/spin/spin_shadow_fixture.c) | 提取实际队首和 combiner 路径；区分容量交接与普通批次发布。 |
| [test_spin_wait.py](../tests/unit/spin/test_spin_wait.py) / [spin_wait_fixture.c](../tests/unit/spin/spin_wait_fixture.c) | guest 用户态执行生产发布/等待汇编；覆盖旧 C 栈后验证完成/native 非局部恢复，以及未执行队首的正常返回；[spin_restore_fixture.c](../tests/unit/spin/spin_restore_fixture.c) 执行共享包恢复汇编，核对 GPR 与最后读取后归还引用。 |
| [spin_node_pool_fixture.c](../tests/unit/spin/spin_node_pool_fixture.c) / [spin_queue_return_fixture.c](../tests/unit/spin/spin_queue_return_fixture.c) | 上述 fixture include 的真实 producer、容量和嵌套返回。 |
| [test_spin_outer_progress.py](../tests/unit/spin/test_spin_outer_progress.py) / [spin_outer_progress_fixture.c](../tests/unit/spin/spin_outer_progress_fixture.c) | 生产 spin batch/frame/outer-release、满 gate 表时 nested ENOMEM/PENDING 包，以及 release 发布和槽复用；不执行实际 JIT。 |
| [test_remote_outer.py](../tests/unit/execution/test_remote_outer.py) / [remote_outer_fixture.c](../tests/unit/execution/remote_outer_fixture.c) | 生产远端/祖先解锁及 native ACK；完整 pt_regs、CALL 包、DONE 前脱链和发布后父 frame 复用；计量开关下的完整包、错误返回及两后端分类。CPU/发布/时钟为替代，不恢复硬件 flags。 |
| [test_remote_deferred_protocol.py](../tests/unit/execution/test_remote_deferred_protocol.py) / [deferred_trace_fixture.c](../tests/unit/execution/deferred_trace_fixture.c) | deferred oracle 与实际选队/trace 代码。 |
| [test_spin_frame_protocol.py](../tests/unit/spin/test_spin_frame_protocol.py) / [spin_refusal_trace_fixture.c](../tests/unit/spin/spin_refusal_trace_fixture.c) | frame/refusal 日志与提取的观察器。 |
| [test_source_lifetime.py](../tests/unit/infrastructure/test_source_lifetime.py) / [source_lifetime_fixture.c](../tests/unit/infrastructure/source_lifetime_fixture.c) | 生产 source/CAPS/retire，内核原语替代。 |
| [test_source_depth_protocol.py](../tests/unit/infrastructure/test_source_depth_protocol.py) | 破坏 source/loader-ref 记录，确认 oracle 拒绝。 |
| [test_mutex_parallel_protocol.py](../tests/unit/mutex/test_mutex_parallel_protocol.py) / [mutex_parallel_client_fixture.c](../tests/unit/mutex/mutex_parallel_client_fixture.c) | 双 frame oracle、pidfd 退出协调、实际客户端的单次 waiter 与两次 peer ioctl 路由。 |
| [test_mutex_stack_protocol.py](../tests/unit/mutex/test_mutex_stack_protocol.py) | 拒绝伪造的栈变化/post-control 日志。 |
| [test_mutex_signal_protocol.py](../tests/unit/mutex/test_mutex_signal_protocol.py) | 同 CPU 嵌套 JIT、CALL 额度包/计数/ACK、signal/peer/原 waiter 的坏日志、身份/顺序和参数。 |
| [test_native_ooo_protocol.py](../tests/unit/execution/test_native_ooo_protocol.py) | A-before-B 日志 oracle。 |
| [test_remote_outer_protocol.py](../tests/unit/execution/test_remote_outer_protocol.py) | 远端祖先依赖及双根身份、owner、JIT/副作用的坏日志拒绝。 |
| [test_remote_depth_protocol.py](../tests/unit/execution/test_remote_depth_protocol.py) | 深链记录及真实 workload wait predicate。 |
| [test_spin_node_protocol.py](../tests/unit/spin/test_spin_node_protocol.py) | reservation/drain 坏记录。 |
| [test_cs_oracle.py](../tests/unit/infrastructure/test_cs_oracle.py) | 实际 workload 状态更新与完整性函数。 |
| [test_benchmark.py](../tests/unit/infrastructure/test_benchmark.py)、[benchmark_fixture.c](../tests/unit/infrastructure/benchmark_fixture.c) | 真实 pthread 驱动的 30 项测量/失败场景及 113 项配对观测检查；含翻译身份/区间/资源、可选十项 JIT/native/队列计数及无效记录、控制台和历史字段边界。替代 ioctl/确定时钟，另验证真实 guest 时钟；日志替身不证明实际 JIT，不加载内核模块。 |
| [test_kernel_baseline.py](../tests/unit/infrastructure/test_kernel_baseline.py) | 基线 reader 的损坏/伪造输入，不读取 live kernel。 |
| [test_regression.py](../tests/unit/infrastructure/test_regression.py) | 用例选择去重、停止边界、证据捕获和离线 verifier；计量选择覆盖直接/组合装载和原超时，拒绝重复配置。 |

## 6. 阅读完以后改哪里

先从自己要改的行为回到第 2 节的执行链：JIT 范围改 analyzer，机器码 lowering 改
普通/特殊 lowerer，出口分类改 `exe.c`，锁/ACK 生命周期改 backend 与 `kd_exec.c`，
学习/发布改 daemon/device。不要在 workload 或 oracle 中放宽判定来绕过生产缺口。

新增功能必须注明目的和约束，选择覆盖该行为的复杂用例；基础已通过时不再默认重复。
涉及 flags 新出口、guest hook reader 或版本隔离时先查 TODO 的授权边界。
阅读与操作文档的完善不代表这些未完成功能已经实现。
