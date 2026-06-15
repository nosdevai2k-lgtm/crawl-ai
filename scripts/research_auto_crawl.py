#!/usr/bin/env python3
"""
Crawl định kỳ mọi nguồn trong YAML — chạy nền để "đọc báo" / gom dữ liệu nghiên cứu.

Chạy từ thư mục gốc repo (có `src/`, `.env` tuỳ chọn):

  .venv\\Scripts\\python.exe scripts\\research_auto_crawl.py --config config.research_digest.example.yaml --interval-sec 1800

Một vòng rồi thoát (phù hợp cron / Task Scheduler):

  .venv\\Scripts\\python.exe scripts\\research_auto_crawl.py --config config.yaml --once

Tuỳ chọn mới:
  --workers N       Số luồng xử lý song song (mặc định 4)
  --max-retries N   Số lần retry mỗi source khi lỗi (mặc định 2)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.pipeline import run_source  # noqa: E402
from src.scheduler import load_context  # noqa: E402

# Graceful shutdown event
_shutdown = threading.Event()


def _install_signal_handlers() -> None:
    """Set shutdown event on SIGINT/SIGTERM for graceful exit."""
    def _handler(signum, frame):
        logging.info("Nhận tín hiệu %s — đang dừng sau khi hoàn tất task hiện tại...", signum)
        _shutdown.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


@dataclass
class RoundStats:
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _process_source(src, storage, settings, client, max_retries: int) -> tuple[str, str, str | None]:
    """Process a single source with retry. Returns (source_id, status, detail)."""
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        if _shutdown.is_set():
            return (src.id, "skipped", "shutdown_requested")
        try:
            res = run_source(src, storage, settings, client)
            if res.changed:
                return (src.id, "ok", f"doc_id={res.document_id} hash={( res.content_hash or '')[:12]}")
            return (src.id, "skipped", res.skipped_reason)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                backoff = 2 ** attempt
                logging.warning("RETRY source=%s attempt=%d/%d backoff=%ds err=%s", src.id, attempt, max_retries, backoff, e)
                # Interruptible backoff
                if _shutdown.wait(timeout=backoff):
                    return (src.id, "skipped", "shutdown_during_retry")
    logging.exception("ERR source=%s after %d attempts", src.id, max_retries, exc_info=last_err)
    return (src.id, "failed", str(last_err))


def _run_round(sources, storage, settings, client, *, workers: int, max_retries: int) -> RoundStats:
    stats = RoundStats()
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_source, src, storage, settings, client, max_retries): src
            for src in sources
        }
        for fut in as_completed(futures):
            if _shutdown.is_set():
                pool.shutdown(wait=False, cancel_futures=True)
                break
            src_id, status, detail = fut.result()
            if status == "ok":
                stats.ok += 1
                logging.info("OK   source=%s %s", src_id, detail)
            elif status == "skipped":
                stats.skipped += 1
                logging.info("SKIP source=%s reason=%s", src_id, detail)
            else:
                stats.failed += 1
                stats.errors.append(f"{src_id}: {detail}")
                logging.error("FAIL source=%s err=%s", src_id, detail)

    elapsed = time.perf_counter() - t0
    logging.info(
        "── Round done: %d ok, %d skipped, %d failed | %.1fs elapsed ──",
        stats.ok, stats.skipped, stats.failed, elapsed,
    )
    return stats


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser(
        description="Vòng lặp crawl song song: mỗi nguồn trong YAML gọi run_source."
    )
    ap.add_argument("--config", type=Path, required=True, help="Đường dẫn config.yaml")
    ap.add_argument("--interval-sec", type=int, default=3600, help="Giây nghỉ giữa hai vòng (mặc định 3600).")
    ap.add_argument("--once", action="store_true", help="Chỉ chạy một vòng rồi thoát.")
    ap.add_argument("--workers", type=int, default=4, help="Số luồng song song (mặc định 4).")
    ap.add_argument("--max-retries", type=int, default=2, help="Retry mỗi source khi lỗi (mặc định 2).")
    args = ap.parse_args()

    cfg = args.config.resolve()
    if not cfg.is_file():
        logging.error("Không thấy file: %s", cfg)
        return 2

    env_path = ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)

    sources, storage, settings, client = load_context(cfg)
    if not sources:
        logging.warning("Không có sources trong %s", cfg)
        return 1

    _install_signal_handlers()
    workers = max(1, args.workers)
    max_retries = max(1, args.max_retries)

    logging.info("Loaded %d sources from %s (workers=%d, retries=%d)", len(sources), cfg, workers, max_retries)

    if args.once:
        _run_round(sources, storage, settings, client, workers=workers, max_retries=max_retries)
        return 0

    interval = max(60, args.interval_sec)
    logging.info("Lặp mỗi %ds (Ctrl+C để dừng gracefully).", interval)

    while not _shutdown.is_set():
        _run_round(sources, storage, settings, client, workers=workers, max_retries=max_retries)
        # Interruptible sleep — wakes immediately on shutdown signal
        _shutdown.wait(timeout=interval)

    logging.info("Shutdown hoàn tất.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
