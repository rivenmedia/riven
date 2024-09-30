from enum import Enum
from typing import Annotated, Generic, Optional, TypeVar
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from program.indexers.tmdb import (
    TmdbCollectionDetails,
    TmdbEpisodeDetails,
    TmdbFindResults,
    TmdbItem,
    TmdbMovieDetails,
    TmdbPagedResults,
    TmdbPagedResultsWithDates,
    TmdbSeasonDetails,
    TmdbTVDetails,
    tmdb,
)
from pydantic import BaseModel

router = APIRouter(
    prefix="/tmdb",
    tags=["tmdb"],
    responses={404: {"description": "Not found"}},
)


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


class IncludeAdult(str, Enum):
    true = "true"
    false = "false"


class CollectionSearchParams:
    def __init__(
        self,
        query: str,
        include_adult: IncludeAdult = IncludeAdult.false,
        language: str = "en-US",
        page: int = 1,
        region: str = None,
    ):
        self.query = query
        self.include_adult = include_adult.value
        self.language = language
        self.page = page
        self.region = region


class MovieSearchParams:
    def __init__(
        self,
        query: str,
        include_adult: IncludeAdult = IncludeAdult.false,
        language: str = "en-US",
        primary_release_year: int = None,
        page: int = 1,
        region: str = None,
        year: int = None,
    ):
        self.query = query
        self.include_adult = include_adult.value
        self.language = language
        self.primary_release_year = primary_release_year
        self.page = page
        self.region = region
        self.year = year


class MultiSearchParams:
    def __init__(
        self,
        query: str,
        include_adult: IncludeAdult = IncludeAdult.false,
        language: str = "en-US",
        page: int = 1,
    ):
        self.query = query
        self.include_adult = include_adult.value
        self.language = language
        self.page = page


class TVSearchParams:
    def __init__(
        self,
        query: str,
        first_air_date_year: int = None,
        include_adult: IncludeAdult = IncludeAdult.false,
        language: str = "en-US",
        page: int = 1,
        year: int = None,
    ):
        self.query = query
        self.first_air_date_year = first_air_date_year
        self.include_adult = include_adult.value
        self.language = language
        self.page = page
        self.year = year


T = TypeVar("T")


class TmdbResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T]
    message: Optional[str]


@router.get("/trending/{type}/{window}", operation_id="get_trending")
async def get_trending(
    params: Annotated[TrendingParams, Depends()],
    type: TrendingType,
    window: TrendingWindow,
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/movie/now_playing", operation_id="get_movies_now_playing")
async def get_movies_now_playing(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResultsWithDates[TmdbItem]]:  # noqa: F821
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


@router.get("/movie/popular", operation_id="get_movies_popular")
async def get_movies_popular(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/movie/top_rated", operation_id="get_movies_top_rated")
async def get_movies_top_rated(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/movie/upcoming", operation_id="get_movies_upcoming")
async def get_movies_upcoming(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResultsWithDates[TmdbItem]]:
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


# FastAPI has router preference, so /movie/now_playing, /movie/popular, /movie/top_rated and /movie/upcoming will be matched first before /movie/{movie_id}, same for /tv/{tv_id}


@router.get("/movie/{movie_id}", operation_id="get_movie_details")
async def get_movie_details(
    movie_id: str,
    params: Annotated[DetailsParams, Depends()],
) -> TmdbResponse[TmdbMovieDetails]:
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


@router.get("/tv/airing_today", operation_id="get_tv_airing_today")
async def get_tv_airing_today(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/tv/on_the_air", operation_id="get_tv_on_the_air")
async def get_tv_on_the_air(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/tv/popular", operation_id="get_tv_popular")
async def get_tv_popular(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/tv/top_rated", operation_id="get_tv_top_rated")
async def get_tv_top_rated(
    params: Annotated[CommonListParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
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


@router.get("/tv/{series_id}", operation_id="get_tv_details")
async def get_tv_details(
    series_id: str,
    params: Annotated[DetailsParams, Depends()],
) -> TmdbResponse[TmdbTVDetails]:
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


@router.get(
    "/tv/{series_id}/season/{season_number}", operation_id="get_tv_season_details"
)
async def get_tv_season_details(
    series_id: int,
    season_number: int,
    params: Annotated[DetailsParams, Depends()],
) -> TmdbResponse[TmdbSeasonDetails]:
    data = tmdb.getTVSeasonDetails(
        params=dict_to_query_string(params.__dict__),
        series_id=series_id,
        season_number=season_number,
    )
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get TV season details for ID {series_id}!",
        }


@router.get(
    "/tv/{series_id}/season/{season_number}/episode/{episode_number}",
    operation_id="get_tv_episode_details",
)
async def get_tv_episode_details(
    series_id: int,
    season_number: int,
    episode_number: int,
    params: Annotated[DetailsParams, Depends()],
) -> TmdbResponse[TmdbEpisodeDetails]:
    data = tmdb.getTVSeasonEpisodeDetails(
        params=dict_to_query_string(params.__dict__),
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number,
    )
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": f"Failed to get TV episode details for ID {series_id}!",
        }


@router.get("/search/collection", operation_id="search_collection")
async def search_collection(
    params: Annotated[CollectionSearchParams, Depends()],
) -> TmdbResponse[TmdbPagedResults[TmdbCollectionDetails]]:
    data = tmdb.getCollectionSearch(params=dict_to_query_string(params.__dict__))
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": "Failed to search for collection!",
        }


@router.get("/search/movie", operation_id="search_movie")
async def search_movie(params: Annotated[MovieSearchParams, Depends()]) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
    data = tmdb.getMovieSearch(params=dict_to_query_string(params.__dict__))
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": "Failed to search for movies!",
        }


@router.get("/search/multi", operation_id="search_multi")
async def search_multi(params: Annotated[MultiSearchParams, Depends()]) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
    data = tmdb.getMultiSearch(params=dict_to_query_string(params.__dict__))
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": "Failed to search for multi!",
        }


@router.get("/search/tv", operation_id="search_tv")
async def search_tv(params: Annotated[TVSearchParams, Depends()]) -> TmdbResponse[TmdbPagedResults[TmdbItem]]:
    data = tmdb.getTVSearch(params=dict_to_query_string(params.__dict__))
    if data:
        return {
            "success": True,
            "data": data,
        }
    else:
        return {
            "success": False,
            "message": "Failed to search for TV shows!",
        }


@router.get("/external_id/{external_id}", operation_id="get_from_external_id")
async def get_from_external_id(
    external_id: str,
    params: Annotated[ExternalIDParams, Depends()],
) -> TmdbResponse[TmdbFindResults]:
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
