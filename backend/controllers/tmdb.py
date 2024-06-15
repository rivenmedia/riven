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
    return urlencode(params)


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
async def get_trending_all(
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
