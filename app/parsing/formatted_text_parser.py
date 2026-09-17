import re

from app.models import (
    KnowledgeNode,
    KnowledgeTree,
    ParseResult,
    ServiceError,
    ValidationIssue,
)

LEVEL_RE = re.compile(r"^LEVEL\s+(\d+)\s*\|\s*(.*)$")
SCOPE_RE = re.compile(r"^SCOPE\s*\|\s*(.*)$")
UNRESOLVED_RE = re.compile(r"^UNRESOLVED\s*\|\s*(\d+)\s*\|\s*(.*)$")
NODE_NUMBER_PREFIX_RE = re.compile(
    r"^\s*\d+(?:\s*\.\s*\d+)+(?:\s*[.、]\s*|\s+)"
)
SCOPE_ITEM_NUMBER_RE = re.compile(
    r"(^|；)\s*\d+(?:\s*\.\s*\d+){2,}(?:\s*[.、]\s*|\s+)", re.MULTILINE
)


def normalize_node_names(nodes: list[KnowledgeNode]) -> None:
    """Remove source curriculum numbering from all display names."""
    for node in nodes:
        normalized = NODE_NUMBER_PREFIX_RE.sub("", node.name, count=1).strip()
        if normalized:
            node.name = normalized
        normalize_node_names(node.children)


def normalize_scope_text(scope: str) -> str:
    """Remove item identifiers and normalize separators without rewriting content."""
    normalized = SCOPE_ITEM_NUMBER_RE.sub(r"\1", scope.strip())
    normalized = re.sub(r"。\s*；", "；", normalized)
    normalized = re.sub(r"；{2,}", "；", normalized)
    return normalized.strip("； ")


class FormattedTextParser:
    def parse(self, text: str, title: str) -> ParseResult:
        stripped = text.strip()
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            raise ServiceError("EMPTY_MODEL_OUTPUT", "模型输出为空", status_code=502)
        if "BEGIN_KNOWLEDGE_TREE" not in lines:
            raise ServiceError("OUTPUT_PROTOCOL_ERROR", "缺少 BEGIN_KNOWLEDGE_TREE")
        if "END_KNOWLEDGE_TREE" not in lines:
            raise ServiceError("OUTPUT_PROTOCOL_ERROR", "缺少 END_KNOWLEDGE_TREE")
        begin = lines.index("BEGIN_KNOWLEDGE_TREE")
        end = lines.index("END_KNOWLEDGE_TREE", begin + 1)
        issues: list[ValidationIssue] = []
        unresolved: list[ValidationIssue] = []
        roots: list[KnowledgeNode] = []
        stack: list[KnowledgeNode] = []
        last_level = 0
        current: KnowledgeNode | None = None
        for line in lines[begin + 1 : end]:
            level_match = LEVEL_RE.fullmatch(line)
            if level_match:
                level = int(level_match.group(1))
                name = level_match.group(2).strip()
                invalid_jump = last_level and level > last_level + 1
                invalid_root = not stack and level != 1
                if level < 1 or invalid_jump or invalid_root:
                    raise ServiceError(
                        "OUTPUT_PROTOCOL_ERROR", f"非法 LEVEL 层级跳跃：{line}"
                    )
                if not name:
                    issues.append(
                        ValidationIssue(
                            severity="error", code="EMPTY_NODE_NAME", message="节点名称为空"
                        )
                    )
                stack = stack[: level - 1]
                siblings = roots if level == 1 else stack[-1].children
                parent_id = "" if level == 1 else stack[-1].id + "."
                node = KnowledgeNode(
                    id=f"{parent_id}{len(siblings) + 1}",
                    name=name,
                )
                siblings.append(node)
                stack.append(node)
                current = node
                last_level = level
                continue
            scope_match = SCOPE_RE.fullmatch(line)
            if scope_match:
                if current is None:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="SCOPE_WITHOUT_NODE",
                            message="SCOPE 没有对应节点",
                        )
                    )
                elif current.scope is not None:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="DUPLICATE_SCOPE",
                            message="同一节点出现多个 SCOPE，保留第一个",
                            node_id=current.id,
                        )
                    )
                else:
                    raw_scope = scope_match.group(1).strip()
                    current.scope = normalize_scope_text(raw_scope) or None
                continue
            unresolved_match = UNRESOLVED_RE.fullmatch(line)
            if unresolved_match:
                issue = ValidationIssue(
                    severity="warning",
                    code="UNRESOLVED",
                    message=unresolved_match.group(2).strip(),
                    page=int(unresolved_match.group(1)),
                )
                unresolved.append(issue)
                continue
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="UNKNOWN_PROTOCOL_LINE",
                    message=f"未定义协议行：{line[:160]}",
                )
            )
        normalize_node_names(roots)
        tree = KnowledgeTree(title=title, selected_range="全部", children=roots)
        return ParseResult(tree=tree, issues=issues, unresolved=unresolved)
