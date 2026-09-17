import argparse
import json
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--range", default="全部")
    parser.add_argument(
        "--document-profile",
        choices=("general", "primary_dskp_sjkc"),
        default="general",
    )
    args = parser.parse_args()
    with args.file.open("rb") as handle:
        response = httpx.post(
            f"{args.base_url.rstrip('/')}/api/v1/knowledge-trees/jobs",
            files={"file": (args.file.name, handle)},
            data={
                "range": args.range,
                "document_profile": args.document_profile,
            },
            timeout=60,
        )
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0 if response.status_code == 202 else 1


if __name__ == "__main__":
    raise SystemExit(main())
