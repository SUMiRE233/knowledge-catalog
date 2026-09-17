import re
import unicodedata
from collections.abc import Iterable

from app.models import (
    KnowledgeNode,
    KnowledgeTree,
    ValidationIssue,
    ValidationReport,
)

RISK_PATTERNS = {
    "EXPLANATORY_TEXT": re.compile(r"(以下是|根据图片|我认为|可能包括|学生需要掌握)"),
    "MARKDOWN_FENCE": re.compile(r"```"),
    "JSON_LIKE_OUTPUT": re.compile(
        r"(^|\n)\s*(\{.*\}|[{}]|\[.*\]|[\[\]])\s*($|\n)"
    ),
    "MODEL_SELF_EXPLANATION": re.compile(r"(作为.{0,8}模型|无法提供|我的分析)"),
}
ALLOWED_FIELDS = {"id", "name", "scope", "children"}
SOURCE_MATCH_EXEMPT_NAMES = {"未知学科"}
NUMBERED_NODE_IN_SCOPE_RE = re.compile(r"(?:^|[；。]\s*)\d+(?:\.\d+)+\s+\S+")


def source_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized)


def walk(nodes: Iterable[KnowledgeNode], path: tuple[str, ...] = ()):
    for node in nodes:
        current = (*path, node.name)
        yield node, current
        yield from walk(node.children, current)


class OutputGuard:
    def validate(
        self,
        tree: KnowledgeTree,
        raw_output: str,
        auxiliary_text: str,
        parser_issues: list[ValidationIssue],
        unresolved: list[ValidationIssue],
    ) -> ValidationReport:
        issues = [*parser_issues, *unresolved]
        nodes = list(walk(tree.children))
        if not nodes:
            issues.append(
                ValidationIssue(
                    severity="error", code="EMPTY_KNOWLEDGE_TREE", message="知识树为空"
                )
            )
        ids: set[str] = set()
        paths: set[tuple[str, ...]] = set()
        compact_source = source_match_text(auxiliary_text)
        for node, path in nodes:
            if not node.name:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="EMPTY_NODE_NAME",
                        message="节点名称为空",
                        node_id=node.id,
                    )
                )
            if node.id in ids:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DUPLICATE_ID",
                        message="节点 ID 重复",
                        node_id=node.id,
                    )
                )
            ids.add(node.id)
            if path in paths:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="DUPLICATE_FULL_PATH",
                        message="完整路径重复",
                        node_id=node.id,
                    )
                )
            paths.add(path)
            extra = set(node.model_dump().keys()) - ALLOWED_FIELDS
            if extra:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="FORBIDDEN_NODE_FIELD",
                        message=f"节点含禁止字段：{sorted(extra)}",
                        node_id=node.id,
                    )
                )
            if len(node.name) > 200:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="NAME_TOO_LONG",
                        message="节点名称超过 200 字符",
                        node_id=node.id,
                    )
                )
            if node.scope and len(node.scope) > 4000:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="SCOPE_TOO_LONG",
                        message="scope 超过 4000 字符",
                        node_id=node.id,
                    )
                )
            if node.scope and NUMBERED_NODE_IN_SCOPE_RE.search(node.scope):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NUMBERED_NODE_IN_SCOPE",
                        message="scope 疑似吞入一个或多个明确编号的子节点",
                        node_id=node.id,
                    )
                )
            if node.scope and node.children:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="NON_LEAF_SCOPE",
                        message="非叶节点不得携带 scope；scope 必须挂到对应叶节点",
                        node_id=node.id,
                    )
                )
            if compact_source and node.name not in SOURCE_MATCH_EXEMPT_NAMES:
                name_found = source_match_text(node.name) in compact_source
                scope_parts = (
                    [part for part in re.split(r"[；;]", node.scope) if part.strip()]
                    if node.scope
                    else []
                )
                scope_found = all(
                    source_match_text(part) in compact_source for part in scope_parts
                )
                if not (name_found and scope_found):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="SOURCE_MATCH_UNCERTAIN",
                            message="名称或 scope 未能在 PDF 文本层中匹配",
                            node_id=node.id,
                        )
                    )
        for code, pattern in RISK_PATTERNS.items():
            if pattern.search(raw_output):
                issues.append(
                    ValidationIssue(
                        severity="warning", code=code, message="模型输出包含风险文本"
                    )
                )
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        return ValidationReport(
            passed=errors == 0,
            error_count=errors,
            warning_count=warnings,
            issues=issues,
        )
