"""TMDB API client"""

from requests import Session

from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
    get_rate_limit_params,
)


TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105


class TMDBApiError(Exception):
    """Base exception for TMDB API related errors"""


class TMDBRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, base_url=base_url, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception=TMDBApiError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)


class TMDBApi:
    """Handles TMDB API communication"""
    
    def __init__(self):
        self.BASE_URL = "https://api.themoviedb.org/3"
        rate_limit_params = get_rate_limit_params(max_calls=40, period=10)  # TMDB allows 40 requests per 10 seconds
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.headers = {
            "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}",
        }
        session.headers.update(self.headers)
        self.request_handler = TMDBRequestHandler(session, base_url=self.BASE_URL)
    
    def validate(self):
        return self.request_handler.execute(HttpMethod.GET, "movie/popular?page=1")
    
    def get_movies_now_playing(self, params: str = "page=1"):
        """Get movies now playing in theaters"""
        return self.request_handler.execute(HttpMethod.GET, f"movie/now_playing?{params}")
    
    def get_movies_popular(self, params: str = "page=1"):
        """Get popular movies"""
        return self.request_handler.execute(HttpMethod.GET, f"movie/popular?{params}")
    
    def get_movies_top_rated(self, params: str = "page=1"):
        """Get top rated movies"""
        return self.request_handler.execute(HttpMethod.GET, f"movie/top_rated?{params}")
    
    def get_movies_upcoming(self, params: str = "page=1"):
        """Get upcoming movies"""
        return self.request_handler.execute(HttpMethod.GET, f"movie/upcoming?{params}")
    
    def get_trending(self, type: str, window: str, params: str = "page=1"):
        """Get trending items by type and time window"""
        return self.request_handler.execute(HttpMethod.GET, f"trending/{type}/{window}?{params}")
    
    def get_tv_airing_today(self, params: str = "page=1"):
        """Get TV shows airing today"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/airing_today?{params}")
    
    def get_tv_on_the_air(self, params: str = "page=1"):
        """Get TV shows on the air"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/on_the_air?{params}")
    
    def get_tv_popular(self, params: str = "page=1"):
        """Get popular TV shows"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/popular?{params}")
    
    def get_tv_top_rated(self, params: str = "page=1"):
        """Get top rated TV shows"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/top_rated?{params}")
    
    def get_from_external_id(self, external_source: str, external_id: str):
        """Get TMDB item from external ID"""
        return self.request_handler.execute(HttpMethod.GET, f"find/{external_id}?external_source={external_source}")
    
    def get_movie_details(self, movie_id: str, params: str = ""):
        """Get movie details"""
        return self.request_handler.execute(HttpMethod.GET, f"movie/{movie_id}?{params}")
    
    def get_tv_details(self, series_id: str, params: str = ""):
        """Get TV series details"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/{series_id}?{params}")
    
    def search_collection(self, query: str, params: str = "page=1"):
        """Search for collections"""
        return self.request_handler.execute(HttpMethod.GET, f"search/collection?query={query}&{params}")
    
    def search_movie(self, query: str, params: str = "page=1"):
        """Search for movies"""
        return self.request_handler.execute(HttpMethod.GET, f"search/movie?query={query}&{params}")
    
    def search_multi(self, query: str, params: str = "page=1"):
        """Search for movies, TV shows, and people"""
        return self.request_handler.execute(HttpMethod.GET, f"search/multi?query={query}&{params}")
    
    def search_tv(self, query: str, params: str = "page=1"):
        """Search for TV shows"""
        return self.request_handler.execute(HttpMethod.GET, f"search/tv?query={query}&{params}")
    
    def get_tv_season_details(self, series_id: int, season_number: int, params: str = ""):
        """Get TV season details"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/{series_id}/season/{season_number}?{params}")
    
    def get_tv_episode_details(self, series_id: int, season_number: int, episode_number: int, params: str = ""):
        """Get TV episode details"""
        return self.request_handler.execute(HttpMethod.GET, f"tv/{series_id}/season/{season_number}/episode/{episode_number}?{params}")
