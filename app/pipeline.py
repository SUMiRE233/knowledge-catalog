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
from app.llm.prompt_composer import UNKNOWN_ROOT_NAME, compose_business_prompt
from app.llm.vanguard import VanguardAnalyzer
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
        self.vanguard = VanguardAnalyzer(model_client, settings)
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
        vanguard_batch_dir = output_dir / "vanguard_batches"
        vanguard_batch_dir.mkdir(exist_ok=True)

        async def save_batch(index: int, output: str) -> None:
            (batch_dir / f"batch_{index:04d}.txt").write_text(output, encoding="utf-8")

        async def analysis_progress(phase: str, completed: int, total: int) -> None:
            if not progress_callback:
                return
            if phase == "merge":
                await progress_callback("merge", 60)
                return
            progress = 45 + int(15 * completed / max(total, 1))
            await progress_callback("analyze", progress)

        vanguard_outputs: dict[int, str] = {}

        async def save_vanguard(index: int, output: str) -> None:
            vanguard_outputs[index] = output
            if index == -1:
                name = "reviewed.txt"
            elif index == 0:
                name = "merged.txt"
            else:
                name = f"batch_{index:04d}.json"
            (vanguard_batch_dir / name).write_text(output, encoding="utf-8")

        async def vanguard_progress(completed: int, total: int) -> None:
            if progress_callback:
                await progress_callback(
                    "vanguard", 25 + int(10 * completed / max(total, 1))
                )

        prepared_payload = document.model_dump(mode="json")
        for page in prepared_payload["pages"]:
            page["image_path"] = f"prepared/pages/{Path(page['image_path']).name}"
        write_json(output_dir / "prepared_document.json", prepared_payload)
        await stage("vanguard", 25)
        tick = time.perf_counter()
        layout_profile, vanguard_batches = await self.vanguard.inspect(
            document,
            output_callback=save_vanguard,
            progress_callback=vanguard_progress,
        )
        stage_durations["vanguard"] = round(time.perf_counter() - tick, 4)
        raw_vanguard = (
            vanguard_outputs.get(-1)
            or vanguard_outputs.get(0)
            or vanguard_batches[0]
        )
        (output_dir / "vanguard_output.txt").write_text(raw_vanguard, encoding="utf-8")
        write_json(
            output_dir / "layout_profile.json",
            layout_profile.model_dump(mode="json"),
        )

        await stage("compose", 38)
        business_prompt = compose_business_prompt(layout_profile)
        (output_dir / "business_prompt.txt").write_text(
            "\n\n".join(
                [
                    "=== EXTRACTION PROMPT ===\n" + business_prompt.extraction,
                    "=== MERGE PROMPT ===\n" + business_prompt.merge,
                    "=== REVIEW PROMPT ===\n" + business_prompt.review,
                ]
            ),
            encoding="utf-8",
        )

        await stage("analyze", 45)
        tick = time.perf_counter()
        model_output, batch_outputs = await self.analyzer.analyze(
            document,
            document_profile=options.document_profile,
            batch_output_callback=save_batch,
            progress_callback=analysis_progress,
            analysis_prompt_override=business_prompt.extraction,
            merge_prompt_override=business_prompt.merge,
            review_prompt_override=business_prompt.review,
        )
        stage_durations["compose_analyze_merge"] = round(
            time.perf_counter() - tick, 4
        )
        (output_dir / "model_output.txt").write_text(model_output, encoding="utf-8")
        await stage("parse", 65)
        parsed = self.parser.parse(
            model_output,
            f"{Path(stored_file.original_filename).stem}知识目录",
        )
        actual_roots = [node.name for node in parsed.tree.children]
        if len(actual_roots) != 1:
            raise ServiceError(
                "OUTPUT_PROTOCOL_ERROR",
                "一次 PDF 生成流程最终必须且只能发布一个 LEVEL 1 根节点",
                status_code=502,
            )
        if layout_profile.document_identity.is_unknown:
            if actual_roots[0] != UNKNOWN_ROOT_NAME:
                raise ServiceError(
                    "OUTPUT_PROTOCOL_ERROR",
                    "文档身份未知时模型必须只使用固定根节点“未知学科”",
                    status_code=502,
                )
            parsed.tree.title = f"{UNKNOWN_ROOT_NAME}知识目录"
        elif actual_roots[0] != layout_profile.document_identity.root_label:
            raise ServiceError(
                "OUTPUT_PROTOCOL_ERROR",
                "模型一级根节点与 Vanguard 的明确身份不一致",
                status_code=502,
            )
        else:
            parsed.tree.title = f"{actual_roots[0]}知识目录"
        expected_ranges = [item.label for item in layout_profile.range_labels]
        if expected_ranges:
            actual_ranges = [
                child.name
                for root in parsed.tree.children
                for child in root.children
            ]
            if actual_ranges != expected_ranges:
                raise ServiceError(
                    "OUTPUT_PROTOCOL_ERROR",
                    "模型未按 Vanguard 的明确年级、册别或学期边界组织二级节点",
                    status_code=502,
                )
        for item in layout_profile.unresolved:
            parsed.issues.append(
                ValidationIssue(
                    severity="warning",
                    code=f"VANGUARD_{item.code}",
                    message=item.description,
                    page=item.page_numbers[0] if item.page_numbers else None,
                )
            )
        auxiliary = "\n".join(page.auxiliary_text or "" for page in document.pages)
        range_resolution = resolve_range(
            parsed.tree,
            options.selected_range,
            auxiliary,
            self.settings.default_grade_range,
        )
        if (
            options.selected_range not in {"", "全部"}
            and range_resolution.method == "configured_default"
        ):
            raise ServiceError(
                "RANGE_NOT_FOUND",
                f"未找到请求范围：{options.selected_range}",
                status_code=404,
            )
        parsed.tree = range_resolution.tree
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
            "vanguard_batch_count": len(vanguard_batches),
            "vanguard_consolidation_call_count": (
                2 if len(vanguard_batches) > 1 else 0
            ),
            "extractor_postprocess_call_count": (
                2 if len(batch_outputs) > 1 else 1
            ),
            "range": options.selected_range,
            "selected_range": parsed.tree.selected_range,
            "range_resolution_method": range_resolution.method,
            "range_evidence": range_resolution.evidence,
            "enhance_images": options.enhance_images,
            "use_ocr_fallback": options.use_ocr_fallback,
            "document_profile": options.document_profile,
            "layout_profile_schema_version": layout_profile.schema_version,
            "generic_prompt_version": business_prompt.version,
            "business_prompt_sha256": business_prompt.sha256,
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
