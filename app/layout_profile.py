from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ServiceError
from app.range_resolution import canonical_range


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentIdentity(StrictModel):
    root_labels: list[str] = Field(default_factory=list, max_length=1)
    subject: str | None = None
    education_stage: str | None = None
    grade_labels: list[str] = Field(default_factory=list)
    volume_labels: list[str] = Field(default_factory=list)
    evidence_pages: list[int] = Field(default_factory=list)

    @property
    def is_unknown(self) -> bool:
        return not self.root_labels

    @property
    def root_label(self) -> str | None:
        return self.root_labels[0] if self.root_labels else None


class RangeLabel(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    evidence_pages: list[int] = Field(min_length=1)


class PageRange(StrictModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> PageRange:
        if self.end < self.start:
            raise ValueError("page range end must not precede start")
        return self


class NodeLevel(StrictModel):
    level: int = Field(ge=1, le=12)
    role_name: str = Field(min_length=1, max_length=100)
    document_label: str | None = Field(default=None, max_length=200)
    visual_cues: list[str] = Field(default_factory=list)


class ScopeSource(StrictModel):
    document_label: str | None = Field(default=None, max_length=200)
    attaches_to_level: int = Field(ge=1, le=12)
    visual_cues: list[str] = Field(default_factory=list)


class ExcludedRegion(StrictModel):
    document_label: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class ContinuationRule(StrictModel):
    kind: Literal[
        "merged_cell_continues",
        "blank_cell_inherits_previous",
        "page_break_continues",
        "repeated_header",
        "section_header_resets",
        "parallel_items",
        "other_visual_relation",
    ]
    description: str = Field(min_length=1, max_length=1000)


class LayoutDefinition(StrictModel):
    layout_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    page_ranges: list[PageRange] = Field(min_length=1)
    layout_kind: Literal["table", "list", "hierarchy", "mixed", "other"]
    node_levels: list[NodeLevel]
    scope_sources: list[ScopeSource] = Field(default_factory=list)
    excluded_regions: list[ExcludedRegion] = Field(default_factory=list)
    continuation_rules: list[ContinuationRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> LayoutDefinition:
        levels = [item.level for item in self.node_levels]
        if sorted(levels) != list(range(1, len(levels) + 1)):
            raise ValueError("node levels must be unique and continuous from 1")
        defined = set(levels)
        if any(source.attaches_to_level not in defined for source in self.scope_sources):
            raise ValueError("scope source must attach to an existing node level")
        return self


class DocumentExclusion(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    page_numbers: list[int] = Field(default_factory=list)


class LayoutUnresolved(StrictModel):
    code: Literal[
        "CONTENT_REGION_NOT_FOUND",
        "NODE_HIERARCHY_UNCLEAR",
        "REGION_ROLE_CONFLICT",
        "CONTINUATION_CONFLICT",
        "PAGE_UNREADABLE",
        "EXPLICIT_RANGE_UNCLEAR",
        "SCOPE_SOURCE_UNCLEAR",
        "EXCLUSION_LABEL_UNCLEAR",
        "MINOR_VISUAL_CUE_UNCLEAR",
        "ROOT_IDENTITY_CONFLICT",
    ]
    page_numbers: list[int] = Field(default_factory=list)
    description: str = Field(min_length=1, max_length=1000)


BLOCKING_UNRESOLVED_CODES = {
    "CONTENT_REGION_NOT_FOUND",
    "NODE_HIERARCHY_UNCLEAR",
    "REGION_ROLE_CONFLICT",
    "CONTINUATION_CONFLICT",
    "PAGE_UNREADABLE",
    "ROOT_IDENTITY_CONFLICT",
}
FORBIDDEN_SCOPE_PATTERN = re.compile(
    r"(学习目标|教学目标|表现标准|能力要求|学生必须能)"
)


class LayoutProfile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_page_count: int = Field(ge=1)
    languages: list[str] = Field(min_length=1)
    document_identity: DocumentIdentity
    range_labels: list[RangeLabel]
    layouts: list[LayoutDefinition] = Field(min_length=1)
    document_exclusions: list[DocumentExclusion] = Field(default_factory=list)
    unresolved: list[LayoutUnresolved] = Field(default_factory=list)

    def validate_page_coverage(
        self, expected_page_count: int, expected_pages: set[int] | None = None
    ) -> None:
        if self.source_page_count != expected_page_count:
            raise ValueError("source_page_count does not match prepared document")
        layout_ids = [layout.layout_id for layout in self.layouts]
        if len(layout_ids) != len(set(layout_ids)):
            raise ValueError("layout_id must be unique")
        covered: list[int] = []
        for layout in self.layouts:
            for page_range in layout.page_ranges:
                if page_range.end > expected_page_count:
                    raise ValueError("page range exceeds prepared document")
                covered.extend(range(page_range.start, page_range.end + 1))
        if len(covered) != len(set(covered)):
            raise ValueError("layout page ranges must not overlap")
        required = expected_pages or set(range(1, expected_page_count + 1))
        if set(covered) != required:
            raise ValueError("layout page ranges do not cover the required pages")
        identity_pages = self.document_identity.evidence_pages
        exclusion_pages = [
            page for exclusion in self.document_exclusions for page in exclusion.page_numbers
        ]
        unresolved_pages = [
            page for item in self.unresolved for page in item.page_numbers
        ]
        range_pages = [
            page for item in self.range_labels for page in item.evidence_pages
        ]
        if any(
            page < 1 or page > expected_page_count
            for page in [
                *identity_pages,
                *range_pages,
                *exclusion_pages,
                *unresolved_pages,
            ]
        ):
            raise ValueError("evidence page is outside prepared document")

    @property
    def blocking_unresolved(self) -> list[LayoutUnresolved]:
        return [item for item in self.unresolved if item.code in BLOCKING_UNRESOLVED_CODES]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @property
    def forbidden_scope_sources(self) -> list[ScopeSource]:
        conflicts: list[ScopeSource] = []
        for layout in self.layouts:
            for source in layout.scope_sources:
                risk_text = " ".join(
                    [source.document_label or "", *source.visual_cues]
                )
                if FORBIDDEN_SCOPE_PATTERN.search(risk_text):
                    conflicts.append(source)
        return conflicts


def parse_layout_profile(
    raw: str,
    expected_page_count: int,
    expected_pages: set[int] | None = None,
    require_node_region: bool = True,
) -> LayoutProfile:
    try:
        payload = raw.strip()
        if payload.startswith("```json\n") and payload.endswith("\n```"):
            payload = payload[len("```json\n") : -len("\n```")].strip()
        elif payload.startswith("```\n") and payload.endswith("\n```"):
            payload = payload[len("```\n") : -len("\n```")].strip()
        value = json.loads(payload)
        profile = LayoutProfile.model_validate(value)
        normalized_ranges: dict[str, tuple[str, set[int]]] = {}
        for item in profile.range_labels:
            canonical = canonical_range(item.label)
            existing_label, pages = normalized_ranges.setdefault(
                canonical, (item.label, set())
            )
            if len(item.label) > len(existing_label):
                existing_label = item.label
            pages.update(item.evidence_pages)
            normalized_ranges[canonical] = (existing_label, pages)
        profile.range_labels = [
            RangeLabel(label=label, evidence_pages=sorted(pages))
            for label, pages in normalized_ranges.values()
        ]
        profile.validate_page_coverage(expected_page_count, expected_pages)
        if require_node_region and not any(
            layout.node_levels for layout in profile.layouts
        ):
            raise ValueError("layout profile has no extractable node region")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ServiceError(
            "VANGUARD_OUTPUT_INVALID",
            "Vanguard 返回的布局 JSON 无效",
            status_code=502,
        ) from exc
    if require_node_region and profile.blocking_unresolved:
        codes = ", ".join(item.code for item in profile.blocking_unresolved)
        raise ServiceError(
            "VANGUARD_LAYOUT_UNRESOLVED",
            f"Vanguard 存在阻断型布局问题：{codes}",
            status_code=422,
        )
    if require_node_region and profile.forbidden_scope_sources:
        raise ServiceError(
            "VANGUARD_LAYOUT_UNRESOLVED",
            "Vanguard 将学习目标、表现标准或能力要求误标为 scope 来源",
            status_code=422,
        )
    return profile
