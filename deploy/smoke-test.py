"""Check a complete deployment through its frontend proxy (stdlib only)."""

import argparse
import json
import time
from urllib.error import URLError
from urllib.request import urlopen


def check(base_url: str) -> None:
    def get(path: str) -> str:
        with urlopen(f"{base_url.rstrip('/')}{path}", timeout=10) as response:
            return response.read().decode("utf-8")

    if "<html" not in get("/").lower():
        raise ValueError("Frontend did not return HTML")
    if get("/healthz").strip() != "ok":
        raise ValueError("Frontend health check failed")
    if json.loads(get("/api/health")) != {"status": "ok"}:
        raise ValueError("Backend health check failed")
    schema = json.loads(get("/api/openapi.json"))
    if "/health" not in schema.get("paths", {}):
        raise ValueError("Backend OpenAPI schema is missing /health")
    if {"url": "/api"} not in schema.get("servers", []):
        raise ValueError("Backend OpenAPI root path must be /api")
    if "/api/openapi.json" not in get("/api/docs"):
        raise ValueError("API documentation uses an incorrect schema URL")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    for attempt in range(args.attempts):
        try:
            check(args.base_url)
        except (URLError, OSError, ValueError) as error:
            if attempt == args.attempts - 1:
                raise SystemExit(f"Smoke test failed: {error}") from error
            time.sleep(5)
        else:
            print(f"Smoke test passed: {args.base_url}")
            return


if __name__ == "__main__":
    main()
