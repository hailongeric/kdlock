# 2026-09-22：共享 CPU 热度 cookie 与冷态快路径

按用户最终定义，**一个CPU只有一份cookie，所有锁共享，它只表示当前CPU是否热**。
`kd_spin_direct_cookie`直接引用已有per-CPU `rate_hot`，没有新增路径位、嵌套深度、
调用点cookie或共享全局热度变量。原先局部cookie版的成绩分别保存在
[第一阶段](20260922-spin-cold-stage1.md)与[公共调用精简阶段](20260922-spin-cold-stage2.md)。

本版基于`d1c8ddf`，保留`31d8fd2`的配对C壳和公共调用精简。调用端统一传
`kd_spin_direct_cookie`，由普通C入口取得一次pin后读取。冷获取只做一次CAS；
失败携带原值进入pending/MCS，采样仍可当场改变CPU热度。

热度不能证明解锁归属，因此冷获取使用锁字低字节状态5；等待期间升温也不改变本次持有状态。
解锁检查此字节后直接release、减少nondelegated、unpin，不查询热度、ticket、context或fast owner。
32位锁宽度、pending/tail和JIT寄存器包/wrapper输入不变。热分支才保存五个callee-saved，
continuation仍位于CALL后POP前，不依赖未捕获的返回寄存器，也不在JIT里写cookie。

**单线程验收通过，竞争验收未通过，provider开关和workload新壳继续默认关闭。**
没有追加性能重复轮次，也没有跨阶段或跨批次选优。

## 同期性能：每线程100000次

recovery guest，plain/cacheline；1/16 cacheline × 1/4/20线程，每配置一轮，共36场。
Linux/TCLock各一次；当前KD observe/adaptive各paired/on与保留clobber/off一次。
两壳来自同一源码；`cookie_storage=percpu_rate_hot/not_applicable`独立记录和分组。
准备、翻译及48000次单CPU预热不计时。每格为 **Mops/s / 完整操作 ns/op**。

| cacheline | 线程 | Linux | TCLock | observe off | observe on | adaptive off | adaptive on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.698 / 59.89 | 13.558 / 73.76 | 8.529 / 117.25 | 12.581 / 79.49 | 8.675 / 115.27 | 12.590 / 79.43 |
| 1 | 4 | 3.586 / 278.83 | 2.981 / 335.47 | 1.897 / 527.12 | 1.764 / 567.02 | 1.837 / 544.32 | 1.771 / 564.71 |
| 1 | 20 | 4.159 / 240.47 | 4.955 / 201.81 | 4.987 / 200.50 | 4.058 / 246.43 | 4.963 / 201.50 | 4.114 / 243.08 |
| 16 | 1 | 13.175 / 75.90 | 11.846 / 84.42 | 8.285 / 120.70 | 10.408 / 96.08 | 9.497 / 105.30 | 10.490 / 95.33 |
| 16 | 4 | 2.094 / 477.55 | 2.258 / 442.84 | 1.605 / 622.96 | 1.549 / 645.47 | 1.603 / 623.77 | 1.567 / 638.31 |
| 16 | 20 | 2.701 / 370.29 | 3.253 / 307.37 | 4.750 / 210.53 | 3.940 / 253.81 | 4.757 / 210.23 | 4.049 / 246.94 |

同期on/off单线程吞吐：c1 observe/adaptive提升47.51%/45.13%，c16提升25.62%/10.45%。
仍未追平同期Linux/TCLock。超出5%退化门槛的配置为：

| 配置 | observe on/off | adaptive on/off |
| --- | ---: | ---: |
| c1 / 4线程 | −7.04% | −3.61%（未超门槛） |
| c1 / 20线程 | −18.64% | −17.11% |
| c16 / 20线程 | −17.05% | −14.87% |

c16四线程分别下降3.49%/2.28%。热路径新增保存/恢复与锁字读取仍有成本，
但本轮未做多线程PMU，不能将全部退化归因于某一项。以上超门槛配置列为待解决问题。

## 独立PMU诊断：每线程10000000次

仅1线程，c1/c16与同样六组，共12场，每配置一次。perf 6.1.159在guest证据目录构建，
没有构建或修改guest内核。PMU覆盖measure客户端及其线程，排除模块加载、翻译、预热；
仍包含客户端启动/绑核、ioctl及锁外计算，**不是纯lock/unlock指令计数**。
五个事件均100%计数覆盖，无复用折算缺口。

| cacheline | 后端/模式/壳 | ns/op | 指令/op | 周期/op | worker CPU/墙钟 | 切换/迁移 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Linux | 20.80 | 50.17 | 57.41 | 99.33% | 3 / 1 |
| 1 | TCLock | 25.10 | 56.18 | 70.46 | 99.60% | 3 / 2 |
| 1 | observe paired/on | 27.01 | 83.17 | 76.46 | 99.05% | 4 / 2 |
| 1 | observe clobber/off | 49.62 | 208.18 | 142.46 | 99.75% | 3 / 1 |
| 1 | adaptive paired/on | 27.12 | 80.16 | 76.28 | 100.00% | 2 / 1 |
| 1 | adaptive clobber/off | 39.60 | 155.17 | 111.47 | 99.88% | 3 / 1 |
| 16 | Linux | 27.25 | 95.16 | 75.20 | 99.35% | 3 / 1 |
| 16 | TCLock | 31.61 | 101.16 | 87.98 | 99.76% | 3 / 1 |
| 16 | observe paired/on | 33.37 | 125.16 | 93.45 | 100.00% | 2 / 1 |
| 16 | observe clobber/off | 56.39 | 252.86 | 160.22 | 99.89% | 3 / 1 |
| 16 | adaptive paired/on | 33.34 | 125.16 | 93.46 | 100.00% | 2 / 1 |
| 16 | adaptive clobber/off | 45.70 | 199.67 | 128.98 | 99.56% | 3 / 1 |

新壳相对保留壳减少约37%–60%的指令、28%–46%的周期。长批次worker CPU时间接近墙钟，
说明收益主要来自执行开销减少；剩余KD/Linux差距也伴随更多指令和周期。
没有把这些计数进一步分摊为各包装函数或寄存器保存的独立成本。

短批次存在额外影响：c1各组worker CPU/墙钟为67.7%–94.8%，墙钟与CPU时间差额
0.608–3.194ms；c16多数接近100%，adaptive/off为85.7%。启动门释放后的等待及调度
会影响短批次分数，但不足以解释全部长短批次差异。未测频率/宿主steal的独立贡献，
不据此作归因。长批次结果不替代100000次矩阵的验收结论；两批都不代表稳定分布。

## 正确性与机器码

- 36/36性能会话、30000000次操作通过；16/16竞争KD有实际JIT，计时正文17857124次。
  8场KD单线程为NO_JIT。业务数据、IRQ/preempt、队列/ACK、锁字、内核错误及排空检查通过。
- 定向8/8场、1300000次操作通过：paired壳/gate关闭109746次JIT，nested 195339次，
  early 49961次；RCUHT observe/adaptive各1/4线程，竞争正文122208/124695次；
  delegation关闭200000次操作且0次JIT。每场均完成并排空。
- 基础2组、冷路由/ABI、原生MCS、paired JIT共5组通过；运行器13项通过。
  冷路由覆盖64种开关、代理、CAS失败、等待升温及持锁变热状态；另覆盖共享CPU热度下
  两锁冷热不同、普通/提前解锁。实际头文件检查两个CPU的热度互不覆盖、五个活跃callee-saved、
  栈及精确SP/IP/BP；JIT检查MINIMAL COMPLETE、入口拒绝、FULL/native续跑。
- 后续混合MCS fixture使用生产selector/native unlock，把普通状态1与冷态状态5的持有者
  放到同一锁上竞争：400000次操作、399762次入队通过，pin/nondelegated归零，
  无重复初始CAS。此次替换原MCS fixture后只重跑对应驱动。
- 冻结机器码：冷caller跳过显式五寄存器组和SP/IP/BP元数据；selector仅一次CAS，
  失败分支传递原值并在取得锁后只写低字节5。冷解锁仅低字节release、计数及unpin。
  普通C必要保存仍存在：sc_body_1保留rbx，selector在当前UBSAN构建中保留rbx/r12/r13。
  没有关闭provider UBSAN；clobber→通用获取/解锁及pinned→通用热度包装调用仍已消除。
- 第一次额外paired/gate-off控制脚本漏拷冻结source，翻译器因找不到输入退出，负载未开始；
  会话已排空，失败日志保留。修正外部控制脚本后上述8场全部通过，生产源码未改动，
  没有因此重复性能矩阵。
- 56场通过记录共151300000次操作。各轮252份源码manifest一致且逐份校验；
  性能与PMU的四种plain caller执行节/重定位相同。独立构建provider仅非分配的BTF元数据
  不同，执行、数据和重定位节相同；保留各自完整ELF哈希，不冒称二进制文件相同。

所有构建、用例和模块加载在recovery guest。内核6.1.159-kdclobber2，Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`；ext4/nokaslr/voluntary，快照
pre_static_boot_20260915，vCPU0..39绑定host CPU0..39。未修改guest内核；本轮只执行spin。
最终无worker、daemon、源模块或后端残留。observe启用捷径后为CPU热后固定准入；adaptive
再判断单锁热度。CPU变热后仍只能按已有MCS采样降温，安静阶段不会逐次读时钟过期。

## 命令与证据

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 900s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 4 20 \
  --hotlock-mode observe adaptive --spin-cold-fastpath on off \
  --repeats 1 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/cold-fast-20260922/percpu-hot/performance
```

PMU使用同一命令的`--threads 1 --iterations 10000000 --pmu`，输出为相邻`pmu/`；
PATH前置`/root/kdlock-evidence/cold-fast-20260922/perf-build`，工具身份见`pmu-tool.json`。
功能控制、完整命令及退出码见`run-functional-v2.py`、`functional-v2/`。

guest目录`/root/kdlock-evidence/cold-fast-20260922/percpu-hot/`；宿主忽略目录：
[性能summary](../../.tmp/cold-fast-20260922/percpu-hot/performance/summary.csv)、
[PMU汇总](../../.tmp/cold-fast-20260922/percpu-hot/pmu/pmu-summary.json)、
[源码/机器码核对](../../.tmp/cold-fast-20260922/percpu-hot/same-source-code-audit.json)、
[完整归档](../../.tmp/cold-fast-20260922/percpu-hot.tar.gz)。归档SHA256：
`e8eefa660dc6cb0fe0f214c86df85695ec708f1392462f4f2103e82a6d67b0e8`。
