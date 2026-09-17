from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.config import Settings
from app.layout_profile import LayoutProfile, parse_layout_profile
from app.llm.batching import batches
from app.llm.client import MultimodalModelClient
from app.models import ModelAnalysisRequest, PreparedDocument, ServiceError

VANGUARD_SCHEMA_INSTRUCTION = """返回且只返回一个 JSON 对象，严格使用以下结构：
{
  "schema_version": "1.0",
  "source_page_count": 整份PDF总页数,
  "languages": ["页面语言"],
  "document_identity": {
    "root_labels": ["整份PDF唯一的目录总根名称；未知时为空数组"],
    "subject": "明确学科或null",
    "education_stage": "明确学段或null",
    "grade_labels": ["明确年级"],
    "volume_labels": ["明确册别"],
    "evidence_pages": [证据页码]
  },
  "range_labels": [{
    "label": "页面原文中的完整年级/册别/学期边界",
    "evidence_pages": [证据页码]
  }],
  "layouts": [{
    "layout_id": "layout_1",
    "page_ranges": [{"start": 1, "end": 1}],
    "layout_kind": "table|list|hierarchy|mixed|other",
    "node_levels": [{
      "level": 1,
      "role_name": "原文结构角色",
      "document_label": "原文表头或null",
      "visual_cues": ["位置、缩进、字号或单元格关系"]
    }],
    "scope_sources": [{
      "document_label": "原文表头或null",
      "attaches_to_level": 1,
      "visual_cues": ["与节点的视觉对应关系"]
    }],
    "excluded_regions": [{
      "document_label": "原文标签",
      "reason": "不属于课程知识目录的原因"
    }],
    "continuation_rules": [{
      "kind": "一个允许的延续规则代码",
      "description": "页面可见的延续证据"
    }]
  }],
  "document_exclusions": [{"label": "排除内容", "page_numbers": [1]}],
  "unresolved": [{
    "code": "一个允许的未解决问题代码",
    "page_numbers": [1],
    "description": "无法确定的原因"
  }]
}

continuation_rules.kind 只允许：merged_cell_continues、blank_cell_inherits_previous、
page_break_continues、repeated_header、section_header_resets、parallel_items、
other_visual_relation。
unresolved.code 只允许：CONTENT_REGION_NOT_FOUND、NODE_HIERARCHY_UNCLEAR、
REGION_ROLE_CONFLICT、CONTINUATION_CONFLICT、PAGE_UNREADABLE、
EXPLICIT_RANGE_UNCLEAR、SCOPE_SOURCE_UNCLEAR、EXCLUSION_LABEL_UNCLEAR、
MINOR_VISUAL_CUE_UNCLEAR。
另允许 ROOT_IDENTITY_CONFLICT，表示不同批次出现互不兼容且无法由页面证据统合的总根。

不得输出 Markdown 代码围栏、解释或知识树。不得增加未定义字段。"""


def vanguard_instruction(total_pages: int, page_numbers: list[int]) -> str:
    return f"""你是课程文档的 Vanguard 布局侦察器。当前整份 PDF 共 {total_pages} 页，
本次只观察真实页码 {page_numbers}。识别这些页面应当如何被后续知识目录抽取器阅读。

只识别视觉结构，不抽取具体知识点：
- 识别页面版式、节点层级、scope 来源、必须排除的区域和跨页延续关系。
- node_levels 表示 root_labels 之下的相对层级，必须从 1 连续编号。
- 一次请求中的全部页面属于同一份 PDF、同一个待发布知识目录资产。root_labels 最多一个，
  只能复制页面明确出现、能够统合整份 PDF 的总根名称。
- 年级、册别或学期不是多个总根。页面明确出现的完整年级、册别或学期名称必须逐项写入
  range_labels，例如“初一上册”，不得拆成“初一”和“上册”后让下游拼接。
- range_labels 只复制页面完整原文并记录各自证据页；没有明确文字时使用空数组。
- 不得根据公式、章节名称、文件名或学科常识推断学科、学段、年级或册别。
- 如果页面没有明确总根，root_labels、grade_labels、volume_labels 使用空数组，其他身份字段可为 null。
- 学习目标、表现标准、教学建议、人文要求等非课程知识内容应进入排除区域。
- scope_sources 只能描述课程内容原文或其具体内涵。学习目标、教学目标、表现标准、
  “学生必须能”和能力要求永远不能成为 scope_sources，即使它们与课程内容按行对齐。
- 不要因为名称类似题型而排除页面明确列出的课程内容。
- page_ranges 只覆盖本次观察的真实页码，不得包含未提交的页。
- 同一页只属于一个 layout；混合页面使用 layout_kind=mixed。
- 封面或完全不含课程知识区域的页面可以使用空 node_levels，并在 excluded_regions 中说明；
  不得为了满足格式而虚构节点层级。
- 当前子请求只看到部分页面时，可以返回一个有直接页面证据的总根或空 root_labels；不得把
  当前批次局部出现的册别、年级或章节冒充整份 PDF 的多个总根。最终唯一根由合并审校确定。

{VANGUARD_SCHEMA_INSTRUCTION}"""


VANGUARD_MERGE_PROMPT = f"""你是 LayoutProfile 合并器。输入是同一份 PDF 不同连续页批次的
Vanguard JSON。将它们合并为整份 PDF 唯一的 LayoutProfile。

允许：合并完全相同的布局、保留真实版式变体、合并页码范围、汇总排除项和 unresolved。
禁止：抽取知识点、改变区域语义以强行统一、补充不存在的年级或学科、删除冲突。
有冲突时必须写入 unresolved；不要猜测。
所有输入都来自同一份 PDF、同一个待发布资产。最终 root_labels 必须恰好为一个有页面证据的
总根，或在整份 PDF 完全没有明确身份时为空数组；绝不能保留多个根。不同批次重复的同名总根
合并为一个；局部年级、册别和学期移入 range_labels。若不同批次根身份无法可靠统合，使用
ROOT_IDENTITY_CONFLICT，不得发布多根结果。
最终 layout_id 必须全局唯一，page_ranges 必须覆盖输入各批次的全部真实页码且不得重叠。
最终 scope_sources 不得包含学习目标、教学目标、表现标准、“学生必须能”或能力要求；
这些区域必须进入 excluded_regions 或 document_exclusions。
最终 range_labels 必须按页面顺序保留所有批次明确看到的完整年级、册别或学期边界，
不得拆词、拼接、推断或因为合并布局而丢失。
若目录页简称与详细页完整名称由页面顺序和原文明确指向同一范围，例如“初一上”与
“初一上册”，只保留详细页的完整原文名称，并合并证据页；不得同时输出两个范围节点。
局部批次仅因续页没有重复显示总标题、年级或册别而产生的 unresolved，在其他批次已有
明确身份和延续证据时应当消解并移除。CONTENT_REGION_NOT_FOUND 只用于整份合并结果中
确实无法找到课程节点区域的页面，不得用于“页面有课程内容但没有重复身份表头”的情况。

{VANGUARD_SCHEMA_INSTRUCTION}"""


VANGUARD_REVIEW_PROMPT = f"""你是 LayoutProfile 最终审校器。输入第一个对象是已合并的
LayoutProfile，后续对象是同一 PDF 的原始分批 Profile。只纠正合并结果，不抽取知识点。

逐项审校：
- page_ranges 无重叠地覆盖整份 PDF；layout_id 全局唯一。
- root_labels 使用页面明确出现的总根，不根据课程内容或文件名推断。
- 整份 PDF 是一个待发布资产。最终 root_labels 只能包含一个总根；重复同名根合并，年级、
  册别和学期归入 range_labels。无法用页面证据解决的多根冲突标记 ROOT_IDENTITY_CONFLICT。
- range_labels 按页面顺序覆盖全部明确年级、册别或学期边界。
- 同一范围同时存在目录简称和详细页完整名称时，只保留详细页完整原文名称，合并证据页。
- 续页未重复身份表头时，使用已确认的前页延续关系；不得仅因此保留
  CONTENT_REGION_NOT_FOUND 或 EXPLICIT_RANGE_UNCLEAR。
- 学习目标、教学目标、表现标准、“学生必须能”和能力要求不得出现在 scope_sources。
- 只有整份证据仍无法解决的结构冲突才能保留 unresolved，不得保留已经被其他批次解决的问题。
- 不改变已确认的节点区域、scope 区域、排除区域和页面顺序。

{VANGUARD_SCHEMA_INSTRUCTION}"""


class VanguardAnalyzer:
    def __init__(self, client: MultimodalModelClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def inspect(
        self,
        document: PreparedDocument,
        output_callback: Callable[[int, str], Awaitable[None]] | None = None,
        progress_callback: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> tuple[LayoutProfile, list[str]]:
        page_batches = batches(document.pages, self.settings.llm_max_images_per_request)
        raw_outputs: list[str] = []
        total_pages = len(document.pages)
        for number, pages in enumerate(page_batches, 1):
            page_numbers = [page.page_number for page in pages]
            response = await self.client.analyze(
                ModelAnalysisRequest(
                    operation="vanguard",
                    instruction=vanguard_instruction(total_pages, page_numbers),
                    pages=pages,
                    batch_number=number,
                    total_batches=len(page_batches),
                )
            )
            self._check_response(response.text, response.finish_reason)
            if output_callback:
                await output_callback(number, response.text)
            parse_layout_profile(
                response.text,
                total_pages,
                set(page_numbers),
                require_node_region=False,
            )
            raw_outputs.append(response.text)
            if progress_callback:
                await progress_callback(number, len(page_batches))
        if len(raw_outputs) == 1:
            return parse_layout_profile(raw_outputs[0], total_pages), raw_outputs
        merged = await self.client.analyze(
            ModelAnalysisRequest(
                operation="vanguard_merge",
                instruction=(
                    f"{VANGUARD_MERGE_PROMPT}\n\n整份 PDF 总页数：{total_pages}。"
                    "最终 page_ranges 必须无重叠地覆盖全部真实页码。"
                ),
                merge_inputs=raw_outputs,
            )
        )
        self._check_response(merged.text, merged.finish_reason)
        if output_callback:
            await output_callback(0, merged.text)
        parse_layout_profile(
            merged.text,
            total_pages,
            require_node_region=False,
        )
        reviewed = await self.client.analyze(
            ModelAnalysisRequest(
                operation="vanguard_merge",
                instruction=(
                    f"{VANGUARD_REVIEW_PROMPT}\n\n整份 PDF 总页数：{total_pages}。"
                ),
                merge_inputs=[merged.text, *raw_outputs],
            )
        )
        self._check_response(reviewed.text, reviewed.finish_reason)
        if output_callback:
            await output_callback(-1, reviewed.text)
        return parse_layout_profile(reviewed.text, total_pages), raw_outputs

    @staticmethod
    def _check_response(text: str, finish_reason: str | None) -> None:
        if not text.strip():
            raise ServiceError("EMPTY_MODEL_OUTPUT", "Vanguard 输出为空", status_code=502)
        if finish_reason in {"length", "max_tokens"}:
            raise ServiceError(
                "MODEL_OUTPUT_TRUNCATED", "Vanguard 输出被截断", status_code=502
            )
