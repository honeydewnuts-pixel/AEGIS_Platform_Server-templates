"""
Lightweight concurrent load probe for /aegis/analyze.

Usage:
  AEGIS_BASE_URL=https://... AEGIS_API_KEY=... AEGIS_ACCOUNT_ID=acc1 \
    python tests/load/bench_analyze.py --concurrency 20 --requests 100
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
import statistics
import time

import httpx


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


async def one(client: httpx.AsyncClient, url: str, key: str, account: str) -> tuple[int, float]:
    t0 = time.perf_counter()
    files = {"image": ("t.png", io.BytesIO(_tiny_png()), "image/png")}
    data = {"account_id": account, "captured_at_ms": str(int(time.time() * 1000))}
    r = await client.post(url, headers={"X-API-Key": key}, files=files, data=data, timeout=60.0)
    return r.status_code, (time.perf_counter() - t0) * 1000


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--requests", type=int, default=50)
    args = p.parse_args()
    base = os.environ["AEGIS_BASE_URL"].rstrip("/")
    key = os.environ["AEGIS_API_KEY"]
    account = os.environ.get("AEGIS_ACCOUNT_ID", "bench")
    url = f"{base}/aegis/analyze"
    sem = asyncio.Semaphore(args.concurrency)
    results: list[tuple[int, float]] = []

    async with httpx.AsyncClient() as client:
        async def run():
            async with sem:
                results.append(await one(client, url, key, account))

        await asyncio.gather(*[run() for _ in range(args.requests)])

    codes = [c for c, _ in results]
    lats = [l for _, l in results]
    print(f"requests={len(results)} concurrency={args.concurrency}")
    print(f"status counts: { {c: codes.count(c) for c in sorted(set(codes))} }")
    print(f"latency_ms avg={statistics.mean(lats):.1f} p50={statistics.median(lats):.1f} max={max(lats):.1f}")


if __name__ == "__main__":
    asyncio.run(main())
