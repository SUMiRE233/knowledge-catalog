import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.inputs.base import InputAdapter
from app.llm.client import OpenAICompatibleMultimodalClient
from app.models import (
    GenerationOptions,
    ModelAnalysisRequest,
    PreparedPage,
    ServiceError,
    StoredFile,
)
from tests.conftest import scanned_pdf_bytes


def test_comma_separated_image_type_setting(monkeypatch):
    monkeypatch.setenv("ALLOWED_IMAGE_TYPES", "image/png,image/jpeg")
    assert Settings().allowed_image_types == ["image/png", "image/jpeg"]


def stored(tmp_path, data, name="scan.pdf", content_type="application/pdf"):
    path = tmp_path / name
    path.write_bytes(data)
    return StoredFile(
        job_id="job",
        original_filename=name,
        safe_filename=name,
        path=path,
        content_type=content_type,
        size_bytes=len(data),
    )


def test_scanned_pdf_preparation(tmp_path):
    value = stored(tmp_path, scanned_pdf_bytes())
    document = InputAdapter(Settings(runtime_dir=tmp_path)).prepare(
        value, GenerationOptions()
    )
    assert document.input_type == "scanned_pdf"
    assert document.pages[0].image_path.is_file()


def test_corrupt_pdf():
    with pytest.raises(ServiceError) as error:
        InputAdapter(Settings()).prepare(
            StoredFile(
                job_id="x",
                original_filename="x.pdf",
                safe_filename="x.pdf",
                path=Path(__file__),
                content_type="application/pdf",
                size_bytes=1,
            ),
            GenerationOptions(),
        )
    assert error.value.code == "INVALID_PDF"


@pytest.mark.asyncio
async def test_real_client_request_has_images_and_text(monkeypatch, tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.llm.client.httpx.AsyncClient",
        lambda **kwargs: original(transport=transport, **kwargs),
    )
    settings = Settings(llm_api_key="key", llm_model="vision", llm_base_url="https://example.test/v1")
    settings.llm_enable_thinking = False
    settings.llm_max_output_tokens = 1234
    client = OpenAICompatibleMultimodalClient(settings)
    await client.analyze(
        ModelAnalysisRequest(
            instruction="inspect",
            pages=[PreparedPage(page_number=7, image_path=image, auxiliary_text="aux")],
        )
    )
    content = captured["messages"][0]["content"]
    assert any(item["type"] == "image_url" for item in content)
    assert any("真实页码：7" in item.get("text", "") for item in content)
    assert captured["enable_thinking"] is False
    assert captured["max_tokens"] == 1234
    assert "max_token" not in captured


@pytest.mark.asyncio
async def test_model_not_configured():
    with pytest.raises(ServiceError) as error:
        await OpenAICompatibleMultimodalClient(
            Settings(_env_file=None, llm_api_key=None, llm_model=None)
        ).analyze(
            ModelAnalysisRequest(instruction="x")
        )
    assert error.value.code == "LLM_NOT_CONFIGURED"
