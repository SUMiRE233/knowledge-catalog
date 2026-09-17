# 教学周期知识目录生成器

这是一个 Python 3.11+、FastAPI 驱动的独立后端。它接收课程大纲、教材范围或教学计划，
以页面图片为多模态模型的主要输入，产出当前教学周期使用的轻量知识树。

它不是知识图谱、题库、题型/错因/能力体系、学生画像或跨地区权威知识库。每次上传都会生成
新树，ID 只在本树内有效。

## 当前发布与完成状态

当前可审计版本为 `0.2.0`，稳定目录发布为
`releases/v1.0.0/KT_MICSS_junior.json`。项目已完成公开 fixture、40 条金标准、
真实 badcase 追溯、稳定 schema、版本化 manifest 和下游兼容说明，进入维护状态。

| 状态 | 内容 |
|---|---|
| 已实现 | PDF/PNG/JPEG/WEBP 接入；PDF 视觉优先渲染；多图模型调用；分批与合并；协议解析；range 筛选；OutputGuard；异步 API；公开合成 fixture；版本化发布 |
| 部分实现 | 扫描 PDF 和普通图片可进入视觉链路，但真实设备、旋转、倾斜和模糊组合覆盖有限；DSKP profile 只适用于已审核的文档族 |
| 设计中 | OCR 文本降级、持久化 JobRepository、共享对象存储、多实例任务执行 |
| 明确不做 | 通用知识图谱、题目/错因分类、学生画像、相似题检索、attempt-organizer 运行逻辑 |

### 五分钟公开复现

公开复现不需要 API key，也不依赖私有课程材料：

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
python scripts/build_public_fixture.py
python scripts/run_public_demo.py --output-dir public_demo_output
python scripts/evaluate_public_fixture.py
```

演示使用两页完全合成的课程表和确定性模型替身，真实执行 PDF 校验、逐页渲染、文本层提取、
协议解析、range、OutputGuard 和 artifact 发布。当前冻结评测为 40/40、0 warning、0 error。
该数字只证明流水线与契约可复现，不代表真实多模态模型准确率。数据与方法见
`fixtures/public/README.md` 和 `evaluation/README.md`。

### 版本化目录与下游契约

- 树 schema：`schemas/knowledge_tree.schema.json`，版本 `1.0.0`；
- 发布 manifest schema：`schemas/release_manifest.schema.json`，版本 `1.0.0`；
- 当前目录：`releases/v1.0.0/KT_MICSS_junior.json`；
- 来源、摘要、计数和限制：`releases/v1.0.0/KT_MICSS_junior.manifest.json`；
- 逻辑名称索引：`releases/catalog-index.json`；
- 集成说明：`docs/ATTEMPT_ORGANIZER_INTEGRATION.md`。

外部请求的规范形式是：

```json
{"knowledge_tree_file": "KT_MICSS_junior"}
```

接收层可内部解析为 `KT_MICSS_junior.json`；带 `.json` 的值只保留为兼容输入。
节点 ID 仅保证在固定目录版本内有效，升级目录版本时必须重新校验。

### 评测、badcase 与来源边界

40 条公开金标准包含 32 条层级/节点断言和 8 条 scope 精确断言。真实文档运行中发现的
年级无证据默认、学习目标 schema 劣化、高中切片缺失分配页和 DSKP 跨批层级漂移，均记录在
`docs/BADCASES.md`，并追溯到规则、提示词、schema 或人工发布边界。

私有课程 PDF、真实密钥、运行缓存和真实模型原始输出均不进入仓库。发布 manifest 只保存
来源标题、SHA-256、生成方法和 `included=false`，以支持审计而不分发源材料。

## 设计边界与视觉优先

原则是：**AI understands. Code prepares, parses, validates and publishes.**

模型读取布局、字号、位置、表格列、合并单元格、缩进和跨页关系，并决定课程语义层级。
程序只接收文件、渲染/轻量增强页面、调用模型、解析限定协议、检查风险和发布 artifact。
业务代码没有课程章节正则解析器、课程状态机或关闭 LLM 时的规则知识树 fallback。

标准 PDF 也先逐页渲染为 PNG，再把图片交给模型。文本层仅作为看不清时的辅助、来源风险
检查与人工追溯；若先压平成文本，会丢失决定结构的视觉信息。扫描 PDF 同样逐页渲染，可做
方向纠正、自动对比度与轻度锐化。PNG/JPEG/WEBP 保留原上传文件并生成规范化页面 PNG。
OCR 仅是未来/显式配置的文本降级位置，第一版不内置 OCR 引擎，也绝不把 OCR 当语义解析器。

## 流程

`HTTP 上传 → 任务 → InputAdapter → 页面图片 → 多模态模型分批分析 → 可选文本合并调用 →
FormattedTextParser → range 树筛选 → OutputGuard → artifacts`

长文档按 `LLM_MAX_IMAGES_PER_REQUEST` 顺序分批。每批包含真实页码、批次信息、上一批路径摘要；
多批时模型以各批协议文本进行最终合并，不再上传所有图片。合并提示禁止创造、改写、扩写或
删除明确课程内容。

模型必须只输出：

```text
BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 节点名称
LEVEL 2 | 大章名称
LEVEL 3 | 子节点名称
SCOPE | 课程内容原文
UNRESOLVED | 3 | 无法可靠识别的原因
END_KNOWLEDGE_TREE
```

解析器只识别 BEGIN/END、LEVEL、SCOPE、UNRESOLVED，按 LEVEL 建父子关系并分配路径 ID。
学习目标不进入知识树协议，程序也不会把它们创建为知识节点。
发布前会去掉所有展示节点名称开头的课程编号（如 `1.0`、`1.1`、`1.1.1.`），并去掉
`scope` 各学习标准开头的来源编号；数字范围、计量数值和 `(i)/(ii)` 等正文信息保持不变。
树内路径只由自动分配的 `id` 表达。连续 scope 条目的 `。；` 会统一为 `；`。
它不猜章节、不拆 scope、不合并相似节点、不删除“应用问题”等内容。range 在完整目录生成后
按模型节点、文本/OCR 年级证据、学段前缀和安全默认值依次解析。

### 谨慎的年级与学段判定

年级分配采用证据优先策略，不会默认归入“初一上”：

1. 优先匹配模型明确输出的年级、学期或册别节点；
2. 模型没有具体年级节点时，只在 PDF 文本层或 OCR 辅助文本中存在唯一、明确年级证据时使用；
3. 只有“初中/高中”学段证据或同学段模型节点时，降级为学段前缀匹配，不推断具体年级；
4. 完全没有证据时使用 `DEFAULT_GRADE_RANGE`，默认值为“全部”。

非精确降级会在 `validation_report.json` 中写入 `RANGE_FALLBACK_APPLIED`，并在
`run_report.json` 中记录 `selected_range`、`range_resolution_method` 和 `range_evidence`。
模型提示明确禁止在无证据时生成“初一上”或其他具体年级。小学 DSKP 标题由模型识别出的
年级生成稳定名称，不使用上传文件的副本编号或版本后缀。

OutputGuard 检查空树/空名、重复 ID/路径、协议未知行、孤立或重复 scope/objective、禁止字段、名称与
scope/objective 长度、解释文本、Markdown/JSON、自我说明、文本层来源匹配、UNRESOLVED、协议边界、
空输出与截断。来源匹配会先统一 Unicode、空格和标点，并逐条核对 scope，减少版式差异造成的
误报警；风险检查仍只报警，不重新理解课程。

## 安装与启动

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS 激活命令为 `source .venv/bin/activate`。在 `.env` 中至少设置
`LLM_API_KEY`、`LLM_MODEL`，并按供应商设置 `LLM_BASE_URL`。接口使用 OpenAI-compatible
`POST /chat/completions`，通过 `MultimodalModelClient` 可替换为其他供应商适配器。
未配置模型时生产任务明确失败为 `LLM_NOT_CONFIGURED`。

全部配置见 `.env.example`：应用/监听地址、runtime、上传限制、图片 MIME、PDF DPI、增强/OCR
开关、模型 base URL/名称/超时/重试/单批图片数、页面保存和日志级别均可配置。密钥不写入
artifact。

## API

- `GET /health`
- `POST /api/v1/knowledge-trees/jobs`：multipart `file`、`range`（默认“全部”）、
  `enhance_images`（默认 true）、`use_ocr_fallback`（默认 false）、
  `document_profile`（`general` 或 `primary_dskp_sjkc`），返回 202
- `GET /api/v1/knowledge-trees/jobs/{job_id}`
- `GET /api/v1/knowledge-trees/jobs/{job_id}/result`
- `GET /api/v1/knowledge-trees/jobs/{job_id}/artifacts/{artifact_name}`

```bash
curl -F "file=@/path/course.pdf" -F "range=初一上册" \
  http://127.0.0.1:8000/api/v1/knowledge-trees/jobs
python scripts/submit_test_file.py /path/course.pdf --range 初一上册
python scripts/wait_for_job.py --job-id YOUR_JOB_ID
```

马来西亚华文小学数学 DSKP 可使用专用批处理脚本（不在脚本中硬编码文件路径或页码）：

```bash
python scripts/generate_primary_knowledge_trees.py \
  --base-url "http://127.0.0.1:8000" \
  --download-dir "./primary_output" \
  "/path/to/DSKP_Matematik_Tahun_1.pdf" \
  "/path/to/DSKP_Matematik_Tahun_2.pdf"
```

脚本使用 `primary_dskp_sjkc` 文档画像，以“年级 → 学习领域 → 课题 →
内容标准”建树，将对应学习标准放入 `scope`。表现标准、级别诠释、
课题目标、人文与价值观、活动建议、评估和行政内容均排除。

已审核的一至六年级树可以合并为一棵小学树，年级仍是严格边界，不跨年级合并同名节点：

```bash
python scripts/merge_primary_knowledge_trees.py \
  primary_output/KT_DSKP_primary_year1.json \
  primary_output/KT_DSKP_primary_year2.json \
  primary_output/KT_DSKP_primary_year3.json \
  primary_output/KT_DSKP_primary_year4.json \
  primary_output/KT_DSKP_primary_year5.json \
  primary_output/KT_DSKP_primary_year6.json \
  --expected-leaves 221 \
  --output primary_output/KT_MICSS_primary.json
```

下游作答整理请求使用无扩展名逻辑名称：`"knowledge_tree_file": "KT_MICSS_primary"`。
接收端负责解析为内部文件 `KT_MICSS_primary.json`。

公开 artifact 固定为 `knowledge_tree.json`、`knowledge_catalog.txt`、`model_output.txt`、
`validation_report.json`、`run_report.json`、`prepared_document.json`。服务器路径不会返回，
页面图片默认不通过公共 API 暴露。文件位于 `runtime/jobs/{job_id}/output/`。

## 测试与真实验收

```bash
ruff check .
pytest
python scripts/acceptance_test_real_pdf.py \
  --base-url "http://127.0.0.1:8000" \
  --file "/path/to/初中数学课程标准.pdf" \
  --range "初一上册" \
  --download-dir "./acceptance_output"
```

自动测试动态创建文本层 PDF、扫描式 PDF、PNG、损坏/加密 PDF 与空文件，使用 Fake 模型，
无需 API key。真实验收脚本只接受客户端本地路径，通过 multipart 上传，不把 PDF 复制进源码。

## 部署限制

`InMemoryJobRepository` 在进程重启后丢失状态；生产环境应替换为持久化任务仓库。
`LocalFileStorage` 仅适合单机，本机磁盘故障或多实例间不可共享。多实例部署应使用共享对象存储
和持久化 JobRepository，并让负载均衡后的实例访问同一任务与 artifact；本项目刻意不内置
Celery、Redis、数据库、事件总线或工作流引擎。
