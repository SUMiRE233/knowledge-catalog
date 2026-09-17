import re
from collections.abc import Awaitable, Callable

from app.config import Settings
from app.llm.batching import batches
from app.llm.client import MultimodalModelClient
from app.llm.prompts import (
    merge_instruction_for_profile,
    primary_hierarchy_review_instruction,
    primary_level_2_boundaries,
    prompts_for_profile,
)
from app.models import ModelAnalysisRequest, PreparedDocument, ServiceError


class DocumentAnalyzer:
    def __init__(self, client: MultimodalModelClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def analyze(
        self,
        document: PreparedDocument,
        document_profile: str = "general",
        batch_output_callback: Callable[[int, str], Awaitable[None]] | None = None,
        progress_callback: Callable[[str, int, int], Awaitable[None]] | None = None,
        analysis_prompt_override: str | None = None,
        merge_prompt_override: str | None = None,
        review_prompt_override: str | None = None,
    ) -> tuple[str, list[str]]:
        default_analysis_prompt, default_merge_prompt = prompts_for_profile(document_profile)
        analysis_prompt = analysis_prompt_override or default_analysis_prompt
        merge_prompt = merge_prompt_override or default_merge_prompt
        page_batches = batches(document.pages, self.settings.llm_max_images_per_request)
        outputs: list[str] = []
        previous = ""
        path_by_level: dict[int, str] = {}
        for number, pages in enumerate(page_batches, 1):
            response = await self.client.analyze(
                ModelAnalysisRequest(
                    operation="extract",
                    instruction=analysis_prompt,
                    pages=pages,
                    batch_number=number,
                    total_batches=len(page_batches),
                    previous_path_summary=previous,
                )
            )
            self._check_response(response.text, response.finish_reason)
            outputs.append(response.text)
            if batch_output_callback:
                await batch_output_callback(number, response.text)
            if progress_callback:
                await progress_callback("analyze", number, len(page_batches))
            previous = self._updated_path_summary(response.text, path_by_level, previous)
        if len(outputs) == 1:
            if review_prompt_override is None:
                return outputs[0], outputs
            reviewed = await self.client.analyze(
                ModelAnalysisRequest(
                    operation="merge",
                    instruction=review_prompt_override,
                    merge_inputs=outputs,
                )
            )
            self._check_response(reviewed.text, reviewed.finish_reason)
            return reviewed.text, outputs
        if progress_callback:
            await progress_callback("merge", len(page_batches), len(page_batches))
        merge_instruction = (
            merge_prompt
            if merge_prompt_override is not None
            else merge_instruction_for_profile(document_profile, merge_prompt, outputs)
        )
        merged = await self.client.analyze(
            ModelAnalysisRequest(
                operation="merge",
                instruction=merge_instruction,
                merge_inputs=outputs,
            )
        )
        self._check_response(merged.text, merged.finish_reason)
        if review_prompt_override is not None:
            reviewed = await self.client.analyze(
                ModelAnalysisRequest(
                    operation="merge",
                    instruction=review_prompt_override,
                    merge_inputs=[merged.text, *outputs],
                )
            )
            self._check_response(reviewed.text, reviewed.finish_reason)
            return reviewed.text, outputs
        if document_profile == "primary_dskp_sjkc" and merge_prompt_override is None:
            review_instruction = primary_hierarchy_review_instruction(
                merged.text, primary_level_2_boundaries(outputs)
            )
            if review_instruction:
                merged = await self.client.analyze(
                    ModelAnalysisRequest(
                        operation="merge",
                        instruction=review_instruction, merge_inputs=[merged.text]
                    )
                )
                self._check_response(merged.text, merged.finish_reason)
        return merged.text, outputs

    @staticmethod
    def _check_response(text: str, finish_reason: str | None) -> None:
        if not text.strip():
            raise ServiceError("EMPTY_MODEL_OUTPUT", "模型输出为空", status_code=502)
        if finish_reason in {"length", "max_tokens"}:
            raise ServiceError("MODEL_OUTPUT_TRUNCATED", "模型输出被截断", status_code=502)

    @staticmethod
    def _last_paths(text: str) -> str:
        levels = re.findall(r"^LEVEL\s+(\d+)\s*\|\s*(.+?)\s*$", text, re.MULTILINE)
        return " / ".join(name for _, name in levels[-3:])[:500]

    @staticmethod
    def _updated_path_summary(
        text: str, path_by_level: dict[int, str], previous: str
    ) -> str:
        levels = re.findall(r"^LEVEL\s+(\d+)\s*\|\s*(.+?)\s*$", text, re.MULTILINE)
        for raw_level, name in levels:
            level = int(raw_level)
            normalized_name = name.strip()
            if path_by_level.get(level) != normalized_name:
                for deeper in [item for item in path_by_level if item > level]:
                    del path_by_level[deeper]
                path_by_level[level] = normalized_name
        if not path_by_level:
            return previous
        return " / ".join(path_by_level[level] for level in sorted(path_by_level))[:500]
