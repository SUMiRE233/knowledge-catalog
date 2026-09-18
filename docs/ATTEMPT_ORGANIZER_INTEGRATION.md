# attempt-organizer 集成契约

Knowledge Catalog 发布不可变、带版本的 JSON 资产，不实现或调用 attempt-organizer 的运行逻辑。

## 稳定资产

- 逻辑名称：`KT_MICSS_junior`
- 当前目录版本：`1.0.0`
- 知识树：`releases/v1.0.0/KT_MICSS_junior.json`
- Manifest：`releases/v1.0.0/KT_MICSS_junior.manifest.json`
- JSON Schema：`schemas/knowledge_tree.schema.json`（`1.0.0`）

规范的外部请求：

```json
{
  "knowledge_tree_file": "KT_MICSS_junior"
}
```

接收层将逻辑名称解析为 `KT_MICSS_junior.json`。为保持向后兼容，调用方仍可传入
`KT_MICSS_junior.json`，但示例和新集成都必须使用不带扩展名的形式。

## 消费方要求

1. 通过 `releases/catalog-index.json` 解析发布版本，或固定使用 `v1.0.0`；
2. 部署前根据 manifest 校验 artifact 的 SHA-256；
3. 节点 ID 仅在固定的目录版本内视为稳定；
4. 节点只读取 `id`、`name`、`scope` 和 `children`；
5. 不推断缺失 scope、不改变层级，也不跨分支合并同名节点；
6. 只有在校验新 manifest/schema 版本后才能升级，并在下游结果中记录所固定的目录版本。
