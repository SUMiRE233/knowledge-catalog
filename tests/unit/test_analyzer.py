from pathlib import Path

import pytest

from app.config import Settings
from app.llm.analyzer import DocumentAnalyzer
from app.llm.prompts import (
    merge_instruction_for_profile,
    primary_hierarchy_review_instruction,
)
from app.models import ModelAnalysisResponse, PreparedDocument, PreparedPage
from app.parsing.formatted_text_parser import FormattedTextParser


class SequenceModel:
    def __init__(self, texts: list[str]):
        self.texts = iter(texts)
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        return ModelAnalysisResponse(text=next(self.texts), finish_reason="stop")


@pytest.mark.asyncio
async def test_analyzer_preserves_context_across_empty_batch(tmp_path: Path):
    first = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 四年级
LEVEL 2 | 数与运算
LEVEL 3 | 1.0 100 000 以内的整数
END_KNOWLEDGE_TREE"""
    empty = "BEGIN_KNOWLEDGE_TREE\nEND_KNOWLEDGE_TREE"
    third = """BEGIN_KNOWLEDGE_TREE
LEVEL 4 | 1.1 数值
SCOPE | 1.1.1 读出和写出数目。
END_KNOWLEDGE_TREE"""
    merged = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 四年级
LEVEL 2 | 数与运算
LEVEL 3 | 1.0 100 000 以内的整数
LEVEL 4 | 1.1 数值
SCOPE | 1.1.1 读出和写出数目。
END_KNOWLEDGE_TREE"""
    model = SequenceModel([first, empty, third, merged])
    pages = []
    for page_number in range(1, 4):
        image_path = tmp_path / f"page_{page_number}.png"
        image_path.write_bytes(b"image")
        pages.append(PreparedPage(page_number=page_number, image_path=image_path))
    document = PreparedDocument(
        source_file_name="year4.pdf", input_type="standard_pdf", pages=pages
    )
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        llm_api_key="fake-key",
        llm_model="fake-model",
        llm_max_images_per_request=1,
    )

    await DocumentAnalyzer(model, settings).analyze(document, "primary_dskp_sjkc")

    assert model.requests[2].previous_path_summary == (
        "四年级 / 数与运算 / 1.0 100 000 以内的整数"
    )


@pytest.mark.asyncio
async def test_split_requests_are_consolidated_before_single_root_validation(
    tmp_path: Path,
):
    first = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 初中数学课程标准
LEVEL 2 | 七年级上册
LEVEL 3 | 数与式
END_KNOWLEDGE_TREE"""
    second = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 初中数学课程标准
LEVEL 2 | 七年级下册
LEVEL 3 | 函数
END_KNOWLEDGE_TREE"""
    merged = first + "\n" + second
    reviewed = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 初中数学课程标准
LEVEL 2 | 七年级上册
LEVEL 3 | 数与式
LEVEL 2 | 七年级下册
LEVEL 3 | 函数
END_KNOWLEDGE_TREE"""
    model = SequenceModel([first, second, merged, reviewed])
    pages = []
    for page_number in (1, 2):
        image_path = tmp_path / f"page_{page_number}.png"
        image_path.write_bytes(b"image")
        pages.append(PreparedPage(page_number=page_number, image_path=image_path))
    document = PreparedDocument(
        source_file_name="course.pdf", input_type="standard_pdf", pages=pages
    )
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        llm_api_key="fake-key",
        llm_model="fake-model",
        llm_max_images_per_request=1,
    )

    final_output, batch_outputs = await DocumentAnalyzer(model, settings).analyze(
        document,
        analysis_prompt_override="每个子请求使用同一个总根",
        merge_prompt_override="合并到唯一总根",
        review_prompt_override="最终只能有一个 LEVEL 1",
    )
    parsed = FormattedTextParser().parse(final_output, "测试目录")

    assert batch_outputs == [first, second]
    assert [request.operation for request in model.requests] == [
        "extract",
        "extract",
        "merge",
        "merge",
    ]
    assert [node.name for node in parsed.tree.children] == ["初中数学课程标准"]
    assert [node.name for node in parsed.tree.children[0].children] == [
        "七年级上册",
        "七年级下册",
    ]


def test_path_summary_keeps_missing_parent_level():
    path = {1: "四年级", 2: "测量与几何", 3: "4.0 时间与时刻"}

    summary = DocumentAnalyzer._updated_path_summary(
        """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 四年级
LEVEL 3 | 6.0 空间
END_KNOWLEDGE_TREE""",
        path,
        "",
    )

    assert summary == "四年级 / 测量与几何 / 6.0 空间"


def test_primary_merge_instruction_lists_only_level_2_boundaries():
    outputs = [
        "BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | 四年级\nLEVEL 2 | 测量与几何\nEND_KNOWLEDGE_TREE",
        "BEGIN_KNOWLEDGE_TREE\nLEVEL 2 | 度量衡\nLEVEL 3 | 5.0 度量衡\nEND_KNOWLEDGE_TREE",
        "BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | 四年级\nLEVEL 2 | 联系与代数\nEND_KNOWLEDGE_TREE",
    ]

    instruction = merge_instruction_for_profile("primary_dskp_sjkc", "merge", outputs)

    assert "批次 1: 测量与几何" in instruction
    assert "批次 3: 联系与代数" in instruction
    assert "批次 2: 度量衡" not in instruction


def test_primary_hierarchy_review_rejects_topic_promoted_to_level_2():
    merged = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 四年级
LEVEL 2 | 测量与几何
LEVEL 3 | 4.0 时间与时刻
LEVEL 2 | 度量衡
LEVEL 3 | 5.0 度量衡
END_KNOWLEDGE_TREE"""

    instruction = primary_hierarchy_review_instruction(
        merged, [(29, "测量与几何"), (36, "联系与代数")]
    )

    assert instruction is not None
    assert "测量与几何、联系与代数" in instruction
    assert "误提升的课题名" in instruction
