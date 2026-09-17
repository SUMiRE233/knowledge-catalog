import pytest

from app.models import KnowledgeNode, KnowledgeTree
from scripts.merge_primary_knowledge_trees import merge_trees, validate_merged_tree


def grade_tree(name: str, leaf_name: str) -> KnowledgeTree:
    return KnowledgeTree(
        title=name,
        selected_range="全部",
        children=[
            KnowledgeNode(
                id="1",
                name=name,
                children=[
                    KnowledgeNode(id="1.1", name=leaf_name, scope=f"{name}范围")
                ],
            )
        ],
    )


def test_merge_keeps_grade_boundaries_and_reindexes_globally():
    grades = ("一年级", "二年级", "三年级", "四年级", "五年级", "六年级")
    trees = [grade_tree(grade, "同名知识点") for grade in reversed(grades)]

    merged = merge_trees(trees)
    report = validate_merged_tree(merged, expected_leaves=6)

    assert [node.name for node in merged.children] == list(grades)
    assert [node.id for node in merged.children] == ["1", "2", "3", "4", "5", "6"]
    assert [node.children[0].id for node in merged.children] == [
        "1.1",
        "2.1",
        "3.1",
        "4.1",
        "5.1",
        "6.1",
    ]
    assert report["leaf_count"] == 6


def test_merge_rejects_duplicate_or_missing_grade():
    trees = [grade_tree("一年级", "A") for _ in range(6)]

    with pytest.raises(ValueError, match="重复"):
        merge_trees(trees)
