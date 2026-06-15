"""APScheduler wiring from config cron expressions."""

from __future__ import annotations

import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import OpenAI

from .config_loader import SourceConfig, load_config
from .document_store import DocumentStore, get_document_store
from .llm import make_llm_client
from .pipeline import run_source
from .settings import Settings, load_settings

logger = logging.getLogger(__name__)


def build_scheduler(
    sources: list[SourceConfig],
    storage: DocumentStore,
    settings: Settings,
    client: OpenAI | None = None,
) -> BackgroundScheduler:
    sched = BackgroundScheduler()
    llm_client = client or make_llm_client(settings)

    for src in sources:
        trigger = CronTrigger.from_crontab(src.schedule_cron)

        def make_runner(s: SourceConfig):
            def run() -> None:
                try:
                    res = run_source(s, storage, settings, llm_client)
                    if res.changed:
                        logger.info(
                            "Updated source=%s doc_id=%s hash=%s",
                            res.source_id,
                            res.document_id,
                            res.content_hash[:12],
                        )
                    else:
                        logger.info(
                            "Skip source=%s reason=%s",
                            res.source_id,
                            res.skipped_reason,
                        )
                except Exception:
                    logger.exception("Job failed for source=%s", s.id)

            return run

        sched.add_job(
            make_runner(src),
            trigger=trigger,
            id=f"source:{src.id}",
            replace_existing=True,
        )
    return sched


def load_context(
    config_path: Path,
) -> tuple[list[SourceConfig], DocumentStore, Settings, OpenAI]:
    settings = load_settings()
    sources = load_config(config_path)
    storage = get_document_store(settings)
    client = make_llm_client(settings)
    return sources, storage, settings, client
