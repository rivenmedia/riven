from datetime import date
from enum import Enum
from typing import Generic, Literal, Optional, TypeVar

from loguru import logger
from pydantic import BaseModel

from program.utils.request import create_service_session, get

TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105

# TODO: Maybe remove the else condition ? It's not necessary since exception is raised 400-450, 500-511, 408, 460, 504, 520, 524, 522, 598 and 599

ItemT = TypeVar("ItemT")

class TmdbMediaType(str, Enum):
    movie = "movie"
    tv = "tv"
    episode = "tv_episode"
    season = "tv_season"


class TmdbItem(BaseModel):
    adult: bool
    backdrop_path: Optional[str]
    id: int
    title: str
    original_title: str
    original_language: str
    overview: str
    poster_path: Optional[str]
    media_type: Optional[TmdbMediaType] = None
    genre_ids: list[int]
    popularity: float
    release_date: str
    video: bool
    vote_average: float
    vote_count: int

class TmdbEpisodeItem(BaseModel):
    id: int
    name: str
    overview: str
    media_type: Literal["tv_episode"]
    vote_average: float
    vote_count: int
    air_date: date
    episode_number: int
    episode_type: str
    production_code: str
    runtime: int
    season_number: int
    show_id: int
    still_path: str

class TmdbSeasonItem(BaseModel):
    id: int
    name: str
    overview: str
    poster_path: str
    media_type: Literal["tv_season"]
    vote_average: float
    air_date: date
    season_number: int
    show_id: int
    episode_count: int


class TmdbPagedResults(BaseModel, Generic[ItemT]):
    page: int
    results: list[ItemT]
    total_pages: int
    total_results: int

class TmdbPagedResultsWithDates(TmdbPagedResults[ItemT], Generic[ItemT]):
    class Dates(BaseModel):
        maximum: date
        minimum: date
    dates: Dates

class TmdbFindResults(BaseModel):
    movie_results: list[TmdbItem]
    tv_results: list[TmdbItem]
    tv_episode_results: list[TmdbEpisodeItem]
    tv_season_results: list[TmdbSeasonItem]

class Genre(BaseModel):
    id: int
    name: str

class BelongsToCollection(BaseModel):
    id: int
    name: str
    poster_path: Optional[str]
    backdrop_path: Optional[str]


class ProductionCompany(BaseModel):
    id: int
    logo_path: Optional[str]
    name: str
    origin_country: str


class ProductionCountry(BaseModel):
    iso_3166_1: str
    name: str


class SpokenLanguage(BaseModel):
    english_name: str
    iso_639_1: str
    name: str

class Network(BaseModel):
    id: int
    logo_path: Optional[str]
    name: str
    origin_country: str

class TmdbMovieDetails(BaseModel):
    adult: bool
    backdrop_path: Optional[str]
    belongs_to_collection: Optional[BelongsToCollection]
    budget: int
    genres: list[Genre]
    homepage: Optional[str]
    id: int
    imdb_id: Optional[str]
    original_language: str
    original_title: str
    overview: Optional[str]
    popularity: float
    poster_path: Optional[str]
    production_companies: list[ProductionCompany]
    production_countries: list[ProductionCountry]
    release_date: Optional[str]
    revenue: int
    runtime: Optional[int]
    spoken_languages: list[SpokenLanguage]
    status: Optional[str]
    tagline: Optional[str]
    title: str
    video: bool
    vote_average: float
    vote_count: int

class TmdbTVDetails(BaseModel):
    adult: bool
    backdrop_path: Optional[str]
    episode_run_time: list[int]
    first_air_date: str
    genres: list[Genre]
    homepage: Optional[str]
    id: int
    in_production: bool
    languages: list[str]
    last_air_date: Optional[str]
    last_episode_to_air: Optional[TmdbEpisodeItem]
    name: str
    next_episode_to_air: Optional[str]
    networks: list[Network]
    number_of_episodes: int
    number_of_seasons: int
    origin_country: list[str]
    original_language: str
    original_name: str
    overview: Optional[str]
    popularity: float
    poster_path: Optional[str]
    production_companies: list[ProductionCompany]
    production_countries: list[ProductionCountry]
    seasons: list[TmdbSeasonItem]
    spoken_languages: list[str]
    status: Optional[str]
    tagline: Optional[str]
    type: Optional[str]
    vote_average: float
    vote_count: int

class TmdbCollectionDetails(BaseModel):
    adult: bool
    backdrop_path: Optional[str]
    id: int
    name: str
    overview: str
    original_language: str
    original_name: str
    poster_path: Optional[str]

class TmdbEpisodeDetails(TmdbEpisodeItem):
    crew: list[dict]
    guest_stars: list[dict]

class TmdbSeasonDetails(BaseModel):
    _id: str
    air_date: str
    episodes: list[TmdbEpisodeDetails]

class TMDB:
    def __init__(self):
        self.API_URL = "https://api.themoviedb.org/3"
        self.session = create_service_session()
        self.HEADERS = {
            "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}",
        }
        self.session.headers.update(self.HEADERS)

    def getMoviesNowPlaying(self, params: str) -> Optional[TmdbPagedResultsWithDates[TmdbItem]]:
        url = f"{self.API_URL}/movie/now_playing?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get movies now playing: {response.data}")
                return None
        except Exception as e:
            logger.error(
                f"An error occurred while getting movies now playing: {str(e)}"
            )
            return None

    def getMoviesPopular(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/movie/popular?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get popular movies: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting popular movies: {str(e)}")
            return None

    def getMoviesTopRated(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/movie/top_rated?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get top rated movies: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting top rated movies: {str(e)}")
            return None

    def getMoviesUpcoming(self, params: str) -> Optional[TmdbPagedResultsWithDates[TmdbItem]]:
        url = f"{self.API_URL}/movie/upcoming?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get upcoming movies: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting upcoming movies: {str(e)}")
            return None

    def getTrending(self, params: str, type: str, window: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/trending/{type}/{window}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get trending {type}: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting trending {type}: {str(e)}")
            return None

    def getTVAiringToday(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/tv/airing_today?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV airing today: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV airing today: {str(e)}")
            return None

    def getTVOnTheAir(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/tv/on_the_air?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV on the air: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV on the air: {str(e)}")
            return None

    def getTVPopular(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/tv/popular?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get popular TV shows: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting popular TV shows: {str(e)}")
            return None

    def getTVTopRated(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/tv/top_rated?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get top rated TV shows: {response.data}")
                return None
        except Exception as e:
            logger.error(
                f"An error occurred while getting top rated TV shows: {str(e)}"
            )
            return None

    def getFromExternalID(self, params: str, external_id: str) -> Optional[TmdbFindResults]:
        url = f"{self.API_URL}/find/{external_id}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get from external ID: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting from external ID: {str(e)}")
            return None

    def getMovieDetails(self, params: str, movie_id: str) -> Optional[TmdbMovieDetails]:
        url = f"{self.API_URL}/movie/{movie_id}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get movie details: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting movie details: {str(e)}")
            return None

    def getTVDetails(self, params: str, series_id: str) -> Optional[TmdbTVDetails]:
        url = f"{self.API_URL}/tv/{series_id}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV details: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV details: {str(e)}")
            return None

    def getCollectionSearch(self, params: str) -> Optional[TmdbPagedResults[TmdbCollectionDetails]]:
        url = f"{self.API_URL}/search/collection?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to search collections: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while searching collections: {str(e)}")
            return None

    def getMovieSearch(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/search/movie?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to search movies: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while searching movies: {str(e)}")
            return None

    def getMultiSearch(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/search/multi?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to search multi: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while searching multi: {str(e)}")
            return None

    def getTVSearch(self, params: str) -> Optional[TmdbPagedResults[TmdbItem]]:
        url = f"{self.API_URL}/search/tv?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to search TV shows: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while searching TV shows: {str(e)}")
            return None

    def getTVSeasonDetails(self, params: str, series_id: int, season_number: int) -> Optional[TmdbSeasonDetails]:
        url = f"{self.API_URL}/tv/{series_id}/season/{season_number}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(f"Failed to get TV season details: {response.data}")
                return None
        except Exception as e:
            logger.error(f"An error occurred while getting TV season details: {str(e)}")
            return None

    def getTVSeasonEpisodeDetails(
        self, params: str, series_id: int, season_number: int, episode_number: int
    ) -> Optional[TmdbEpisodeDetails]:
        url = f"{self.API_URL}/tv/{series_id}/season/{season_number}/episode/{episode_number}?{params}"
        try:
            response = get(self.session, url)
            if response.is_ok and response.data:
                return response.data
            else:
                logger.error(
                    f"Failed to get TV season episode details: {response.data}"
                )
                return None
        except Exception as e:
            logger.error(
                f"An error occurred while getting TV season episode details: {str(e)}"
            )
            return None


tmdb = TMDB()