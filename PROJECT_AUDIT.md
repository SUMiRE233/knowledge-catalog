# Knowledge Catalog 项目完成审计

审计日期：2026-09-18

**总体状态：已完成（COMPLETED）**

该状态仅适用于 Knowledge Catalog 仓库及其独立完成标准，不代表整个“学生作答智能系统”已经完成。

## 完成门槛

| 门槛 | 证据 | 结果 |
|---|---|---|
| 公开可复现 | `fixtures/public/`、`scripts/run_public_demo.py` | 通过 |
| 可人工核验的金标准 | `evaluation/gold/public_fixture_gold.jsonl` 中的 41 条断言 | 通过 |
| 负责人批准的合成金标准 | 审批记录与冻结清单，2026-09-17 | 通过 |
| 已记录评测 | `evaluation/results/public_fixture_eval.json` | 41/41，0 个错误 |
| 真实 badcase | `docs/BADCASES.md` 中 7 个可追溯案例 | 通过 |
| 稳定 schema | `schemas/knowledge_tree.schema.json` 1.0.0 | 通过 |
| 版本化发布物 | `releases/v1.0.0/KT_MICSS_junior.json` 及其 manifest | 通过 |
| 下游契约 | `docs/ATTEMPT_ORGANIZER_INTEGRATION.md` | 通过 |
| 仓库卫生 | 已排除私有输入、`.env`、缓存和历史运行输出 | 通过 |
| 开源许可与远程仓库 | MIT；`git@github.com:SUMiRE233/knowledge-catalog.git` | 通过 |
| 自动检查 | Ruff、81 项 pytest、公开演示、发布完整性和仓库卫生审计 | 通过 |
| 真实模型对照已批准金标准 | `evaluation/results/public_fixture_live_eval.json`：Qwen 41/41，知识树精确一致 | 通过 |

## 证据边界

合成评测使用确定性模型替身，验证真实的文件准备、PDF 渲染、Vanguard 契约、解析器、范围解析、
OutputGuard 和发布流程。课程负责人于 2026-09-17 批准全部 41 条合成断言，但该结果不衡量真实模型
在未见真实 PDF 上的语义准确率。2026-09-18，当前配置的 Qwen 模型通过生产 Service 路径完成
41/41 条断言、33/33 条精确节点路径和 8/8 条精确 scope；结果保持唯一根，且没有 Guard warning
或 error。该结果仍只是对已知合成 fixture 的一次 temperature-zero 运行。私有输入和模型原始输出
均未提交。

## 停止决策

实现、确定性复现和真实模型合成数据验证门槛均已满足。真实模型评测期间，已批准金标准保持冻结。
仓库恢复为已完成后的维护状态，并停止继续扩张功能。未见真实 PDF 盲测、OCR、分布式基础设施和
通用知识图谱能力仍属于可选的未来成熟度工作。

## 与完成标准的对应关系

项目总纲第 4.1 节要求具备可解释的文档到目录流水线、公开 fixture、30–50 条可人工核验断言、
可追溯真实 badcase，以及不包含私有课程材料的整洁 Git 历史。对应证据依次位于
`README.md`/`API.md`、`fixtures/public/`、已批准的 41 条合成金标准、`docs/BADCASES.md` 和
`scripts/check_repository_hygiene.py`。所有必需门槛均已通过，仓库现处于维护模式。
