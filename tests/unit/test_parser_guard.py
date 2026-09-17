import pytest

from app.models import KnowledgeNode, KnowledgeTree, ServiceError
from app.parsing.formatted_text_parser import FormattedTextParser
from app.publishing import catalog_lines
from app.range_resolution import resolve_range, select_range
from app.validation.output_guard import OutputGuard
from tests.conftest import GOOD_OUTPUT


def test_normal_text_to_json_and_application_problem_preserved():
    result = FormattedTextParser().parse(GOOD_OUTPUT, "目录")
    dumped = result.tree.model_dump()
    assert dumped["children"][0]["children"][0]["children"][1]["name"] == "应用问题"
    assert set(dumped["children"][0]) == {
        "id",
        "name",
        "scope",
        "children",
    }


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("LEVEL 1 | A\nEND_KNOWLEDGE_TREE", "BEGIN"),
        ("BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | A", "END"),
        (
            "BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | A\nLEVEL 3 | B\nEND_KNOWLEDGE_TREE",
            "跳跃",
        ),
    ],
)
def test_serious_protocol_errors(text, fragment):
    with pytest.raises(ServiceError, match=fragment):
        FormattedTextParser().parse(text, "x")


def test_scope_without_node_and_unknown_line_are_warnings():
    text = """BEGIN_KNOWLEDGE_TREE
SCOPE | orphan
这里是解释
LEVEL 1 | A
END_KNOWLEDGE_TREE"""
    result = FormattedTextParser().parse(text, "x")
    assert {issue.code for issue in result.issues} == {
        "SCOPE_WITHOUT_NODE",
        "UNKNOWN_PROTOCOL_LINE",
    }


def test_duplicate_scope_warning():
    text = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | A
SCOPE | one
SCOPE | two
END_KNOWLEDGE_TREE"""
    result = FormattedTextParser().parse(text, "x")
    assert result.tree.children[0].scope == "one"
    assert result.issues[0].code == "DUPLICATE_SCOPE"


def test_all_display_names_drop_hierarchical_number_prefixes():
    text = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 高中数学内容标准
LEVEL 2 | 1.1 有子节点的项目
LEVEL 3 | 1.1.1. 直角坐标系，象限，距离公式
LEVEL 2 | 3D 图形
END_KNOWLEDGE_TREE"""
    parsed = FormattedTextParser().parse(text, "目录").tree
    parent = parsed.children[0].children[0]
    assert parent.name == "有子节点的项目"
    assert parent.children[0].name == "直角坐标系，象限，距离公式"
    assert parsed.children[0].children[1].name == "3D 图形"


def test_scope_drops_item_numbers_and_normalizes_mixed_punctuation():
    text = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 一年级
LEVEL 2 | 1.0 整数
LEVEL 3 | 1.1 数值
SCOPE | 1.1.1 读出数目。；1.1.2 写出数目。
END_KNOWLEDGE_TREE"""

    parsed = FormattedTextParser().parse(text, "目录").tree
    topic = parsed.children[0].children[0]

    assert topic.name == "整数"
    assert topic.children[0].name == "数值"
    assert topic.children[0].scope == "读出数目；写出数目。"


def test_source_match_ignores_spacing_and_punctuation():
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[
            KnowledgeNode(
                id="1",
                name="数值",
                scope="读出数目；写出数目。",
            )
        ],
    )

    report = OutputGuard().validate(
        tree,
        "BEGIN_KNOWLEDGE_TREE\nEND_KNOWLEDGE_TREE",
        "1.1 数 值\n1.1.1 读出数目。\n1.1.2 写出数目。",
        [],
        [],
    )

    assert not any(issue.code == "SOURCE_MATCH_UNCERTAIN" for issue in report.issues)


def test_explanatory_output_warning():
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[KnowledgeNode(id="1", name="A")],
    )
    report = OutputGuard().validate(tree, "以下是\n```json\n{}", "", [], [])
    codes = {issue.code for issue in report.issues}
    assert {"EXPLANATORY_TEXT", "MARKDOWN_FENCE", "JSON_LIKE_OUTPUT"} <= codes


def test_range_filter_and_alias():
    parsed = FormattedTextParser().parse(GOOD_OUTPUT, "x").tree
    selected = select_range(parsed, "初一上")
    assert selected.selected_range == "初一上"
    assert selected.children[0].name == "初一上册"


@pytest.mark.parametrize("model_name", ["初一上", "初一上学期", "七年级上册"])
def test_range_filter_normalizes_model_aliases(model_name):
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[KnowledgeNode(id="1", name=model_name)],
    )
    selected = select_range(tree, "初一上册")
    assert selected.children[0].name == model_name


def test_range_not_found():
    parsed = FormattedTextParser().parse(GOOD_OUTPUT, "x").tree
    resolution = resolve_range(parsed, "初三下册")
    assert resolution.method == "model_stage_prefix"
    assert resolution.tree.selected_range == "初中"
    assert resolution.tree.children[0].name == "初一上册"


def test_unique_source_grade_is_used_when_model_has_no_grade_node():
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[KnowledgeNode(id="1", name="函数")],
    )
    resolution = resolve_range(tree, "高二上册", "高中二年级上册 数学")
    assert resolution.method == "source_exact"
    assert resolution.tree.selected_range == "高二上册"


def test_stage_prefix_is_used_without_specific_grade_evidence():
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[KnowledgeNode(id="1", name="函数")],
    )
    resolution = resolve_range(tree, "高二上册", "高中数学课程")
    assert resolution.method == "source_stage_prefix"
    assert resolution.tree.selected_range == "高中"


def test_no_grade_evidence_uses_safe_default_all():
    tree = KnowledgeTree(
        title="x",
        selected_range="全部",
        children=[KnowledgeNode(id="1", name="函数")],
    )
    resolution = resolve_range(tree, "高二上册", "数学课程")
    assert resolution.method == "configured_default"
    assert resolution.tree.selected_range == "全部"


def test_catalog_format():
    parsed = FormattedTextParser().parse(GOOD_OUTPUT, "x").tree
    lines = catalog_lines(parsed.children)
    assert lines[0] == "1|初一上册"
    assert "1.1.2|初一上册/完整数/应用问题|完整数四则运算的应用问题" in lines


def test_guard_blocks_numbered_child_nodes_swallowed_by_scope():
    parsed = FormattedTextParser().parse(
        """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 数学
LEVEL 2 | 完整数
SCOPE | 1.1 概念 定义；1.2 运算 加减乘除
END_KNOWLEDGE_TREE""",
        "目录",
    )
    report = OutputGuard().validate(parsed.tree, "", "", parsed.issues, [])

    assert report.passed is False
    assert "NUMBERED_NODE_IN_SCOPE" in {issue.code for issue in report.issues}


def test_guard_blocks_scope_on_non_leaf_node():
    parsed = FormattedTextParser().parse(
        """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 数学
SCOPE | 错误挂在父节点的描述
LEVEL 2 | 子节点
END_KNOWLEDGE_TREE""",
        "目录",
    )
    report = OutputGuard().validate(parsed.tree, "", "", parsed.issues, [])

    assert report.passed is False
    assert "NON_LEAF_SCOPE" in {issue.code for issue in report.issues}
