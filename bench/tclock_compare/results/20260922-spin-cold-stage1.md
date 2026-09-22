# 2026-09-22：配对冷路径，第一阶段

配对 C 壳和 CPU 冷捷径已实现，旧 API 保留；本阶段尚未精简旧 clobber 包装和
pinned 热度包装。**单线程改善，但 20 线程下降 12.64%–14.43%，超过 5% 门槛，
因此 provider 和 workload 默认仍关闭新路径。** 单轮结果不表示稳定分布；没有补跑重复轮次。

`on` 是 paired 壳 + `spin_cold_fastpath=1`，`off` 是同一源码构建的保留 clobber 壳 + 0。
两组 JIT ABI 都是 clobber-v1。observe 开启捷径后为 CPU 热后固定准入；adaptive
还判断单锁热度。CPU 曾变热后仍依赖后续 MCS 样本降温，没有逐次 TSC。

## 同期性能

recovery guest；plain/cacheline，1/16 cacheline × 1/4/20线程，每线程100000次，
每配置一轮。Linux/TCLock 各一次，KD observe/adaptive 各 on/off 一次，共36场。
准备和单CPU48000次预热不计时；每格为 **Mops/s / 完整操作 ns/op**。

| cacheline | 线程 | Linux | TCLock | observe off | observe on | adaptive off | adaptive on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.927 / 59.08 | 13.697 / 73.01 | 6.951 / 143.85 | 12.883 / 77.62 | 8.186 / 122.16 | 13.215 / 75.67 |
| 1 | 4 | 3.774 / 264.98 | 2.987 / 334.84 | 1.812 / 551.85 | 1.787 / 559.58 | 1.842 / 542.75 | 1.843 / 542.63 |
| 1 | 20 | 4.120 / 242.72 | 5.049 / 198.06 | 5.053 / 197.90 | 4.343 / 230.23 | 5.012 / 199.54 | 4.378 / 228.40 |
| 16 | 1 | 13.152 / 76.04 | 11.707 / 85.42 | 6.251 / 159.97 | 11.713 / 85.37 | 7.293 / 137.11 | 10.606 / 94.29 |
| 16 | 4 | 2.248 / 444.80 | 2.184 / 457.92 | 1.598 / 625.80 | 1.547 / 646.62 | 1.573 / 635.55 | 1.553 / 644.07 |
| 16 | 20 | 2.889 / 346.10 | 3.280 / 304.89 | 4.783 / 209.06 | 4.093 / 244.33 | 4.789 / 208.81 | 4.106 / 243.52 |

c1 单线程 on/off 吞吐提升 observe 85.33%、adaptive 61.44%；c16 分别87.37%、45.42%。
4线程变化为 −3.22% 至 +0.02%，20线程全部超出允许退化。热分支新增的保存/恢复也进入
JIT 正文；机器码可确认这项额外工作，但本阶段没有 PMU/指令归因，不能将全部退化归于它。
后续公共调用精简单独提交、单独测量，不把两阶段成绩合并选优。

## 验证

- 36/36会话完成并排空，30000000次计时操作数据正确；16/16竞争KD有实际JIT，
  共17908700次计时JIT正文。8场KD单线程为NO_JIT。IRQ/preempt、锁字、业务计数、
  退休和内核日志检查均通过。最终没有 worker、daemon 或相关模块残留。
- 基础2项和直接相关8项最终全部通过：冷路由/配对ABI、获取抢占、原生MCS、热度采样、
  clobber准入、native-after-outer、注册/端点、原有clobber wrapper。首次native-after-outer
  fixture缺少u8/u16定义导致编译失败，补齐后3297项检查及4项测试通过，失败日志保留。
  运行器13项通过，验证新壳与旧壳不混合汇总。
- 冷路由生产函数覆盖64种开关、delegation、热度变化和CAS失败组合：获取一次pin/CAS，
  失败传递原值，等待期间升温仍按冷态完成，解锁保留pending/tail，nondelegated归零。
  真实头文件用破坏五个callee-saved寄存器的汇编callee测试跨锁/解锁活跃值、栈及SP/IP/BP。
- 冻结ELF确认冷分支不执行五寄存器组保存，也不计算SP/IP/BP；冷获取一次CAS、无热表/context
  查询，冷解锁只低字节release、计数和unpin。编译器仍为C活跃值保存必要寄存器：
  sc_body_1保留rbx，provider入口因UBSAN及慢分支保留rbx/r12；没有关闭provider UBSAN。
  热continuation为CALL后的POP序列，cookie在其后赋值。
- benchmark provider以W=1、SELFTEST=0构建；日志仅有既有Perl locale告警。
  内核为6.1.159-kdclobber2，Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，
  ext4/nokaslr/voluntary；快照pre_static_boot_20260915，vCPU0..39绑定host CPU0..39。
  未修改、构建或安装guest内核。provider默认mutex_jit=1，本轮只执行spin。
- 本阶段未跑RCUHT、nested/early、长批次PMU；这些留给公共调用精简后的定向验收。

## 命令与证据

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  timeout --kill-after=10s 900s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 4 20 \
  --hotlock-mode observe adaptive --spin-cold-fastpath on off \
  --repeats 1 --iterations 100000 \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/cold-fast-20260922/stage1/performance
```

guest证据 `/root/kdlock-evidence/cold-fast-20260922/stage1/`；宿主忽略归档：
[summary](../../.tmp/cold-fast-20260922/stage1/performance/summary.csv)、
[records](../../.tmp/cold-fast-20260922/stage1/performance/records.json)、
[provider机器码](../../.tmp/cold-fast-20260922/stage1/performance/provider-assembly.txt)、
[完整stage1归档](../../.tmp/cold-fast-20260922/stage1.tar.gz)。
250份冻结source哈希校验通过；构建/翻译/命令/ELF身份均保存在归档。
归档SHA256：`8312bee47b064ad047f28ca313a4473094383dd16ff1d8c50e8212e6176826dd`。
