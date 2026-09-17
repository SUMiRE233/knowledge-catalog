import argparse
import json
import sys
from pathlib import Path

import httpx
from wait_for_job import wait

FORBIDDEN_FIELDS = {
    "parent_id", "subject", "page", "source", "source_text", "difficulty",
    "question_type", "ability", "error_type", "prerequisite", "related_to",
    "confidence", "metadata", "description", "learning_objective",
}


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("children", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="使用真实 PDF 和真实多模态模型执行验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--range", default="全部")
    parser.add_argument("--download-dir", type=Path, default=Path("acceptance_output"))
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()
    if not args.file.is_file():
        print(f"ERROR: 文件不存在：{args.file}", file=sys.stderr)
        return 2
    try:
        with args.file.open("rb") as handle:
            response = httpx.post(
                f"{args.base_url.rstrip('/')}/api/v1/knowledge-trees/jobs",
                files={"file": (args.file.name, handle, "application/pdf")},
                data={"range": args.range, "enhance_images": "true"},
                timeout=120,
            )
        if response.status_code != 202:
            print(f"ERROR: 上传失败 {response.status_code}: {response.text}", file=sys.stderr)
            return 3
        payload = response.json()
        job_id = payload["job_id"]
        print(f"job_id={job_id}")
        state = wait(args.base_url, job_id, args.timeout)
        if state["status"] == "failed":
            error = state["error"]
            print(f"ERROR: {error['code']}: {error['message']}", file=sys.stderr)
            return 4
        result_url = f"{args.base_url.rstrip('/')}{payload['result_url']}"
        result_response = httpx.get(result_url, timeout=60)
        result_response.raise_for_status()
        result = result_response.json()
        target = args.download_dir / job_id
        target.mkdir(parents=True, exist_ok=True)
        for name in result["artifacts"]:
            artifact = httpx.get(
                f"{args.base_url.rstrip('/')}/api/v1/knowledge-trees/jobs/{job_id}/artifacts/{name}",
                timeout=120,
            )
            artifact.raise_for_status()
            (target / name).write_bytes(artifact.content)
            print(f"downloaded {name}")
        tree = result["knowledge_tree"]
        nodes = list(walk(tree["children"]))
        forbidden = [
            (node["id"], sorted(set(node) & FORBIDDEN_FIELDS))
            for node in nodes
            if set(node) & FORBIDDEN_FIELDS
        ]
        report = result["validation_report"]
        model_output = (target / "model_output.txt").read_text(encoding="utf-8").strip()
        prepared = json.loads((target / "prepared_document.json").read_text(encoding="utf-8"))
        checks = {
            "page_images_prepared": bool(prepared["pages"])
            and all(
                page["image_path"].endswith(".png")
                for page in prepared["pages"]
            ),
            "protocol_complete": model_output.startswith("BEGIN_KNOWLEDGE_TREE")
            and model_output.endswith("END_KNOWLEDGE_TREE"),
            "tree_nonempty": bool(nodes),
            "no_forbidden_fields": not forbidden,
            "validation_has_no_errors": report["error_count"] == 0,
        }
        summary = {
            "checks": checks,
            "node_count": len(nodes),
            "warnings": report["warning_count"],
            "errors": report["error_count"],
            "output_dir": str(target),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if all(checks.values()) else 5
    except (httpx.HTTPError, TimeoutError, KeyError, ValueError) as exc:
        print(f"ERROR: 验收失败：{exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
