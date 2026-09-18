# 版本化发布

`catalog-index.json` 将稳定的逻辑名称映射到最新的不可变版本。每个版本目录均包含下游兼容的
知识树和来源 manifest。

此处不分发源 PDF。manifest 记录源文件的 SHA-256，并明确标识源文件是否包含在发布物中。
目录发布必须从已审查的知识树通过 `scripts/publish_catalog.py` 生成；临时 runtime artifact
不属于正式发布物。
