from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ServiceError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class StoredFile(BaseModel):
    job_id: str
    original_filename: str
    safe_filename: str
    path: Path
    content_type: str
    size_bytes: int


class GenerationOptions(BaseModel):
    selected_range: str = "全部"
    enhance_images: bool = True
    use_ocr_fallback: bool = False
    document_profile: Literal["general", "primary_dskp_sjkc"] = "general"


class PreparedPage(BaseModel):
    page_number: int
    image_path: Path
    auxiliary_text: str | None = None


class PreparedDocument(BaseModel):
    source_file_name: str
    input_type: Literal["standard_pdf", "scanned_pdf", "image"]
    pages: list[PreparedPage]


class ModelAnalysisRequest(BaseModel):
    instruction: str
    pages: list[PreparedPage] = Field(default_factory=list)
    batch_number: int | None = None
    total_batches: int | None = None
    previous_path_summary: str | None = None
    merge_inputs: list[str] = Field(default_factory=list)


class ModelAnalysisResponse(BaseModel):
    text: str
    finish_reason: str | None = None


class KnowledgeNode(BaseModel):
    id: str
    name: str
    scope: str | None = None
    children: list[KnowledgeNode] = Field(default_factory=list)


class KnowledgeTree(BaseModel):
    title: str
    selected_range: str
    children: list[KnowledgeNode] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str
    node_id: str | None = None
    page: int | None = None


class ValidationReport(BaseModel):
    passed: bool
    error_count: int
    warning_count: int
    issues: list[ValidationIssue]


class ParseResult(BaseModel):
    tree: KnowledgeTree
    issues: list[ValidationIssue]
    unresolved: list[ValidationIssue]


class GenerationResult(BaseModel):
    tree: KnowledgeTree
    validation_report: ValidationReport
    artifacts: list[str]
    output_dir: Path
    node_count: int
    leaf_node_count: int


JobStatus = Literal["pending", "processing", "succeeded", "failed"]
JobStage = Literal[
    "upload", "inspect", "render", "preprocess", "analyze", "merge", "parse", "validate", "publish"
]


class JobError(BaseModel):
    code: str
    message: str


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus = "pending"
    stage: JobStage = "upload"
    progress: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: JobError | None = None
    result: dict | None = None


ProgressCallback = Callable[[JobStage, int], Awaitable[None]]
