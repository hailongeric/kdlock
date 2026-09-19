# Spin benchmark 历史索引（2026-09-15 至 09-17）

这些阶段报告的实现已经被后续版本替代。重复的操作命令与实现说明从当前目录
删除，保留本页的结果、证据身份及固定 Git 版本入口。当前路径见
[执行路径](../EXECUTION_PATHS.md)，当前成绩见
[2026-09-19 三方复测](../../tclock_compare/results/20260919-state-access.md)。

下列结果均为历史记录，**本次文档整理没有重跑实验**。旧扫描通常使用
“kdlock 最佳吞吐 / Linux 中位吞吐”，每臂两次；当前三方对照用五轮中位数。
不同统计口径、caller ABI、源码冻结和准备方式的成绩不能拼接成同环境比较。
原始 `/tmp` 归档在仓库之外，新 checkout 不自带这些文件；哈希是原报告记录，
本次未重新认证全部旧归档。Git 版本保存完整表格、失败记录和运行命令。

所有旧报告可从提交 `2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24` 查看，例如在仓库根目录执行：

```sh
git show 2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24:bench/spin_cacheline/results/20260917-wwjump.md
```

<a id="20260915-post-work"></a>

## 2026-09-15：锁外乘加基线

120 场；增加四组锁外乘加后的完整扫描，不能与此前无锁外计算的成绩直接比较。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260915-post-work.md)。
归档：`/tmp/spin-cacheline-best-post-work-evidence-20260915.tar.gz`。
SHA256：`39710cebd3a72eb287df3cd9f2ee044bce4ad57ca194fdfaac90c64ce69b9340`。

<a id="20260917-stackless"></a>

## 2026-09-17：查询与栈改动

120 场；多线程最佳吞吐 0.544–0.647 Mops/s，仍低于原生。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-stackless.md)。
归档：`/tmp/kdlock-spin-bench-host-20260917/guest.tar.gz`。
SHA256：`d4817cd14508fe904a39c7f2f19b4e5af4dbf216d6c4ae49ccc4adc033c5f499`。

<a id="20260917-frame-fast"></a>

## 2026-09-17：单锁 frame 精简

16 场；20 线程两点最佳吞吐 0.855/0.850 Mops/s；每臂仅两个样本。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-frame-fast.md)。
归档：`/tmp/kdlock-frame-fast-20260917/evidence.tar.gz`。
SHA256：`30029f2d256562e052d1d48738e0b1fe149cf02e51f2ac9e1b62e3650562fc71`。

<a id="20260917-waiter-packet"></a>

## 2026-09-17：waiter 包与 lease

16 场；20 线程两点最佳吞吐 1.029/0.951 Mops/s，4 线程两点下降 2.4%/1.7%。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-waiter-packet.md)。
归档：`/tmp/kdlock-waiter-packet-20260917/evidence.tar.gz`。
SHA256：`3f297ec5b52a09d61553836dcabbb133ed448b0351fc43a1f0abe74ca8623dc5`。

<a id="20260917-tclock-shared"></a>

## 2026-09-17：共享 request

16 场；20 线程两点均约 0.905 Mops/s，未测得整体提速；冻结在恢复 shadow 等待栈之前，尚无锁侧 WWJUMP。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-tclock-shared.md)。
归档：`/tmp/kdlock-tclock-jit-20260917/evidence.tar.gz`。
SHA256：`c668405de0ea788b12c653dea1a3c735cb7510d4a5ec46db1251bbca9efe1ced`。

<a id="20260917-current-spin"></a>

## 2026-09-17：shadow 等待与嵌套状态

120 场；8–20 线程最佳吞吐 0.880–0.940 Mops/s；单锁负载不能验证嵌套优化收益。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-current-spin.md)。
归档：`/tmp/kdlock-spin-current-20260917.NDIlms/evidence.tar.gz`。
SHA256：`f65bc552d854c1b755dfef83a8c0858e63da9c26738940d06152f526dda9980a`。

<a id="20260917-batch"></a>

## 2026-09-17：per-CPU 统计与批内复用

16 场；20 线程两点最佳吞吐 1.299/1.285 Mops/s；三项改动合并测量，无独立归因。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-batch.md)。
归档：`/tmp/kdlock-spin-batch-20260917/evidence.tar.gz`。
SHA256：`c11cb68aaedd98aee13657617e1059633b3874614f0b5a12086df52e8c2457c8`。

<a id="20260917-wwjump"></a>

## 2026-09-17：旧锁侧 WWJUMP

16 场；20 线程两点最佳吞吐 1.550/1.519 Mops/s，实际 WWJUMP 计数为正；当时的汇编 shell/C step 已被统一 C 循环替代。

[原始报告与完整证据索引](https://github.com/hailongeric/kdlock/blob/2b16d6fa20801c1dd7a9c25c3bac5b8d0d046c24/bench/spin_cacheline/results/20260917-wwjump.md)。
归档：`/tmp/kdlock-wwjump-20260917/evidence.tar.gz`。
SHA256：`d753b9c1c4bd0fd79420438d5c44e8486597073578c49b9b234d950e40c01144`。
