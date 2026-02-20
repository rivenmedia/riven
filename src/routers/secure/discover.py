"""TMDB/TVDB discovery proxy routes for the SPA."""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from kink import di
from sqlalchemy import select

from program.apis.tmdb_api import TMDBApi
from program.apis.tvdb_api import TVDBApi
from program.db.db import db_session
from program.media.item import MediaItem

router = APIRouter(tags=["discover"])

TMDB_MEDIA_TYPE = Literal["movie", "tv"]


def _get_tmdb() -> TMDBApi:
    return di[TMDBApi]


def _get_tvdb() -> TVDBApi:
    return di[TVDBApi]


def _tmdb_request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    tmdb = _get_tmdb()
    query_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    response = tmdb.session.get(path, params=query_params)
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"TMDB request failed for endpoint '{path}'",
        )
    data = response.json()
    return cast(dict[str, Any], data) if isinstance(data, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    parsed = list[dict[str, Any]]()
    for item in cast(list[Any], value):
        if isinstance(item, dict):
            parsed.append(cast(dict[str, Any], item))
    return parsed


def _dict_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _normalize_tmdb_item(
    item: dict[str, Any], media_type: TMDB_MEDIA_TYPE, indexer: str = "tmdb"
) -> dict[str, Any]:
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
        "tmdb_id": str(item.get("id", "")),
        "tvdb_id": item.get("tvdb_id"),
    }


def _normalize_tmdb_person(item: dict[str, Any]) -> dict[str, Any]:
    profile_path = item.get("profile_path")
    image = f"https://image.tmdb.org/t/p/w500{profile_path}" if profile_path else None
    known_for = []

    for credit in _dict_list(item.get("known_for")):
        media_type = credit.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        known_for.append(_normalize_tmdb_item(credit, media_type))

    return {
        "id": str(item.get("id", "")),
        "name": item.get("name") or "Unknown",
        "media_type": "person",
        "indexer": "tmdb",
        "known_for_department": item.get("known_for_department"),
        "profile_path": image,
        "popularity": item.get("popularity"),
        "known_for": known_for,
    }


def _normalize_tvdb_item(entry: dict[str, Any]) -> dict[str, Any]:
    translations_raw = entry.get("translations")
    translations = _dict_map(translations_raw)
    title = cast(str | None, translations.get("eng") or entry.get("name"))
    if not title:
        for value in translations.values():
            if isinstance(value, str) and value:
                title = value
                break
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
        "tmdb_id": None,
        "tvdb_id": str(tvdb_id) if tvdb_id else None,
    }


def _library_status_for_results(
    results: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    tmdb_ids = {
        str(item.get("tmdb_id") or item.get("id"))
        for item in results
        if item.get("media_type") in ("movie", "tv")
        and item.get("indexer") == "tmdb"
        and (item.get("tmdb_id") or item.get("id"))
    }
    tvdb_ids = {
        str(item.get("tvdb_id") or item.get("id"))
        for item in results
        if (item.get("indexer") == "tvdb" or item.get("tvdb_id"))
        and (item.get("tvdb_id") or item.get("id"))
    }

    if not tmdb_ids and not tvdb_ids:
        return {}, {}

    query = select(MediaItem).where(MediaItem.type.in_(["movie", "show"]))
    if tmdb_ids and tvdb_ids:
        query = query.where(
            (MediaItem.tmdb_id.in_(tmdb_ids)) | (MediaItem.tvdb_id.in_(tvdb_ids))
        )
    elif tmdb_ids:
        query = query.where(MediaItem.tmdb_id.in_(tmdb_ids))
    elif tvdb_ids:
        query = query.where(MediaItem.tvdb_id.in_(tvdb_ids))

    tmdb_status: dict[str, dict[str, Any]] = {}
    tvdb_status: dict[str, dict[str, Any]] = {}

    with db_session() as session:
        matches = session.execute(query).scalars().all()

    for item in matches:
        payload = {
            "in_library": True,
            "library_item_id": str(item.id),
            "library_state": item.last_state.name if item.last_state else None,
            "library_type": item.type,
            "library_title": item.title,
        }
        if item.tmdb_id:
            tmdb_status[str(item.tmdb_id)] = payload
        if item.tvdb_id:
            tvdb_status[str(item.tvdb_id)] = payload

    return tmdb_status, tvdb_status


def _attach_library_status(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tmdb_status, tvdb_status = _library_status_for_results(results)

    for item in results:
        library_payload = {
            "in_library": False,
            "library_item_id": None,
            "library_state": None,
            "library_type": None,
            "library_title": None,
        }

        if item.get("indexer") == "tvdb":
            lookup_id = str(item.get("tvdb_id") or item.get("id") or "")
            if lookup_id in tvdb_status:
                library_payload = tvdb_status[lookup_id]
        elif item.get("media_type") in ("movie", "tv"):
            tmdb_lookup = str(item.get("tmdb_id") or item.get("id") or "")
            if tmdb_lookup in tmdb_status:
                library_payload = tmdb_status[tmdb_lookup]
            else:
                tvdb_lookup = str(item.get("tvdb_id") or "")
                if tvdb_lookup and tvdb_lookup in tvdb_status:
                    library_payload = tvdb_status[tvdb_lookup]

        item.update(library_payload)

    return results


def _paged_response(data: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "results": results,
        "page": data.get("page", 1),
        "total_pages": data.get("total_pages", 1),
        "total_results": data.get("total_results", len(results)),
    }


def _tmdb_media_collection(path: str, media_type: TMDB_MEDIA_TYPE) -> dict[str, Any]:
    data = _tmdb_request(path)
    normalized = [
        _normalize_tmdb_item(item, media_type) for item in _dict_list(data.get("results"))
    ]
    return _paged_response(data, _attach_library_status(normalized))


@router.get("/discover/tmdb/movie")
async def discover_tmdb_movie(
    request: Request, page: int = Query(1, ge=1)
) -> dict[str, Any]:
    """Proxy to TMDB discover movie with passthrough filters."""

    params: dict[str, Any] = dict(request.query_params)
    params["page"] = page
    data = _tmdb_request("discover/movie", params=params)
    results = [
        _normalize_tmdb_item(item, "movie") for item in _dict_list(data.get("results"))
    ]
    return _paged_response(data, _attach_library_status(results))


@router.get("/discover/tmdb/tv")
async def discover_tmdb_tv(request: Request, page: int = Query(1, ge=1)) -> dict[str, Any]:
    """Proxy to TMDB discover TV with passthrough filters."""

    params: dict[str, Any] = dict(request.query_params)
    params["page"] = page
    data = _tmdb_request("discover/tv", params=params)
    results = [_normalize_tmdb_item(item, "tv") for item in _dict_list(data.get("results"))]
    return _paged_response(data, _attach_library_status(results))


@router.get("/search/tmdb/movie", summary="Search TMDB movies")
async def search_tmdb_movie(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    data = _tmdb_request("search/movie", params={"query": query, "page": page})
    results = [
        _normalize_tmdb_item(item, "movie") for item in _dict_list(data.get("results"))
    ]
    return _paged_response(data, _attach_library_status(results))


@router.get("/search/tmdb/tv", summary="Search TMDB TV")
async def search_tmdb_tv(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    data = _tmdb_request("search/tv", params={"query": query, "page": page})
    results = [_normalize_tmdb_item(item, "tv") for item in _dict_list(data.get("results"))]
    return _paged_response(data, _attach_library_status(results))


@router.get("/search/tmdb/multi", summary="Search TMDB movies, TV and people")
async def search_tmdb_multi(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    include_people: bool = Query(True),
) -> dict[str, Any]:
    data = _tmdb_request("search/multi", params={"query": query, "page": page})
    results: list[dict[str, Any]] = []

    for item in _dict_list(data.get("results")):
        media_type = item.get("media_type")
        if media_type in ("movie", "tv"):
            results.append(_normalize_tmdb_item(item, media_type))
        elif media_type == "person" and include_people:
            results.append(_normalize_tmdb_person(item))

    _attach_library_status(results)
    return _paged_response(data, results)


@router.get("/trending/tmdb/{media_type}/{window}", summary="TMDB trending")
async def trending_tmdb(media_type: str, window: str) -> dict[str, Any]:
    if media_type not in ("movie", "tv", "all"):
        raise HTTPException(
            status_code=400, detail="media_type must be movie, tv, or all"
        )
    if window not in ("day", "week"):
        raise HTTPException(status_code=400, detail="window must be day or week")

    data = _tmdb_request(f"trending/{media_type}/{window}")
    results: list[dict[str, Any]] = []
    for item in _dict_list(data.get("results")):
        item_media_type = item.get("media_type") or media_type
        if item_media_type in ("movie", "tv"):
            results.append(_normalize_tmdb_item(item, item_media_type))

    return _paged_response(data, _attach_library_status(results))


@router.get("/tmdb/movie/{movie_id}", summary="TMDB movie details")
async def tmdb_movie_details(movie_id: str) -> dict[str, Any]:
    data = _tmdb_request(
        f"movie/{movie_id}",
        params={
            "append_to_response": (
                "credits,recommendations,similar,videos,images,watch/providers,"
                "keywords,external_ids"
            )
        },
    )

    library_probe = _attach_library_status([_normalize_tmdb_item(data, "movie")])[0]
    data["library"] = {
        "in_library": library_probe.get("in_library", False),
        "library_item_id": library_probe.get("library_item_id"),
        "library_state": library_probe.get("library_state"),
        "library_type": library_probe.get("library_type"),
        "library_title": library_probe.get("library_title"),
    }
    return data


@router.get("/tmdb/tv/{tv_id}", summary="TMDB TV details")
async def tmdb_tv_details(tv_id: str) -> dict[str, Any]:
    data = _tmdb_request(
        f"tv/{tv_id}",
        params={
            "append_to_response": (
                "credits,recommendations,similar,videos,images,watch/providers,"
                "keywords,external_ids,content_ratings"
            )
        },
    )

    library_probe = _attach_library_status([_normalize_tmdb_item(data, "tv")])[0]
    data["library"] = {
        "in_library": library_probe.get("in_library", False),
        "library_item_id": library_probe.get("library_item_id"),
        "library_state": library_probe.get("library_state"),
        "library_type": library_probe.get("library_type"),
        "library_title": library_probe.get("library_title"),
    }
    return data


@router.get("/tmdb/movie/{movie_id}/credits", summary="TMDB movie credits")
async def tmdb_movie_credits(movie_id: str) -> dict[str, Any]:
    return _tmdb_request(f"movie/{movie_id}/credits")


@router.get("/tmdb/tv/{tv_id}/credits", summary="TMDB TV credits")
async def tmdb_tv_credits(tv_id: str) -> dict[str, Any]:
    return _tmdb_request(f"tv/{tv_id}/credits")


@router.get("/tmdb/movie/{movie_id}/recommendations", summary="TMDB movie recs")
async def tmdb_movie_recommendations(movie_id: str) -> dict[str, Any]:
    return _tmdb_media_collection(f"movie/{movie_id}/recommendations", "movie")


@router.get("/tmdb/movie/{movie_id}/similar", summary="TMDB similar movies")
async def tmdb_movie_similar(movie_id: str) -> dict[str, Any]:
    return _tmdb_media_collection(f"movie/{movie_id}/similar", "movie")


@router.get("/tmdb/tv/{tv_id}/recommendations", summary="TMDB TV recs")
async def tmdb_tv_recommendations(tv_id: str) -> dict[str, Any]:
    return _tmdb_media_collection(f"tv/{tv_id}/recommendations", "tv")


@router.get("/tmdb/tv/{tv_id}/similar", summary="TMDB similar TV")
async def tmdb_tv_similar(tv_id: str) -> dict[str, Any]:
    return _tmdb_media_collection(f"tv/{tv_id}/similar", "tv")


def _normalize_person_credits(
    data: dict[str, Any],
    key: str,
    default_media_type: TMDB_MEDIA_TYPE | None = None,
) -> list[dict[str, Any]]:
    credits: list[dict[str, Any]] = []
    for item in _dict_list(data.get(key)):
        media_type = item.get("media_type") or default_media_type
        if media_type not in ("movie", "tv"):
            continue

        normalized = _normalize_tmdb_item(item, media_type)
        normalized["credit_id"] = item.get("credit_id")
        normalized["character"] = item.get("character")
        normalized["job"] = item.get("job")
        credits.append(normalized)

    _attach_library_status(credits)
    return credits


@router.get("/tmdb/person/{person_id}", summary="TMDB person details")
async def tmdb_person_details(person_id: str) -> dict[str, Any]:
    return _tmdb_request(
        f"person/{person_id}",
        params={
            "append_to_response": "combined_credits,movie_credits,tv_credits,images,"
            "external_ids",
        },
    )


@router.get("/tmdb/person/{person_id}/combined_credits", summary="TMDB person credits")
async def tmdb_person_combined_credits(person_id: str) -> dict[str, Any]:
    data = _tmdb_request(f"person/{person_id}/combined_credits")
    cast = _normalize_person_credits(data, "cast")
    crew = _normalize_person_credits(data, "crew")
    return {"id": person_id, "cast": cast, "crew": crew}


@router.get("/tmdb/person/{person_id}/movie_credits", summary="TMDB person movie credits")
async def tmdb_person_movie_credits(person_id: str) -> dict[str, Any]:
    data = _tmdb_request(f"person/{person_id}/movie_credits")
    cast = _normalize_person_credits(data, "cast", default_media_type="movie")
    crew = _normalize_person_credits(data, "crew", default_media_type="movie")
    return {"id": person_id, "cast": cast, "crew": crew}


@router.get("/tmdb/person/{person_id}/tv_credits", summary="TMDB person TV credits")
async def tmdb_person_tv_credits(person_id: str) -> dict[str, Any]:
    data = _tmdb_request(f"person/{person_id}/tv_credits")
    cast = _normalize_person_credits(data, "cast", default_media_type="tv")
    crew = _normalize_person_credits(data, "crew", default_media_type="tv")
    return {"id": person_id, "cast": cast, "crew": crew}


@router.get("/search/tvdb", summary="Search TVDB")
async def search_tvdb(
    query: str | None = Query(None),
    remote_id: str | None = Query(None),
    type: str = Query("series"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    if not query and not remote_id:
        raise HTTPException(status_code=400, detail="query or remote_id required")

    tvdb = _get_tvdb()
    result = tvdb.search(
        query=query, type=type, limit=limit, offset=offset, remote_id=remote_id
    )
    if not result:
        return {"results": [], "page": 1, "total_pages": 0, "total_results": 0}

    data_list = _dict_list(result.get("data"))
    links = _dict_map(result.get("links"))
    total_value = links.get("total_items", len(data_list))
    total = int(total_value) if isinstance(total_value, int | str) else len(data_list)

    results: list[dict[str, Any]] = []
    for entry in data_list:
        if entry.get("type") == "series":
            results.append(_normalize_tvdb_item(entry))
    _attach_library_status(results)

    return {
        "results": results,
        "page": offset // limit + 1,
        "total_pages": max(1, (total + limit - 1) // limit),
        "total_results": total,
    }


@router.get("/tvdb/series/{series_id}", summary="TVDB series details")
async def tvdb_series_details(series_id: str) -> dict[str, Any]:
    tvdb = _get_tvdb()
    series = tvdb.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    return series.model_dump()
