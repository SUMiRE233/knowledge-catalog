"""Fail when tracked files include private inputs, caches, outputs, or likely secrets."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    "runtime/",
    "test_input/",
    "acceptance_output/",
    "generated_knowledge_trees/",
    "output/",
    "tmp/",
    "smoke_output",
    "primary_review_output_",
    "primary_year4_",
)
PRIVATE_ASSET_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".csv",
    ".tsv",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".zip",
    ".7z",
    ".rar",
}
ALLOWED_PUBLIC_ASSETS = {"fixtures/public/synthetic_curriculum.pdf"}
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"^LLM_API_KEY[ \t]*=[ \t]*[^\s<]+", re.MULTILINE),
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def ignored_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-ci", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def main() -> int:
    tracked = tracked_files()
    violations = [f"tracked file is ignored: {item}" for item in ignored_tracked_files()]
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if normalized == ".env" or any(
            normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES
        ):
            violations.append(f"forbidden tracked path: {normalized}")
        if (
            Path(normalized).suffix.lower() in PRIVATE_ASSET_SUFFIXES
            and normalized not in ALLOWED_PUBLIC_ASSETS
        ):
            violations.append(f"non-public document or binary asset: {normalized}")
        path = ROOT / relative
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                violations.append(f"possible secret in: {normalized}")
                break
    if violations:
        print("\n".join(violations))
        return 1
    print(f"repository hygiene passed for {len(tracked)} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
