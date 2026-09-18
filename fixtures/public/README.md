# 公开 fixture

`synthetic_curriculum.pdf` 是完全合成、采用 MIT 许可的课程表。它并非派生自真实课程标准，
也不包含任何私有课程材料。

文件说明：

- `synthetic_curriculum_spec.json`：供人工阅读的事实来源；
- `synthetic_curriculum.pdf`：可复现演示使用的两页视觉输入；
- `expected_model_output.txt`：确定性多模态客户端替身的响应。

重新构建 PDF：

```bash
python scripts/build_public_fixture.py
```

构建器会嵌入中文 TrueType 字体，确保 fixture 可在浏览器和桌面 PDF 阅读器中正常渲染。
如果系统标准位置中没有受支持的字体，请在重新构建前将 `PUBLIC_FIXTURE_FONT` 指向本地 TTF/TTC 文件。

该 fixture 覆盖 PDF 校验、逐页渲染、辅助文本提取、协议解析、范围解析、验证和 artifact 发布。
由于语义响应已经冻结，它不衡量真实模型准确率。

两页内容作为同一个 PDF 上传，因此必须形成一个发布的知识树资产。预期知识树只有一个文档根；
`七年级上册` 和 `七年级下册` 是该根下的范围节点，而不是两个并列根。
