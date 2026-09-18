"""使用冻结的候选金标准评测公开合成 fixture。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path

from scripts.run_public_demo import run_demo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "evaluation" / "gold" / "public_fixture_gold.jsonl"
DEFAULT_MANIFEST = ROOT / "evaluation" / "gold" / "public_fixture_gold.manifest.json"
DEFAULT_REPORT = ROOT / "evaluation" / "results" / "public_fixture_eval.json"


def load_gold(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify_frozen_files(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["frozen_files"]:
        path = ROOT / item["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise RuntimeError(f"冻结文件发生变化：{item['path']}")
    return manifest


def index_tree(tree: dict) -> dict[tuple[str, ...], dict]:
    indexed = {}

    def walk(nodes: list[dict], parents: tuple[str, ...] = ()) -> None:
        for node in nodes:
            path = (*parents, node["name"])
            indexed[path] = node
            walk(node["children"], path)

    walk(tree["children"])
    return indexed


def evaluate(tree: dict, gold: list[dict]) -> dict:
    indexed = index_tree(tree)
    results = []
    for item in gold:
        path = tuple(item["path"])
        node = indexed.get(path)
        if item["kind"] == "node":
            passed = node is not None
            actual = "present" if passed else "missing"
        else:
            actual = node.get("scope") if node else None
            passed = actual == item["expected"]
        results.append({"id": item["id"], "passed": passed, "actual": actual})
    passed = sum(item["passed"] for item in results)
    return {
        "assertion_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "accuracy": passed / len(results) if results else 0.0,
        "failures": [item for item in results if not item["passed"]],
    }


async def run_evaluation(gold_path: Path, report_path: Path, manifest_path: Path) -> dict:
    manifest = verify_frozen_files(manifest_path)
    with tempfile.TemporaryDirectory(prefix="knowledge-catalog-public-eval-") as directory:
        demo_dir = Path(directory) / "demo"
        demo = await run_demo(demo_dir)
        tree = json.loads(
            (demo_dir / "artifacts" / "knowledge_tree.json").read_text(encoding="utf-8")
        )
        metrics = evaluate(tree, load_gold(gold_path))
    report = {
        "evaluation_id": f"{manifest['gold_set_id']}-evaluation",
        "evaluated_at": date.today().isoformat(),
        "dataset": {
            "type": "synthetic",
            "fixture": "fixtures/public/synthetic_curriculum.pdf",
            "regression_reference": "evaluation/gold/public_fixture_gold.jsonl",
            "gold_set_id": manifest["gold_set_id"],
            "approval_status": manifest["approval_status"],
            "assertions": metrics["assertion_count"],
        },
        "execution": {
            "runs": 1,
            "semantic_executor": "deterministic_test_double",
            "pipeline": (
                "PDF 渲染 -> Vanguard -> LayoutProfile 审查 -> PromptComposer -> "
                "抽取 -> 协议审查 -> 解析 -> 范围筛选 -> Guard -> 发布"
            ),
            "model_request_count": demo["model_request_count"],
            "image_count": demo["image_count"],
        },
        "metrics": metrics,
        "pipeline_validation": {
            "warning_count": demo["warning_count"],
            "error_count": demo["error_count"],
        },
        "claim_boundary": (
            "本结果衡量合成 fixture 上确定性流水线和契约的可复现性，不衡量真实多模态模型准确率。"
            f"人工审批状态：{manifest['approval_status']}。"
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = asyncio.run(run_evaluation(args.gold, args.report, args.manifest))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["metrics"]["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
