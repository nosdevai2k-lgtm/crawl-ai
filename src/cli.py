"""CLI: run-once, daemon, list-sources."""

from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
import yaml

from .config_loader import load_config
from .export_parquet import export_recent_to_parquet
from .opml_import import feeds_to_yaml_sources, merge_opml_into_config, parse_opml_feeds
from .pipeline import run_source
from .scheduler import build_scheduler, load_context

app = typer.Typer(add_completion=False, help="crawl-ai: crawl + Ollama")


def _config_path(config: Optional[Path]) -> Path:
    path = config if config is not None else Path.cwd() / "config.yaml"
    if not path.is_file():
        raise typer.BadParameter(f"Không tìm thấy file config: {path}")
    return path


@app.command("list-sources")
def list_sources_cmd(
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Đường dẫn config.yaml"
    ),
) -> None:
    """In ra id và type của mọi nguồn trong config."""
    cfg = _config_path(config)
    for s in load_config(cfg):
        typer.echo(f"{s.id}\t{s.type}\t{s.schedule_cron}")


@app.command("run-once")
def run_once_cmd(
    source: Optional[str] = typer.Option(None, "--source", "-s"),
    all_sources: bool = typer.Option(False, "--all", "-a"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Đường dẫn config.yaml"
    ),
) -> None:
    """Chạy pipeline một lần cho một hoặc tất cả nguồn."""
    cfg = _config_path(config)
    sources, storage, settings, client = load_context(cfg)
    if not all_sources and not source:
        typer.echo("Cần --source <id> hoặc --all", err=True)
        raise typer.Exit(code=1)
    targets = sources if all_sources else [s for s in sources if s.id == source]
    if not targets:
        typer.echo(f"Không tìm thấy nguồn: {source}", err=True)
        raise typer.Exit(code=1)
    if all_sources:
        # Nguồn ưu tiên cao (chính thống) chạy trước.
        from .source_trust import sort_sources

        targets = sort_sources(targets)
    for s in targets:
        res = run_source(s, storage, settings, client)
        if res.changed:
            typer.echo(
                f"[OK] {s.id} changed doc_id={res.document_id} hash={res.content_hash[:16]}..."
            )
        else:
            typer.echo(f"[skip] {s.id} reason={res.skipped_reason}")


@app.command("daemon")
def daemon_cmd(
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Đường dẫn config.yaml"
    ),
) -> None:
    """Chạy scheduler nền theo cron trong config."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = _config_path(config)
    sources, storage, settings, client = load_context(cfg)
    sched = build_scheduler(sources, storage, settings, client)
    sched.start()
    typer.echo("Scheduler đã chạy. Ctrl+C để dừng.")

    shutdown = False

    def _handle_signal(signum: int, frame: object) -> None:
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not shutdown:
            time.sleep(1)
    finally:
        sched.shutdown(wait=True)
        if hasattr(storage, "close"):
            storage.close()
        typer.echo("Đã dừng gracefully.")


@app.command("import-opml")
def import_opml_cmd(
    opml: Path = typer.Argument(..., exists=True, readable=True, help="File .opml / .xml"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="config.yaml (tạo mới nếu chưa có)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Chỉ in YAML ra stdout, không ghi file"
    ),
    cron: str = typer.Option(
        "15 * * * *", "--cron", help="schedule_cron cho feed mới (RSS)"
    ),
) -> None:
    """Gộp các outline có xmlUrl từ OPML vào config.yaml (tránh trùng URL/id)."""
    cfg = config if config is not None else Path.cwd() / "config.yaml"
    if dry_run:
        feeds = parse_opml_feeds(opml)
        blob = {"sources": feeds_to_yaml_sources(feeds, schedule_cron=cron)}
        typer.echo(
            yaml.safe_dump(blob, allow_unicode=True, default_flow_style=False, sort_keys=False)
        )
        typer.echo(f"# feeds trong OPML: {len(feeds)}", err=True)
        return
    added, skipped = merge_opml_into_config(opml, cfg, default_cron=cron)
    typer.echo(f"Đã ghi {cfg} — thêm {added}, bỏ qua (trùng) {skipped}.")


@app.command("export-parquet")
def export_parquet_cmd(
    out: Path = typer.Option(
        Path("data/export.parquet"),
        "--out",
        "-o",
        help="Đường dẫn file .parquet",
    ),
    limit: int = typer.Option(10_000, "--limit", "-n", help="Số bản ghi tối đa"),
    truncate_raw: int = typer.Option(
        32_000, "--truncate-raw", help="Cắt raw_text khi xuất (ký tự)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="config.yaml (chỉ để load_context / .env)"
    ),
) -> None:
    """Xuất documents gần đây (SQLite hoặc Mongo theo .env) sang Parquet."""
    cfg = _config_path(config)
    _sources, storage, _settings, _client = load_context(cfg)
    n = export_recent_to_parquet(
        storage, out, limit=limit, truncate_raw=truncate_raw
    )
    typer.echo(f"Đã xuất {n} dòng → {out.resolve()}")


@app.command("auto-crawl")
def auto_crawl_cmd(
    goal: str = typer.Argument(..., help="Mô tả mục tiêu crawl bằng ngôn ngữ tự nhiên"),
    seed_url: Optional[str] = typer.Option(None, "--seed-url", help="URL gốc làm ngữ cảnh"),
    images: bool = typer.Option(False, "--images", help="Tải ảnh cho nguồn URL"),
    expand: bool = typer.Option(False, "--expand", help="Theo link trên trang (text + ảnh, cả web nước ngoài)"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="config.yaml (chỉ để load_context / .env)"
    ),
) -> None:
    """Prompt -> LLM gợi ý nguồn -> tự crawl & lưu."""
    from .auto_crawl import auto_crawl

    cfg = _config_path(config)
    _sources, storage, settings, client = load_context(cfg)
    items = auto_crawl(
        goal, storage, settings, client=client, seed_url=seed_url,
        crawl_images=images, expand_links=expand,
    )
    for it in items:
        label = f"{it.suggestion.get('kind')}: {it.suggestion.get('value')}"
        if it.error:
            typer.echo(f"[err] {label} — {it.error}")
        elif it.result and it.result.changed:
            typer.echo(f"[OK] {label} doc_id={it.result.document_id}")
        else:
            reason = it.result.skipped_reason if it.result else "no_result"
            typer.echo(f"[skip] {label} reason={reason}")


@app.command("harvest-images")
def harvest_images_cmd(
    name: str = typer.Argument(..., help="Tên địa danh/chủ đề (VD: 'Vịnh Hạ Long')"),
    out_dir: Optional[Path] = typer.Option(None, "--out", "-o", help="Thư mục lưu ảnh (mặc định data/images/<slug>)"),
    en_name: Optional[str] = typer.Option(None, "--en", help="Tên tiếng Anh (tăng số ảnh)"),
    target: int = typer.Option(400, "--target", "-n", help="Số ảnh mục tiêu (300-500)"),
) -> None:
    """Thu thập nhiều ảnh cho một địa danh (image-search đa truy vấn → tải → tự duyệt)."""
    from .image_harvest import harvest_landmark
    from .quick_sources import _slug_id
    from .settings import load_settings

    settings = load_settings()
    out = out_dir or (Path("data/images") / _slug_id("", name).strip("_"))
    typer.echo(f"Đang thu thập ảnh '{name}' → {out} (mục tiêu {target})…")
    stats = harvest_landmark(
        name, out, user_agent=settings.user_agent, timeout=settings.http_timeout,
        en_name=en_name, target=target,
    )
    typer.echo(
        f"Xong: lưu {stats['saved']} ảnh (urls={stats['urls']}, "
        f"nhỏ={stats['too_small']}, trùng={stats['dup']}, hỏng={stats['failed']}, "
        f"không-ảnh={stats['not_image']})"
    )


@app.command("harvest-faces")
def harvest_faces_cmd(
    name: str = typer.Argument(..., help="Tên nhân vật (VD: 'Tô Lâm')"),
    out_dir: Optional[Path] = typer.Option(None, "--out", "-o", help="Thư mục lưu (mặc định data/images/human/<slug>)"),
    en_name: Optional[str] = typer.Option(None, "--en", help="Tên tiếng Anh"),
    target: int = typer.Option(120, "--target", "-n", help="Số ảnh mục tiêu"),
) -> None:
    """Thu thập ảnh khuôn mặt/chân dung vào data/images/human/<slug> để search nhân vật."""
    from .face_harvest import default_face_out_dir, harvest_faces
    from .search import build_index
    from .settings import load_settings

    settings = load_settings()
    out = out_dir or default_face_out_dir(name)
    typer.echo(f"Đang thu thập mặt '{name}' → {out} (mục tiêu {target})…")
    stats = harvest_faces(
        name,
        out,
        user_agent=settings.user_agent,
        timeout=settings.http_timeout,
        en_name=en_name,
        target=target,
    )
    build_index()
    typer.echo(
        f"Xong: lưu {stats['saved']} ảnh · index rebuilt (urls={stats['urls']}, "
        f"lọc={stats['off_topic']}, trùng={stats['dup']})"
    )


@app.command("deep-crawl")
def deep_crawl_cmd(
    url: str = typer.Argument(..., help="Start URL for deep crawl"),
    max_depth: int = typer.Option(2, "--depth", "-d", help="Max link depth"),
    max_pages: int = typer.Option(20, "--max-pages", "-n", help="Max pages to crawl"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="config.yaml"
    ),
) -> None:
    """BFS deep crawl: follow internal links from a start URL."""
    from .deep_crawl import deep_crawl_bfs

    cfg = _config_path(config)
    _sources, storage, settings, _client = load_context(cfg)
    typer.echo(f"Deep crawling {url} (depth={max_depth}, max_pages={max_pages})...")
    result = deep_crawl_bfs(
        url,
        max_depth=max_depth,
        max_pages=max_pages,
        user_agent=settings.user_agent,
        timeout=settings.http_timeout,
    )
    typer.echo(f"Crawled {len(result.pages)} pages, {len(result.urls_failed)} failed.")
    for page in result.pages:
        typer.echo(f"  [{page.depth}] {page.url} ({len(page.text)} chars, {len(page.links)} links)")



@app.command("kg-rebuild")
def kg_rebuild_cmd(
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Đường dẫn config.yaml"
    ),
    limit: int = typer.Option(5000, "--limit", "-n", help="Số document gần nhất để index"),
) -> None:
    """Xây lại Knowledge Graph từ documents đã crawl."""
    from .kg.indexer import rebuild_kg_from_store

    cfg = _config_path(config)
    _sources, storage, settings, _client = load_context(cfg)
    stats = rebuild_kg_from_store(settings.database_path, storage, limit=limit)
    typer.echo(f"KG rebuild: {stats['docs']} docs, {stats['entities']} entities, {stats['media']} media")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
