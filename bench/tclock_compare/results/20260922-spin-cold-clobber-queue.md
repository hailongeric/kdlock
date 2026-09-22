# 2026-09-22：内联 CPU 热度、原 clobber 与冷队列门槛

基于`2db1e74`，按用户最新要求删除配对C壳的手工五寄存器push/pop。
宏先取得一次preempt pin，直接读取已有per-CPU热度，冷分支调用原生入口，
热分支直接调用原pinned clobber-v1核心。编译器可按clobber列表在判断前保存活跃值。
cookie仍只引用一个CPU的一份`rate_hot`，所有锁共享，不记录路径或嵌套深度。
32位锁字、寄存器包、wrapper输入及准入约束不变；仅外层接入新壳，内层恢复原clobber调用。

冷入口仍是完整spinlock：一次初始CAS，失败携原值进入pending/MCS；使用非组合节点，
没有可被代理的request/frame。等待期间升温不改变本次原生获取，解锁按锁字低字节5处理，
保留pending/tail并配对nondelegated计数及pin。删除了`kd_spin_direct_enter`选择器。

新增加载后只读参数`spin_hot_min_queue`，范围0–16、默认4，仅冷捷径开启时生效。
0恢复原MCS发布采样；N>0时冷CPU在取得队头所有权、交接前，看到含自己至少N个已链接
节点才累计样本；最多读取N−1个next，缺链不等待。仍每4个合格事件检查40亿TSC窗口，
热CPU继续原发布采样，单锁阈值不变，不新增逐次读时钟或第二份热度。

初始CPU均冷、每线程最多一个在途节点且没有其他负载先暖CPU时，1/2/3线程无法达到N=4，
因此可长期保持原生。4线程仅可能满足门槛，不保证升温。已热CPU仍可能在2/3线程时保持热；
没有后续MCS时不会检查时钟、热值可以一直缓存。此参数调节冷态晋升，不实现新的退热机制。

**本轮仍不默认开启新壳或冷捷径。** 三线程明显改善，但c1单线程adaptive短批次下降9.05%，
20线程observe的c1/c16下降5.83%/5.67%，未满足既定验收线。保留单轮结果，不追加重复测量。

## 同期性能

recovery guest，1/16 cacheline × 1/2/3/4/20线程，Linux/TCLock/KD两模式两壳，
共60配置，每配置一次、每线程100000次。on为`cold_clobber`/开关1/门槛4，
off为同一生产源码的保留`clobber`/开关0/门槛0。准备、翻译、48000次单CPU预热不计时。
每格为 **Mops/s / 完整操作ns/op**，不能当作独立获取锁延迟。

| cachelines | threads | Linux | TCLock | KD observe off | KD observe on | KD adaptive off | KD adaptive on |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 18.431 / 54.26 | 15.512 / 64.47 | 8.895 / 112.43 | 13.506 / 74.04 | 14.280 / 70.03 | 12.987 / 77.00 |
| 1 | 2 | 2.754 / 363.09 | 3.861 / 259.02 | 2.168 / 461.15 * | 2.293 / 436.15 | 1.974 / 506.63 | 2.242 / 446.10 |
| 1 | 3 | 3.480 / 287.32 | 2.481 / 403.10 | 1.645 / 607.81 | 2.632 / 379.88 | 1.663 / 601.16 | 2.674 / 374.01 |
| 1 | 4 | 3.651 / 273.93 | 3.245 / 308.15 | 1.813 / 551.72 | 1.797 / 556.45 | 1.869 / 535.19 | 1.790 / 558.70 |
| 1 | 20 | 4.220 / 236.95 | 4.949 / 202.05 | 4.019 / 248.80 | 3.785 / 264.20 | 4.005 / 249.67 | 3.920 / 255.11 |
| 16 | 1 | 12.943 / 77.26 | 12.245 / 81.67 | 7.044 / 141.97 | 10.583 / 94.50 | 8.882 / 112.59 | 10.451 / 95.68 |
| 16 | 2 | 1.442 / 693.54 | 2.010 / 497.49 | 1.405 / 711.49 | 1.592 / 628.31 | 1.597 / 626.27 | 1.603 / 623.90 |
| 16 | 3 | 1.995 / 501.37 | 1.889 / 529.51 | 1.282 / 779.99 | 1.905 / 525.01 | 1.283 / 779.39 | 1.899 / 526.55 |
| 16 | 4 | 2.136 / 468.09 | 2.200 / 454.65 | 1.572 / 636.10 | 1.511 / 661.83 | 1.558 / 641.70 | 1.501 / 666.41 |
| 16 | 20 | 2.855 / 350.23 | 3.314 / 301.77 | 3.942 / 253.70 | 3.718 / 268.96 | 3.913 / 255.55 | 3.757 / 266.19 |

星号项保留原验收失败，不参与有效性能对照：两线程测量完成200000次且数据正确、已排空，
但旧oracle要求observe只要线程数>1就必须JIT，因零正文而停止。日志有111683次slowpath，
CPU已热但combiner=0，不能断言该会话没有MCS；少线程队头可能没有可代理后继。
修正后plain 2/3线程零正文标为`NO_JIT_LOW_CONTENTION`，不记JIT PASS；20线程及竞争
nested/early仍要求真实正文。先前失败原样保留，独立控制器只继续剩余50配置。

两段分别为**9 OK＋1 NO_JIT失败**、**50 OK**，不是统一60/60通过。
两段各253份源码清单仅README/session/test_direct三个运行器文件不同；生产源码和9项
ELF/客户端哈希完全相同并逐份核验。60份原始测量共3600万次操作均通过业务/worker/排空检查。

有效on/off吞吐变化：c1/c16三线程observe为+60.00%/+48.57%，adaptive为+60.73%/+48.02%；
两线程adaptive为+13.57%/+0.38%，c16 observe为+13.24%。
单线程observe为+51.84%/+50.24%，adaptive为−9.05%/+17.67%。
四线程下降0.85%–4.21%；二十线程observe下降5.83%/5.67%，adaptive下降2.13%/4.00%。
单轮差异不代表稳定分布。

## 热正文与机器码

实际冻结caller中，c1新壳在`0x50d`直接GS读取，冷CALL位于`0x516`，
跳过SP/IP/BP准备；热CALL位于`0x52a`，continuation `0x52f`立即执行payload，无POP。
五寄存器保存由编译器放在函数序言`0x4dd..0x4e5`，返回时恢复；保留壳同样保存。
provider冷入口只有一次初始CAS 0→5，失败传原值到完整慢路径。

八场20线程的发布后jit.S与bin.txt逐指令核对，按热解锁、预算未耗尽路径计数：

| 正文入口到公共wrapper exit，不含公共wrapper/排队 | 历史手工配对壳 | 本轮新壳 | 本轮保留壳 |
| --- | ---: | ---: | ---: |
| c1 | 64 | 28 | 19 |
| c16 | 139 | 103 | 94 |

手工适配的36条指令已消失。剩余增量9条为锁字寻址/读取/比较/分支4条、分支块预算处理4条、
额外正文witness写入1条。热获取还增加内联开关/热度判断，队列采样增加策略判断。
这些额外工作已确认，但未做多线程PMU或分项消融，不能把全部剩余退化归给这9条指令。
八场20线程JIT比例99.7226%–99.8586%，无not-ready/native fallback，JIT/combiner无一致下降。
历史壳仅用于解释静态代码变化，本轮没有运行旧版本或用跨批次时间差计算收益。

## 独立单线程PMU

仅adaptive、c1/c16、两种当前调用壳，各10000000次、各一场，均通过并排空。
perf覆盖measure客户端和worker，排除准备/预热，包含锁外循环及客户端成本。
五事件计数覆盖率均100%；本表不替代上述短批次验收。

| cacheline | 壳/开关 | ns/op | 指令/op | 周期/op | worker CPU/墙钟 | 切换/迁移 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | cold_clobber/on | 27.27 | 72.13 | 75.39 | 99.53% | 3/2 |
| 1 | clobber/off | 40.00 | 153.17 | 109.67 | 99.72% | 3/2 |
| 16 | cold_clobber/on | 32.66 | 117.14 | 92.40 | 99.02% | 3/2 |
| 16 | clobber/off | 44.95 | 198.18 | 128.46 | 99.54% | 3/1 |

长批次显示指令及周期减少，CPU时间接近墙钟；短批次c1 adaptive两壳CPU/墙钟均约84%，
但这不足以解释其反向成绩，频率/宿主调度等贡献未分离。不因长批次较好而改判短批次。

## 相关验证与限制

- 基础2组及冷路由/ABI、原生MCS、paired JIT、hotlock共4组通过；25项热度错误变体被检出。
  初次ABI fixture使用`-mpreferred-stack-boundary=3`，调用用户态libc时SIGSEGV；改为4保持
  16字节栈对齐后原断言通过，生产代码未为此修改。初次5通过/1失败及诊断均保留。
- ABI覆盖双CPU实际GS读取、活跃寄存器、精确SP/IP/BP、开关/代理/热度组合、嵌套及提前解锁；
  wrapper覆盖COMPLETE、入口拒绝和FULL/native续跑。生产native混合MCS fixture完成400000次，
  399911次入队，pin/在途计数归零。运行器修正后21项通过。
- 新壳1/2/3线程12场均零JIT，明确为`NO_JIT_COLD`；两壳4/20线程16场均有实际JIT，
  合计17868307个计时正文。所有会话spin/exec invariant及overflow为0，无匹配内核错误。
- 定向7场共1200000次操作完成并排空：新壳gate关闭119765个JIT正文；delegation关闭0；
  门槛0/三线程33387；nested 194789；early 49934；RCUHT单线程0、四线程131850，哈希完整性正确。
  nested/early/RCUHT竞争正例使用门槛0以确保覆盖热协议。未运行全量或真实中断压力测试。
- normal provider以W=1构建；保留11条既有objtool警告，函数/类型与前版相同，另有Perl locale警告。
  全部构建和模块运行在recovery guest，加载时`mutex_jit=1`但本轮负载仅spin；未修改guest内核。
  最终无worker、daemon、workload或后端残留，source/frame/writer及队列均排空。

## 命令与证据

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 900s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 2 3 4 20 \
  --hotlock-mode observe adaptive --spin-cold-fastpath on off --spin-hot-min-queue 4 \
  --repeats 1 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/cold-clobber-20260922/performance
```

首次失败后的`continue.py`只执行未测50项，保存独立source/plan/records。
`functional-controller.py`记录7场控制及完整命令。PMU使用上述运行器的
`--backends kdlock --threads 1 --hotlock-mode adaptive --iterations 10000000 --pmu`。
单位验证命令为`make -C tests/unit run PY_TESTS='spin/test_spin_cold.py spin/test_spin_nondelegated.py codegen/test_spin_paired_jit.py infrastructure/test_hotlock_sampling.py'`，
只对失败cold组重跑`python3 tests/unit/run.py spin/test_spin_cold.py`；运行器为`python3 bench/tclock_compare/test_direct.py`。

内核`6.1.159-kdclobber2`，Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，
ext4/nokaslr/voluntary，快照`pre_static_boot_20260915`，vCPU0..39固定host CPU0..39。
guest证据：`/root/kdlock-evidence/cold-clobber-20260922/`。
宿主忽略目录保存[分段性能核对](../../.tmp/cold-clobber-20260922/performance-audit.json)、
[JIT机器码核对](../../.tmp/cold-clobber-20260922/jit-code-audit.json)、
[源码/ELF核对](../../.tmp/cold-clobber-20260922/source-code-audit.json)、
[PMU汇总](../../.tmp/cold-clobber-20260922/pmu/pmu-summary.json)和
[完整归档](../../.tmp/cold-clobber-20260922.tar.gz)。归档SHA256：
`152b3e9a0ddb4b4751ef9581bc213f1385fdf4829b477dc5319ff3aa99768e45`。
