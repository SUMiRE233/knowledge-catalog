# 教学周期知识目录生成器

这是一个 Python 3.11+、FastAPI 驱动的独立后端。它接收课程大纲、教材范围或教学计划，
以页面图片为多模态模型的主要输入，产出当前教学周期使用的轻量知识树。

它不是知识图谱、题库、题型/错因/能力体系、学生画像或跨地区权威知识库。每次上传都会生成
新树，ID 只在本树内有效。

代码与仓库内明确标记的公开合成数据采用 [MIT License](LICENSE)。仓库地址：
`git@github.com:SUMiRE233/knowledge-catalog.git`。私有课程材料、真实模型输出、密钥和运行缓存
不属于许可发布内容，并由 `.gitignore` 与仓库卫生检查阻止进入版本控制。

面向维护者的文档和后续 Git 提交说明统一使用中文。提交信息遵循 Conventional Commits，
例如 `docs: 将审计与评测说明改为中文`。已发布的历史提交不为语言统一而重写。

## 当前发布与完成状态

当前生成器版本为 `0.3.0`，稳定目录发布仍为
`releases/v1.0.0/KT_MICSS_junior.json`。项目已完成公开 fixture、课程负责人审批的 41 条
公开合成金标准、真实 badcase 追溯、稳定知识树 schema、版本化 manifest 和下游兼容说明。
合成金标准状态为 `human_approved_synthetic_gold`；它闭合工程复现和数据契约验收，但不代表
真实多模态模型在未见课程 PDF 上的泛化准确率。
当前配置的 Qwen 已通过同一生产 Service 对公开合成 PDF 的 live-gold 验证：41/41 断言、
33/33 节点路径、8/8 scope、唯一根、0 warning、0 error。该结果是已知 synthetic fixture
上的单次 temperature-zero 运行，不作为未见真实 PDF 泛化证据。

| 状态 | 内容 |
|---|---|
| 已实现 | PDF/PNG/JPEG/WEBP 接入；PDF 视觉优先渲染；Vanguard 布局侦察；动态业务提示词；多图模型调用；分批与合并；协议解析；range 筛选；OutputGuard；异步 API；公开合成 fixture；版本化发布 |
| 部分实现 | 扫描 PDF 和普通图片可进入视觉链路，但真实设备、旋转、倾斜和模糊组合覆盖有限；真实模型泛化仍缺少未见 PDF 盲测 |
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
Vanguard、协议解析、range、OutputGuard 和 artifact 发布。当前回归评测为 41/41、
0 warning、0 error。
该数字只证明流水线与契约可复现，不代表真实多模态模型准确率。数据与方法见
`fixtures/public/README.md` 和 `evaluation/README.md`。

### 版本化目录与下游契约

- 树 schema：`schemas/knowledge_tree.schema.json`，版本 `1.0.0`；
- 布局 schema：`schemas/layout_profile.schema.json`，版本 `1.0`；
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

负责人已批准的 41 条公开合成金标准包含 33 条层级/节点断言和 8 条 scope 精确断言。真实文档运行中发现的
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

`HTTP 上传 → 任务 → InputAdapter → 页面图片 → Vanguard 布局侦察 → LayoutProfile 校验 →
PromptComposer → 多模态模型分批抽取 → 可选文本合并调用 → FormattedTextParser →
range 树筛选 → OutputGuard → artifacts`

Vanguard 先识别节点层级、scope 来源、排除区域和跨页关系，只返回严格 JSON，不抽取知识点。
系统校验并规范化 LayoutProfile，再将它嵌入固定通用提示词生成实际 BusinessPrompt。
多批 Profile 会经过合并和一次纯文本审校；知识树合并后也进行一次只允许修正协议、范围挂载
和 scope 归属的纯文本审校，随后仍由 Parser 与 OutputGuard 独立裁决。
长文档继续按 `LLM_MAX_IMAGES_PER_REQUEST` 顺序分批；Vanguard 分批结果只在同一 PDF 内合并，
知识抽取批次包含真实页码和上一批路径摘要。合并提示禁止创造、改写、扩写或删除明确课程内容。

一次 API 请求必须只上传一份逻辑上应当被统合的 PDF，并且只发布一个知识目录资产。上游负责
确保这份 PDF 的所有页面属于同一课程目录；不要把互不相关、原本应独立发布的课程材料拼成一个
请求。分批只是同一 PDF 的内部传输方式：子请求可以重复同一个总根或暂时看不到总标题，最终
合并审校后必须且只能有一个 `LEVEL 1`。年级、册别和学期属于该根下的范围节点。页面没有明确
总身份时仍生成唯一技术根 `未知学科`；Vanguard 无法解决的根身份冲突会阻止发布。

模型必须只输出：

```text
BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 整份 PDF 的唯一总根
LEVEL 2 | 年级、册别或学期范围
LEVEL 3 | 大章名称
LEVEL 4 | 子节点名称
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

### 谨慎的文档身份判定

文档身份采用页面证据优先策略，不会根据公式、章节名称、上传文件名或学科常识推断：

1. 优先匹配模型明确输出的年级、学期或册别节点；
2. 模型没有具体年级节点时，只在 PDF 文本层或 OCR 辅助文本中存在唯一、明确年级证据时使用；
3. 只有“初中/高中”学段证据或同学段模型节点时，降级为学段前缀匹配，不推断具体年级；
4. 完全没有可作为一级根节点的身份信息时，固定输出技术根节点“未知学科”；
5. 请求具体 range 但只能得到“未知学科”时返回 `RANGE_NOT_FOUND`，不得猜测年级。

非精确降级会在 `validation_report.json` 中写入 `RANGE_FALLBACK_APPLIED`，并在
`run_report.json` 中记录 `selected_range`、`range_resolution_method` 和 `range_evidence`。
模型提示明确禁止在无证据时生成“初一上”或其他具体年级。“未知学科”是约定的技术容器，
不参与 PDF 文本层来源匹配。
目录页简称和详细页全称通过现有配置化 range 别名规范化，例如“初一上”统一为“初一上册”；
这只处理身份边界名称，不参与课程内容、知识点或父子关系判断。

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
  `document_profile`（兼容字段，仍接受 `general` 或 `primary_dskp_sjkc`；两者均执行 Vanguard），返回 202
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

脚本仍传入兼容值 `primary_dskp_sjkc`，但布局、层级、scope 来源和排除区域均由当前 PDF
的 Vanguard 结果决定，不再切换到一套静态课程模板提示词。

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

公开 artifact 包括原有知识树、目录、模型输出、验证/运行报告和准备文档，并新增
`vanguard_output.txt`、`layout_profile.json`、`business_prompt.txt`，用于审计实际布局判断与
提示词组合。服务器路径不会返回，页面图片默认不通过公共 API 暴露。
文件位于 `runtime/jobs/{job_id}/output/`。

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
