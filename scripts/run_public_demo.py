"""Run the real preparation/parser/guard/publisher path on the public fixture."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from app.config import Settings
from app.infrastructure.storage import LocalFileStorage
from app.models import GenerationOptions, ModelAnalysisResponse, StoredFile
from app.pipeline import KnowledgeTreeGenerationService
from app.publishing import PUBLIC_ARTIFACTS
from scripts.build_public_fixture import DEFAULT_OUTPUT, build_fixture

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_OUTPUT = ROOT / "fixtures" / "public" / "expected_model_output.txt"


class PublicFixtureModel:
    """Deterministic test double; this demo does not claim model-quality accuracy."""

    def __init__(self, protocol_path: Path = EXPECTED_OUTPUT):
        self.text = protocol_path.read_text(encoding="utf-8")
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if request.operation == "vanguard":
            profile = {
                "schema_version": "1.0",
                "source_page_count": 2,
                "languages": ["zh"],
                "document_identity": {
                    "root_labels": ["合成初中数学课程纲要（公开评测版）"],
                    "subject": "数学",
                    "education_stage": "初中",
                    "grade_labels": ["七年级"],
                    "volume_labels": ["上册", "下册"],
                    "evidence_pages": [1, 2],
                },
                "range_labels": [
                    {"label": "七年级上册", "evidence_pages": [1]},
                    {"label": "七年级下册", "evidence_pages": [2]},
                ],
                "layouts": [
                    {
                        "layout_id": "synthetic_table",
                        "page_ranges": [{"start": 1, "end": 2}],
                        "layout_kind": "table",
                        "node_levels": [
                            {
                                "level": 1,
                                "role_name": "单元",
                                "document_label": "单元",
                                "visual_cues": ["表格第一列"],
                            },
                            {
                                "level": 2,
                                "role_name": "主题",
                                "document_label": "课程内容",
                                "visual_cues": ["表格第二列"],
                            },
                        ],
                        "scope_sources": [
                            {
                                "document_label": "内容范围",
                                "attaches_to_level": 2,
                                "visual_cues": ["表格第三列"],
                            }
                        ],
                        "excluded_regions": [
                            {
                                "document_label": "学习目标",
                                "reason": "不是课程知识目录",
                            }
                        ],
                        "continuation_rules": [],
                    }
                ],
                "document_exclusions": [],
                "unresolved": [],
            }
            return ModelAnalysisResponse(
                text=json.dumps(profile, ensure_ascii=False), finish_reason="stop"
            )
        return ModelAnalysisResponse(text=self.text, finish_reason="stop")


async def run_demo(output_dir: Path, fixture_pdf: Path = DEFAULT_OUTPUT) -> dict:
    if not fixture_pdf.exists():
        build_fixture(output_path=fixture_pdf)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"输出目录非空：{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = output_dir / "_runtime"
    storage = LocalFileStorage(runtime)
    job_id = "public-fixture-demo"
    input_dir = storage.job_dir(job_id) / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    stored_path = input_dir / fixture_pdf.name
    shutil.copy2(fixture_pdf, stored_path)
    stored = StoredFile(
        job_id=job_id,
        original_filename=fixture_pdf.name,
        safe_filename=fixture_pdf.name,
        path=stored_path,
        content_type="application/pdf",
        size_bytes=stored_path.stat().st_size,
    )
    model = PublicFixtureModel()
    settings = Settings(
        runtime_dir=runtime,
        llm_api_key="synthetic-demo-key",
        llm_model="deterministic-public-fixture",
        llm_max_images_per_request=4,
        pdf_render_dpi=120,
    )
    service = KnowledgeTreeGenerationService(settings, storage, model)
    result = await service.generate(stored, GenerationOptions(selected_range="全部"))
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir()
    for name in PUBLIC_ARTIFACTS:
        shutil.copy2(result.output_dir / name, artifacts_dir / name)
    shutil.rmtree(runtime)
    return {
        "fixture_type": "synthetic",
        "semantic_executor": "deterministic_test_double",
        "model_request_count": len(model.requests),
        "image_count": len(model.requests[0].pages),
        "node_count": result.node_count,
        "leaf_count": result.leaf_node_count,
        "warning_count": result.validation_report.warning_count,
        "error_count": result.validation_report.error_count,
        "artifacts_dir": str(artifacts_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("public_demo_output"))
    parser.add_argument("--fixture", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = asyncio.run(run_demo(args.output_dir, args.fixture))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
