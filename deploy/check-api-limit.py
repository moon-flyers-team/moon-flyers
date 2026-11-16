"""Exercise API throttling on an isolated test stack, never on a live deployment."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def check(base_url: str) -> None:
    def status(index: int, path: str = "/api/health") -> int:
        # These client-controlled headers must not create new rate-limit buckets.
        request = Request(base_url + path, headers={
            "X-Forwarded-For": f"198.51.100.{index % 254 + 1}",
            "X-Real-IP": f"203.0.113.{index % 254 + 1}",
            "Host": f"client-{index}.invalid",
        })
        try:
            with urlopen(request, timeout=10) as response:
                return response.status
        except HTTPError as error:
            error.close()
            return error.code

    # A fresh stack must allow the dashboard's initial multi-site request burst.
    for index in range(40):
        if status(index) != 200:
            raise AssertionError("Normal dashboard-sized burst was rejected")
    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(status, range(240)))
    if 429 not in statuses or set(statuses) - {200, 429}:
        raise AssertionError(f"Expected throttling with only 200/429 responses: {set(statuses)}")
    if status(0, "/healthz") != 200 or status(0, "/") != 200:
        raise AssertionError("API throttling must not block frontend health or static HTML")
    time.sleep(9)  # Drain the 80-request burst at 10 requests/second.
    if status(0) != 200:
        raise AssertionError("API did not recover after the burst drained")
    print("API rate limit passed: normal burst, spoofed headers, 429, static access, recovery")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Loopback URL of an isolated test stack")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
        parser.error("Use an explicit http://127.0.0.1:PORT isolated test origin")
    check(args.base_url.rstrip("/"))
