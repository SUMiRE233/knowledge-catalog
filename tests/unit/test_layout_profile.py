import json
from pathlib import Path

import pytest

from app.config import Settings
from app.layout_profile import parse_layout_profile
from app.llm.prompt_composer import compose_business_prompt
from app.llm.vanguard import VanguardAnalyzer
from app.models import PreparedDocument, PreparedPage, ServiceError
from tests.conftest import FakeModel


def profile_value() -> dict:
    return {
        "schema_version": "1.0",
        "source_page_count": 2,
        "languages": ["zh"],
        "document_identity": {
            "root_labels": [],
            "subject": None,
            "education_stage": None,
            "grade_labels": [],
            "volume_labels": [],
            "evidence_pages": [],
        },
        "range_labels": [],
        "layouts": [
            {
                "layout_id": "layout_1",
                "page_ranges": [{"start": 1, "end": 2}],
                "layout_kind": "table",
                "node_levels": [
                    {
                        "level": 1,
                        "role_name": "章",
                        "document_label": "章",
                        "visual_cues": ["第一列"],
                    },
                    {
                        "level": 2,
                        "role_name": "项目",
                        "document_label": "课程内容",
                        "visual_cues": ["第二列"],
                    },
                ],
                "scope_sources": [
                    {
                        "document_label": "具体内涵",
                        "attaches_to_level": 2,
                        "visual_cues": ["第三列"],
                    }
                ],
                "excluded_regions": [
                    {"document_label": "学习目标", "reason": "不属于课程内容"}
                ],
                "continuation_rules": [],
            }
        ],
        "document_exclusions": [],
        "unresolved": [],
    }


def test_unknown_identity_prompt_uses_fixed_non_inferred_root():
    profile = parse_layout_profile(json.dumps(profile_value()), 2)
    prompt = compose_business_prompt(profile)

    assert profile.document_identity.is_unknown
    assert "LEVEL 1 | 未知学科" in prompt.extraction
    assert "不得根据课程内容或文件名推断身份" in prompt.extraction
    assert prompt.sha256 == compose_business_prompt(profile).sha256


def test_explicit_range_labels_are_inserted_without_combining_fragments():
    value = profile_value()
    value["document_identity"]["root_labels"] = ["初中数学课程标准"]
    value["document_identity"]["subject"] = "数学"
    value["document_identity"]["education_stage"] = "初中"
    value["range_labels"] = [
        {"label": "初一上册", "evidence_pages": [1]},
        {"label": "初一下册", "evidence_pages": [2]},
    ]
    profile = parse_layout_profile(json.dumps(value), 2)

    prompt = compose_business_prompt(profile)

    assert "初一上册" in prompt.extraction
    assert "初一下册" in prompt.extraction
    assert "不得拆词、拼接、改写或省略" in prompt.extraction
    assert "允许的 LEVEL 2 范围节点" in prompt.review
    assert "最终协议必须且只能有一个 LEVEL 1" in prompt.extraction
    assert "同一个 LEVEL 1" in prompt.extraction
    assert "唯一允许的一级根节点" in prompt.merge
    assert "最终结果必须且只能出现一次" in prompt.review


def test_multiple_document_roots_are_rejected_even_before_tree_extraction():
    value = profile_value()
    value["document_identity"]["root_labels"] = ["七年级上册", "七年级下册"]

    with pytest.raises(ServiceError) as error:
        parse_layout_profile(json.dumps(value), 2, require_node_region=False)

    assert error.value.code == "VANGUARD_OUTPUT_INVALID"


def test_unresolved_root_identity_conflict_blocks_final_profile():
    value = profile_value()
    value["unresolved"] = [
        {
            "code": "ROOT_IDENTITY_CONFLICT",
            "page_numbers": [1, 2],
            "description": "两个批次给出无法统合的总根",
        }
    ]

    parse_layout_profile(json.dumps(value), 2, require_node_region=False)
    with pytest.raises(ServiceError) as error:
        parse_layout_profile(json.dumps(value), 2)

    assert error.value.code == "VANGUARD_LAYOUT_UNRESOLVED"


def test_configured_range_aliases_are_canonicalized_and_deduplicated():
    value = profile_value()
    value["range_labels"] = [
        {"label": "初一上", "evidence_pages": [1]},
        {"label": "初一上册", "evidence_pages": [2]},
    ]

    profile = parse_layout_profile(json.dumps(value), 2)

    assert [item.model_dump() for item in profile.range_labels] == [
        {"label": "初一上册", "evidence_pages": [1, 2]}
    ]


def test_range_alias_matching_does_not_rewrite_a_single_source_label():
    value = profile_value()
    value["range_labels"] = [
        {"label": "七年级上册", "evidence_pages": [1]},
    ]

    profile = parse_layout_profile(json.dumps(value), 2)

    assert profile.range_labels[0].label == "七年级上册"


def test_single_markdown_fence_around_vanguard_json_is_mechanically_unwrapped():
    raw = "```json\n" + json.dumps(profile_value()) + "\n```"
    profile = parse_layout_profile(raw, 2)
    assert profile.schema_version == "1.0"


def test_explanatory_text_outside_vanguard_json_is_rejected():
    raw = "以下是结果\n```json\n" + json.dumps(profile_value()) + "\n```"
    with pytest.raises(ServiceError) as error:
        parse_layout_profile(raw, 2)
    assert error.value.code == "VANGUARD_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(extra="forbidden"),
        lambda value: value["layouts"][0].update(
            page_ranges=[{"start": 1, "end": 1}]
        ),
        lambda value: value["layouts"][0]["node_levels"][1].update(level=3),
    ],
)
def test_invalid_layout_profile_is_rejected(mutate):
    value = profile_value()
    mutate(value)
    with pytest.raises(ServiceError) as error:
        parse_layout_profile(json.dumps(value), 2)
    assert error.value.code == "VANGUARD_OUTPUT_INVALID"


def test_blocking_unresolved_is_rejected():
    value = profile_value()
    value["unresolved"] = [
        {
            "code": "REGION_ROLE_CONFLICT",
            "page_numbers": [1],
            "description": "同一区域可能是节点或学习目标",
        }
    ]
    with pytest.raises(ServiceError) as error:
        parse_layout_profile(json.dumps(value), 2)
    assert error.value.code == "VANGUARD_LAYOUT_UNRESOLVED"

    partial = parse_layout_profile(
        json.dumps(value), 2, require_node_region=False
    )
    assert partial.blocking_unresolved[0].code == "REGION_ROLE_CONFLICT"


def test_exclusion_only_partial_layout_is_allowed_but_not_as_complete_document():
    value = profile_value()
    value["layouts"][0]["node_levels"] = []
    value["layouts"][0]["scope_sources"] = []
    raw = json.dumps(value)

    partial = parse_layout_profile(raw, 2, require_node_region=False)
    assert partial.layouts[0].node_levels == []

    with pytest.raises(ServiceError) as error:
        parse_layout_profile(raw, 2)
    assert error.value.code == "VANGUARD_OUTPUT_INVALID"


def test_learning_objective_cannot_be_scope_source_in_final_profile():
    value = profile_value()
    value["layouts"][0]["scope_sources"][0]["document_label"] = "学习目标"
    raw = json.dumps(value)

    parse_layout_profile(raw, 2, require_node_region=False)
    with pytest.raises(ServiceError) as error:
        parse_layout_profile(raw, 2)
    assert error.value.code == "VANGUARD_LAYOUT_UNRESOLVED"


@pytest.mark.asyncio
async def test_vanguard_keeps_existing_image_batch_limit(tmp_path: Path):
    pages = []
    for page_number in range(1, 6):
        image = tmp_path / f"page_{page_number}.png"
        image.write_bytes(b"image")
        pages.append(PreparedPage(page_number=page_number, image_path=image))
    document = PreparedDocument(
        source_file_name="course.pdf",
        input_type="standard_pdf",
        pages=pages,
    )
    model = FakeModel()
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        llm_api_key="x",
        llm_model="x",
        llm_max_images_per_request=4,
    )

    profile, raw_batches = await VanguardAnalyzer(model, settings).inspect(document)

    assert len(raw_batches) == 2
    assert [request.operation for request in model.requests] == [
        "vanguard",
        "vanguard",
        "vanguard_merge",
        "vanguard_merge",
    ]
    assert profile.source_page_count == 5
    assert len(profile.layouts) == 2
