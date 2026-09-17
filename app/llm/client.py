import asyncio
import base64
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings
from app.models import (
    ModelAnalysisRequest,
    ModelAnalysisResponse,
    ServiceError,
)


class MultimodalModelClient(Protocol):
    async def analyze(self, request: ModelAnalysisRequest) -> ModelAnalysisResponse: ...


async def _image_url(path: Path) -> str:
    import asyncio
    encoded = await asyncio.to_thread(
        lambda: base64.b64encode(path.read_bytes()).decode("ascii")
    )
    return f"data:image/png;base64,{encoded}"


class OpenAICompatibleMultimodalClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def analyze(self, request: ModelAnalysisRequest) -> ModelAnalysisResponse:
        if not self.settings.llm_api_key or not self.settings.llm_model:
            raise ServiceError("LLM_NOT_CONFIGURED", "未配置有效的多模态模型")
        content: list[dict] = [{"type": "text", "text": request.instruction}]
        if request.batch_number:
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"批次 {request.batch_number}/{request.total_batches}；"
                        f"上一批末尾路径：{request.previous_path_summary or '无'}"
                    ),
                }
            )
        for page in request.pages:
            content.append({"type": "text", "text": f"真实页码：{page.page_number}"})
            content.append(
                {"type": "image_url", "image_url": {"url": await _image_url(page.image_path)}}
            )
            if page.auxiliary_text:
                content.append(
                    {
                        "type": "text",
                        "text": f"第 {page.page_number} 页辅助文本（不得据此猜结构）：\n"
                        f"{page.auxiliary_text}",
                    }
                )
        if request.merge_inputs:
            content.append(
                {
                    "type": "text",
                    "text": "\n\n".join(
                        f"--- 批次 {i} ---\n{text}"
                        for i, text in enumerate(request.merge_inputs, 1)
                    ),
                }
            )
        payload = {
            "model": self.settings.llm_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": self.settings.llm_max_output_tokens,
        }
        if self.settings.llm_enable_thinking is not None:
            payload["enable_thinking"] = self.settings.llm_enable_thinking
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 500 and attempt < self.settings.llm_max_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.is_error:
                    raise ServiceError(
                        "LLM_REQUEST_FAILED",
                        f"模型服务请求失败（HTTP {response.status_code}）",
                        status_code=502,
                    )
                body = response.json()
                choice = body["choices"][0]
                text = choice["message"].get("content") or ""
                return ModelAnalysisResponse(
                    text=text,
                    finish_reason=choice.get("finish_reason"),
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self.settings.llm_max_retries:
                    raise ServiceError("LLM_TIMEOUT", "模型请求超时", status_code=504) from exc
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt >= self.settings.llm_max_retries:
                    raise ServiceError(
                        "LLM_REQUEST_FAILED", "模型服务响应无效", status_code=502
                    ) from exc
            await asyncio.sleep(0.25 * (2**attempt))
        raise ServiceError("LLM_REQUEST_FAILED", "模型请求失败", status_code=502) from last_error
