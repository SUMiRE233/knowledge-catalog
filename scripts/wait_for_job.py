import argparse
import sys
import time

import httpx


def wait(base_url: str, job_id: str, timeout: float = 900) -> dict:
    deadline = time.monotonic() + timeout
    url = f"{base_url.rstrip('/')}/api/v1/knowledge-trees/jobs/{job_id}"
    while time.monotonic() < deadline:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        state = response.json()
        print(f"{state['status']} {state['stage']} {state['progress']}%")
        if state["status"] in {"succeeded", "failed"}:
            return state
        time.sleep(1)
    raise TimeoutError("等待任务超时")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    try:
        state = wait(args.base_url, args.job_id, args.timeout)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if state["status"] == "failed":
        print(f"ERROR: {state['error']['code']}: {state['error']['message']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
