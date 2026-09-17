
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import (
    FakeModel,
    encrypted_pdf_bytes,
    png_bytes,
    scanned_pdf_bytes,
    submit,
    text_pdf_bytes,
)


def status(client, response):
    return client.get(response.json()["status_url"]).json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_standard_pdf_upload_result_and_artifacts(client, fake_model):
    response = submit(client, text_pdf_bytes())
    assert response.status_code == 202
    state = status(client, response)
    assert state["status"] == "succeeded"
    result = client.get(response.json()["result_url"])
    assert result.status_code == 200
    assert result.json()["knowledge_tree"]["children"][0]["name"] == "初一上册"
    assert fake_model.requests[0].operation == "vanguard"
    assert fake_model.requests[0].pages[0].image_path.suffix == ".png"
    assert fake_model.requests[1].operation == "extract"
    artifact = client.get(
        f"/api/v1/knowledge-trees/jobs/{response.json()['job_id']}/artifacts/knowledge_tree.json"
    )
    assert artifact.status_code == 200
    report = client.get(
        f"/api/v1/knowledge-trees/jobs/{response.json()['job_id']}/artifacts/run_report.json"
    ).json()
    assert report["schema_version"] == "1.0.0"
    assert report["generator_version"] == "0.3.0"
    assert report["generation_source"]["filename"] == "course.pdf"
    assert len(report["generation_source"]["sha256"]) == 64
    assert report["layout_profile_schema_version"] == "1.0"
    assert len(report["business_prompt_sha256"]) == 64
    for name in ("vanguard_output.txt", "layout_profile.json", "business_prompt.txt"):
        assert client.get(
            f"/api/v1/knowledge-trees/jobs/{response.json()['job_id']}/artifacts/{name}"
        ).status_code == 200


def test_png_upload(client):
    response = submit(client, png_bytes(), "page.png", "image/png")
    assert status(client, response)["status"] == "succeeded"


def test_existing_document_profile_still_uses_vanguard_prompt(client, fake_model, settings):
    response = submit(
        client,
        png_bytes(),
        "primary.png",
        "image/png",
        document_profile="primary_dskp_sjkc",
    )
    assert status(client, response)["status"] == "succeeded"
    assert fake_model.requests[0].operation == "vanguard"
    assert fake_model.requests[1].operation == "extract"
    assert "layout_profile_json" in fake_model.requests[1].instruction
    output = settings.runtime_dir / "jobs" / response.json()["job_id"] / "output"
    report = json.loads((output / "run_report.json").read_text(encoding="utf-8"))
    assert report["document_profile"] == "primary_dskp_sjkc"
    result = client.get(response.json()["result_url"]).json()
    assert result["knowledge_tree"]["title"] == "初一上册知识目录"


def test_unknown_identity_uses_fixed_root_and_specific_range_is_not_guessed(tmp_path):
    unknown_profile = {
        "schema_version": "1.0",
        "source_page_count": 1,
        "languages": ["zh"],
        "document_identity": {
            "root_labels": [],
            "subject": None,
            "education_stage": None,
            "grade_labels": [],
            "volume_labels": [],
            "evidence_pages": [],
        },
        "range_labels": [],
        "layouts": [
            {
                "layout_id": "layout_1",
                "page_ranges": [{"start": 1, "end": 1}],
                "layout_kind": "list",
                "node_levels": [
                    {
                        "level": 1,
                        "role_name": "课程单元",
                        "document_label": None,
                        "visual_cues": ["标题层级"],
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
    output = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 未知学科
LEVEL 2 | 函数
END_KNOWLEDGE_TREE"""
    settings = Settings(runtime_dir=tmp_path, llm_api_key="x", llm_model="x")
    with TestClient(create_app(settings, FakeModel(output, layout_profile=unknown_profile))) as api:
        all_response = submit(api, png_bytes(), "unknown.png", "image/png")
        assert status(api, all_response)["status"] == "succeeded"
        result = api.get(all_response.json()["result_url"]).json()["knowledge_tree"]
        assert result["title"] == "未知学科知识目录"
        assert result["children"][0]["name"] == "未知学科"

        ranged = submit(
            api,
            png_bytes(),
            "unknown.png",
            "image/png",
            **{"range": "初一上册"},
        )
        ranged_state = status(api, ranged)
        assert ranged_state["status"] == "failed"
        assert ranged_state["error"]["code"] == "RANGE_NOT_FOUND"


def test_unknown_document_profile_is_rejected(client):
    response = submit(
        client,
        png_bytes(),
        "primary.png",
        "image/png",
        document_profile="unknown",
    )
    assert response.status_code == 422


def test_scanned_pdf_upload(client):
    response = submit(client, scanned_pdf_bytes())
    assert status(client, response)["status"] == "succeeded"


def test_empty_file_rejected(client):
    response = submit(client, b"")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_invalid_type_rejected(client):
    response = submit(client, b"hello", "x.txt", "text/plain")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"


@pytest.mark.parametrize(
    ("data", "expected"),
    [(b"%PDF-broken", "INVALID_PDF"), (encrypted_pdf_bytes(), "ENCRYPTED_PDF")],
)
def test_bad_pdf_task_failure(client, data, expected):
    response = submit(client, data)
    state = status(client, response)
    assert state["status"] == "failed"
    assert state["error"]["code"] == expected


def test_file_size_limit(tmp_path):
    settings = Settings(runtime_dir=tmp_path, max_upload_size_mb=1, llm_api_key="x", llm_model="x")
    with TestClient(create_app(settings, FakeModel())) as client:
        response = submit(client, b"x" * (1024 * 1024 + 1), "big.png", "image/png")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_filename_traversal_is_sanitized(client, settings):
    response = submit(client, png_bytes(), "../../evil.png", "image/png")
    job_id = response.json()["job_id"]
    files = list((settings.runtime_dir / "jobs" / job_id / "input").iterdir())
    assert [file.name for file in files] == ["evil.png"]


def test_artifact_traversal_and_unknown_job(client):
    assert client.get("/api/v1/knowledge-trees/jobs/nope").status_code == 404
    response = submit(client, png_bytes(), "x.png", "image/png")
    job_id = response.json()["job_id"]
    assert client.get(
        f"/api/v1/knowledge-trees/jobs/{job_id}/artifacts/not-public.txt"
    ).status_code == 404
    assert client.get(
        f"/api/v1/knowledge-trees/jobs/{job_id}/artifacts/%2e%2e%5cknowledge_tree.json"
    ).status_code in {404, 422}


def test_multi_job_isolation(client, settings):
    first = submit(client, png_bytes("one"), "same.png", "image/png").json()["job_id"]
    second = submit(client, png_bytes("two"), "same.png", "image/png").json()["job_id"]
    assert first != second
    assert (settings.runtime_dir / "jobs" / first / "input" / "same.png").is_file()
    assert (settings.runtime_dir / "jobs" / second / "input" / "same.png").is_file()


def test_range_and_not_found(client, settings):
    good = submit(client, text_pdf_bytes(), **{"range": "初一上"})
    assert status(client, good)["status"] == "succeeded"
    bad = submit(client, text_pdf_bytes(), **{"range": "初三下册"})
    bad_state = status(client, bad)
    assert bad_state["status"] == "succeeded"
    result = client.get(bad.json()["result_url"]).json()
    assert result["knowledge_tree"]["selected_range"] == "初中"
    assert any(
        issue["code"] == "RANGE_FALLBACK_APPLIED"
        for issue in result["validation_report"]["issues"]
    )
    output = settings.runtime_dir / "jobs" / bad.json()["job_id"] / "output"
    assert (output / "prepared_document.json").is_file()
    assert (output / "model_output.txt").read_text(encoding="utf-8") == FakeModel().text
    assert list((output / "model_batches").glob("batch_*.txt"))


@pytest.mark.parametrize(
    ("model", "code"),
    [
        (FakeModel(""), "EMPTY_MODEL_OUTPUT"),
        (FakeModel("BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | A"), "OUTPUT_PROTOCOL_ERROR"),
        (
            FakeModel(
                "BEGIN_KNOWLEDGE_TREE\nLEVEL 1 | A\nEND_KNOWLEDGE_TREE",
                "length",
            ),
            "MODEL_OUTPUT_TRUNCATED",
        ),
    ],
)
def test_model_output_failures(tmp_path, model, code):
    settings = Settings(runtime_dir=tmp_path, llm_api_key="x", llm_model="x")
    with TestClient(create_app(settings, model)) as client:
        response = submit(client, png_bytes(), "x.png", "image/png")
        state = status(client, response)
    assert state["status"] == "failed"
    assert state["error"]["code"] == code


def test_final_tree_rejects_multiple_level_one_roots(tmp_path):
    output = """BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 初一上册
LEVEL 2 | 数与式
LEVEL 1 | 初一下册
LEVEL 2 | 方程
END_KNOWLEDGE_TREE"""
    settings = Settings(runtime_dir=tmp_path, llm_api_key="x", llm_model="x")
    with TestClient(create_app(settings, FakeModel(output))) as client:
        response = submit(client, png_bytes(), "x.png", "image/png")
        state = status(client, response)

    assert state["status"] == "failed"
    assert state["error"]["code"] == "OUTPUT_PROTOCOL_ERROR"
    assert "只能发布一个 LEVEL 1" in state["error"]["message"]


def test_unconfigured_model_job(tmp_path):
    settings = Settings(runtime_dir=tmp_path, llm_api_key=None, llm_model=None)
    with TestClient(create_app(settings)) as client:
        response = submit(client, png_bytes(), "x.png", "image/png")
        state = status(client, response)
    assert state["error"]["code"] == "LLM_NOT_CONFIGURED"


class TimeoutModel:
    async def analyze(self, request):
        from app.models import ServiceError

        raise ServiceError("LLM_TIMEOUT", "模型请求超时", status_code=504)


def test_model_timeout(tmp_path):
    settings = Settings(runtime_dir=tmp_path, llm_api_key="x", llm_model="x")
    with TestClient(create_app(settings, TimeoutModel())) as client:
        response = submit(client, png_bytes(), "x.png", "image/png")
        state = status(client, response)
    assert state["error"]["code"] == "LLM_TIMEOUT"


def test_job_not_ready(client):
    import asyncio

    from app.models import JobRecord

    asyncio.run(client.app.state.jobs.create(JobRecord(job_id="pending")))
    response = client.get("/api/v1/knowledge-trees/jobs/pending/result")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_READY"
