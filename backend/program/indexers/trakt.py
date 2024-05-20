"""Trakt updater module"""

from datetime import datetime, timedelta
from typing import Generator, Optional

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get

CLIENT_ID = "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3"


class TraktIndexer:
    """Trakt updater class"""

    def __init__(self):
        self.key = "traktindexer"
        self.ids = []
        self.initialized = True
        self.settings = settings_manager.settings.indexer

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Run the Trakt indexer for the given item."""
        if not item:
            logger.error("Item is None")
            return
        if (imdb_id := item.imdb_id) is None:
            logger.error("Item %s does not have an imdb_id, cannot index it", item.log_string)
            return
        item = create_item_from_imdb_id(imdb_id)
        if not item:
            logger.error("Failed to get item from imdb_id: %s", imdb_id)
            return
        if isinstance(item, Show):
            self._add_seasons_to_show(item, imdb_id)
        item.indexed_at = datetime.now()
        yield item

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        if not item.indexed_at:
            return True
        settings = settings_manager.settings.indexer
        try:
            # Need to handle this situation better
            # Failed to parse date: 1st Jan 2019 with format: DD MMM YYYY
            # Failed to match 'DD MMM YYYY' when parsing '1st Jan 2019'.
            # Should we try to parse this date too if it fails?
            interval = timedelta(seconds=settings.update_interval)
            return datetime.now() - item.indexed_at > interval
        except Exception:
            logger.error(f"Failed to parse date: {item.indexed_at} with format: {interval}")
            return False

    def _add_seasons_to_show(self, show: Show, imdb_id: str):
        """Add seasons to the given show using Trakt API."""
        seasons = get_show(imdb_id)
        for season in seasons:
            if season.number == 0:
                continue
            season_item = _map_item_from_data(season, "season")
            for episode in season.episodes:
                episode_item = _map_item_from_data(episode, "episode")
                season_item.add_episode(episode_item)
            show.add_season(season_item)


def _map_item_from_data(data, item_type: str) -> Optional[MediaItem]:
    """Map trakt.tv API data to MediaItemContainer."""
    if item_type not in ["movie", "show", "season", "episode"]:
        logger.debug("Unknown item type %s for %s not found in list of acceptable objects", item_type, data.title)
        return None
    formatted_aired_at = _get_formatted_date(data, item_type)
    item = {
        "title": getattr(data, "title", None),
        "year": getattr(data, "year", None),
        "status": getattr(data, "status", None),
        "aired_at": formatted_aired_at,
        "imdb_id": getattr(data.ids, "imdb", None),
        "tvdb_id": getattr(data.ids, "tvdb", None),
        "tmdb_id": getattr(data.ids, "tmdb", None),
        "genres": getattr(data, "genres", None),
        "network": getattr(data, "network", None),
        "country": getattr(data, "country", None),
        "language": getattr(data, "language", None),
        "requested_at": datetime.now(),
        "is_anime": "anime" in getattr(data, "genres", []),
    }

    match item_type:
        case "movie":
            return Movie(item)
        case "show":
            return Show(item)
        case "season":
            item["number"] = data.number
            return Season(item)
        case "episode":
            item["number"] = data.number
            return Episode(item)
        case _:
            return None


def _get_formatted_date(data, item_type: str) -> Optional[datetime]:
    """Get the formatted aired date from the data."""
    if item_type in ["show", "season", "episode"] and (first_aired := getattr(data, "first_aired", None)):
        return datetime.strptime(first_aired, "%Y-%m-%dT%H:%M:%S.%fZ")
    if item_type == "movie" and (released := getattr(data, "released", None)):
        return datetime.strptime(released, "%Y-%m-%d")
    return None


def get_show(imdb_id: str) -> dict:
    """Wrapper for trakt.tv API show method."""
    url = f"https://api.trakt.tv/shows/{imdb_id}/seasons?extended=episodes,full"
    response = get(url, additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID})
    return response.data if response.is_ok and response.data else {}


def create_item_from_imdb_id(imdb_id: str) -> Optional[MediaItem]:
    """Wrapper for trakt.tv API search method."""
    url = f"https://api.trakt.tv/search/imdb/{imdb_id}?extended=full"
    response = get(url, additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID})
    if not response.is_ok or not response.data:
        return None
    media_type = response.data[0].type
    data = response.data[0]
    return _map_item_from_data(data.movie, media_type) if media_type == "movie" else \
           _map_item_from_data(data.show, media_type) if media_type == "show" else \
           _map_item_from_data(data.season, media_type) if media_type == "season" else \
           _map_item_from_data(data.episode, media_type) if media_type == "episode" else None

def get_imdbid_from_tmdb(tmdb_id: str) -> Optional[str]:
    """Wrapper for trakt.tv API search method."""
    url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}?extended=full"
    response = get(url, additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID})
    if not response.is_ok or not response.data:
        return None
    if response.data[0].hasattr("ids"):
        return response.data[0].ids.get("imdb", None)
