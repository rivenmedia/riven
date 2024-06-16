from enum import Enum
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from program.indexers.tmdb import TMDB

router = APIRouter(
    prefix="/tmdb",
    tags=["tmdb"],
    responses={404: {"description": "Not found"}},
)

tmdb = TMDB()


def dict_to_query_string(params: dict):
    filtered_params = {k: v for k, v in params.items() if v is not None}
    return urlencode(filtered_params)


class CommonListParams:
    def __init__(self, language: str = "en-US", page: int = 1):
        self.language = language
        self.page = page


class TrendingParams:
    def __init__(self, language: str = "en-US", page: int = 1):
        self.language = language
        self.page = page


class TrendingType(str, Enum):
    all = "all"
    movie = "movie"
    tv = "tv"
    person = "person"


class TrendingWindow(str, Enum):
    day = "day"
    week = "week"


class ExternalIDExternalSource(str, Enum):
    imdb_id = "imdb_id"
    facebook_id = "facebook_id"
    instagram_id = "instagram_id"
    tvdb_id = "tvdb_id"
    tiktok_id = "tiktok_id"
    twitter_id = "twitter_id"
    wikidata_id = "wikidata_id"
    youtube_id = "youtube_id"


class ExternalIDParams:
    def __init__(
        self, language: str = "en-US", external_source: ExternalIDExternalSource = None
    ):
        self.language = language
        self.external_source = external_source.value if external_source else None


class DetailsParams:
    def __init__(self, language: str = "en-US", append_to_response: str = None):
        self.language = language
        self.append_to_response = append_to_response


@router.get("/movie/now_playing")
async def get_movies_now_playing(params: Annotated[CommonListParams, Depends()]):
    movies = tmdb.getMoviesNowPlaying(params=dict_to_query_string(params.__dict__))
    if movies:
        return {
            "success": True,
            "data": movies,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get movies now playing!",
        }


@router.get("/movie/popular")
async def get_movies_popular(params: Annotated[CommonListParams, Depends()]):
    movies = tmdb.getMoviesPopular(params=dict_to_query_string(params.__dict__))
    if movies:
        return {
            "success": True,
            "data": movies,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get popular movies!",
        }


@router.get("/movie/top_rated")
async def get_movies_top_rated(params: Annotated[CommonListParams, Depends()]):
    movies = tmdb.getMoviesTopRated(params=dict_to_query_string(params.__dict__))
    if movies:
        return {
            "success": True,
            "data": movies,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get top rated movies!",
        }


@router.get("/movie/upcoming")
async def get_movies_upcoming(params: Annotated[CommonListParams, Depends()]):
    movies = tmdb.getMoviesUpcoming(params=dict_to_query_string(params.__dict__))
    if movies:
        return {
            "success": True,
            "data": movies,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get upcoming movies!",
        }


@router.get("/trending/{type}/{window}")
async def get_trending(
    params: Annotated[TrendingParams, Depends()],
    type: TrendingType,
    window: TrendingWindow,
):
    trending = tmdb.getTrending(
        params=dict_to_query_string(params.__dict__),
        type=type.value,
        window=window.value,
    )
    if trending:
        return {
            "success": True,
            "data": trending,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get trending {type}!",
        }


@router.get("/tv/airing_today")
async def get_tv_airing_today(params: Annotated[CommonListParams, Depends()]):
    tv = tmdb.getTVAiringToday(params=dict_to_query_string(params.__dict__))
    if tv:
        return {
            "success": True,
            "data": tv,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get TV airing today!",
        }


@router.get("/tv/on_the_air")
async def get_tv_on_the_air(params: Annotated[CommonListParams, Depends()]):
    tv = tmdb.getTVOnTheAir(params=dict_to_query_string(params.__dict__))
    if tv:
        return {
            "success": True,
            "data": tv,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get TV on the air!",
        }


@router.get("/tv/popular")
async def get_tv_popular(params: Annotated[CommonListParams, Depends()]):
    tv = tmdb.getTVPopular(params=dict_to_query_string(params.__dict__))
    if tv:
        return {
            "success": True,
            "data": tv,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get popular TV shows!",
        }


@router.get("/tv/top_rated")
async def get_tv_top_rated(params: Annotated[CommonListParams, Depends()]):
    tv = tmdb.getTVTopRated(params=dict_to_query_string(params.__dict__))
    if tv:
        return {
            "success": True,
            "data": tv,
        }
    else:
        return {
            "success": False,
            "message": "Failed to get top rated TV shows!",
        }


@router.get("/external_id/{external_id}")
async def get_from_external_id(
    external_id: str,
    params: Annotated[ExternalIDParams, Depends()],
):
    data = tmdb.getFromExternalID(
        params=dict_to_query_string(params.__dict__),
        external_id=external_id,
    )
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get data for external ID {external_id}!",
        }


# FastAPI has router preference, so /movie/now_playing, /movie/popular, /movie/top_rated and /movie/upcoming will be matched first before /movie/{movie_id}, same for /tv/{tv_id}


@router.get("/movie/{movie_id}")
async def get_movie_details(
    movie_id: str,
    params: Annotated[DetailsParams, Depends()],
):
    data = tmdb.getMovieDetails(
        params=dict_to_query_string(params.__dict__),
        movie_id=movie_id,
    )
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get movie details for ID {movie_id}!",
        }


@router.get("/tv/{series_id}")
async def get_tv_details(
    series_id: str,
    params: Annotated[DetailsParams, Depends()],
):
    data = tmdb.getTVDetails(
        params=dict_to_query_string(params.__dict__),
        series_id=series_id,
    )
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get TV details for ID {series_id}!",
        }
