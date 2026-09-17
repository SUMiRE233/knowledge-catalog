from app.llm.prompts import (
    ANALYSIS_PROMPT,
    MERGE_PROMPT,
    PRIMARY_DSKP_ANALYSIS_PROMPT,
    PRIMARY_DSKP_MERGE_PROMPT,
    prompts_for_profile,
)


def test_prompts_forbid_default_grade_and_flattened_toc():
    assert "不得默认输出“初一上”" in ANALYSIS_PROMPT
    assert "不能写成该册别的 SCOPE" in ANALYSIS_PROMPT
    assert "学段 → 册别/年级 → 章/单元 → 课程内容" in MERGE_PROMPT
    assert "不得把所有册别、章节和课程条目压成同一 LEVEL" in MERGE_PROMPT


def test_prompts_preserve_numbered_three_column_hierarchy():
    assert "1、1.1、1.1.1" in ANALYSIS_PROMPT
    assert "LEVEL 4 | 编号具体内涵" in ANALYSIS_PROMPT
    assert "不得在合并时把最低一级编号条目改成 SCOPE" in MERGE_PROMPT


def test_prompts_exclude_learning_objectives_from_tree_protocol():
    assert "学习目标、题型、错因、能力、解释不得成为节点或 SCOPE" in ANALYSIS_PROMPT
    assert "OBJECTIVE" not in ANALYSIS_PROMPT
    assert "OBJECTIVE" not in MERGE_PROMPT


def test_primary_dskp_profile_maps_columns_and_excludes_non_curriculum_content():
    assert "内容标准”列" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "学习标准”原文" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "表现标准”列" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "人文" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "活动建议" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "六年级" in PRIMARY_DSKP_ANALYSIS_PROMPT
    assert "年级 → 学习领域 → 课题 → 内容标准" in PRIMARY_DSKP_MERGE_PROMPT
    assert prompts_for_profile("primary_dskp_sjkc") == (
        PRIMARY_DSKP_ANALYSIS_PROMPT,
        PRIMARY_DSKP_MERGE_PROMPT,
    )
