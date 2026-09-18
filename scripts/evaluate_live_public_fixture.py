"""使用已批准的合成金标准评测当前真实多模态模型。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.infrastructure.storage import LocalFileStorage
from app.llm.client import OpenAICompatibleMultimodalClient
from app.models import GenerationOptions, ModelAnalysisRequest, StoredFile
from app.pipeline import KnowledgeTreeGenerationService
from app.publishing import PUBLIC_ARTIFACTS
from scripts.evaluate_public_fixture import (
    DEFAULT_GOLD,
    DEFAULT_MANIFEST,
    evaluate,
    index_tree,
    load_gold,
    verify_frozen_files,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "fixtures" / "public" / "synthetic_curriculum.pdf"
DEFAULT_REPORT = ROOT / "evaluation" / "results" / "public_fixture_live_eval.json"


class CountingClient:
    def __init__(self, client: OpenAICompatibleMultimodalClient):
        self.client = client
        self.operations: list[str] = []

    async def analyze(self, request: ModelAnalysisRequest):
        self.operations.append(request.operation)
        return await self.client.analyze(request)


def compare_complete_tree(tree: dict, gold: list[dict]) -> dict:
    indexed = index_tree(tree)
    actual_paths = set(indexed)
    expected_paths = {
        tuple(item["path"]) for item in gold if item["kind"] == "node"
    }
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    matched = len(expected_paths & actual_paths)
    precision = matched / len(actual_paths) if actual_paths else 0.0
    recall = matched / len(expected_paths) if expected_paths else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    scope_items = [item for item in gold if item["kind"] == "scope"]
    scope_passed = sum(
        indexed.get(tuple(item["path"]), {}).get("scope") == item["expected"]
        for item in scope_items
    )
    return {
        "expected_node_count": len(expected_paths),
        "actual_node_count": len(actual_paths),
        "matched_node_count": matched,
        "node_precision": precision,
        "node_recall": recall,
        "node_f1": f1,
        "missing_paths": [list(path) for path in missing],
        "extra_paths": [list(path) for path in extra],
        "scope_count": len(scope_items),
        "scope_passed_count": scope_passed,
        "scope_exact_accuracy": scope_passed / len(scope_items) if scope_items else 0.0,
        "unique_root": len(tree.get("children", [])) == 1,
        "exact_tree_match": not missing and not extra,
    }


async def run_live_evaluation(
    fixture: Path,
    gold_path: Path,
    manifest_path: Path,
    report_path: Path,
    output_dir: Path,
) -> dict:
    manifest = verify_frozen_files(manifest_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"输出目录非空：{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(runtime_dir=output_dir / "_runtime")
    client = CountingClient(OpenAICompatibleMultimodalClient(settings))
    storage = LocalFileStorage(settings.runtime_dir)
    job_id = f"live-public-gold-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    input_dir = storage.job_dir(job_id) / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    stored_path = input_dir / fixture.name
    shutil.copy2(fixture, stored_path)
    stored = StoredFile(
        job_id=job_id,
        original_filename=fixture.name,
        safe_filename=fixture.name,
        path=stored_path,
        content_type="application/pdf",
        size_bytes=stored_path.stat().st_size,
    )
    started = datetime.now(UTC)
    result = await KnowledgeTreeGenerationService(settings, storage, client).generate(
        stored,
        GenerationOptions(selected_range="全部"),
    )
    finished = datetime.now(UTC)
    tree = result.tree.model_dump(mode="json")
    gold = load_gold(gold_path)
    assertions = evaluate(tree, gold)
    completeness = compare_complete_tree(tree, gold)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir()
    for name in PUBLIC_ARTIFACTS:
        shutil.copy2(result.output_dir / name, artifacts_dir / name)
    report = {
        "evaluation_id": f"{manifest['gold_set_id']}-live-evaluation",
        "evaluated_at": finished.isoformat(),
        "dataset": {
            "type": "synthetic",
            "fixture": "fixtures/public/synthetic_curriculum.pdf",
            "gold_set_id": manifest["gold_set_id"],
            "approval_status": manifest["approval_status"],
        },
        "execution": {
            "semantic_executor": "live_multimodal_model",
            "model_name": settings.llm_model,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": round((finished - started).total_seconds(), 3),
            "model_request_count": len(client.operations),
            "operations": client.operations,
        },
        "gold_assertions": assertions,
        "complete_tree": completeness,
        "pipeline_validation": result.validation_report.model_dump(mode="json"),
        "passed": (
            assertions["failed_count"] == 0
            and completeness["exact_tree_match"]
            and completeness["scope_exact_accuracy"] == 1.0
            and completeness["unique_root"]
            and result.validation_report.error_count == 0
        ),
        "claim_boundary": (
            "本结果是在评测设计已知的合成 PDF 上进行的一次 temperature-zero 真实模型运行，"
            "不代表模型在未见真实 PDF 上的泛化能力。"
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "tmp" / "live_public_gold_evaluation",
    )
    args = parser.parse_args()
    report = asyncio.run(
        run_live_evaluation(
            args.fixture,
            args.gold,
            args.manifest,
            args.report,
            args.output_dir,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
