"""TMDB API client"""

from program.utils.request import SmartSession


TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105


class TMDBApiError(Exception):
    """Base exception for TMDB API related errors"""


class TMDBApi:
    """Handles TMDB API communication"""
    
    def __init__(self):
        self.BASE_URL = "https://api.themoviedb.org/3"

        rate_limits = {
            "api.themoviedb.org": {"rate": 50, "capacity": 1000}  # 50 requests per second
        }
        
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=2,
            backoff_factor=0.3
        )
        self.session.headers.update({
            "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}",
        })
    
    def validate(self):
        return self.session.get("movie/popular?page=1")
    
    def get_movies_now_playing(self, params: str = "page=1"):
        """Get movies now playing in theaters"""
        return self.session.get(f"movie/now_playing?{params}")
    
    def get_movies_popular(self, params: str = "page=1"):
        """Get popular movies"""
        return self.session.get(f"movie/popular?{params}")
    
    def get_movies_top_rated(self, params: str = "page=1"):
        """Get top rated movies"""
        return self.session.get(f"movie/top_rated?{params}")
    
    def get_movies_upcoming(self, params: str = "page=1"):
        """Get upcoming movies"""
        return self.session.get(f"movie/upcoming?{params}")
    
    def get_trending(self, type: str, window: str, params: str = "page=1"):
        """Get trending items by type and time window"""
        return self.session.get(f"trending/{type}/{window}?{params}")
    
    def get_tv_airing_today(self, params: str = "page=1"):
        """Get TV shows airing today"""
        return self.session.get(f"tv/airing_today?{params}")
    
    def get_tv_on_the_air(self, params: str = "page=1"):
        """Get TV shows on the air"""
        return self.session.get(f"tv/on_the_air?{params}")
    
    def get_tv_popular(self, params: str = "page=1"):
        """Get popular TV shows"""
        return self.session.get(f"tv/popular?{params}")
    
    def get_tv_top_rated(self, params: str = "page=1"):
        """Get top rated TV shows"""
        return self.session.get(f"tv/top_rated?{params}")
    
    def get_from_external_id(self, external_source: str, external_id: str):
        """Get TMDB item from external ID"""
        return self.session.get(f"find/{external_id}?external_source={external_source}")
    
    def get_movie_details(self, movie_id: str, params: str = ""):
        """Get movie details"""
        return self.session.get(f"movie/{movie_id}?{params}")
    
    def get_tv_details(self, series_id: str, params: str = ""):
        """Get TV series details"""
        return self.session.get(f"tv/{series_id}?{params}")
    
    def search_collection(self, query: str, params: str = "page=1"):
        """Search for collections"""
        return self.session.get(f"search/collection?query={query}&{params}")
    
    def search_movie(self, query: str, params: str = "page=1"):
        """Search for movies"""
        return self.session.get(f"search/movie?query={query}&{params}")
    
    def search_multi(self, query: str, params: str = "page=1"):
        """Search for movies, TV shows, and people"""
        return self.session.get(f"search/multi?query={query}&{params}")
    
    def search_tv(self, query: str, params: str = "page=1"):
        """Search for TV shows"""
        return self.session.get(f"search/tv?query={query}&{params}")
    
    def get_tv_season_details(self, series_id: int, season_number: int, params: str = ""):
        """Get TV season details"""
        return self.session.get(f"tv/{series_id}/season/{season_number}?{params}")
    
    def get_tv_episode_details(self, series_id: int, season_number: int, episode_number: int, params: str = ""):
        """Get TV episode details"""
        return self.session.get(f"tv/{series_id}/season/{season_number}/episode/{episode_number}?{params}")
