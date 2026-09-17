import time
from datetime import UTC, datetime
from pathlib import Path

from app.catalog_contract import (
    GENERATOR_VERSION,
    KNOWLEDGE_TREE_SCHEMA_VERSION,
    sha256_file,
)
from app.config import Settings
from app.inputs.base import InputAdapter
from app.llm.analyzer import DocumentAnalyzer
from app.llm.client import MultimodalModelClient
from app.models import (
    GenerationOptions,
    GenerationResult,
    KnowledgeNode,
    ProgressCallback,
    ServiceError,
    StoredFile,
    ValidationIssue,
)
from app.parsing.formatted_text_parser import FormattedTextParser
from app.publishing import PUBLIC_ARTIFACTS, write_catalog, write_json
from app.range_resolution import resolve_range
from app.validation.output_guard import OutputGuard, walk


def counts(nodes: list[KnowledgeNode]) -> tuple[int, int, int]:
    all_nodes = [node for node, _ in walk(nodes)]
    return (
        len(all_nodes),
        sum(not node.children for node in all_nodes),
        sum(bool(node.scope) for node in all_nodes),
    )


def stable_primary_title(nodes: list[KnowledgeNode]) -> str:
    if len(nodes) == 1 and nodes[0].name:
        return f"马来西亚华文小学数学{nodes[0].name}知识目录"
    return "马来西亚华文小学数学知识目录"


class KnowledgeTreeGenerationService:
    def __init__(
        self,
        settings: Settings,
        storage,
        model_client: MultimodalModelClient,
    ):
        self.settings = settings
        self.storage = storage
        self.adapter = InputAdapter(settings)
        self.analyzer = DocumentAnalyzer(model_client, settings)
        self.parser = FormattedTextParser()
        self.guard = OutputGuard()

    async def generate(
        self,
        stored_file: StoredFile,
        options: GenerationOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> GenerationResult:
        started = datetime.now(UTC)
        stage_durations: dict[str, float] = {}

        async def stage(name: str, progress: int) -> float:
            if progress_callback:
                await progress_callback(name, progress)
            return time.perf_counter()

        tick = await stage("inspect", 10)
        document = self.adapter.prepare(stored_file, options)
        stage_durations["inspect_render_preprocess"] = round(time.perf_counter() - tick, 4)
        output_dir = self.storage.output_dir(stored_file.job_id)
        batch_dir = output_dir / "model_batches"
        batch_dir.mkdir(exist_ok=True)

        async def save_batch(index: int, output: str) -> None:
            (batch_dir / f"batch_{index:04d}.txt").write_text(output, encoding="utf-8")

        async def analysis_progress(phase: str, completed: int, total: int) -> None:
            if not progress_callback:
                return
            if phase == "merge":
                await progress_callback("merge", 60)
                return
            progress = 35 + int(20 * completed / max(total, 1))
            await progress_callback("analyze", progress)

        prepared_payload = document.model_dump(mode="json")
        for page in prepared_payload["pages"]:
            page["image_path"] = f"prepared/pages/{Path(page['image_path']).name}"
        write_json(output_dir / "prepared_document.json", prepared_payload)
        await stage("analyze", 35)
        tick = time.perf_counter()
        model_output, batch_outputs = await self.analyzer.analyze(
            document,
            document_profile=options.document_profile,
            batch_output_callback=save_batch,
            progress_callback=analysis_progress,
        )
        stage_durations["analyze_merge"] = round(time.perf_counter() - tick, 4)
        (output_dir / "model_output.txt").write_text(model_output, encoding="utf-8")
        await stage("parse", 65)
        parsed = self.parser.parse(
            model_output,
            f"{Path(stored_file.original_filename).stem}知识目录",
        )
        auxiliary = "\n".join(page.auxiliary_text or "" for page in document.pages)
        range_resolution = resolve_range(
            parsed.tree,
            options.selected_range,
            auxiliary,
            self.settings.default_grade_range,
        )
        parsed.tree = range_resolution.tree
        if options.document_profile == "primary_dskp_sjkc":
            parsed.tree.title = stable_primary_title(parsed.tree.children)
        if range_resolution.method not in {"requested_all", "model_exact"}:
            parsed.issues.append(
                ValidationIssue(
                    severity="warning",
                    code="RANGE_FALLBACK_APPLIED",
                    message=(
                        f"请求范围“{options.selected_range}”未获精确模型节点支持，"
                        f"采用 {range_resolution.method}：{parsed.tree.selected_range}"
                    ),
                )
            )
        await stage("validate", 78)
        validation = self.guard.validate(
            parsed.tree, model_output, auxiliary, parsed.issues, parsed.unresolved
        )
        if not parsed.tree.children:
            raise ServiceError("EMPTY_KNOWLEDGE_TREE", "知识树为空")
        if validation.error_count:
            raise ServiceError("OUTPUT_PROTOCOL_ERROR", "模型输出未通过验证")
        await stage("publish", 90)
        write_json(
            output_dir / "knowledge_tree.json",
            parsed.tree.model_dump(mode="json", exclude_none=False),
        )
        write_catalog(output_dir / "knowledge_catalog.txt", parsed.tree)
        write_json(
            output_dir / "validation_report.json",
            validation.model_dump(mode="json"),
        )
        node_count, leaf_count, scope_count = counts(parsed.tree.children)
        finished = datetime.now(UTC)
        run_report = {
            "schema_version": KNOWLEDGE_TREE_SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "job_id": stored_file.job_id,
            "original_filename": stored_file.original_filename,
            "input_type": document.input_type,
            "file_size_bytes": stored_file.size_bytes,
            "page_count": len(document.pages),
            "batch_count": len(batch_outputs),
            "range": options.selected_range,
            "selected_range": parsed.tree.selected_range,
            "range_resolution_method": range_resolution.method,
            "range_evidence": range_resolution.evidence,
            "enhance_images": options.enhance_images,
            "use_ocr_fallback": options.use_ocr_fallback,
            "document_profile": options.document_profile,
            "model_name": self.settings.llm_model or "fake/injected",
            "started_at": started,
            "finished_at": finished,
            "stage_durations_seconds": stage_durations,
            "node_count": node_count,
            "leaf_node_count": leaf_count,
            "scope_nonempty_count": scope_count,
            "scope_empty_count": node_count - scope_count,
            "unresolved_count": len(parsed.unresolved),
            "warning_count": validation.warning_count,
            "error_count": validation.error_count,
            "success": True,
            "generation_source": {
                "kind": "uploaded_document",
                "filename": stored_file.original_filename,
                "sha256": sha256_file(stored_file.path),
                "input_type": document.input_type,
                "page_count": len(document.pages),
            },
        }
        write_json(output_dir / "run_report.json", run_report)
        if progress_callback:
            await progress_callback("publish", 100)
        return GenerationResult(
            tree=parsed.tree,
            validation_report=validation,
            artifacts=sorted(PUBLIC_ARTIFACTS),
            output_dir=output_dir,
            node_count=node_count,
            leaf_node_count=leaf_count,
        )
