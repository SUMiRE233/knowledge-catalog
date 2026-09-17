import argparse
import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.layout_profile import parse_layout_profile
from app.llm.client import OpenAICompatibleMultimodalClient
from app.llm.prompt_composer import compose_business_prompt
from app.llm.prompts import (
    merge_instruction_for_profile,
    primary_hierarchy_review_instruction,
    primary_level_2_boundaries,
    prompts_for_profile,
)
from app.models import ModelAnalysisRequest, ServiceError
from app.parsing.formatted_text_parser import FormattedTextParser
from app.publishing import write_catalog, write_json
from app.range_resolution import resolve_range
from app.validation.output_guard import OutputGuard


async def run(
    job_dir: Path, output_dir: Path, selected_range: str, document_profile: str
) -> int:
    batch_paths = sorted((job_dir / "output" / "model_batches").glob("batch_*.txt"))
    if not batch_paths:
        print("ERROR: no saved model batches")
        return 2
    batch_outputs = [path.read_text(encoding="utf-8") for path in batch_paths]
    client = OpenAICompatibleMultimodalClient(Settings())
    prepared = json.loads(
        (job_dir / "output" / "prepared_document.json").read_text(encoding="utf-8")
    )
    layout_profile_path = job_dir / "output" / "layout_profile.json"
    if layout_profile_path.is_file():
        profile = parse_layout_profile(
            layout_profile_path.read_text(encoding="utf-8"),
            len(prepared["pages"]),
        )
        merge_prompt = compose_business_prompt(profile).merge
        merge_mode = "layout_profile"
    else:
        _, merge_prompt = prompts_for_profile(document_profile)
        merge_prompt = merge_instruction_for_profile(
            document_profile, merge_prompt, batch_outputs
        )
        merge_mode = "legacy_document_profile"
    try:
        response = await client.analyze(
            ModelAnalysisRequest(
                operation="merge",
                instruction=merge_prompt,
                merge_inputs=batch_outputs,
            )
        )
    except ServiceError as exc:
        print(f"ERROR: {exc.code}: {exc.message}")
        return 3
    if response.finish_reason in {"length", "max_tokens"}:
        print("ERROR: merged output truncated")
        return 4
    if merge_mode == "legacy_document_profile" and document_profile == "primary_dskp_sjkc":
        review_instruction = primary_hierarchy_review_instruction(
            response.text, primary_level_2_boundaries(batch_outputs)
        )
        if review_instruction:
            response = await client.analyze(
                ModelAnalysisRequest(
                    operation="merge",
                    instruction=review_instruction,
                    merge_inputs=[response.text],
                )
            )
            if response.finish_reason in {"length", "max_tokens"}:
                print("ERROR: reviewed output truncated")
                return 4
    source_name = prepared["source_file_name"]
    parsed = FormattedTextParser().parse(
        response.text,
        f"{Path(source_name).stem}知识目录",
    )
    auxiliary = "\n".join(page.get("auxiliary_text") or "" for page in prepared["pages"])
    resolution = resolve_range(parsed.tree, selected_range, auxiliary, "全部")
    report = OutputGuard().validate(
        resolution.tree,
        response.text,
        auxiliary,
        parsed.issues,
        parsed.unresolved,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model_output.txt").write_text(response.text, encoding="utf-8")
    write_json(
        output_dir / "knowledge_tree.json",
        resolution.tree.model_dump(mode="json", exclude_none=False),
    )
    write_catalog(output_dir / "knowledge_catalog.txt", resolution.tree)
    write_json(output_dir / "validation_report.json", report.model_dump(mode="json"))
    print(
        json.dumps(
            {
                "batch_count": len(batch_outputs),
                "merge_mode": merge_mode,
                "finish_reason": response.finish_reason,
                "selected_range": resolution.tree.selected_range,
                "resolution_method": resolution.method,
                "warning_count": report.warning_count,
                "error_count": report.error_count,
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.error_count == 0 else 5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--range", default="全部")
    parser.add_argument(
        "--document-profile",
        choices=("general", "primary_dskp_sjkc"),
        default="general",
    )
    args = parser.parse_args()
    return asyncio.run(
        run(args.job_dir, args.output_dir, args.range, args.document_profile)
    )


if __name__ == "__main__":
    raise SystemExit(main())
