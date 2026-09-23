# 历史验收索引

本页只索引历史冻结版本。当前行为见 [执行流](JIT_EXECUTION.md)及 [DESIGN](DESIGN.md)，
命令与近期验证见 [tests](../tests/README.md)和 [bench](../bench/README.md)。
历史通过项不能拼接为当前全量通过，旧透明hook命令只能用于匹配checkout。

最新组合版本的覆盖见[默认热度分流完整三轮](../bench/tclock_compare/results/20260923-spin-default-heat-full3.md)，
`1eaaf99`/`39b0e7c`的修改、失败候选及比较边界见
[性能调查](../bench/tclock_compare/results/20260923-spin-single-hot-balance.md)。
其他性能阶段统一从[历史索引](../bench/spin_cacheline/results/HISTORY.md)进入。
仍未解决的pinned mutex、并发冷准备以及动态地址/flags/原地覆盖限制见
[TODO](TODO.md#current-checkpoint)。文档整理不修复这些问题，也不构成测试重跑。

## 仍被引用的冻结记录

以下保留现有文档引用的锚点。全部早期记录、原始失败、源码身份和当时命令可从
[整理前完整索引](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md)
或本地Git读取，不再逐行复制未使用的主题入口：

```sh
git show 17f146e52f9f52485b8211addb7dab7195e70452:docs/VALIDATION.md
```

原始归档在忽略目录或guest证据目录，新checkout不自带产物；旧哈希只标识原记录，
不表示本次重新认证所有归档。已删除的是重复索引说明，不是原始证据。

| 主题 | 完整证据说明 |
| --- | --- |
| <a id="mutex-oversubscription-assessment"></a>Mutex Oversubscription Assessment | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-oversubscription-assessment) |
| <a id="context-symbol-matching"></a>Context-Symbol Matching | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#context-symbol-matching) |
| <a id="main-plan-acceptance-audit"></a>Main-Plan Acceptance Audit | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#main-plan-acceptance-audit) |
| <a id="dynamic-pointer-screening-gap"></a>Dynamic Pointer Screening Gap | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#dynamic-pointer-screening-gap) |
| <a id="real-mutex-stack-mutation"></a>Real Mutex Stack Mutation | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#real-mutex-stack-mutation) |
| <a id="mutex-control-stack-check"></a>Mutex Control Stack Check | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-control-stack-check) |
| <a id="source-and-hook-lifetime-review"></a>Source And Hook Lifetime Review | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#source-and-hook-lifetime-review) |
| <a id="native-registration-phase-guard"></a>Native Registration Phase Guard | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-registration-phase-guard) |
| <a id="captured-kernel-baseline"></a>Captured Kernel Baseline | [整理前记录](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#captured-kernel-baseline) |
