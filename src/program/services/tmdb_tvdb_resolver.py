"""TMDB to TVDB ID resolver with in-memory TTL cache.

Isolated module to resolve TMDB TV series IDs to TVDB IDs using TMDB's
external_ids endpoint. Results are cached in-memory to avoid repeated API
calls during a single discovery session.

This module is intentionally decoupled from the main codebase so that
upstream merges remain clean. Only discover.py imports it.
"""

from __future__ import annotations

import threading
import time

_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# tmdb_id -> (tvdb_id | None, expires_at)
_cache: dict[str, tuple[str | None, float]] = {}
_cache_lock = threading.Lock()


def resolve_batch(tmdb_tv_ids: set[str]) -> dict[str, str | None]:
    """Resolve a set of TMDB TV series IDs to their TVDB equivalents.

    Uses TMDB's ``tv/{id}/external_ids`` endpoint.  Resolved values are cached
    for 24 hours so subsequent discovery pages are essentially free.

    Args:
        tmdb_tv_ids: Set of TMDB TV series ID strings.

    Returns:
        Mapping of ``tmdb_id -> tvdb_id``.  ``tvdb_id`` is ``None`` when TMDB
        has no TVDB cross-reference for the series.
    """
    if not tmdb_tv_ids:
        return {}

    now = time.monotonic()
    result: dict[str, str | None] = {}
    ids_to_fetch: list[str] = []

    with _cache_lock:
        for tmdb_id in tmdb_tv_ids:
            entry = _cache.get(tmdb_id)
            if entry is not None and entry[1] > now:
                result[tmdb_id] = entry[0]
            else:
                ids_to_fetch.append(tmdb_id)

    if not ids_to_fetch:
        return result

    # Lazy import to avoid circular imports and keep this module standalone.
    try:
        from kink import di
        from program.apis.tmdb_api import TMDBApi

        tmdb = di[TMDBApi]
    except Exception:
        for tmdb_id in ids_to_fetch:
            result[tmdb_id] = None
        return result

    expires_at = now + _CACHE_TTL_SECONDS

    for tmdb_id in ids_to_fetch:
        tvdb_id: str | None = None
        try:
            response = tmdb.session.get(f"tv/{tmdb_id}/external_ids")
            if response.ok:
                data = response.json()
                raw = data.get("tvdb_id")
                tvdb_id = str(raw) if raw else None
        except Exception:
            pass

        result[tmdb_id] = tvdb_id
        with _cache_lock:
            _cache[tmdb_id] = (tvdb_id, expires_at)

    return result
