import argparse
import asyncio
import time
from pathlib import Path

import fitz

from app.config import Settings
from app.llm.batching import batches
from app.llm.client import OpenAICompatibleMultimodalClient
from app.llm.prompts import ANALYSIS_PROMPT
from app.models import ModelAnalysisRequest, PreparedPage, ServiceError


async def run(pdf_path: Path, pages_dir: Path) -> int:
    settings = Settings()
    client = OpenAICompatibleMultimodalClient(settings)
    document = fitz.open(pdf_path)
    try:
        pages = [
            PreparedPage(
                page_number=index + 1,
                image_path=pages_dir / f"page_{index + 1:04d}.png",
                auxiliary_text=document[index].get_text("text").strip() or None,
            )
            for index in range(document.page_count)
        ]
    finally:
        document.close()
    page_batches = batches(pages, settings.llm_max_images_per_request)
    for number, batch in enumerate(page_batches, 1):
        started = time.perf_counter()
        page_range = f"{batch[0].page_number}-{batch[-1].page_number}"
        try:
            response = await client.analyze(
                ModelAnalysisRequest(
                    instruction=ANALYSIS_PROMPT,
                    pages=batch,
                    batch_number=number,
                    total_batches=len(page_batches),
                )
            )
        except ServiceError as exc:
            elapsed = time.perf_counter() - started
            print(
                f"batch={number}/{len(page_batches)} pages={page_range} "
                f"elapsed={elapsed:.2f}s error={exc.code} message={exc.message}"
            )
            return 1
        elapsed = time.perf_counter() - started
        print(
            f"batch={number}/{len(page_batches)} pages={page_range} "
            f"elapsed={elapsed:.2f}s finish={response.finish_reason} chars={len(response.text)}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.pdf, args.pages_dir))


if __name__ == "__main__":
    raise SystemExit(main())
