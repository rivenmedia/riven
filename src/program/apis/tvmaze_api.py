"""TVMaze API client module"""

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from requests import Session

from program.media.item import Episode, MediaItem
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseType,
    create_service_session,
    get_cache_params,
    get_rate_limit_params,
)

class TVMazeAPIError(Exception):
    """Base exception for TVMaze API related errors"""

class TVMazeRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, response_type=ResponseType.SIMPLE_NAMESPACE, request_logging: bool = False):
        super().__init__(session, response_type=response_type, custom_exception=TVMazeAPIError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs):
        return super()._request(method, endpoint, **kwargs)

class TVMazeAPI:
    """Handles TVMaze API communication"""
    BASE_URL = "https://api.tvmaze.com"

    def __init__(self):
        rate_limit_params = get_rate_limit_params(max_calls=20, period=10)
        tvmaze_cache = get_cache_params("tvmaze", 86400)
        session = create_service_session(
            rate_limit_params=rate_limit_params, 
            use_cache=True, 
            cache_params=tvmaze_cache
        )
        self.request_handler = TVMazeRequestHandler(session)

    def get_show_by_imdb_id(self, imdb_id: str) -> Optional[dict]:
        """Get show information by IMDb ID"""
        if not imdb_id:
            return None
        
        url = f"{self.BASE_URL}/lookup/shows"
        response = self.request_handler.execute(
            HttpMethod.GET, 
            url,
            params={"imdb": imdb_id}
        )
        if not response.is_ok:
            return None

        show_url = f"{self.BASE_URL}/shows/{response.data.id}"
        show_response = self.request_handler.execute(HttpMethod.GET, show_url)
        return show_response.data if show_response.is_ok else None

    def get_episode_by_number(self, show_id: int, season: int, episode: int) -> Optional[datetime]:
        """Get episode information by show ID and episode number"""
        if not show_id or not season or not episode:
            return None

        url = f"{self.BASE_URL}/shows/{show_id}/episodebynumber"
        response = self.request_handler.execute(
            HttpMethod.GET,
            url,
            params={
                "season": season,
                "number": episode
            }
        )
        
        if not response.is_ok or not response.data:
            return None

        return self._parse_air_date(response.data)

    def _parse_air_date(self, episode_data) -> Optional[datetime]:
        """Parse episode air date from TVMaze response"""
        if airstamp := getattr(episode_data, "airstamp", None):
            try:
                return datetime.fromisoformat(airstamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.debug(f"Failed to parse TVMaze airstamp: {airstamp} - {e}")

        try:
            if airdate := getattr(episode_data, "airdate", None):
                if airtime := getattr(episode_data, "airtime", None):
                    dt_str = f"{airdate}T{airtime}"
                    return datetime.fromisoformat(dt_str)
                return datetime.fromisoformat(airdate)
        except (ValueError, AttributeError) as e:
            logger.error(f"Failed to parse TVMaze air date/time: {airdate}/{airtime} - {e}")
        
        return None

    def get_episode_release_time(self, item: MediaItem) -> Optional[datetime]:
        """Get episode release time for a media item"""
        if not isinstance(item, Episode) or not item.parent or not item.parent.parent or not item.parent.parent.imdb_id:
            return None

        show = self.get_show_by_imdb_id(item.parent.parent.imdb_id)
        if not show or not hasattr(show, "id"):
            return None

        # Get episode air date from regular schedule
        air_date = self.get_episode_by_number(show.id, item.parent.number, item.number)
        
        # Check streaming releases for next 7 days
        today = datetime.now()
        for i in range(7):
            check_date = today + timedelta(days=i)
            url = f"{self.BASE_URL}/schedule/web"
            response = self.request_handler.execute(
                HttpMethod.GET, 
                url, 
                params={
                    "date": check_date.strftime("%Y-%m-%d"),
                    "country": ""
                }
            )
            
            if not response.is_ok:
                continue
                
            for release in response.data:
                if not release or not hasattr(release, "show"):
                    continue
                    
                if (getattr(release.show, "externals", {}).get("imdb") == item.parent.parent.imdb_id and
                    getattr(release, "season", 0) == item.parent.number and
                    getattr(release, "number", 0) == item.number):
                    
                    streaming_date = self._parse_air_date(release)
                    if streaming_date and (not air_date or streaming_date < air_date):
                        air_date = streaming_date
                        logger.debug(f"Found earlier streaming release time for {item.log_string}")

        return air_date