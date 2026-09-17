import argparse
import json
import sys
from pathlib import Path

import httpx
from wait_for_job import wait

PROFILE = "primary_dskp_sjkc"
FORBIDDEN_FIELDS = {
    "ability",
    "confidence",
    "description",
    "difficulty",
    "error_type",
    "learning_objective",
    "metadata",
    "page",
    "parent_id",
    "prerequisite",
    "question_type",
    "related_to",
    "source",
    "source_text",
    "subject",
}
EXCLUDED_NAME_MARKERS = {
    "21 世纪技能",
    "人文",
    "价值观",
    "国家原则",
    "学习目标",
    "教育哲学",
    "教师职责",
    "表现标准",
    "评估",
    "课题目标",
    "跨课程元素",
}
PERFORMANCE_SCOPE_MARKERS = {
    "以创意和创新的方式",
    "级别 诠释",
    "表现标准",
}
BLOCKING_VALIDATION_CODES = {
    "DUPLICATE_SCOPE",
    "SCOPE_WITHOUT_NODE",
    "UNKNOWN_PROTOCOL_LINE",
}


def walk(nodes: list[dict]):
    for node in nodes:
        yield node
        yield from walk(node.get("children", []))


def inspect_tree(tree: dict) -> dict:
    nodes = list(walk(tree.get("children", [])))
    forbidden = [
        {"id": node.get("id"), "fields": sorted(set(node) & FORBIDDEN_FIELDS)}
        for node in nodes
        if set(node) & FORBIDDEN_FIELDS
    ]
    excluded = [
        {"id": node.get("id"), "name": node.get("name")}
        for node in nodes
        if any(marker in str(node.get("name", "")) for marker in EXCLUDED_NAME_MARKERS)
    ]
    suspicious_scopes = [
        {"id": node.get("id"), "scope": node.get("scope")}
        for node in nodes
        if any(
            marker in str(node.get("scope", ""))
            for marker in PERFORMANCE_SCOPE_MARKERS
        )
    ]
    leaves = [node for node in nodes if not node.get("children")]
    return {
        "node_count": len(nodes),
        "leaf_count": sum(not node.get("children") for node in nodes),
        "scope_nonempty_count": sum(bool(node.get("scope")) for node in nodes),
        "leaf_without_scope_count": sum(not node.get("scope") for node in leaves),
        "forbidden_fields": forbidden,
        "excluded_name_hits": excluded,
        "suspicious_scope_hits": suspicious_scopes,
        "passed": (
            bool(nodes)
            and not forbidden
            and not excluded
            and not suspicious_scopes
            and all(node.get("scope") for node in leaves)
        ),
    }


def generate_one(
    client: httpx.Client,
    base_url: str,
    source: Path,
    download_dir: Path,
    timeout: float,
) -> dict:
    with source.open("rb") as handle:
        response = client.post(
            f"{base_url}/api/v1/knowledge-trees/jobs",
            files={"file": (source.name, handle, "application/pdf")},
            data={
                "range": "全部",
                "enhance_images": "true",
                "use_ocr_fallback": "false",
                "document_profile": PROFILE,
            },
            timeout=120,
        )
    if response.status_code != 202:
        raise RuntimeError(f"上传失败 HTTP {response.status_code}: {response.text}")

    submitted = response.json()
    job_id = submitted["job_id"]
    print(f"{source.name}: job_id={job_id}")
    state = wait(base_url, job_id, timeout)
    if state["status"] != "succeeded":
        error = state.get("error") or {}
        raise RuntimeError(f"{error.get('code', 'UNKNOWN')}: {error.get('message', '任务失败')}")

    result_response = client.get(f"{base_url}{submitted['result_url']}", timeout=60)
    result_response.raise_for_status()
    result = result_response.json()
    target = download_dir / job_id
    target.mkdir(parents=True, exist_ok=False)
    for artifact_name in result["artifacts"]:
        artifact = client.get(
            f"{base_url}/api/v1/knowledge-trees/jobs/{job_id}/artifacts/{artifact_name}",
            timeout=120,
        )
        artifact.raise_for_status()
        (target / artifact_name).write_bytes(artifact.content)

    inspection = inspect_tree(result["knowledge_tree"])
    validation = result["validation_report"]
    blocking_issues = [
        issue for issue in validation["issues"] if issue["code"] in BLOCKING_VALIDATION_CODES
    ]
    summary = {
        "source_file": str(source),
        "job_id": job_id,
        "output_dir": str(target),
        "profile": PROFILE,
        "validation_warning_count": validation["warning_count"],
        "validation_error_count": validation["error_count"],
        "blocking_validation_issues": blocking_issues,
        **inspection,
    }
    summary["passed"] = (
        summary["passed"] and validation["error_count"] == 0 and not blocking_issues
    )
    (target / "primary_profile_check.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量提交马来西亚华文小学数学 DSKP，生成知识树"
    )
    parser.add_argument("files", nargs="+", type=Path, help="一至多个 DSKP PDF")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--download-dir", type=Path, default=Path("primary_output"))
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args()

    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        print(f"ERROR: 文件不存在: {', '.join(missing)}", file=sys.stderr)
        return 2
    non_pdf = [str(path) for path in args.files if path.suffix.lower() != ".pdf"]
    if non_pdf:
        print(f"ERROR: 仅接受 PDF: {', '.join(non_pdf)}", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    args.download_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    failures = []
    with httpx.Client() as client:
        for source in args.files:
            try:
                summary = generate_one(
                    client,
                    base_url,
                    source.resolve(),
                    args.download_dir,
                    args.timeout,
                )
                summaries.append(summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            except (httpx.HTTPError, TimeoutError, KeyError, ValueError, RuntimeError) as exc:
                failures.append({"source_file": str(source), "error": str(exc)})
                print(f"ERROR: {source.name}: {exc}", file=sys.stderr)

    batch_summary = {
        "profile": PROFILE,
        "succeeded": len(summaries),
        "failed": len(failures),
        "results": summaries,
        "failures": failures,
    }
    (args.download_dir / "primary_generation_summary.json").write_text(
        json.dumps(batch_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if failures:
        return 4
    return 0 if all(item["passed"] for item in summaries) else 5


if __name__ == "__main__":
    raise SystemExit(main())
