# 知识树生成 API

> 运行时 `knowledge_tree.json` 遵循 `schemas/knowledge_tree.schema.json`（1.0.0）。
> `run_report.json` 包含 `schema_version`、`generator_version` 和不含服务器路径的
> `generation_source`（文件名、SHA-256、输入类型、页数）。

基础地址示例：`http://127.0.0.1:8000`

当前接口未配置 CORS。浏览器前端建议通过同源反向代理访问，或在后端补充允许的前端域名。

## 交互流程

1. 前端上传文件并获得 `job_id`。
2. 每 1–2 秒查询任务状态。
3. `status=succeeded` 后获取结果。
4. 按需下载 artifact。
5. `status=failed` 时展示 `error.code` 和 `error.message`，停止轮询。

## 健康检查

`GET /health`

成功响应 `200`：

```json
{
  "status": "ok"
}
```

## 创建生成任务

`POST /api/v1/knowledge-trees/jobs`

请求类型：`multipart/form-data`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `file` | File | 是 | - | PDF、PNG、JPEG 或 WEBP |
| `range` | string | 否 | `全部` | 如 `全部`、`初一上册`、`初中` |
| `enhance_images` | boolean | 否 | `true` | 是否做轻量图像增强 |
| `use_ocr_fallback` | boolean | 否 | `false` | OCR 预留开关，当前尚未接入 OCR 引擎 |
| `document_profile` | string | 否 | `general` | 兼容字段；接受 `general` 或 `primary_dskp_sjkc`，两者均执行 Vanguard |

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-trees/jobs \
  -F "file=@课程标准.pdf" \
  -F "range=全部" \
  -F "enhance_images=true" \
  -F "use_ocr_fallback=false" \
  -F "document_profile=general"
```

系统首先通过 Vanguard 从当前 PDF 识别布局、节点层级、scope 来源和排除区域，随后将通过
Schema 校验的 `layout_profile.json` 嵌入通用提示词。`document_profile` 不再选择静态课程模板。

一次请求只允许表达一个逻辑上应当统合的 PDF 知识目录资产。即使系统为模型调用把页面拆成
多个内部子请求，最终结果也必须且只能有一个 `LEVEL 1` 总根；年级、册别和学期放在总根下。
上游不得把互不相关、应分别发布的课程 PDF 预先拼接后作为一次请求上传。多根最终结果返回
`OUTPUT_PROTOCOL_ERROR`，根身份无法由整份页面证据解决时返回 `VANGUARD_LAYOUT_UNRESOLVED`。

成功响应 `202`：

```json
{
  "job_id": "840920ca-05ae-49ec-8017-3cd506a7dda0",
  "status": "pending",
  "status_url": "/api/v1/knowledge-trees/jobs/840920ca-05ae-49ec-8017-3cd506a7dda0",
  "result_url": "/api/v1/knowledge-trees/jobs/840920ca-05ae-49ec-8017-3cd506a7dda0/result"
}
```

## 查询任务状态

`GET /api/v1/knowledge-trees/jobs/{job_id}`

状态值：`pending`、`processing`、`succeeded`、`failed`

阶段值：`upload`、`inspect`、`render`、`preprocess`、`vanguard`、`compose`、`analyze`、
`merge`、`parse`、`validate`、`publish`

处理中响应 `200`：

```json
{
  "job_id": "840920ca-05ae-49ec-8017-3cd506a7dda0",
  "status": "processing",
  "stage": "analyze",
  "progress": 46,
  "created_at": "2026-07-24T17:56:00.473628Z",
  "updated_at": "2026-07-24T17:57:30.000000Z",
  "error": null
}
```

失败响应仍为 `200`，通过业务状态判断：

```json
{
  "job_id": "840920ca-05ae-49ec-8017-3cd506a7dda0",
  "status": "failed",
  "stage": "analyze",
  "progress": 43,
  "created_at": "2026-07-24T17:56:00.473628Z",
  "updated_at": "2026-07-24T17:57:30.000000Z",
  "error": {
    "code": "LLM_TIMEOUT",
    "message": "模型请求超时"
  }
}
```

## 获取任务结果

`GET /api/v1/knowledge-trees/jobs/{job_id}/result`

仅在任务成功后调用。未完成时返回 `409 JOB_NOT_READY`。

成功响应 `200`：

```json
{
  "knowledge_tree": {
    "title": "初中数学课程标准知识目录",
    "selected_range": "全部",
    "children": [
      {
        "id": "1",
        "name": "初中",
        "scope": null,
        "children": [
          {
            "id": "1.1",
            "name": "初一上",
            "scope": null,
            "children": []
          }
        ]
      }
    ]
  },
  "validation_report": {
    "passed": true,
    "error_count": 0,
    "warning_count": 1,
    "issues": [
      {
        "severity": "warning",
        "code": "SOURCE_MATCH_UNCERTAIN",
        "message": "名称或 scope 未能在 PDF 文本层中匹配",
        "node_id": "1.1",
        "page": null
      }
    ]
  },
  "artifacts": [
    "business_prompt.txt",
    "knowledge_catalog.txt",
    "knowledge_tree.json",
    "layout_profile.json",
    "model_output.txt",
    "prepared_document.json",
    "run_report.json",
    "vanguard_output.txt",
    "validation_report.json"
  ]
}
```

知识节点固定只有：

```ts
type KnowledgeNode = {
  id: string;
  name: string;
  scope: string | null;
  children: KnowledgeNode[];
};
```

叶子节点的 `name` 是用于展示和归类的名称，不保留模型输出中的层级编号前缀。
例如 `1.1 完整数与自然数的概念` 发布为 `完整数与自然数的概念`；非叶子节点名称保持原文，
节点路径编号仍由 `id` 字段表达。

如果处理后的 PDF 不包含可由页面证据确认的学科、学段或年级身份，系统使用固定技术根节点
`未知学科`，不会根据文件名或课程内容猜测年级。此时 `range=全部` 可以发布结果；请求具体
范围时返回 `RANGE_NOT_FOUND`。

`warning_count > 0` 不代表任务失败；前端可提示“结果存在需复核项”。`error_count > 0` 的结果不会发布为成功任务。

## 下载 artifact

`GET /api/v1/knowledge-trees/jobs/{job_id}/artifacts/{artifact_name}`

公开白名单：

- `knowledge_tree.json`
- `knowledge_catalog.txt`
- `model_output.txt`
- `validation_report.json`
- `run_report.json`
- `prepared_document.json`
- `vanguard_output.txt`
- `layout_profile.json`
- `business_prompt.txt`

响应为文件流，前端可使用 `Blob` 下载。非白名单名称返回 `404 ARTIFACT_NOT_FOUND`。

## 错误格式

非任务业务错误统一格式：

```json
{
  "error": {
    "code": "INVALID_FILE_TYPE",
    "message": "仅支持 PDF、PNG、JPEG 和 WEBP"
  }
}
```

常见 HTTP 状态：

| HTTP | 错误码示例 | 含义 |
|---:|---|---|
| 400 | `EMPTY_FILE`、`INVALID_PDF`、`INVALID_IMAGE` | 请求文件无效 |
| 404 | `JOB_NOT_FOUND`、`ARTIFACT_NOT_FOUND`、`RANGE_NOT_FOUND` | 资源或请求范围不存在 |
| 409 | `JOB_NOT_READY` | 任务尚未成功 |
| 413 | `FILE_TOO_LARGE` | 文件超过限制 |
| 502 | `LLM_REQUEST_FAILED`、`EMPTY_MODEL_OUTPUT`、`VANGUARD_OUTPUT_INVALID`、`VANGUARD_LAYOUT_UNRESOLVED`、`OUTPUT_PROTOCOL_ERROR` | 模型服务、布局或知识树协议异常 |
| 504 | `LLM_TIMEOUT` | 模型请求超时 |

## 前端轮询示例

```ts
async function waitForJob(baseUrl: string, statusUrl: string) {
  while (true) {
    const response = await fetch(`${baseUrl}${statusUrl}`);
    const job = await response.json();

    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new Error(`${job.error.code}: ${job.error.message}`);

    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}
```
