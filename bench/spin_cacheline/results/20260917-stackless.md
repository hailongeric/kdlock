# 2026-09-17：查询优化与 spin 栈改动后的完整对比

**30 个配置、120/120 个会话校验通过并正常排空**。每线程 100,000 次，
线程数 1/4/8/12/16/20，cacheline 数 1/2/4/8/16；每配置两对，
原生与 kdlock 各 2 个有效样本，交替执行顺序。全部使用 guest CPU 0–19，
位于 NUMA 节点 0；未运行 24 线程。

本轮使用提交 `6ef43bf` 的生产实现，包含 hotlock/gate 无锁读取、注册及请求内
查找复用、IRQ-off task 准入、移除 spin 独立 C 栈和无栈等待。
运行前 benchmark 观测补丁因 `exe.c` 上下文变化而无法应用；仅更新了
`bench/spin_cacheline/provider/observation.patch` 的上下文，quiet 日志与正文计数
逻辑未变。该修正随本结果文档提交；运行归档保留补丁的精确内容和哈希。

与 [2026-09-15 的锁外乘加扫描](20260915-post-work.md) 相比，内核 Build ID、
CPU 放置、cacheline 负载源码、每线程迭代数和重复次数保持一致。两组每次
解锁返回后仍执行相同的 4 组局部乘加；吞吐包含这段锁外工作。

## 主要结果

- 多线程 kdlock 最佳吞吐为 **0.544–0.647 Mops/s**；最高值在
  **1 条 cacheline、4 线程**，JIT 占比 **85.59%**。
- 多线程 **kdlock 最佳 / 原生中位数为 0.1659–0.2935**，仍明显慢于原生。
- 与上次同配置的 kdlock 最佳吞吐相比，25 个多线程配置提升
  **40.5%–100.6%**，各配置提升幅度的中位数为 **52.9%**。
  20 线程的五个配置提升约 **52.3%–55.1%**。
- 10 个单线程 kdlock 会话均为 **NO_JIT**；各配置最佳吞吐为原生中位数的
  **81.3%–88.9%**，不能把这些成绩算作代理执行收益。

主指标沿用 **kdlock 最高有效吞吐 / 原生有效吞吐中位数**。以下单位为
所有线程合计的百万次完整临界区/秒（Mops/s）；JIT 占比和 kdlock 吞吐来自
同一个最佳会话。每组仅 2 个样本，比较的是虚拟机中的观测最佳值；没有逐项
消融测量，不能把全部提升归因于某一项优化。4 线程的代理比例也有变化。

| cacheline | 线程 | 原生中位 Mops/s | kdlock 最佳 Mops/s | best/median | 最佳会话 JIT 占比/状态 | 较 9/15 kdlock 最佳 |
| ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | 1 | 11.589 | 9.449 | 0.8153 | 0.00% / NO_JIT | +1.0% |
| 1 | 4 | 3.163 | 0.647 | 0.2046 | 85.59% / JIT | +40.5% |
| 1 | 8 | 3.280 | 0.544 | 0.1659 | 99.29% / JIT | +49.8% |
| 1 | 12 | 3.159 | 0.556 | 0.1760 | 99.83% / JIT | +51.9% |
| 1 | 16 | 3.242 | 0.559 | 0.1726 | 99.76% / JIT | +51.2% |
| 1 | 20 | 3.197 | 0.572 | 0.1789 | 99.87% / JIT | +52.5% |
| 2 | 1 | 10.835 | 9.631 | 0.8889 | 0.00% / NO_JIT | +9.4% |
| 2 | 4 | 2.845 | 0.635 | 0.2233 | 83.75% / JIT | +100.6% |
| 2 | 8 | 2.803 | 0.557 | 0.1988 | 99.70% / JIT | +53.1% |
| 2 | 12 | 2.728 | 0.559 | 0.2049 | 99.65% / JIT | +52.3% |
| 2 | 16 | 2.840 | 0.568 | 0.1999 | 99.72% / JIT | +52.9% |
| 2 | 20 | 2.707 | 0.572 | 0.2112 | 99.84% / JIT | +53.1% |
| 4 | 1 | 11.171 | 9.081 | 0.8129 | 0.00% / NO_JIT | -6.6% |
| 4 | 4 | 2.572 | 0.599 | 0.2329 | 73.12% / JIT | +46.9% |
| 4 | 8 | 2.573 | 0.562 | 0.2182 | 99.33% / JIT | +53.5% |
| 4 | 12 | 2.519 | 0.560 | 0.2224 | 99.83% / JIT | +51.8% |
| 4 | 16 | 2.655 | 0.566 | 0.2134 | 99.80% / JIT | +52.1% |
| 4 | 20 | 2.580 | 0.573 | 0.2222 | 99.83% / JIT | +53.5% |
| 8 | 1 | 10.740 | 9.043 | 0.8420 | 0.00% / NO_JIT | -2.8% |
| 8 | 4 | 2.516 | 0.550 | 0.2185 | 77.67% / JIT | +45.3% |
| 8 | 8 | 2.379 | 0.555 | 0.2334 | 99.50% / JIT | +53.7% |
| 8 | 12 | 2.285 | 0.564 | 0.2467 | 99.82% / JIT | +54.9% |
| 8 | 16 | 2.355 | 0.567 | 0.2407 | 99.76% / JIT | +54.2% |
| 8 | 20 | 2.287 | 0.579 | 0.2531 | 99.87% / JIT | +55.1% |
| 16 | 1 | 9.873 | 8.698 | 0.8810 | 0.00% / NO_JIT | -1.5% |
| 16 | 4 | 1.990 | 0.547 | 0.2751 | 78.97% / JIT | +74.8% |
| 16 | 8 | 1.902 | 0.556 | 0.2925 | 99.28% / JIT | +55.6% |
| 16 | 12 | 1.931 | 0.566 | 0.2932 | 99.84% / JIT | +55.0% |
| 16 | 16 | 1.916 | 0.562 | 0.2935 | 99.78% / JIT | +52.9% |
| 16 | 20 | 1.954 | 0.572 | 0.2927 | 99.85% / JIT | +52.3% |

## 验证与运行条件

共完成 **122,000,000 次临界区操作**，测量期实际 JIT 正文合计
**59,006,188 次**：60 个原生、10 个单线程 NO_JIT、50 个多线程 JIT 会话。
五种 cacheline 规模均有实际 JIT 证据；最长测量批次 **3.526 秒**。
所有会话的数据、绑核、计数和排空检查通过，新增内核日志无 fault/warning。
模块正常 retire/卸载，daemon 与已知调用者均退出。

运行于 `6.1.159-kdstatic2` recovery guest，Build ID
`460d77502af4709a0cca794b322cedc20c2cc478`，`nokaslr`、voluntary 抢占。
宿主 monitor 已确认 `pre_static_boot_20260915` 快照，未重启虚拟机或修改内核。
`watchdog_thresh=10`、`soft_watchdog=1` 和 printk 设置保持不变。
provider 使用 `bench_quiet=1`、`jit_timing=0`，保留默认 `mutex_jit=1`，
实际只执行本 spin 负载，不作为 mutex 功能或性能验收。

运行前两个基础 C 程序、15 项 benchmark 检查及 7 项汇编归档检查通过。
专用 provider 的 `W=1` 构建、工作负载模块及客户端构建通过，保留既有汇编
objtool 警告。首次观测补丁应用失败发生在构建阶段，没有加载失败版本；
归档保留失败日志和修正后的构建/检查日志。未执行全量单元或其他 live 矩阵。

收尾再次核对内核源码/build/live 身份、boot ID、冻结源码和二进制未变。
离线独立复算了全部计数器差值、绑核/聚合、原生中位数和 kdlock 最佳会话，
并校验 **184 个冻结源码文件、4 个二进制、180 个生成物哈希**。
这些文件一致性检查与运行期数据/排空检查分开保存。

## 命令与证据

以下命令在 guest 运行，SSH 外层另加 4000 秒时限：

```sh
cd /root/host_fs/kdlock
export PATH=/tmp/kdlock-gs-venv/bin:$PATH
LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 \
KDLOCK_SNAPSHOT_TAG=pre_static_boot_20260915 timeout 3900s \
  python3 bench/spin_cacheline/run.py \
  --kernel-source /root/linux-6.1.159-kdstatic2 \
  --kernel-baseline /root/kdlock-kernel-baselines/spin-static2-20260915 \
  --cachelines 1 2 4 8 16 --threads 1 4 8 12 16 20 --cpus 0-19 \
  --iterations 100000 --repeats 2 \
  --output /tmp/spin-cacheline-stackless-20260917
```

- 宿主可读的 [汇总 CSV](/tmp/kdlock-spin-bench-host-20260917/evidence/spin-cacheline-stackless-20260917/summary.csv)、
  [逐会话 CSV](/tmp/kdlock-spin-bench-host-20260917/evidence/spin-cacheline-stackless-20260917/raw.csv)、
  [逐对 CSV](/tmp/kdlock-spin-bench-host-20260917/evidence/spin-cacheline-stackless-20260917/pairs.csv)。
- [独立复核与前次对比](/tmp/kdlock-spin-bench-host-20260917/audit.json)、
  [最终环境/排空检查](/tmp/kdlock-spin-bench-host-20260917/evidence/spin-cacheline-stackless-20260917/postflight.json)。
- [五种临界区的汇编索引](../../.tmp/spin_cacheline/spin-cacheline-stackless-20260917-u5o9d2hw/README.md)。
  按临界区去重保留 native/JIT 汇编，来源涵盖 60 个 kdlock 会话。
- guest 原始目录：`/tmp/spin-cacheline-stackless-20260917`；
  构建及检查日志：`/tmp/kdlock-spin-bench-preflight-20260917`。
- 宿主证据目录：`/tmp/kdlock-spin-bench-host-20260917/`，包含宿主提交身份、
  运行时观测补丁、源码哈希、runner 日志与归档。

原始 guest 归档为
[`guest.tar.gz`](/tmp/kdlock-spin-bench-host-20260917/guest.tar.gz)，SHA256：

```text
d4817cd14508fe904a39c7f2f19b4e5af4dbf216d6c4ae49ccc4adc033c5f499
```

归档保留原符号链接；宿主查看副本仅解出普通文件和目录，避免链接到 guest 的
绝对路径。报告在测量及归档完成后补写；冻结的 README 是运行前版本。
