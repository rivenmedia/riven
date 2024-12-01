"""TVMaze API client module"""

from datetime import datetime, timedelta, timezone
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
        
        # Obtain the local timezone
        self.local_tz = datetime.now().astimezone().tzinfo

    def get_show_by_imdb_id(self, imdb_id: str) -> Optional[dict]:
        """Get show information by IMDb ID"""
        if not imdb_id:
            return None
        
        url = f"{self.BASE_URL}/lookup/shows"
        try:
            response = self.request_handler.execute(
                HttpMethod.GET, 
                url,
                params={"imdb": imdb_id}
            )
            if response.is_ok and response.data:
                logger.debug(f"Found TVMaze show for IMDb ID {imdb_id}: ID={getattr(response.data, 'id', None)}")
                return response.data
            else:
                logger.debug(f"No TVMaze show found for IMDb ID: {imdb_id}")
                return None
        except Exception as e:
            logger.debug(f"Error getting TVMaze show for IMDb ID {imdb_id}: {e}")
            return None

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
                # Handle both 'Z' suffix and explicit timezone
                timestamp = airstamp.replace('Z', '+00:00')
                if '.' in timestamp:
                    # Strip milliseconds but preserve timezone
                    parts = timestamp.split('.')
                    base = parts[0]
                    tz = parts[1][parts[1].find('+'):]
                    timestamp = base + tz if '+' in parts[1] else base + '+00:00'
                elif not ('+' in timestamp or '-' in timestamp):
                    # Add UTC timezone if none specified
                    timestamp = timestamp + '+00:00'
                # Convert to user's timezone
                utc_dt = datetime.fromisoformat(timestamp)
                return utc_dt.astimezone(self.local_tz)
            except (ValueError, AttributeError) as e:
                logger.debug(f"Failed to parse TVMaze airstamp: {airstamp} - {e}")

        try:
            if airdate := getattr(episode_data, "airdate", None):
                if airtime := getattr(episode_data, "airtime", None):
                    # Combine date and time with UTC timezone first
                    dt_str = f"{airdate}T{airtime}+00:00"
                    utc_dt = datetime.fromisoformat(dt_str)
                    # Convert to user's timezone
                    return utc_dt.astimezone(self.local_tz)
                # If we only have a date, set time to midnight in user's timezone
                local_midnight = datetime.fromisoformat(f"{airdate}T00:00:00").replace(tzinfo=self.local_tz)
                return local_midnight
        except (ValueError, AttributeError) as e:
            logger.error(f"Failed to parse TVMaze air date/time: {airdate}/{getattr(episode_data, 'airtime', None)} - {e}")
        
        return None

    def get_episode_release_time(self, episode: Episode) -> Optional[datetime]:
        """Get episode release time from TVMaze."""
        if not episode or not episode.parent or not episode.parent.parent:
            return None

        show = episode.parent.parent
        if not hasattr(show, 'tvmaze_id') or not show.tvmaze_id:
            # Try to get TVMaze ID using IMDb ID
            show_data = self.get_show_by_imdb_id(show.imdb_id)
            if show_data:
                show.tvmaze_id = getattr(show_data, 'id', None)
                logger.debug(f"Set TVMaze ID {show.tvmaze_id} for show {show.title} (IMDb: {show.imdb_id})")
            else:
                logger.debug(f"Could not find TVMaze ID for show {show.title} (IMDb: {show.imdb_id})")
                return None

        if not show.tvmaze_id:
            logger.debug(f"No valid TVMaze ID for show {show.title}")
            return None

        # Log what we're checking
        logger.debug(f"Found regular schedule time for {show.title} S{episode.parent.number:02d}E{episode.number:02d}: {episode.aired_at}")

        # Get episode by number
        try:
            logger.debug(f"Checking streaming schedule for {show.title} S{episode.parent.number:02d}E{episode.number:02d} (Show ID: {show.tvmaze_id})")
            release_time = self.get_episode_by_number(show.tvmaze_id, episode.parent.number, episode.number)
            if release_time:
                logger.debug(f"Final release time for {show.title} S{episode.parent.number:02d}E{episode.number:02d}: {release_time}")
                return release_time
        except TVMazeAPIError as e:
            if "404" in str(e):
                # This is expected for future episodes that don't exist in TVMaze yet
                logger.debug(f"Episode not found in TVMaze (likely future episode): {show.title} S{episode.parent.number:02d}E{episode.number:02d}")
            else:
                # Log other API errors
                logger.error(f"TVMaze API error for {show.title} S{episode.parent.number:02d}E{episode.number:02d}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting TVMaze time for {show.title} S{episode.parent.number:02d}E{episode.number:02d}: {e}")
            return None

        return None