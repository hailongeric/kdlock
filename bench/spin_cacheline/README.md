# Spinlock cacheline microbenchmark

独立比较同一 `spinlock_t` 临界区的原生执行与 kdlock 动态翻译执行。
多线程在一次 ioctl 内连续争抢共享锁，增加锁竞争等待和线程间交接的机会；
每次 `sc_body_N()` 返回后，执行少量仅用局部寄存器的无业务意义计算，再抢下一次锁。
负载热循环不插入主动调度、延时或额外等待。单线程档用于无竞争基线。
内核临界区驱动和共享 ioctl 头文件统一位于
[`workload_modules/spin_cacheline/`](../../workload_modules/spin_cacheline/)。
本目录保留客户端、运行器、测试和专用 provider 观测代码。
`run.py` 负责 CLI 与扫描，`bench_runtime.py` 提供计划/校验/环境工具，
`bench_session.py` 管理单会话准备、测量和排空；职责索引见
[bench/README.md](../README.md#代码组织)。源码冻结也包含内核的 `.inc` 实现。
生产锁实现仍位于 `include/`、`kernel_module/`；运行器不修改 guest 内核。
可显式选择已经构建、启动并验证的独立实验内核，见下文的内核身份参数。
环境准备与恢复快照遵循 [操作手册](../../docs/AGENTS.md)；编译、单元测试及
模块运行都只在 recovery guest `/root/host_fs/kdlock` 中进行。

## 最新对比

主指标为 **kdlock 最高有效吞吐 / 原生有效吞吐中位数**，用于观察本次样本中的
最佳表现；完整定义见[结果解释](#结果解释)。增加 4 组锁外乘加后的
[最新完整扫描](results/20260915-post-work.md) 已完成 30 个配置、120 个会话，
使用每线程 10 万次、1/4/8/12/16/20 线程。该页列出原生中位数、kdlock 最佳值、
比值和最佳会话的 JIT 占比，并链接全部原始 CSV。

<a id="source-organization"></a>

## 代码整理回归（2026-09-15）

以下是增加锁外计算前的历史回归。拆分运行器与内核私有组件后，在同一
`6.1.159-kdstatic2` recovery guest
验证 `--cachelines 1 16 --threads 1 4 --cpus 0-3 --iterations 100000 --repeats 2`：
**16/16 会话完成、数据校验和排空通过**，共 4,000,000 次临界区操作。
8 个原生会话、4 个单线程 NO_JIT 会话、4 个多线程实际 JIT 会话；测量期
正文合计 1,081,670 次。最长测量批次 1.261 秒，watchdog 保持不变。
此轮用于验证代码组织和运行流程，没有运行 24 线程，也没有替代下文的完整扫描。

源码冻结包含 176 个输入文件，其中 44 个 `.inc` 分别属于生产源码和专用
provider 副本；4 个二进制与生成物哈希均已核对。原始结果在
`/tmp/kdlock-organization-bench-20260915`，归档及收尾检查说明见
[tests/README.md](../../tests/README.md#source-organization)。本次不据此宣称性能变化。

## 默认实验

| 项目 | 值 |
| --- | --- |
| 有效负载 | 1、2、4、8、16 条 64B cacheline |
| 一次操作 | 持有同一把锁，对每条有效 cacheline 上的一个 64 位计数器读改写一次 |
| 锁外间隔 | 每次正文返回后，4 组依赖前一结果的 64 位乘加；两组完全相同 |
| 主要对比 | 同一配置下，kdlock 最高有效吞吐 / 原生有效吞吐中位数 |
| 线程 | 1、4、8、12、16、20、24；每线程固定一个不同 guest CPU |
| CPU | 默认 0–23，使用列表的前 T 个；实际核对在线、亲和性、NUMA 节点及 64B line |
| 测量迭代 | 每线程 10,000 次，一个 ioctl 完成全部迭代 |
| 重复 | 每配置两对：原生→kdlock、kdlock→原生 |
| 扫描 | 35 个配置、70 对、140 个独立测量会话 |

当前 guest 的 CPU 0–19 位于节点 0，20–39 位于节点 1。按默认 CPU 顺序，
1–20 线程各档在节点 0，24 线程档使用节点 0 的 20 个 CPU 和节点 1 的 4 个 CPU。
运行器保存实际每线程 CPU/节点映射，CSV 和终端表标明 `single_node` 或
`cross_node`；24 线程结果同时包含跨节点放置的影响。可用 `--cpus` 指定顺序，
脚本不推断宿主机物理核关系，也不改变 guest 拓扑或内存分配策略。

N 只计有效负载 cacheline，不含锁、控制状态、栈或框架访问。数据槽的大小和
对齐均为 64B，包含 8B 计数器和 56B 填充；锁和控制状态另行对齐。
五个临界区固定展开，使用 `READ_ONCE/WRITE_ONCE`；规模选择和循环控制均在锁外。
热循环包含调用临界区、4 组局部乘加、更新完成次数和循环判断，没有 `cond_resched()`、
sleep/yield、额外自旋等待或定期信号轮询。进入循环后执行完整批次，再返回 ioctl。
临界区内不读时钟、不打印、不调用服务。每阶段核对所有 16 个计数器的前后
差值；未访问的槽必须不变。模块重载初始化新会话，不在测量中重置数据。

## 编译和运行

已有 guest 内核必须通过只读基线检查，使用 `nokaslr`、voluntary preemption
及 [固定 Python 运行依赖](../../disassem/requirements.txt)。如果使用 venv，
把该环境的 `bin` 放在 PATH 首位，使 daemon 子进程使用同一解释器。

```sh
cd /root/host_fs/kdlock
export LC_ALL=C
make -C bench/spin_cacheline all test

# 只预览参数和配对顺序；不构建、不加载、不创建结果目录。
python3 bench/spin_cacheline/run.py --dry-run

# 从宿主机 monitor 实际确认 recovery 快照后才设置。
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=pre_native_resume_20260905_1110
timeout 3600s python3 bench/spin_cacheline/run.py \
  --output /tmp/spin-cacheline-scan-20260914
```

快照 tag 是当前环境的示例，填写实际确认的 tag；环境变量不是快照证明。
宿主机发起 SSH 时也加总时限，例如 `timeout 3700s ssh ...`，不能只依靠
`ConnectTimeout`。脚本核对空闲状态和拓扑、构建本目录的专用 provider、daemon
和 benchmark，保留构建日志；普通 `kernel_module/` 的源码和构建产物不会被覆盖。

<a id="rerun-100k-no24"></a>

### 2026-09-15：每线程十万次完整重跑（不含 24 线程）

本节保留当时**尚无锁外乘加、采用配对比值中位数**的结果；不是当前负载的成绩。
当前的最佳值/中位数口径见[结果解释](#结果解释)，旧归档不覆盖或重新标记。

用户确认后，将每线程批次由 1,000,000 次缩短为 **100,000 次**，在正常排空、
保存上次故障证据后，重启到同一 `6.1.159-kdstatic2` 实验内核。
Build ID 为 `460d77502af4709a0cca794b322cedc20c2cc478`，临界区、一次 ioctl
批量抢锁、watchdog 和内核配置均保持不变。以下结果来自新的完整扫描，
不混入此前百万次批次的部分结果。

```sh
# recovery guest；先从宿主 monitor 确认恢复快照，宿主 SSH 外层限时 4000 秒。
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout 3900s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 2 4 8 16 --threads 1 4 8 12 16 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /tmp/spin-cacheline-no24-100k-20260915
```

**30 个配置、60 对、120/120 个会话完成并通过校验**，共完成
**122,000,000 次临界区操作**。60 个原生会话、10 个单线程 NO_JIT 会话、
50 个多线程实际 JIT 会话；测量期正文计数合计 **58,787,194** 次。
五种 cacheline 规模均获得有效的测量期实际 JIT 证据。所有 worker 固定在
guest CPU 0–19、NUMA 节点 0，未运行 24 线程。

下面吞吐量单位为 **百万次完整临界区/秒（Mops/s）**，是全部线程的总吞吐。
原生与 kdlock 吞吐各取两个会话的中位数；吞吐比取两对 kdlock/原生比值的
中位数，JIT 占比也取两个测量会话的中位数。只做两对，不宣称统计显著性。

| cacheline | 线程 | 原生 Mops/s | kdlock Mops/s | 配对吞吐比 | JIT 占比 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 11.923 | 8.421 | 0.7064 | 0.00% |
| 1 | 4 | 3.088 | 0.462 | 0.1498 | 77.41% |
| 1 | 8 | 3.365 | 0.359 | 0.1068 | 99.46% |
| 1 | 12 | 3.255 | 0.363 | 0.1116 | 99.71% |
| 1 | 16 | 3.479 | 0.369 | 0.1059 | 99.81% |
| 1 | 20 | 3.293 | 0.369 | 0.1119 | 99.82% |
| 2 | 1 | 11.419 | 8.598 | 0.7559 | 0.00% |
| 2 | 4 | 2.905 | 0.426 | 0.1463 | 74.55% |
| 2 | 8 | 3.021 | 0.364 | 0.1207 | 99.54% |
| 2 | 12 | 2.849 | 0.368 | 0.1291 | 99.78% |
| 2 | 16 | 3.006 | 0.373 | 0.1240 | 99.78% |
| 2 | 20 | 2.854 | 0.374 | 0.1309 | 99.87% |
| 4 | 1 | 12.231 | 8.766 | 0.7181 | 0.00% |
| 4 | 4 | 2.642 | 0.367 | 0.1388 | 68.04% |
| 4 | 8 | 2.718 | 0.366 | 0.1347 | 99.68% |
| 4 | 12 | 2.591 | 0.375 | 0.1448 | 99.83% |
| 4 | 16 | 2.770 | 0.373 | 0.1347 | 99.75% |
| 4 | 20 | 2.663 | 0.377 | 0.1417 | 99.84% |
| 8 | 1 | 10.704 | 7.729 | 0.7246 | 0.00% |
| 8 | 4 | 2.423 | 0.445 | 0.1834 | 75.97% |
| 8 | 8 | 2.351 | 0.369 | 0.1570 | 99.39% |
| 8 | 12 | 2.339 | 0.371 | 0.1586 | 99.75% |
| 8 | 16 | 2.430 | 0.375 | 0.1545 | 99.68% |
| 8 | 20 | 2.308 | 0.375 | 0.1628 | 99.82% |
| 16 | 1 | 10.415 | 13.207 | 1.3356 | 0.00% |
| 16 | 4 | 2.017 | 0.330 | 0.1635 | 70.03% |
| 16 | 8 | 1.923 | 0.378 | 0.1966 | 99.50% |
| 16 | 12 | 1.932 | 0.364 | 0.1882 | 99.73% |
| 16 | 16 | 1.969 | 0.371 | 0.1886 | 99.76% |
| 16 | 20 | 1.972 | 0.374 | 0.1895 | 99.80% |

单线程均为 **NO_JIT、JIT 占比 0**。1/2/4/8 条 cacheline 的单线程 kdlock
吞吐为原生的 70.6%–75.6%，仍有开销差距。
16 条 cacheline 的单线程两对比值分别为 **0.6081、2.0631**；
kdlock 两次 wall 时间分别为 14.451、5.130 ms，原生为 8.787、10.583 ms，
波动明显。原始有效样本全部保留；不能由其中位数 1.3356 认定稳定性能提升，
这些批次边界时间也不能单独确定波动来自哪个函数。本次多线程吞吐比为
**0.1059–0.1966**，kdlock 仍明显慢于原生。
缩短批次解决了本次扫描的持续占用时间问题，没有改变锁算法；实际 JIT 发生
不代表性能提升。该环境为虚拟机，不宣称宿主物理核独占，也不把吞吐比当作
锁等待概率或持有线程切换次数。

最长测量批次为 **5.44 秒**，全程未出现 watchdog、
kernel fault 或数据错误。每会话均确认 worker/请求排空，kdlock 正常 retire
到 state=2、modules/frames/writers=0，再正常卸载；结束后再次确认 guest 空闲、
内核身份和冻结源码一致。`watchdog_thresh=10`、`soft_watchdog=1` 未改动。
原始 CSV 同时保留摊销 ns/op 和线程 CPU 时间；ns/op 是整批 wall 时间除以
完成次数，不是单次获取锁延迟。时钟只在批次边界读取。

guest 原始目录为 `/tmp/spin-cacheline-no24-100k-20260915`；宿主可读副本位于
`/tmp/spin-cacheline-no24-100k-evidence-20260915/`，其中同名子目录提供
[汇总 CSV](/tmp/spin-cacheline-no24-100k-evidence-20260915/spin-cacheline-no24-100k-20260915/summary.csv)、
[逐会话 CSV](/tmp/spin-cacheline-no24-100k-evidence-20260915/spin-cacheline-no24-100k-20260915/raw.csv) 和
[逐对 CSV](/tmp/spin-cacheline-no24-100k-evidence-20260915/spin-cacheline-no24-100k-20260915/pairs.csv)。离线核对了 127 个冻结输入、
4 个二进制、全部计数器差值/聚合/配对，以及 240 次生成物哈希；
离线核对只证明已保存文件的一致性，运行和排空另有 guest 原始记录。

归档 `/tmp/spin-cacheline-no24-100k-20260915.tar.gz` 保存 3859 个普通文件，
包括源码/二进制、原始会话、生成物、日志、重启/快照记录和最终排空检查。
SHA256：

```text
7cf0995137e6014eb5a6f6c92968fa861307acdd3a80ce1fb36919003ee488f5
```

本结果段落在扫描结束后补写，归档中的 README 是运行前的冻结版本。

### 百万次批次：实际命令（故障后停止）

2026-09-15 首次批次选择 **1、4、8、12、16、20 线程**，CPU 0–19，全部位于当前
guest 的节点 0。五种 cacheline 规模，每线程 1,000,000 次，每点两对，合计
**30 个配置、60 对、120 个会话**。沿用上一轮优化的独立实验内核：

**此百万次扫描未完成**：12 线程的 kdlock 长批次触发 watchdog，运行器已停止。
以下保留实际使用的命令，不能把百万次批次视为高线程档的已验证配置。

```sh
# recovery guest；快照须已经从宿主 monitor 实际确认。
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout 3900s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 2 4 8 16 --threads 1 4 8 12 16 20 --cpus 0-19 \
  --iterations 1000000 --repeats 2 \
  --output /tmp/spin-cacheline-no24-20260915
```

宿主 SSH 外层时限设为 4000 秒。追加 `--dry-run` 可检查本次 120 会话计划；
这次显式排除 24 线程，不更改运行器支持的线程档位。

### 百万次批次：保留的失败结果

计划 120 个会话，实际 **13 个通过、1 个 KERNEL_FAULT、106 个 NOT_RUN**。
24 线程不在计划中，也未执行。此前通过的会话共完成 64,000,000 次操作，
其中 7 个原生会话、2 个单线程 NO_JIT、4 个实际 JIT 会话；有效配对 6 对，
测量期 JIT 正文合计 21,116,765 次。完整配对都属于 1 条 cacheline：

| 线程 | 原生摊销 ns/op | kdlock 摊销 ns/op | 配对吞吐比中位数 | 测量期 JIT 次数 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 38.59 | 50.57 | 0.7631 | 0（NO_JIT） |
| 4 | 286.37 | 3001.74 | 0.0954 | 5,151,572 |
| 8 | 281.31 | 2759.34 | 0.1020 | 15,965,193 |

第 14 个会话 `c01-t12-r00-kdlock` 在测量期报告：

```text
watchdog: BUG: soft lockup - CPU#0 stuck for 25s! [sc_worker:23888]
```

CPU 0–11 均出现同类报告；等待线程的 RIP 位于
`__kd_spin_lock_longjmp+0xc8/+0xcc`，另一个 CPU 位于生成代码。
实际内核 `watchdog_thresh=10`，soft-lockup 阈值按该源码为其两倍；
`soft_watchdog=1`、`softlockup_panic=0`。这一批 12,000,000 次操作耗时
**32.62 秒**。证据指向百万次长批次在 voluntary 内核中持续占用 CPU，
使 watchdog 线程迟迟得不到调度；并非 syscall 次数过多。

客户端最终返回，所有线程各完成 1,000,000 次、数据差值正确；这不取消
KERNEL_FAULT，也不生成该会话的有效性能比。诊断时已无 worker/daemon，
active/frame/writer 为零，计数稳定；随后正常 retire 到 state=2、
modules/frame/writer 全零，再按顺序卸载两个模块。未强制卸载、未关闭 watchdog、
未在热循环加入让出或延时。运行器的原始失败状态保留，未自动重试。

1 条 cacheline 的 JIT 已有本次证据；2/4/8/16 条 cacheline 尚未运行，
本轮仍为 UNVERIFIED。12 线程仅有一个有效原生会话，缺少有效 kdlock 配对；
16/20 线程未执行，不能称为完整扫描通过。此后经用户确认，已用新目录完成
[每线程 100,000 次的独立扫描](#rerun-100k-no24)；两次结果不合并。

guest 故障时的原始目录为 `/tmp/spin-cacheline-no24-20260915`，诊断目录为
`/tmp/spin-cacheline-no24-fault-20260915`；已在重启前归档，guest 的这些临时
目录随重启清理。宿主可读结果、CSV 及部分扫描离线
校验位于 `/tmp/spin-cacheline-no24-evidence-20260915/`。
归档 `spin-cacheline-no24-failed-20260915.tar.gz` 保存 610 个普通文件，包括
全部已获得的冻结源码/二进制、命令、原始 JSON/CSV、生成物、故障日志和清理
记录，SHA256：

```text
4760ac4e8f132bd40f17c86ac2362f7e86b0f371a2ef3b791e0d3a7ff2a1fb05
```

离线检查覆盖 127 个冻结输入、有效会话数据和配对、24 次生成物哈希核对，
失败与未运行项保持原分类。正文循环和生产实现本轮没有改动；此结果段落在
扫描停止后补写，归档中的 README 是运行前的冻结版本。

### 构建产物和单点选择

`make all` 包含 `provider`、`module` 和 `client`。只构建原生负载可执行
`make -C bench/spin_cacheline module client`；`module` 委托给
`workload_modules/spin_cacheline/Makefile`，输出同目录的 `spin_cacheline.ko`。
`provider/prepare.py` 将当前项目的
provider 源码和头文件复制到 `.build/provider/`，只在副本应用
`provider/observation.patch` 并加入 `provider/kd_bench.c`、`provider/kd_bench.h`，
再按 `KDLOCK_SELFTEST=0 KDLOCK_NUMA=0` 构建。补丁仅包含常规日志开关和
wrapper 返回后的正文计数接入，不改变锁协议、准入检查或 wrapper ABI。
不维护另一份完整 kdlock 源码；项目更新导致补丁上下文不匹配时构建直接失败，
需要先检查并更新观测补丁，不能用模糊匹配绕过。

测试模块输出为 `.build/provider/kernel_module/kdlock_km.ko`，模块名仍为
`kdlock_km`，以复用现有 daemon/设备接口，因此不能与普通 provider 同时加载。
普通 `make -C kernel_module` 不包含这些 benchmark 参数或计数开销。
`manifest.json` 记录原始输入、观测层及最终副本的哈希；扫描结果同时冻结这些
文件和实际加载的模块。`make clean` 只清理本 benchmark 的构建产物。

缩小参数示例（仍按两对执行，四个会话）：

```sh
timeout 600s python3 bench/spin_cacheline/run.py \
  --cachelines 4 --threads 8 --iterations 10000 --repeats 2 \
  --cpus 0-7 --output /tmp/spin-cacheline-c4-t8
```

`--cachelines`、`--threads` 接受空格分隔的多个值；`--cpus` 接受逗号或区间，
保持输入顺序且拒绝重复。`--repeats` 指每配置的**配对数**，必须是正偶数。
`--iterations I` 是**每个线程在一次 `SC_RUN` ioctl 内执行的抢锁次数**，范围
1–100,000,000，默认 10,000。需要更长的批次时，例如指定
`--iterations 1000000`，每线程仍只提交一次 RUN；不要在用户态循环调用 ioctl。
结果目录须在源码树外且不存在，拒绝覆盖。扫描期间不要改源码或二进制；
脚本会在会话边界比对输入哈希。需要有序提前停止时创建结果目录下的 `STOP`
文件，当前会话排空后停止，保留后续 `NOT_RUN`。

单独试用原生模块不需要 kdlock 符号（同样遵守恢复环境和外层时限）：

```sh
insmod workload_modules/spin_cacheline/spin_cacheline.ko
bench/spin_cacheline/client --layout
timeout 120s bench/spin_cacheline/client \
  --cachelines 4 --iterations 10000 --cpus 0,1,2,3
bench/spin_cacheline/client --counts
# 确认客户端退出、计数查询成功且 active=0 后：
rmmod spin_cacheline
```

这只是组件运行方法，不替代配对扫描；超时之后不要继续执行卸载命令。

## 两组执行流

每个会话先加载独立源模块、查询布局并确认初始计数为零。原生组整个会话
都不加载 kdlock。kdlock 组装载本目录生成的专用 provider
`.build/provider/kernel_module/kdlock_km.ko`，装载参数为：
`target_process=sc_worker bench_quiet=1 bench_lock_addr=<被测锁地址> jit_timing=0`，
启动现有 daemon，继承 `KD_JIT_BODY_WITNESS=1`。

两组均由 T 个绑核线程先执行每线程 1 次、等待 1 秒，再执行每线程 12,000 次。
这是预热和现有热锁频率采样的自然准备；不调用强制晋升接口、不增加竞争线程。
kdlock 组等待对应 `sc_body_N` 的唯一 spin 条目 NORMAL，检查非空生成物及正文
标记、成功的翻译子进程结果，并等待翻译者退出。随后停止 daemon、确认无
writer/frame；两组均再等待 2 秒。发布失败或准备超时不能冒充 NO_JIT。

客户端使用 C11 原子变量 `ready/go/abort` 起跑，不使用 mutex 或条件变量。
每个线程完成绑核后发布 ready，再用 `pause` 等待 go；主线程等所有已创建线程
ready 后读取 wall 时钟，用 release store 放行，worker 用 acquire load 接收。
任一创建/绑核失败会发布 abort，并放行、回收已创建线程，不执行负载。
ready 和 go 分开对齐到 cacheline；编译时要求这些原子类型始终 lock-free。
原子起跑等待只在 ioctl 前发生，批次内不设同步屏障或交接等待。
起跑前的自旋不计入 worker CPU 时间；wall 区间从主线程放行前的时间戳，到
最后一个 worker 在 ioctl 返回后取得的时间戳，worker CPU 时间分别取线程
CPU 时钟。准备阶段不计入测量。
kdlock 测量前后分别读取只读 `bench_jit_bodies`，并核对条目和生成物哈希未变。

驱动的执行登记和计数快照也使用原子状态：非负值表示在途 worker 数，-1
表示快照独占。读取快照必须成功将 0 改为 -1；期间新 RUN 返回 EBUSY。存在
worker 或其他快照时，计数查询返回 EBUSY。最后一个 worker 的 release 退出
与快照的 acquire 进入配对，避免仅检查 active=0 后与新写入发生竞争。这些
操作每个 ioctl 只在循环前后执行，被测临界区仍使用同一把 `spinlock_t`。

专用 provider 的 `bench_quiet` 默认 false，`bench_lock_addr` 默认 0（不计数），
均仅能在装载时指定。quiet 关闭常规逐次日志，保留 warning/error、拒绝诊断、汇总和全部协议
检查。实际 wrapper 返回且正文标记为 1 时，匹配锁按一次逻辑 dispatcher 调用
计数；同一调用的多个 wrapper continuation 不重复计数。计数采用 per-CPU 槽，
不增加全局原子更新；只读 getter 求和包括 offline CPU。**只能在调用者和 frame
排空后解读精确累计值**，执行中读取只是近似快照。两元素 wrapper ABI 不变。

## 临界区与测试伪代码

所有线程更新模块全局的同一个 `sc_data` 数组，并争用同一把 `sc_lock`。
例如 N=4 时，[payload.h](../../workload_modules/spin_cacheline/payload.h)
展开的临界区如下；N=1/2/8/16 只改变显式更新的槽数，每次获取锁完成一次 op。
每槽只读改写一个 64 位值，64B
表示槽的占用与间距，不表示每次操作从内存读取完整的 64B。

```c
static void sc_body_4(void)
{
    spin_lock(&sc_lock);
    WRITE_ONCE(sc_data[0].value, READ_ONCE(sc_data[0].value) + 1);
    WRITE_ONCE(sc_data[1].value, READ_ONCE(sc_data[1].value) + 1);
    WRITE_ONCE(sc_data[2].value, READ_ONCE(sc_data[2].value) + 1);
    WRITE_ONCE(sc_data[3].value, READ_ONCE(sc_data[3].value) + 1);
    spin_unlock(&sc_lock);
}
```

增大 `--iterations` 只增加获取锁的次数，不增加单次持锁的工作量：
**每次持锁仍只执行 N 次计数器自增**。锁内没有重复执行这组更新的循环，
也不主动刷新缓存或强制每次更新产生 cache miss。

以下是一次测量的成功路径，对应 [client.c](client.c) 与
[module.c](../../workload_modules/spin_cacheline/module.c)。
N 是数据 cacheline 数，T 是线程数，I 是每线程迭代数；`now()` 返回纳秒数。
外层运行器在每个配置依次执行原生→kdlock、kdlock→原生，
两组各自重建会话并完成前述准备。
kdlock 的 JIT 计数在客户端测量前、返回且排空后分别读取；预热不计入差值。

```text
client_main(N, T, I):
    fd = open(device)
    layout = ioctl(fd, SC_LAYOUT)             // 检查共享锁与数据槽布局
    before = ioctl(fd, SC_COUNTS)             // 此时无 worker
    atomic ready = 0; atomic go = false; atomic abort = false
    创建 T 个 worker，各自指定一个不同的 guest CPU
    while load_acquire(ready) != T: pause()
    t0_ns = now(CLOCK_MONOTONIC)
    store_release(go, true)
    join 所有 worker
    t1_ns = max(worker.finished_ns)           // 使用已记录时间，不在 join 后重新计时
    after = ioctl(fd, SC_COUNTS)              // 在测量区间之后
    completed = sum(worker.completed)
    assert 所有 worker 成功且各自 completed == I
    assert completed == T * I
    assert after[j] - before[j] == (completed if j < N else 0), 对所有 16 个槽
    wall_ns = t1_ns - t0_ns
    throughput = completed * 1e9 / wall_ns
    amortized_ns_op = wall_ns / completed
    worker_cpu_ns = sum(worker.cpu_ns)
    close(fd)

worker(cpu, N, I):
    request = {cachelines: N, iterations: I}
    绑定并核对 CPU，设置线程名             // 全部在 ready 之前
    fetch_add_acq_rel(ready, 1)
    while !load_acquire(go): pause()
    if load_relaxed(abort): return
    cpu_start_ns = now(CLOCK_THREAD_CPUTIME_ID)
    ioctl(fd, SC_RUN, &request)               // 仅一次；结果写回 request.completed
    finished_ns = now(CLOCK_MONOTONIC)
    cpu_ns = now(CLOCK_THREAD_CPUTIME_ID) - cpu_start_ns
    返回 request.completed、finished_ns、cpu_ns

kernel_SC_RUN(request):
    copy_from_user(request)                   // 整批只复制一次输入
    校验 N、I；选择已展开的 sc_body_N          // 选择在循环外
    原子登记在途 worker；快照独占时返回 EBUSY
    completed = 0
    local_state = 1                          // 每个 ioctl 私有，跨迭代保留
    while completed < I:                     // 整个循环都在一次 ioctl 的内核调用中
        sc_body_N()                          // lock → N 次读改写 → unlock
        repeat 4 times:                      // 锁已释放，仅为下一次抢锁留一个小间隔
            local_state = (local_state * 1664525 + 1013904223) mod 2^64
        completed += 1
    原子注销在途 worker
    request.completed = completed
    copy_to_user(request)                    // 整批只复制一次输出
    return 0
```

锁外计算实现在 [post_work.h](../../workload_modules/spin_cacheline/post_work.h)。
实际代码固定展开为 4 条 `imulq` 和 4 条 `addq`，用 `asm volatile` 保证最终结果
即使不被业务使用也不会被删除；操作数只在寄存器中，不更新共享 sink 或计数器。
它在正文函数返回后执行，不进入 JIT 临界区，也不增加每次 op 的 syscall。
两组执行完全相同的计算，wall 时间和线程 CPU 时间都包含其开销；不扣减估算值。
这个短间隔增加其他线程在下一次申请前获取锁的机会，**不保证公平交接**。

创建或绑核失败时，实际代码设置原子 abort、放行并回收已创建线程，负载不执行。
ioctl 失败、迭代不完整或数据校验失败都不能生成有效性能比。
RUN 循环不再轮询信号并返回部分完成的 EINTR；停止和卸载仍须等待固定批次完成并排空。

## 时钟与 syscall 开销

`clock_ns` 这类读时钟函数**会影响性能**。本实现的函数名是 `now(clockid_t)`，
它调用 `clock_gettime` 并将结果换算成 ns；只在整批操作边界调用，内核循环
和临界区内均没有计时。下面统计的是一次成功的**测量客户端调用**，不含
运行器的预热、布局辅助查询、JIT 观测及排空检查：

| 调用 | 次数 | 位置 |
| --- | --- | --- |
| `SC_RUN` ioctl | T | 每个 worker 一次，每次执行 I 次抢锁 |
| `SC_LAYOUT` / `SC_COUNTS` ioctl | 1 / 2 | 测量开始前 / 测量前后 |
| `clock_gettime(CLOCK_MONOTONIC)` | T+1 | 主线程放行前一次，每个 worker 返回后一次 |
| `clock_gettime(CLOCK_THREAD_CPUTIME_ID)` | 2T | 每个 worker 的整批操作前后各一次 |

因此执行 T×I 次临界区只需要 T 次 RUN，总 ioctl 数为 T+3，读时钟共 3T+1 次。
例如 T=16、I=10,000 时，160,000 次抢锁对应 16 次 RUN、3 次布局/计数 ioctl
和 49 次读时钟；增大 I 不增加这些调用次数。定向客户端测试在不同批次大小
下检查这一调用预算，观测只存在于测试夹具，不加入性能测量程序。

函数调用次数不等于实际 syscall 次数：`CLOCK_MONOTONIC` 可走 vDSO，仍可能
回退到 syscall；当前 guest 内核的 `CLOCK_THREAD_CPUTIME_ID` 走 syscall
回退。无论采用哪条时钟路径，都有执行成本，不能把 vDSO 当作零开销。

固定成本没有从结果中扣除。放行后的线程 CPU 时钟读取、ioctl 进出与返回后
的 wall 时间戳都影响测量边界；某个 worker 最后的 CPU 时钟读取虽晚于它自己
的结束时间戳，也可能与其他 worker 的测量区间重叠。增大 I 可以摊薄批次边界
成本，但本测试没有单独量化时钟开销，不能据此给出误差百分比。

热循环没有用户态发起的 syscall，也不主动调度或等待；每次解锁返回后完成
局部乘加再开始下一轮抢锁。中断和 guest/宿主调度仍可能影响执行，每次 `sc_body_N()` 调用、
循环控制、已有 hook 和 kdlock 观测也有成本。因此这里报告的是包含框架成本的
整批临界区吞吐。连续抢锁不保证每次解锁都换一个持有线程；当前没有记录原生
获取锁失败次数、等待时间、持锁时间或持有线程切换次数，不能由这些结果量化
竞争程度；总吞吐随线程数增长也不能证明没有竞争或锁已经饱和。

## 结果解释

主表以吞吐为选择指标，这里的 medium 按 **median（中位数）**处理：

```text
native_median = median(所有有效原生会话的 completed / wall_seconds)
kdlock_best   = max(所有有效 kdlock 会话的 completed / wall_seconds)
best_ratio    = kdlock_best / native_median
```

只在同一 cacheline 数、线程数、迭代数、CPU 放置和同一冻结运行输入内选择。
这是**本次样本中 kdlock 的最佳观测表现对原生中位数**，不等于理论极限或典型性能；
取样次数增多会影响最大值，因此表中同时显示两组有效样本数。默认每组 2 个样本，
需要更多观察时显式增大正偶数 `--repeats`。不跨配置挑原生较慢的一组，
也不取逐对比值的最大值。所有原始样本与原有配对比值仍保留供检查。

kdlock 最佳吞吐对应的会话名、摊销 ns/op、JIT 次数/占比/状态来自**同一个会话**。
最快样本若是 NO_JIT，仍显示 NO_JIT。准备失败、数据错误、未排空和未运行样本
均不参与选择；任一组没有有效样本时比值留空。两组分别取有效样本，未完成配对
仍在 `pairs.csv` 留空，主表通过有效样本数明确展示这种情况。

结果目录包含 `environment.json`、CPU 拓扑、内核基线与构建身份、输入和二进制
SHA256、源码/二进制副本、payload 反汇编；每会话保留 `session.json`、各阶段
客户端 JSON、命令/PID、布局、翻译指标、生成物、kernel 日志及 retirement 状态。
构建或准备失败也保留已取得的证据。

| 输出 | 含义 |
| --- | --- |
| `raw.csv` | 每会话 CPU/NUMA 放置、完成次数、wall ns、吞吐、摊销 ns/op、线程 CPU ns、实际 JIT 次数/占比、数据校验与状态 |
| `pairs.csv` | 每对 NUMA 放置、kdlock/原生吞吐比及先后顺序；无效或缺失组为留空 |
| `summary.csv` / 终端表 | 原生吞吐中位数、kdlock 最高吞吐、best/median、有效样本数及最佳会话的 JIT 信息；CSV 另保留原有中位数和配对汇总 |
| `summary.json` | `comparison_policy=best_kdlock_over_median_native`、完整度、各配置汇总及测量期实际 JIT 覆盖 |

一次 op 是一次完整临界区，包含 N 次计数器更新。吞吐为完成 op / wall 时间，
`amortized_ns_op` 为 wall 时间 / 全体线程完成 op；不是单次获取锁的延迟。
线程 CPU 时间包含锁外乘加、ioctl/框架成本，也不等同于锁内成本。主表比值
大于 1 表示 kdlock 最佳观测吞吐高于原生中位数，小于 1 表示更低。
`best_kdlock_over_median_native` 是新主指标；`median_kdlock_over_native` 仍是
旧的逐对吞吐比中位数。两者不可互换，不据最佳值宣称统计显著性。
缺少每会话节点映射的历史结果重汇总时，NUMA 放置标为 `unknown`，不根据 CPU 编号推断。
此前含每 256 次调度点、2/4/8/16 线程的结果属于旧负载，不能作为当前连续抢锁版本的结果。
增加锁外乘加前的结果也属于另一负载版本；其历史成绩保持原标注。

`NO_JIT` 表示发布准备成功、测量完成且数据正确，但**测量期间**返回的 JIT
正文数为零；JIT 占比记 0，保留性能和配对比值，不能记为实际 JIT 验收通过。
预热曾执行 JIT 不改变此分类。每种 N 至少一个线程配置出现有效的测量期正文，
才验证该规模的 JIT 对比；否则明确列为 UNVERIFIED。正常排空的 NO_JIT 可继续
扫描；准备失败、数据错误不计算有效性能比。离线重生成汇总：

```sh
python3 bench/spin_cacheline/summarize.py /tmp/spin-cacheline-scan-20260914
```

<a id="assembly-inspection"></a>

### 汇编查看目录

`run.py` 和 `profile.py` 在每个 kdlock 会话成功完成测量、排空、停止翻译者及
正常卸载后，自动复制汇编到：

```text
bench/.tmp/spin_cacheline/<结果目录名>-<随机后缀>/
  README.md                      # 可点击的逐会话索引，随会话完成更新
  index.json                     # 参数、JIT 状态/次数/占比和 SHA256
  c01-t04-r01-kdlock/
    native.S                     # 翻译前的 sc_body_1，模块反汇编及重定位注释
    JIT.S                        # 生成器 asm/jit.S 原样复制，仅改文件名大小写
    bin.txt                      # JIT 机器码（含 wrapper）的 objdump 反汇编
    metadata.json                # 来源路径、入口/TGID、会话参数、文件 SHA256
```

**`bin.txt` 来自 `objdump ... asm/jit.bin`，是 JIT 之后的代码。** 翻译前请查看
`native.S`，它从该次运行的 `payload-disassembly.txt` 提取对应完整 `sc_body_N`，
保留锁调用和重定位信息；其中地址是模块 ELF 节内偏移，不是 guest 运行地址。
`JIT.S` 中还保留了生成器的原指令注释，实际运行入口和代码地址见 `metadata.json`。

运行器输出 `Assembly: ...`，并在原始结果目录写入 `assembly-export.json`，指向
本次查看目录。各会话的文件完整写入后才公开目录，索引逐次更新；复制和哈希
核对都位于计时区间之外，热循环不增加文件操作、时钟调用或 syscall。
每次扫描、每次补导出均创建新目录，不覆盖已有副本；目录由 Git 忽略且不进入
源码冻结。原始 workspace、生成器命名和测量结果保留不变。

导出按记录的 RIP/TGID 定位生成物，核对测量前后的发布记录与 SHA256。
新会话同时记录 `jit.bin`、`jit.S`、`bin.txt` 的测量前后哈希；旧结果只记录前两者，
补导出时将 `bin_txt_hashed_during_measurement` 标为 `false`，另存复制时哈希。
NO_JIT 仍保存已生成的汇编并标明正文数为 0，不能据文件存在判定实际执行了 JIT。
原生组没有 JIT 生成物；失败、未完成或未排空的会话不读取 workspace、不导出。
应有的文件缺失或已记录的哈希不符时停止导出，原始证据不覆盖。

对已保存的结果补导出（只处理文件，不加载模块、不执行 workload）：

```sh
python3 bench/spin_cacheline/assembly.py /tmp/spin-cacheline-best-post-work-20260915
```

该命令只在 `bench/.tmp/` 新建副本和索引，不向历史结果目录补写文件。它也可以
读取宿主机已解压的证据目录。recovery guest 使用 ext4，guest 内的查看目录
不会自动出现在宿主机共享源码；在宿主机将终端给出的准确目录复制回来：

```sh
mkdir -p bench/.tmp/spin_cacheline
# 将 <本次目录名> 替换为 Assembly 输出中的完整目录名，先确认本地同名目录不存在。
timeout 60s scp -r -P 2222 \
  'root@127.0.0.1:/root/host_fs/kdlock/bench/.tmp/spin_cacheline/<本次目录名>' \
  bench/.tmp/spin_cacheline/
```

这些副本供查看，不替代原始证据归档。需要清理时，仅删除已经查看完毕的那一个
临时结果目录；`make clean` 不删除它们，也不清理原始结果。

<a id="assembly-validation"></a>

#### 汇编导出验证（2026-09-15）

recovery guest 已通过 9 项定向检查：`test_assembly.py` 的 6 项检查，以及既有
单 ioctl/固定时钟调用次数、NO_JIT/配对比值、计划顺序检查。导出检查覆盖
RIP/TGID 匹配、未排空会话不读取 workspace、缺失/变更产物拒绝、完整目录发布、
新目录不覆盖旧副本，以及新旧发布哈希格式。

随后从[锁外乘加完整扫描](results/20260915-post-work.md)补导出 60 个 kdlock
会话，每个包含 `native.S`、`JIT.S`、`bin.txt`，合计 180 份汇编文件；
50 个会话为实际 JIT、10 个为 NO_JIT。全部副本与原始证据逐文件核对，原始
3889 个普通文件和源码冻结清单保持不变。此步骤未重新运行性能负载。

当前宿主机本地副本的
[逐会话索引](../.tmp/spin_cacheline/spin-cacheline-best-post-work-20260915-uhgjgmxe/README.md)
包含全部参数和文件链接。该目录是 Git 忽略的临时查看副本，不随提交或克隆分发；
清理后可用上面的补导出命令从保留的原始结果重新生成。
验证日志保存在 `/tmp/kdlock-bench-assembly-20260915/guest-checks/unit.log`，
导出及证据不变性记录为同目录的 `verification.json`。

### 单线程为什么仍有 kdlock 开销

热锁发现按访问频率晋升，并不要求出现锁等待；单线程预热也能达到阈值。
当前生产实现为已登记、已发布的 spin 入口增加了
[原生快路径](../../include/kd_spin_fast.h)：每 CPU 缓存最近的锁地址、入口 RIP
和 gate。来源仍 OPEN、根调用没有已有抢占 pin/IRQ/迁移限制、缓存匹配且整个
私有调度字 S 为零时，直接尝试获取原生锁 L。成功后执行原临界区，解锁时释放
L 并清除 per-CPU 持有记录。这条路径不注册入口、不分配 ticket、不获取 S，也
不执行 JIT；与原生参与者的互斥仍完全由 L 提供。

缓存未命中或原锁获取失败、S 已有持有者/排队请求时，进入原有发现、登记与
委托路径。缓存仅在正常来源 pin 和 NORMAL 发布之后建立，不用线程数判断
是否关闭 JIT，也不改变本 benchmark 的准备和正文计数标准。即使检查 S 为空
之后另一线程进入委托，双方仍须获取 L，不能同时执行临界区。持有记录在 L
释放后、恢复抢占前清除，参与关闭准入后的路由和退休忙检查；快路径持有期间
的嵌套 hook 保持原生执行。

spin selector 的目标名比较使用装载时准备的掩码，仍匹配到 NUL，忽略终止符后
的旧字节，长于 task comm 的目标不会匹配。来源 OPEN 读取已内联；一般路径
的 ticket 栈对象移到独立 helper，减少原生返回时的栈保存和检查。

旧接口下 NO_JIT 仍有独立 selector、回调调用和快路径判断成本。合并入口实验
先尝试缓存中的纯原生获取，解锁先匹配保留的 owner；只有未命中才进行目标
选择。临时抢占 pin 的释放和选择逻辑移到慢路径，减少成功路径的寄存器保存。
它仍要检查原锁、S、来源和 CPU 上下文，并保留 owner 记录，不能视为零开销。
单线程没有其他请求可合并，不能把 NO_JIT 自动解读为原生基线开销。旧版本
每次经过登记、三遍 32-slot 扫描和 12 对内部 irqsave 锁的分析见
[历史调查](../../docs/VALIDATION.md#single-thread-investigation)，优化后配对数据、
同批次 hook 对照与剩余差距见
[先前优化](../../docs/VALIDATION.md#native-fast-path-optimization) 与
[直接调用及热点验证](../../docs/VALIDATION.md#spin-static-dispatch-profiling)。

### 单独测量 hook 调用成本

[`dispatch_floor/`](dispatch_floor/) 是独立诊断 provider，沿用同一负载驱动和
客户端，依次测量无 provider、selector 固定返回原生、selector 加最小原生
lock/unlock 回调三种情况。回调只调用 Linux 原锁 API，没有 kdlock 发现、
ticket、私有队列或 JIT。**这些是调用成本对照，不是 kdlock 成绩，也不计入
实际 JIT 验收。** 不加入默认扫描；常规扫描会拒绝残留的诊断 provider。

```sh
# 仍要求 recovery guest、已确认快照和外层 SSH timeout。
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 timeout 390s \
  python3 bench/spin_cacheline/dispatch_floor/run.py \
  --iterations 100000 --repeats 4 --output /tmp/spin-dispatch-floor-new
```

每轮三组，交替正序/倒序；每样本重载模块，并复用批次时钟、数据检查、内核
错误扫描和正常清理。结果、冻结输入和二进制单独归档。它测量当前 VM/内核的
最小回调对照，不能据此宣称通用硬件下界或改名为标准原生基线。
支持合并入口的实验内核会增加第四组 `combined`：一次直接分派到无条件原生
lock/unlock 回调，不做 selector、缓存或 JIT。旧三组仍使用原安装接口；第四组
才对应合并入口的最小回调成本。具体组别由构建产物导入的接口决定并记录。

### 独立内核实验与热点采样

默认仍验证捕获的原内核。已构建并启动的
[`spin_static` 实验](../../kernel_experiments/spin_static/README.md) 必须显式
指定自己的源码和基线；普通扫描、调用成本对照和采样入口均支持：

```sh
--kernel-source /root/linux-6.1.159-kdstatic2 \
--kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915
```

检查仍覆盖配置、命名源码、构建产物及 live Build ID。每份输出保存所选基线；
不同内核的结果分别记录，各自以同内核原生组配对，不能合并为一批。

[`profile.py`](profile.py) 在正常准备和发布后，用 `perf record` 对实际 worker
做低频内核 IP 采样。每线程仍只有一个 RUN ioctl，不在锁循环中增加时钟或探针。
先用正常扫描构建并验证二进制，再单独采样，例如在原内核上：

```sh
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 timeout 240s \
  python3 bench/spin_cacheline/profile.py \
  --perf /root/kdlock-tools/perf-6.1.159/perf \
  --arm kdlock --threads 1 --cachelines 1 --iterations 100000000 \
  --output /tmp/spin-profile-new
```

实验内核额外传入上面的两个身份参数。四线程诊断选 `--threads 4`，建议
`--iterations 1000000`，避免等待开销使会话超时。默认事件为 `cycles:k`、
频率 499 Hz；禁用 callchain，要求 ftrace/function profiling 保持关闭。
perf 需要在 guest 从对应源码构建并确认事件可用；不在宿主执行。

输出包括原始 `perf.data`、IP/period 样本、符号及大小、实际 JIT 正文差值、
数据检查和排空记录。[`profile_summary.py`](profile_summary.py) 可离线重新汇总，
按样本 period 加权，使用冻结 ELF 和确切生成代码范围；未解析地址保留为
`unresolved`。符号占比表示采到的执行位置，受采样误差和指令归属偏移影响，
不是独立函数计时，也不是锁竞争概率或单次等待延迟。采样会话明确标注
`performance_result=false`，不加入正式性能比值。当前测量与解释见
[验证记录](../../docs/VALIDATION.md)。

## 排空与限制

顺序是停止新 workload → 等全部 ioctl/pthread/客户端退出 → 确认计数查询无
active、provider 无 frame → 等翻译者退出并停止 daemon → 确认无 writer →
`device_session.py retire` 成功（含既有 queue/task/origin 检查）→ 卸载源模块 →
卸载 kdlock。脚本执行此顺序，不强制卸载。`SC_COUNTS` 遇 active 返回 EBUSY。

内核故障、超时、日志丢失或排空不明时立即停止，不自动重试、取消请求或卸载。
检查记录的 PID 和串口，遵循操作手册恢复 guest。超时进程可能仍在内核中，父
进程消失不能证明队列为空；保留的运行中生成目录不能视为完整证据。

这是虚拟机结果，CPU 固定只保证 guest CPU 亲和性，不宣称宿主物理核独占；
模块内存也不额外施加 NUMA 分配策略。原生基线仍使用既有 hook 补丁内核。
quiet 保留必要诊断、原有运行时计数和生成代码正文标记，不是零观测开销。
静态准入、原地发布与 hook reader 生命周期的现有限制继续适用。本实验不扩展
mutex、NUMA 策略、访问时 guard、flags 修复或其他延期正确性功能。
