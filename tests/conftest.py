from io import BytesIO

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import Settings
from app.main import create_app
from app.models import ModelAnalysisResponse

GOOD_OUTPUT = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 初一上册
LEVEL 2 | 完整数
LEVEL 3 | 1.1 完整数与自然数的概念
SCOPE | 完整数与自然数的介绍
LEVEL 3 | 1.2 应用问题
SCOPE | 完整数四则运算的应用问题
END_KNOWLEDGE_TREE"""


class FakeModel:
    def __init__(self, text=GOOD_OUTPUT, finish_reason="stop"):
        self.text = text
        self.finish_reason = finish_reason
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        return ModelAnalysisResponse(text=self.text, finish_reason=self.finish_reason)


def png_bytes(text="课程页面"):
    image = Image.new("RGB", (500, 300), "white")
    ImageDraw.Draw(image).text((20, 20), text, fill="black")
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def text_pdf_bytes():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Grade 7 curriculum content")
    data = document.tobytes()
    document.close()
    return data


def scanned_pdf_bytes():
    document = fitz.open()
    page = document.new_page(width=500, height=300)
    page.insert_image(page.rect, stream=png_bytes())
    data = document.tobytes()
    document.close()
    return data


def encrypted_pdf_bytes():
    document = fitz.open()
    document.new_page()
    data = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    document.close()
    return data


@pytest.fixture
def fake_model():
    return FakeModel()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        runtime_dir=tmp_path / "runtime",
        max_upload_size_mb=2,
        llm_model="fake-model",
        llm_api_key="fake-key",
        llm_max_images_per_request=4,
    )


@pytest.fixture
def client(settings, fake_model):
    with TestClient(create_app(settings, fake_model)) as test_client:
        yield test_client


def submit(client, data, filename="course.pdf", content_type="application/pdf", **form):
    return client.post(
        "/api/v1/knowledge-trees/jobs",
        files={"file": (filename, data, content_type)},
        data=form,
    )
