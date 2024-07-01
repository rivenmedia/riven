"""Trakt updater module"""

from datetime import datetime, timedelta
from typing import Generator, Optional, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get

CLIENT_ID = "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3"


class TraktIndexer:
    """Trakt updater class"""
    key = "TraktIndexer"

    def __init__(self):
        self.key = "traktindexer"
        self.initialized = True
        self.settings = settings_manager.settings.indexer

    def copy_items(self, itema: MediaItem, itemb: MediaItem) -> MediaItem:
        if isinstance(itema, Show) and isinstance(itemb, Show):
            for seasona, seasonb in zip(itema.seasons, itemb.seasons):
                for episodea, episodeb in zip(seasona.episodes, seasonb.episodes):
                    self._copy_episode_attributes(episodea, episodeb)
        elif isinstance(itema, Movie) and isinstance(itemb, Movie):
            self._copy_movie_attributes(itema, itemb)
        return itemb

    @staticmethod
    def _copy_episode_attributes(source: Episode, target: Episode) -> None:
        target.update_folder = source.update_folder
        target.symlinked = source.symlinked
        target.is_anime = source.is_anime

    @staticmethod
    def _copy_movie_attributes(source: Movie, target: Movie) -> None:
        target.update_folder = source.update_folder
        target.symlinked = source.symlinked
        target.is_anime = source.is_anime

    def run(self, in_item: MediaItem) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the Trakt indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return
        if not (imdb_id := in_item.imdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id, cannot index it")
            return

        item = create_item_from_imdb_id(imdb_id)
        if not isinstance(item, MediaItem):
            logger.error(f"Failed to get item from imdb_id: {imdb_id}")
            return

        if isinstance(item, Show):
            self._add_seasons_to_show(item, imdb_id)

        item = self.copy_items(in_item, item)
        item.indexed_at = datetime.now()
        yield item

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        if not item.indexed_at or not item.title:
            return True

        settings = settings_manager.settings.indexer

        try:
            interval = timedelta(seconds=settings.update_interval)
            return datetime.now() - item.indexed_at > interval
        except Exception:
            logger.error(f"Failed to parse date: {item.indexed_at}")
            return False

    @staticmethod
    def _add_seasons_to_show(show: Show, imdb_id: str):
        """Add seasons to the given show using Trakt API."""
        if not isinstance(show, Show):
            logger.error(f"Item {show.log_string} is not a show")
            return

        if not imdb_id or not imdb_id.startswith("tt"):
            logger.error(f"Item {show.log_string} does not have an imdb_id, cannot index it")
            return
        
        
        seasons = get_show(imdb_id)
        for season in seasons:
            if season.number == 0:
                continue
            season_item = _map_item_from_data(season, "season")
            if season_item:
                for episode_data in season.episodes:
                    episode_item = _map_item_from_data(episode_data, "episode")
                    if episode_item:
                        season_item.add_episode(episode_item)
                show.add_season(season_item)

        # Propagate important global attributes to seasons and episodes
        show.propagate_attributes_to_childs()

def _map_item_from_data(data, item_type: str) -> Optional[MediaItem]:
    """Map trakt.tv API data to MediaItemContainer."""
    if item_type not in ["movie", "show", "season", "episode"]:
        logger.debug(f"Unknown item type {item_type} for {data.title}")
        return None

    formatted_aired_at = _get_formatted_date(data, item_type)
    year = getattr(data, "year", None) or (formatted_aired_at.year if formatted_aired_at else None)

    item = {
        "title": getattr(data, "title", None),
        "year": year,
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
    }
        
    item["is_anime"] = (
        ("anime" in item['genres'] or "animation" in item['genres']) if item['genres']
        and item["country"] in ("jp", "kr")
        else False
    )

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
            logger.error(f"Failed to create item from data: {data}")
            return None

def _get_formatted_date(data, item_type: str) -> Optional[datetime]:
    """Get the formatted aired date from the data."""
    date_str = getattr(data, "first_aired" if item_type in ["show", "season", "episode"] else "released", None)
    date_format = "%Y-%m-%dT%H:%M:%S.%fZ" if item_type in ["show", "season", "episode"] else "%Y-%m-%d"
    return datetime.strptime(date_str, date_format) if date_str else None


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
        logger.error(f"Failed to create item using imdb id: {imdb_id}")
        return None

    data = next((d for d in response.data if d.type in ["show", "movie", "season", "episode"]), None)
    return _map_item_from_data(getattr(data, data.type), data.type) if data else None

def get_imdbid_from_tmdb(tmdb_id: str) -> Optional[str]:
    """Wrapper for trakt.tv API search method."""
    url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}?extended=full"
    response = get(url, additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID})
    if not response.is_ok or not response.data:
        return None
    return next((ns.movie.ids.imdb if ns.type == 'movie' else ns.show.ids.imdb for ns in response.data if ns.type in ['movie', 'show']), None)
