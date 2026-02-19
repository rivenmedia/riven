"""TMDB/TVDB discovery proxy routes for the SPA."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from kink import di

from program.apis.tmdb_api import TMDBApi
from program.apis.tvdb_api import TVDBApi

router = APIRouter(tags=["discover"])


def _get_tmdb() -> TMDBApi:
    return di[TMDBApi]


def _get_tvdb() -> TVDBApi:
    return di[TVDBApi]


def _normalize_tmdb_item(item: dict, media_type: str, indexer: str = "tmdb") -> dict:
    """Normalize TMDB result for frontend."""
    release_date = item.get("release_date") or item.get("first_air_date") or ""
    year = release_date[:4] if release_date else None
    poster = item.get("poster_path")
    poster_path = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None
    return {
        "id": str(item.get("id", "")),
        "title": item.get("title") or item.get("name") or "Unknown",
        "poster_path": poster_path,
        "year": year,
        "media_type": media_type,
        "indexer": indexer,
        "overview": item.get("overview"),
        "vote_average": item.get("vote_average"),
    }


def _normalize_tvdb_item(entry: dict) -> dict:
    """Normalize TVDB search result for frontend."""
    translations = entry.get("translations") or {}
    title = translations.get("eng") if isinstance(translations, dict) else entry.get("name")
    if not title and isinstance(translations, dict):
        title = next((v for v in translations.values() if v), None)
    title = title or entry.get("name") or "Unknown"
    year = entry.get("year")
    image_url = entry.get("image_url")
    tvdb_id = entry.get("tvdb_id") or entry.get("id")
    return {
        "id": str(tvdb_id) if tvdb_id else "",
        "title": title,
        "poster_path": image_url,
        "year": year,
        "media_type": "tv",
        "indexer": "tvdb",
        "overview": entry.get("overview"),
        "vote_average": None,
    }


@router.get("/discover/tmdb/movie")
async def discover_tmdb_movie(
    page: int = Query(1, ge=1),
    **kwargs: Any,
) -> dict:
    """Proxy to TMDB discover movie."""
    tmdb = _get_tmdb()
    params = {"page": page, **{k: v for k, v in kwargs.items() if v is not None}}
    r = tmdb.session.get("discover/movie", params=params)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    data = r.json()
    results = [_normalize_tmdb_item(i, "movie") for i in data.get("results", [])]
    return {"results": results, "page": data.get("page", 1), "total_pages": data.get("total_pages", 1), "total_results": data.get("total_results", 0)}


@router.get("/discover/tmdb/tv")
async def discover_tmdb_tv(
    page: int = Query(1, ge=1),
    **kwargs: Any,
) -> dict:
    """Proxy to TMDB discover TV."""
    tmdb = _get_tmdb()
    params = {"page": page, **{k: v for k, v in kwargs.items() if v is not None}}
    r = tmdb.session.get("discover/tv", params=params)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    data = r.json()
    results = [_normalize_tmdb_item(i, "tv") for i in data.get("results", [])]
    return {"results": results, "page": data.get("page", 1), "total_pages": data.get("total_pages", 1), "total_results": data.get("total_results", 0)}


@router.get("/search/tmdb/movie", summary="Search TMDB movies")
async def search_tmdb_movie(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
) -> dict:
    """Proxy to TMDB search movie."""
    tmdb = _get_tmdb()
    r = tmdb.session.get("search/movie", params={"query": query, "page": page})
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    data = r.json()
    results = [_normalize_tmdb_item(i, "movie") for i in data.get("results", [])]
    return {"results": results, "page": data.get("page", 1), "total_pages": data.get("total_pages", 1), "total_results": data.get("total_results", 0)}


@router.get("/search/tmdb/tv", summary="Search TMDB TV")
async def search_tmdb_tv(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
) -> dict:
    """Proxy to TMDB search TV."""
    tmdb = _get_tmdb()
    r = tmdb.session.get("search/tv", params={"query": query, "page": page})
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    data = r.json()
    results = [_normalize_tmdb_item(i, "tv") for i in data.get("results", [])]
    return {"results": results, "page": data.get("page", 1), "total_pages": data.get("total_pages", 1), "total_results": data.get("total_results", 0)}


@router.get("/trending/tmdb/{media_type}/{window}", summary="TMDB trending")
async def trending_tmdb(media_type: str, window: str) -> dict:
    """Proxy to TMDB trending."""
    if media_type not in ("movie", "tv", "all"):
        raise HTTPException(status_code=400, detail="media_type must be movie, tv, or all")
    if window not in ("day", "week"):
        raise HTTPException(status_code=400, detail="window must be day or week")
    tmdb = _get_tmdb()
    r = tmdb.session.get(f"trending/{media_type}/{window}")
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    data = r.json()
    results = []
    for i in data.get("results", []):
        mt = i.get("media_type") or media_type
        if mt in ("movie", "tv"):
            results.append(_normalize_tmdb_item(i, mt))
    return {"results": results, "page": 1, "total_pages": 1, "total_results": len(results)}


@router.get("/tmdb/movie/{movie_id}", summary="TMDB movie details")
async def tmdb_movie_details(movie_id: str) -> dict:
    """Proxy to TMDB movie details."""
    tmdb = _get_tmdb()
    r = tmdb.session.get(f"movie/{movie_id}")
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    return r.json()


@router.get("/tmdb/tv/{tv_id}", summary="TMDB TV details")
async def tmdb_tv_details(tv_id: str) -> dict:
    """Proxy to TMDB TV details."""
    tmdb = _get_tmdb()
    r = tmdb.session.get(f"tv/{tv_id}")
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail="TMDB request failed")
    return r.json()


@router.get("/search/tvdb", summary="Search TVDB")
async def search_tvdb(
    query: str | None = Query(None),
    remote_id: str | None = Query(None),
    type: str = Query("series"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Proxy to TVDB search."""
    if not query and not remote_id:
        raise HTTPException(status_code=400, detail="query or remote_id required")
    tvdb = _get_tvdb()
    result = tvdb.search(query=query, type=type, limit=limit, offset=offset, remote_id=remote_id)
    if not result:
        return {"results": [], "page": 1, "total_pages": 0, "total_results": 0}
    data_list = result.get("data", [])
    links = result.get("links", {})
    total = links.get("total_items", len(data_list))
    # Filter to series only and normalize
    results = []
    for entry in data_list:
        if isinstance(entry, dict) and entry.get("type") == "series":
            results.append(_normalize_tvdb_item(entry))
    return {"results": results, "page": offset // limit + 1, "total_pages": max(1, (total + limit - 1) // limit), "total_results": total}


@router.get("/tvdb/series/{series_id}", summary="TVDB series details")
async def tvdb_series_details(series_id: str) -> dict:
    """Proxy to TVDB series details."""
    tvdb = _get_tvdb()
    series = tvdb.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    return series.model_dump()
