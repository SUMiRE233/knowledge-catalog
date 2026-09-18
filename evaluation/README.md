# 评测说明

当前公开回归 fixture 包含 41 条可人工阅读的断言：

- 33 条精确层级/路径断言，其中包括唯一根约束；
- 8 条精确 scope 断言。

执行确定性评测：

```bash
python scripts/evaluate_public_fixture.py
```

上述命令使用确定性模型替身。若要让当前已配置的真实多模态模型通过同一 Service 流水线接受评测，执行：

```bash
python scripts/evaluate_live_public_fixture.py \
  --output-dir tmp/live_public_gold_evaluation
```

真实模型评测器会验证所有冻结文件的哈希，只把原始审查 artifact 保存到被忽略的本地输出目录，
并把可安全提交的聚合报告写入 `results/public_fixture_live_eval.json`。报告包含金标准断言准确率、
精确节点路径的 precision/recall/F1、scope 准确率、多余/缺失路径、唯一根约束和 OutputGuard 结果。
这不是未见真实 PDF 盲测。

2026-09-18 记录的 Qwen 运行通过 41/41 条断言，匹配全部 33 条节点路径和 8 条被检查的 scope，
没有多余或缺失路径，保持唯一根，且 OutputGuard 的 warning 和 error 均为 0。聚合证据已提交；
模型原始 artifact 仍保留在被忽略的本地评测目录中。

这些断言在实现期间编写，并于 2026-09-17 由课程负责人逐项审查和明确批准，状态为
`human_approved_synthetic_gold`。

候选集通过 `gold/public_fixture_gold.manifest.json` 中的 SHA-256 冻结。评测器会在执行前验证
每个冻结文件；fixture、可读规格、确定性语义输出或断言发生漂移时立即失败。逐项审批结果记录在
`PUBLIC_SYNTHETIC_GOLD_REVIEW.md`，审批元数据记录在 manifest 中。

已提交的确定性结果位于 `results/public_fixture_eval.json`。数据集是合成数据，执行次数为 1，
语义执行器是确定性模型替身。因此，41/41 仅证明准备、解析、验证和发布契约可复现，不能表述为
多模态模型在真实课程材料上的准确率。

未来可通过未见真实 PDF 盲测衡量真实模型的泛化能力。这属于独立的成熟度步骤，不是当前合成
金标准所提供的证据。

真实文档的失败模式及回归边界记录在 `docs/BADCASES.md`，仓库不保留对应的私有源 PDF。
