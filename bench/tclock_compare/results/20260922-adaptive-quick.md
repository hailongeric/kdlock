# 2026-09-22：默认双准入模式与 adaptive 快速三方结果

运行器默认同时测 KD observe、KD adaptive；Linux/TCLock 每配置各测一次，供两种
KD 模式比较。KD 会话目录带模式后缀，汇总按模式分组，加载后核对实际模块参数。
`--hotlock-mode adaptive` 或 `observe` 仍可单独选择。默认 cacheline 40 场、RCUHT
20 场，每配置一轮；没有修改锁实现、阈值或负载。

本轮按快速结果要求，只测 adaptive：**1/16 cacheline × 1/4/20线程 × 三后端 ×
一轮，共18场，18/18通过，1500万次计时操作完成并排空。** 四场竞争KD均有实际JIT；
两场单线程为NO_JIT。observe 双模式矩阵规划与汇总通过单元检查，本轮未重跑observe性能。

## 三方结果

plain/cacheline、adaptive、spin_delegate=on；每线程100000次，每配置仅第0轮。
单CPU48000次预热与JIT准备不计时。单位为 **Mops/s / ns/op**，包含临界区、
锁外四组乘加和循环，是完整操作的摊销时间。每格对应一个实际完成且已排空的会话。

| cacheline | 线程 | Linux | TCLock | KD adaptive | KD/Linux | KD/TCLock |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 16.723 / 59.80 | 14.727 / 67.90 | 8.445 / 118.41 | 0.505× | 0.573× |
| 1 | 4 | 3.648 / 274.14 | 3.427 / 291.83 | 1.838 / 544.08 | 0.504× | 0.536× |
| 1 | 20 | 4.000 / 249.98 | 4.966 / 201.37 | 5.048 / 198.09 | 1.262× | 1.017× |
| 16 | 1 | 12.947 / 77.24 | 11.850 / 84.39 | 6.940 / 144.10 | 0.536× | 0.586× |
| 16 | 4 | 2.038 / 490.79 | 2.229 / 448.57 | 1.553 / 643.83 | 0.762× | 0.697× |
| 16 | 20 | 5.015 / 199.41 | 3.308 / 302.31 | 4.818 / 207.56 | 0.961× | 1.456× |

单线程和4线程KD低于两组对照。20线程KD在c1高于两组对照，c16高于TCLock、低于
Linux。本轮只有一次测量，不能据此确定稳定差异，也不能将历史observe成绩当作同期对照。

| cacheline | 线程 | 计时区间实际JIT正文 | 占计时操作比例 | JIT验收 |
| --- | ---: | ---: | ---: | --- |
| 1 | 1 | 0 | 0% | NO_JIT |
| 1 | 4 | 233781 | 58.44525% | PASS |
| 1 | 20 | 1995415 | 99.77075% | PASS |
| 16 | 1 | 0 | 0% | NO_JIT |
| 16 | 4 | 250382 | 62.59550% | PASS |
| 16 | 20 | 1995997 | 99.79985% | PASS |

## 验证与环境

- 基于`4081b09`的工作区，只改运行器、相关测试和文档。运行前329个跟踪文件与guest
  SHA256一致；已有结果文档的用户改动保留，完整运行前差异随证据归档。
- guest运行器单元12/12通过，覆盖默认双模式、单模式选择、独立汇总、无效样本排除和
  重复轮次顺序。CLI dry-run确认cacheline40场、RCUHT20场；功能模式20场由单元检查。
- recovery guest `6.1.159-kdclobber2`，Build ID
  `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`，ext4、nokaslr、voluntary；
  运行器通过内核身份和固定Python依赖检查。未修改或重建guest内核。
- monitor确认`pre_static_boot_20260915`快照。40个vCPU一对一绑定宿主CPU0..39，
  前20个同物理插槽；运行后映射未变。guest worker按对应CPU编号绑定。
- 运行器构建normal provider、daemon、三方workload及TCLock后端；构建日志保留
  Perl locale告警。provider默认mutex_jit=1，实际负载仅spin，不构成mutex验证。
- 18场业务数据、IRQ/preempt、模式身份、内核日志和排空检查通过；4/4竞争KD有实际JIT。
  TCLock代理次数保持UNMEASURED。最终无worker、daemon、workload或provider残留。
- 运行后249份冻结输入与8份二进制哈希一致。未追加重复性能、完整双模式矩阵、
  RCUHT、nested/early、SELFTEST或PMU；结果文档在本轮完成后更新。

## 命令与证据

```sh
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 \
  LC_ALL=C timeout --kill-after=10s 900s python3 bench/tclock_compare/run.py \
  --backends native tclock kdlock --cachelines 1 16 --threads 1 4 20 \
  --repeats 1 --iterations 100000 --scenario plain --hotlock-mode adaptive \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/adaptive-quick-20260922T110215Z/adaptive
```

guest完整证据目录：`/root/kdlock-evidence/adaptive-quick-20260922T110215Z/`。
固定venv、内外层timeout、完整命令及退出码见其中`validation/`。

- [三方汇总](../../.tmp/adaptive-quick-20260922T110215Z/adaptive/summary.csv)
- [原始会话](../../.tmp/adaptive-quick-20260922T110215Z/adaptive/records.json)
- [运行后审计](../../.tmp/adaptive-quick-20260922T110215Z/post-run-audit.json)
- [完整归档](../../.tmp/adaptive-quick-20260922T110215Z.tar.gz)

原始证据在忽略目录，新checkout不自带。归档SHA256：
`466f6aaefa4d74f70dfd5c057fe841852c60bb9dac03c844f0ff3c32f14d14ea`。
