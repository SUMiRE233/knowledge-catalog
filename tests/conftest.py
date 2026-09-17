import json
import re
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
    def __init__(self, text=GOOD_OUTPUT, finish_reason="stop", layout_profile=None):
        self.text = text
        self.finish_reason = finish_reason
        self.layout_profile = layout_profile
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if request.operation == "vanguard":
            total_match = re.search(r"整份 PDF 共 (\d+) 页", request.instruction)
            total = int(total_match.group(1)) if total_match else len(request.pages)
            pages = [page.page_number for page in request.pages]
            profile = self.layout_profile or {
                "schema_version": "1.0",
                "source_page_count": total,
                "languages": ["zh"],
                "document_identity": {
                    "root_labels": ["初一上册"],
                    "subject": "数学",
                    "education_stage": "初中",
                    "grade_labels": ["初一"],
                    "volume_labels": ["上册"],
                    "evidence_pages": [pages[0]],
                },
                "range_labels": [],
                "layouts": [
                    {
                        "layout_id": f"layout_{pages[0]}",
                        "page_ranges": [{"start": min(pages), "end": max(pages)}],
                        "layout_kind": "table",
                        "node_levels": [
                            {
                                "level": 1,
                                "role_name": "章",
                                "document_label": "课程内容",
                                "visual_cues": ["测试布局"],
                            }
                        ],
                        "scope_sources": [],
                        "excluded_regions": [],
                        "continuation_rules": [],
                    }
                ],
                "document_exclusions": [],
                "unresolved": [],
            }
            return ModelAnalysisResponse(
                text=json.dumps(profile, ensure_ascii=False), finish_reason="stop"
            )
        if request.operation == "vanguard_merge":
            profiles = [json.loads(value) for value in request.merge_inputs]
            if "最终审校器" in request.instruction:
                return ModelAnalysisResponse(
                    text=json.dumps(profiles[0], ensure_ascii=False),
                    finish_reason="stop",
                )
            merged = profiles[0]
            merged["layouts"] = [
                layout for profile in profiles for layout in profile["layouts"]
            ]
            return ModelAnalysisResponse(
                text=json.dumps(merged, ensure_ascii=False), finish_reason="stop"
            )
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
