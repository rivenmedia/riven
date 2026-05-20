"""Export/import human-readable library backups as ZIP bundles on disk."""

from __future__ import annotations

import csv
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kink import di
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from program.apis.tmdb_api import TMDBApi
from program.apis.tvdb_api import TVDBApi
from program.db.db import db_session
from program.db.db_functions import item_exists_by_any_id
from program.media.item import Episode, MediaItem, Season, Show
from program.media.stream import Stream
from program.managers.event_manager import Event
from program.program import Program
from program.settings import settings_manager
from program.utils import data_dir_path, get_version
from program.utils.logging import logger

BACKUPS_DIR = data_dir_path / "backups"
FORMAT_VERSION = 1
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
PIN_LOOKUP_RETRIES = 3
PIN_LOOKUP_DELAY_SECONDS = 5.0

LIBRARY_MOVIES = "library/movies.csv"
LIBRARY_TV_SHOWS = "library/tv-shows.csv"
LIBRARY_PINNED_EPISODES = "library/pinned-episodes.csv"
STREAMS_DIR = "streams"
MANIFEST_FILE = "manifest.json"
SETTINGS_FILE = "settings.json"

LIBRARY_HEADERS = ("title", "year", "imdb_id")
PINNED_EPISODE_HEADERS = (
    "title",
    "year",
    "imdb_id",
    "item_type",
    "season_number",
    "episode_number",
    "show_imdb_id",
)
STREAM_PIN_HEADERS = (
    "imdb_id",
    "item_type",
    "season_number",
    "episode_number",
    "show_imdb_id",
    "infohash",
    "torrent_id",
    "raw_title",
    "parsed_title",
    "resolution",
    "original_filename",
)

SENSITIVE_KEY_RE = re.compile(
    r"(api_key|apikey|token|password|secret|_key$)",
    re.IGNORECASE,
)


@dataclass
class ExportBundleOptions:
    include_settings: bool = True
    redact_secrets: bool = False


@dataclass
class ImportBundleOptions:
    restore_settings: bool = False
    skip_existing_titles: bool = True
    restore_pins: bool = True


@dataclass
class ExportResult:
    success: bool
    filename: str | None = None
    message: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    success: bool
    message: str = ""
    added_movies: int = 0
    added_shows: int = 0
    skipped_titles: int = 0
    pins_restored: int = 0
    pins_failed: int = 0
    errors: list[str] = field(default_factory=list)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_provider_filename(provider: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", provider.strip().lower())
    return safe or "unknown"


def _csv_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def is_sensitive_field_name(name: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(name))


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=_json_default)


def redact_settings(data: Any) -> Any:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if is_sensitive_field_name(key):
                out[key] = "***REDACTED***"
            else:
                out[key] = redact_settings(value)
        return out
    if isinstance(data, list):
        return [redact_settings(v) for v in data]
    return data


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(headers), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({h: _csv_str(row.get(h)) for h in headers})


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _parse_int(value: str | None) -> int | None:
    if not value or not str(value).strip().isdigit():
        return None
    return int(str(value).strip())


def _item_year(item: MediaItem) -> int | None:
    if item.year is not None:
        return int(item.year)
    if item.aired_at:
        return item.aired_at.year
    return None


def _find_stream_row(item: MediaItem) -> Stream | None:
    if not item.active_stream:
        return None
    active_hash = item.active_stream.infohash.lower()
    for stream in list(item.streams) + list(item.blacklisted_streams):
        if stream.infohash.lower() == active_hash:
            return stream
    return None


def _provider_for_pin(item: MediaItem, default_provider: str | None) -> str:
    entry = item.media_entry
    if entry and entry.provider:
        return str(entry.provider)
    if default_provider:
        return default_provider
    return "unknown"


def _pin_row_for_item(
    item: MediaItem,
    default_provider: str | None,
) -> tuple[str, dict[str, Any]] | None:
    if not item.active_stream:
        return None

    stream = _find_stream_row(item)
    show_imdb = item.get_top_imdb_id() or ""
    season_number = ""
    episode_number = ""
    imdb_id = item.imdb_id or ""

    if isinstance(item, Season):
        season_number = _csv_str(item.number)
        imdb_id = imdb_id or show_imdb
    elif isinstance(item, Episode):
        season_number = _csv_str(item.parent.number)
        episode_number = _csv_str(item.number)
        imdb_id = imdb_id or ""

    row = {
        "imdb_id": imdb_id,
        "item_type": item.type,
        "season_number": season_number,
        "episode_number": episode_number,
        "show_imdb_id": show_imdb if item.type in ("season", "episode") else "",
        "infohash": item.active_stream.infohash,
        "torrent_id": _csv_str(item.active_stream.id),
        "raw_title": stream.raw_title if stream else "",
        "parsed_title": stream.parsed_title if stream else "",
        "resolution": stream.resolution if stream else "",
        "original_filename": (
            item.media_entry.original_filename if item.media_entry else ""
        ),
    }
    provider = _provider_for_pin(item, default_provider)
    return provider, row


def _default_downloader_provider() -> str | None:
    program = _get_program()
    if (
        program.services
        and program.services.downloader
        and program.services.downloader.service
    ):
        return program.services.downloader.service.key
    return None


def _get_program() -> Program:
    return di[Program]


def _get_tmdb() -> TMDBApi:
    return di[TMDBApi]


def _get_tvdb() -> TVDBApi | None:
    try:
        return di[TVDBApi]
    except Exception:
        return None


def export_bundle(options: ExportBundleOptions) -> ExportResult:
    logger.info(
        "[backup] Starting export (include_settings={}, redact_secrets={})",
        options.include_settings,
        options.redact_secrets,
    )
    warnings: list[str] = []
    default_provider = _default_downloader_provider()
    if default_provider:
        logger.info("[backup] Default downloader provider for unpinned entries: {}", default_provider)

    movie_rows: list[dict[str, Any]] = []
    show_rows: list[dict[str, Any]] = []
    pinned_episode_rows: list[dict[str, Any]] = []
    pins_by_provider: dict[str, list[dict[str, Any]]] = {}

    with db_session() as session:
        top_level = (
            session.execute(
                select(MediaItem).where(MediaItem.type.in_(["movie", "show"]))
            )
            .scalars()
            .all()
        )

        logger.info("[backup] Querying library: {} top-level items", len(top_level))

        for item in top_level:
            if not item.imdb_id:
                msg = f"Skipped {item.type} id={item.id} (no imdb_id)"
                warnings.append(msg)
                logger.warning("[backup] {}", msg)
                continue
            row = {
                "title": item.title,
                "year": _csv_str(_item_year(item)),
                "imdb_id": item.imdb_id,
            }
            if item.type == "movie":
                movie_rows.append(row)
            else:
                show_rows.append(row)

        pinned_items = (
            session.execute(
                select(MediaItem)
                .options(
                    selectinload(MediaItem.streams),
                    selectinload(MediaItem.blacklisted_streams),
                    selectinload(MediaItem.filesystem_entries),
                )
                .where(MediaItem.active_stream.isnot(None))
            )
            .unique()
            .scalars()
            .all()
        )

        for item in pinned_items:
            pin = _pin_row_for_item(item, default_provider)
            if not pin:
                continue
            provider, row = pin
            pins_by_provider.setdefault(provider, []).append(row)

            if item.type in ("season", "episode"):
                pinned_episode_rows.append(
                    {
                        "title": item.title,
                        "year": _csv_str(_item_year(item)),
                        "imdb_id": item.imdb_id or "",
                        "item_type": item.type,
                        "season_number": row["season_number"],
                        "episode_number": row["episode_number"],
                        "show_imdb_id": row["show_imdb_id"],
                    }
                )

        logger.info(
            "[backup] Collected {} movies, {} shows, {} pinned items "
            "({} providers)",
            len(movie_rows),
            len(show_rows),
            sum(len(v) for v in pins_by_provider.values()),
            len(pins_by_provider),
        )

    movie_rows.sort(key=lambda r: (r.get("title") or "").lower())
    show_rows.sort(key=lambda r: (r.get("title") or "").lower())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = BACKUPS_DIR / f"_export_{timestamp}"
    work_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[backup] Writing CSVs to temp dir {}", work_dir)

    try:
        _write_csv(work_dir / LIBRARY_MOVIES, LIBRARY_HEADERS, movie_rows)
        logger.info("[backup] Wrote {} ({})", LIBRARY_MOVIES, len(movie_rows))
        _write_csv(work_dir / LIBRARY_TV_SHOWS, LIBRARY_HEADERS, show_rows)
        logger.info("[backup] Wrote {} ({})", LIBRARY_TV_SHOWS, len(show_rows))
        _write_csv(
            work_dir / LIBRARY_PINNED_EPISODES,
            PINNED_EPISODE_HEADERS,
            pinned_episode_rows,
        )
        logger.info(
            "[backup] Wrote {} ({})",
            LIBRARY_PINNED_EPISODES,
            len(pinned_episode_rows),
        )

        stream_paths: list[str] = []
        for provider, rows in sorted(pins_by_provider.items()):
            rel = f"{STREAMS_DIR}/{_sanitize_provider_filename(provider)}.csv"
            _write_csv(work_dir / rel, STREAM_PIN_HEADERS, rows)
            stream_paths.append(rel)
            logger.info("[backup] Wrote {} ({} pins)", rel, len(rows))

        if options.include_settings:
            settings_data = settings_manager.settings.model_dump(mode="json")
            if options.redact_secrets:
                settings_data = redact_settings(settings_data)
            (work_dir / SETTINGS_FILE).write_text(
                _json_dumps(settings_data),
                encoding="utf-8",
            )
            logger.info(
                "[backup] Wrote {} (redact_secrets={})",
                SETTINGS_FILE,
                options.redact_secrets,
            )

        manifest: dict[str, Any] = {
            "format_version": FORMAT_VERSION,
            "riven_version": get_version(),
            "created_at": _utc_now_iso(),
            "export_options": {
                "include_settings": options.include_settings,
                "redact_secrets": options.redact_secrets,
            },
            "files": {
                "movies": LIBRARY_MOVIES,
                "tv_shows": LIBRARY_TV_SHOWS,
                "pinned_episodes": LIBRARY_PINNED_EPISODES,
                "stream_providers": stream_paths,
            },
            "counts": {
                "movies": len(movie_rows),
                "tv_shows": len(show_rows),
                "pinned_episodes": len(pinned_episode_rows),
                "pinned_streams": sum(len(v) for v in pins_by_provider.values()),
                "pins_by_provider": {k: len(v) for k, v in pins_by_provider.items()},
            },
            "warnings": warnings,
        }
        if options.include_settings:
            manifest["files"]["settings"] = SETTINGS_FILE

        (work_dir / MANIFEST_FILE).write_text(
            _json_dumps(manifest),
            encoding="utf-8",
        )

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        out_name = f"riven-backup_{timestamp}.riven-backup.zip"
        out_path = BACKUPS_DIR / out_name

        logger.info("[backup] Creating ZIP {}", out_path)
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in work_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(work_dir).as_posix())

        zip_bytes = out_path.stat().st_size
        logger.success(
            "[backup] Export complete: {} ({:.2f} MB), movies={}, shows={}, pins={}",
            out_name,
            zip_bytes / (1024 * 1024),
            len(movie_rows),
            len(show_rows),
            sum(len(v) for v in pins_by_provider.values()),
        )
        if warnings:
            logger.warning("[backup] Export finished with {} warning(s)", len(warnings))

        return ExportResult(
            success=True,
            filename=out_name,
            message="Backup bundle created",
            manifest=manifest,
        )
    except Exception as e:
        logger.exception("[backup] Export failed")
        return ExportResult(
            success=False,
            message=str(e),
            manifest={"warnings": warnings},
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.debug("[backup] Removed temp export dir {}", work_dir)


def bundle_download_path(filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("Invalid filename")
    if not (
        filename.endswith(".zip") or filename.endswith(".riven-backup.zip")
    ):
        raise ValueError("Invalid backup file type")
    return BACKUPS_DIR / filename


def _load_manifest(extract_dir: Path) -> dict[str, Any]:
    manifest_path = extract_dir / MANIFEST_FILE
    if not manifest_path.exists():
        raise ValueError("manifest.json missing from backup")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported backup format version: {manifest.get('format_version')}"
        )
    return manifest


def _resolve_imdb_to_tmdb_id(imdb_id: str) -> str | None:
    tmdb = _get_tmdb()
    results = tmdb.get_from_external_id("imdb_id", imdb_id)
    if results.movie_results:
        return str(results.movie_results[0].id)
    return None


def _resolve_imdb_to_tvdb_id(imdb_id: str) -> str | None:
    tvdb = _get_tvdb()
    if not tvdb:
        return None
    hits = tvdb.search_by_imdb_id(imdb_id)
    if not hits:
        return None
    for hit in hits:
        if hit.movie:
            continue
        series_data = hit.series
        if not series_data:
            continue
        if isinstance(series_data, dict):
            series_id = series_data.get("id")
        else:
            series_id = series_data
        if series_id is not None:
            return str(series_id)
    return None


def _add_media_item(program: Program, payload: dict[str, Any]) -> None:
    program.em.add_item(MediaItem(payload))


def _import_library_titles(
    extract_dir: Path,
    options: ImportBundleOptions,
    result: ImportResult,
) -> None:
    program = _get_program()
    movies = _read_csv(extract_dir / LIBRARY_MOVIES)
    shows = _read_csv(extract_dir / LIBRARY_TV_SHOWS)

    logger.info(
        "[backup] Importing library titles: {} movies, {} shows in CSV "
        "(skip_existing={})",
        len(movies),
        len(shows),
        options.skip_existing_titles,
    )

    for row in movies:
        imdb_id = (row.get("imdb_id") or "").strip()
        if not imdb_id:
            continue
        if options.skip_existing_titles and item_exists_by_any_id(imdb_id=imdb_id):
            result.skipped_titles += 1
            logger.debug("[backup] Skip movie (exists): {}", imdb_id)
            continue
        tmdb_id = _resolve_imdb_to_tmdb_id(imdb_id)
        if not tmdb_id:
            msg = f"Movie {imdb_id}: could not resolve TMDB id"
            result.errors.append(msg)
            logger.warning("[backup] {}", msg)
            continue
        if item_exists_by_any_id(tmdb_id=tmdb_id):
            result.skipped_titles += 1
            logger.debug("[backup] Skip movie (tmdb exists): {} -> {}", imdb_id, tmdb_id)
            continue
        _add_media_item(
            program,
            {
                "tmdb_id": tmdb_id,
                "imdb_id": imdb_id,
                "requested_by": "backup-restore",
                "requested_at": datetime.now(),
            },
        )
        result.added_movies += 1
        title = (row.get("title") or imdb_id).strip()
        logger.info("[backup] Queued movie: {} [{}] tmdb={}", title, imdb_id, tmdb_id)

    for row in shows:
        imdb_id = (row.get("imdb_id") or "").strip()
        if not imdb_id:
            continue
        if options.skip_existing_titles and item_exists_by_any_id(imdb_id=imdb_id):
            result.skipped_titles += 1
            logger.debug("[backup] Skip show (exists): {}", imdb_id)
            continue
        tvdb_id = _resolve_imdb_to_tvdb_id(imdb_id)
        if tvdb_id:
            if item_exists_by_any_id(tvdb_id=tvdb_id):
                result.skipped_titles += 1
                logger.debug("[backup] Skip show (tvdb exists): {} -> {}", imdb_id, tvdb_id)
                continue
            _add_media_item(
                program,
                {
                    "tvdb_id": tvdb_id,
                    "imdb_id": imdb_id,
                    "requested_by": "backup-restore",
                    "requested_at": datetime.now(),
                },
            )
            result.added_shows += 1
            title = (row.get("title") or imdb_id).strip()
            logger.info(
                "[backup] Queued show: {} [{}] tvdb={}", title, imdb_id, tvdb_id
            )
            continue

        tmdb = _get_tmdb()
        find = tmdb.get_from_external_id("imdb_id", imdb_id)
        if find.tv_results:
            tmdb_tv_id = str(find.tv_results[0].id)
            if item_exists_by_any_id(tmdb_id=tmdb_tv_id):
                result.skipped_titles += 1
                logger.debug("[backup] Skip show (tmdb exists): {} -> {}", imdb_id, tmdb_tv_id)
                continue
            _add_media_item(
                program,
                {
                    "imdb_id": imdb_id,
                    "tmdb_id": tmdb_tv_id,
                    "requested_by": "backup-restore",
                    "requested_at": datetime.now(),
                },
            )
            result.added_shows += 1
            title = (row.get("title") or imdb_id).strip()
            logger.info(
                "[backup] Queued show: {} [{}] tmdb={}", title, imdb_id, tmdb_tv_id
            )
        else:
            msg = f"Show {imdb_id}: could not resolve TVDB/TMDB id"
            result.errors.append(msg)
            logger.warning("[backup] {}", msg)

    logger.info(
        "[backup] Library import phase done: +{} movies, +{} shows, {} skipped",
        result.added_movies,
        result.added_shows,
        result.skipped_titles,
    )


def _restore_settings_from_bundle(extract_dir: Path) -> None:
    path = extract_dir / SETTINGS_FILE
    if not path.exists():
        logger.info("[backup] No settings.json in bundle; skipping settings restore")
        return
    logger.info("[backup] Restoring settings from {}", SETTINGS_FILE)
    data = json.loads(path.read_text(encoding="utf-8"))
    updated = settings_manager.settings.model_validate(data)
    settings_manager.load(settings_dict=updated.model_dump())
    settings_manager.save()
    logger.success("[backup] Settings restored and saved to disk")


def _resolve_item_for_pin(
    session: Session,
    row: dict[str, str],
) -> MediaItem | None:
    item_type = (row.get("item_type") or "movie").strip().lower()
    imdb_id = (row.get("imdb_id") or "").strip()
    show_imdb = (row.get("show_imdb_id") or "").strip()
    season_number = _parse_int(row.get("season_number"))
    episode_number = _parse_int(row.get("episode_number"))

    if item_type == "movie":
        return session.execute(
            select(MediaItem).where(
                MediaItem.type == "movie",
                MediaItem.imdb_id == imdb_id,
            )
        ).scalar_one_or_none()

    if item_type == "show":
        target = imdb_id or show_imdb
        return session.execute(
            select(MediaItem).where(
                MediaItem.type == "show",
                MediaItem.imdb_id == target,
            )
        ).scalar_one_or_none()

    if item_type == "season":
        show = (
            session.execute(
                select(Show)
                .options(selectinload(Show.seasons))
                .where(Show.imdb_id == show_imdb)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not show or season_number is None:
            return None
        return next((s for s in show.seasons if s.number == season_number), None)

    if item_type == "episode":
        if imdb_id:
            ep = session.execute(
                select(Episode).where(Episode.imdb_id == imdb_id)
            ).scalar_one_or_none()
            if ep:
                return ep

        show = (
            session.execute(
                select(Show)
                .options(selectinload(Show.seasons).selectinload(Season.episodes))
                .where(Show.imdb_id == show_imdb)
            )
            .unique()
            .scalar_one_or_none()
        )
        if not show:
            return None
        if season_number is not None and episode_number is not None:
            season = next((s for s in show.seasons if s.number == season_number), None)
            if season:
                return next(
                    (e for e in season.episodes if e.number == episode_number),
                    None,
                )
        if episode_number is not None:
            return show.get_absolute_episode(episode_number, season_number)

    return None


def _stream_from_row(row: dict[str, str]) -> Stream:
    infohash = (row.get("infohash") or "").strip().lower()
    raw_title = (row.get("raw_title") or "").strip() or infohash
    parsed_title = (row.get("parsed_title") or "").strip() or raw_title
    resolution = (row.get("resolution") or "").strip() or "unknown"

    stream = object.__new__(Stream)
    stream.infohash = infohash
    stream.raw_title = raw_title
    stream.parsed_title = parsed_title
    stream.rank = 0
    stream.lev_ratio = 0.0
    stream.resolution = resolution
    stream.is_cached = False
    return stream


def restore_pinned_stream(
    item: MediaItem,
    stream: Stream,
    provider: str,
    session: Session,
) -> bool:
    program = _get_program()
    downloader = program.services.downloader if program.services else None
    if not downloader or not downloader.initialized:
        logger.warning(
            "[backup] Cannot restore pin for {}: downloader not initialized",
            item.log_string,
        )
        return False

    service = next(
        (s for s in downloader.initialized_services if s.key == provider),
        None,
    )
    if not service:
        logger.warning(
            "[backup] Cannot restore pin for {}: provider '{}' not configured",
            item.log_string,
            provider,
        )
        return False

    item_merged = session.merge(item)
    existing = next(
        (
            s
            for s in item_merged.streams
            if s.infohash.lower() == stream.infohash.lower()
        ),
        None,
    )
    target = existing or stream
    if existing is None:
        session.add(stream)
        item_merged.streams.append(stream)
        session.flush()

    logger.info(
        "[backup] Activating pin for {} on {} (infohash={})",
        item_merged.log_string,
        provider,
        stream.infohash,
    )
    success = downloader.start_manual_download(
        item=item_merged,
        stream=target,
        service=service,
        file_ids=None,
    )
    if success:
        session.commit()
        logger.success(
            "[backup] Pin restored for {} on {} ({})",
            item_merged.log_string,
            provider,
            stream.infohash,
        )
        try:
            program.em.add_event(Event("Downloader", item_merged.id))
        except Exception:
            pass
    else:
        logger.warning(
            "[backup] Pin activate failed for {} on {} ({})",
            item_merged.log_string,
            provider,
            stream.infohash,
        )
    return success


def _import_pins(extract_dir: Path, result: ImportResult) -> None:
    streams_root = extract_dir / STREAMS_DIR
    if not streams_root.exists():
        logger.info("[backup] No streams/ directory in bundle; skipping pin restore")
        return

    provider_files = sorted(streams_root.glob("*.csv"))
    total_rows = sum(len(_read_csv(p)) for p in provider_files)
    logger.info(
        "[backup] Restoring pins from {} provider file(s), {} total row(s)",
        len(provider_files),
        total_rows,
    )

    for provider_file in provider_files:
        provider = provider_file.stem
        rows = _read_csv(provider_file)
        logger.info("[backup] Processing {} ({} pins)", provider_file.name, len(rows))
        for row in rows:
            infohash = (row.get("infohash") or "").strip()
            if not infohash:
                result.pins_failed += 1
                msg = f"{provider}: row missing infohash"
                result.errors.append(msg)
                logger.warning("[backup] {}", msg)
                continue

            pin_ok = False
            for attempt in range(PIN_LOOKUP_RETRIES):
                with db_session() as session:
                    item = _resolve_item_for_pin(session, row)
                    if not item:
                        if attempt < PIN_LOOKUP_RETRIES - 1:
                            logger.debug(
                                "[backup] Pin lookup retry {}/{} for {} {} "
                                "(item not found yet)",
                                attempt + 1,
                                PIN_LOOKUP_RETRIES,
                                row.get("item_type"),
                                row.get("imdb_id") or row.get("show_imdb_id"),
                            )
                        if attempt >= PIN_LOOKUP_RETRIES - 1:
                            result.pins_failed += 1
                            msg = (
                                f"{provider} {infohash}: item not found "
                                f"({row.get('item_type')} "
                                f"{row.get('imdb_id') or row.get('show_imdb_id')})"
                            )
                            result.errors.append(msg)
                            logger.warning("[backup] {}", msg)
                        continue

                    stream = _stream_from_row(row)
                    try:
                        if restore_pinned_stream(item, stream, provider, session):
                            result.pins_restored += 1
                            pin_ok = True
                        else:
                            result.pins_failed += 1
                            result.errors.append(
                                f"{provider} {infohash}: activate failed "
                                f"for item {item.id}"
                            )
                            pin_ok = True
                    except Exception as e:
                        session.rollback()
                        result.pins_failed += 1
                        msg = f"{provider} {infohash}: {e}"
                        result.errors.append(msg)
                        logger.exception("[backup] {}", msg)
                        pin_ok = True

                if pin_ok:
                    break
                if attempt < PIN_LOOKUP_RETRIES - 1:
                    logger.info(
                        "[backup] Waiting {}s before pin retry for {}",
                        PIN_LOOKUP_DELAY_SECONDS,
                        infohash,
                    )
                    time.sleep(PIN_LOOKUP_DELAY_SECONDS)

    logger.info(
        "[backup] Pin restore phase done: {} restored, {} failed",
        result.pins_restored,
        result.pins_failed,
    )


def import_bundle(upload_path: Path, options: ImportBundleOptions) -> ImportResult:
    result = ImportResult(success=False, message="Import failed")
    extract_dir = BACKUPS_DIR / f"_import_{int(time.time())}"
    extract_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "[backup] Starting import from {} (restore_settings={}, "
        "skip_existing={}, restore_pins={})",
        upload_path.name,
        options.restore_settings,
        options.skip_existing_titles,
        options.restore_pins,
    )

    try:
        size = upload_path.stat().st_size
        logger.info("[backup] Upload size: {:.2f} MB", size / (1024 * 1024))
        if size > MAX_UPLOAD_BYTES:
            result.message = (
                f"Backup file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
            )
            logger.error("[backup] {}", result.message)
            return result

        logger.info("[backup] Extracting to {}", extract_dir)
        with zipfile.ZipFile(upload_path, "r") as zf:
            zf.extractall(extract_dir)

        manifest = _load_manifest(extract_dir)
        counts = manifest.get("counts", {})
        logger.info(
            "[backup] Loaded manifest v{} (riven {}, exported {}): "
            "movies={}, shows={}, pins={}",
            manifest.get("format_version"),
            manifest.get("riven_version"),
            manifest.get("created_at"),
            counts.get("movies"),
            counts.get("tv_shows"),
            counts.get("pinned_streams"),
        )

        if options.restore_settings:
            _restore_settings_from_bundle(extract_dir)

        _import_library_titles(extract_dir, options, result)

        if options.restore_pins:
            logger.info(
                "[backup] Waiting {}s for new titles to index before pin restore",
                PIN_LOOKUP_DELAY_SECONDS,
            )
            time.sleep(PIN_LOOKUP_DELAY_SECONDS)
            _import_pins(extract_dir, result)
        else:
            logger.info("[backup] Pin restore disabled; skipping streams/")

        result.success = True
        result.message = (
            f"Import complete: +{result.added_movies} movies, "
            f"+{result.added_shows} shows, "
            f"{result.pins_restored} pins restored, "
            f"{result.pins_failed} pins failed"
        )
        if result.errors:
            logger.warning(
                "[backup] Import completed with {} error(s); showing first in logs",
                len(result.errors),
            )
            for err in result.errors[:10]:
                logger.warning("[backup]   {}", err)
        logger.success("[backup] {}", result.message)
        return result
    except Exception as e:
        logger.exception("[backup] Import failed")
        result.message = str(e)
        result.errors.append(str(e))
        return result
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        logger.debug("[backup] Removed temp import dir {}", extract_dir)
        if upload_path.name.startswith("_uploaded_"):
            upload_path.unlink(missing_ok=True)


def clean_bundle_exports(filename: str | None = None) -> tuple[bool, list[str]]:
    """Delete bundle zip file(s) from BACKUPS_DIR."""
    if not BACKUPS_DIR.exists():
        return True, []

    deleted: list[str] = []
    if filename:
        try:
            path = bundle_download_path(filename)
        except ValueError:
            return False, []
        if path.exists():
            path.unlink()
            deleted.append(filename)
        return True, deleted

    for path in BACKUPS_DIR.glob("*.riven-backup.zip"):
        path.unlink()
        deleted.append(path.name)
    for path in BACKUPS_DIR.glob("riven-backup_*.zip"):
        if path.name not in deleted:
            path.unlink()
            deleted.append(path.name)
    return True, deleted
