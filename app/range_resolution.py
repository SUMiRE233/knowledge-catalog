from dataclasses import dataclass

from app.models import KnowledgeNode, KnowledgeTree

RANGE_ALIASES = {
    "初一上": "初一上册",
    "初一上学期": "初一上册",
    "七年级上": "初一上册",
    "七年级上册": "初一上册",
    "七年级第一学期": "初一上册",
    "初一下": "初一下册",
    "初一下学期": "初一下册",
    "七年级下": "初一下册",
    "七年级下册": "初一下册",
    "七年级第二学期": "初一下册",
    "初二上": "初二上册",
    "初二上学期": "初二上册",
    "八年级上": "初二上册",
    "八年级上册": "初二上册",
    "八年级第一学期": "初二上册",
    "初二下": "初二下册",
    "初二下学期": "初二下册",
    "八年级下": "初二下册",
    "八年级下册": "初二下册",
    "八年级第二学期": "初二下册",
    "初三上": "初三上册",
    "初三上学期": "初三上册",
    "九年级上": "初三上册",
    "九年级上册": "初三上册",
    "九年级第一学期": "初三上册",
    "初三下": "初三下册",
    "初三下学期": "初三下册",
    "九年级下": "初三下册",
    "九年级下册": "初三下册",
    "九年级第二学期": "初三下册",
    "高一上": "高一上册",
    "高一上学期": "高一上册",
    "高中一年级上册": "高一上册",
    "高一下": "高一下册",
    "高一下学期": "高一下册",
    "高中一年级下册": "高一下册",
    "高二上": "高二上册",
    "高二上学期": "高二上册",
    "高中二年级上册": "高二上册",
    "高二下": "高二下册",
    "高二下学期": "高二下册",
    "高中二年级下册": "高二下册",
    "高三上": "高三上册",
    "高三上学期": "高三上册",
    "高中三年级上册": "高三上册",
    "高三下": "高三下册",
    "高三下学期": "高三下册",
    "高中三年级下册": "高三下册",
}
CANONICAL_RANGES = set(RANGE_ALIASES.values())


@dataclass(frozen=True)
class RangeResolution:
    tree: KnowledgeTree
    method: str
    evidence: list[str]


def compact_text(value: str) -> str:
    return "".join(value.split())


def canonical_range(value: str) -> str:
    compact = compact_text(value)
    return RANGE_ALIASES.get(compact, compact)


def grade_stage(value: str) -> str | None:
    canonical = canonical_range(value)
    if canonical.startswith(("初一", "初二", "初三")) or canonical.startswith(
        ("七年级", "八年级", "九年级", "初中")
    ):
        return "初中"
    if canonical.startswith(("高一", "高二", "高三", "高中")):
        return "高中"
    return None


def walk_nodes(nodes: list[KnowledgeNode]):
    for node in nodes:
        yield node
        yield from walk_nodes(node.children)


def source_grade_evidence(text: str) -> set[str]:
    compact = compact_text(text)
    found: set[str] = set()
    terms = {**RANGE_ALIASES, **{name: name for name in CANONICAL_RANGES}}
    for term, canonical in terms.items():
        if term in compact:
            found.add(canonical)
    return found


def source_stage_evidence(text: str, detailed: set[str]) -> set[str]:
    stages = {stage for item in detailed if (stage := grade_stage(item))}
    compact = compact_text(text)
    stages.update(stage for stage in ("初中", "高中") if stage in compact)
    return stages


def topmost_stage_nodes(nodes: list[KnowledgeNode], stage: str) -> list[KnowledgeNode]:
    selected: list[KnowledgeNode] = []
    for node in nodes:
        if grade_stage(node.name) == stage:
            selected.append(node.model_copy(deep=True))
        else:
            selected.extend(topmost_stage_nodes(node.children, stage))
    return selected


def with_selection(
    tree: KnowledgeTree,
    selected_range: str,
    children: list[KnowledgeNode] | None = None,
) -> KnowledgeTree:
    return KnowledgeTree(
        title=tree.title,
        selected_range=selected_range,
        children=(
            children
            if children is not None
            else [node.model_copy(deep=True) for node in tree.children]
        ),
    )


def resolve_range(
    tree: KnowledgeTree,
    requested: str,
    auxiliary_text: str = "",
    default_range: str = "全部",
) -> RangeResolution:
    if requested in {"", "全部"}:
        return RangeResolution(with_selection(tree, "全部"), "requested_all", [])

    target = canonical_range(requested)
    for node in walk_nodes(tree.children):
        if canonical_range(node.name) == target:
            return RangeResolution(
                with_selection(tree, requested, [node.model_copy(deep=True)]),
                "model_exact",
                [f"model:{node.name}"],
            )

    source_details = source_grade_evidence(auxiliary_text)
    model_grade_nodes = [
        node
        for node in walk_nodes(tree.children)
        if canonical_range(node.name) in CANONICAL_RANGES
    ]
    if len(source_details) == 1 and target in source_details and not model_grade_nodes:
        return RangeResolution(
            with_selection(tree, requested),
            "source_exact",
            [f"source:{target}"],
        )

    requested_stage = grade_stage(target)
    if requested_stage:
        stage_nodes = topmost_stage_nodes(tree.children, requested_stage)
        if stage_nodes:
            return RangeResolution(
                with_selection(tree, requested_stage, stage_nodes),
                "model_stage_prefix",
                [f"model_stage:{requested_stage}"],
            )
        source_stages = source_stage_evidence(auxiliary_text, source_details)
        if requested_stage in source_stages:
            return RangeResolution(
                with_selection(tree, requested_stage),
                "source_stage_prefix",
                [f"source_stage:{requested_stage}"],
            )

    fallback = canonical_range(default_range) or "全部"
    fallback_stage = grade_stage(fallback)
    if fallback_stage:
        fallback_nodes = topmost_stage_nodes(tree.children, fallback_stage)
        if fallback_nodes:
            return RangeResolution(
                with_selection(tree, fallback_stage, fallback_nodes),
                "configured_default_stage",
                [f"default:{fallback_stage}"],
            )
    return RangeResolution(
        with_selection(tree, fallback),
        "configured_default",
        [f"default:{fallback}"],
    )


def select_range(tree: KnowledgeTree, requested: str) -> KnowledgeTree:
    """Compatibility wrapper for callers that do not provide source evidence."""
    return resolve_range(tree, requested).tree
