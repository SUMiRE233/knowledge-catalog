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
ALLOWED_PDFS = {"fixtures/public/synthetic_curriculum.pdf"}
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


def main() -> int:
    violations = []
    for relative in tracked_files():
        normalized = relative.replace("\\", "/")
        if normalized == ".env" or any(
            normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES
        ):
            violations.append(f"forbidden tracked path: {normalized}")
        if normalized.lower().endswith(".pdf") and normalized not in ALLOWED_PDFS:
            violations.append(f"non-public PDF: {normalized}")
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
    print(f"repository hygiene passed for {len(tracked_files())} tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
