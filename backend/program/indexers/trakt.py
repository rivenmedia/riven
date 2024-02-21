"""Trakt updater module"""

from datetime import datetime, timedelta
from typing import Optional
from utils.logger import logger
from utils.request import get
from program.media.item import Movie, Show, Season, Episode, MediaItem, ItemId
from program.settings.manager import settings_manager

CLIENT_ID = "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3"


class TraktIndexer:
    """Trakt updater class"""

    def __init__(self):
        self.key = 'traktindexer'
        self.ids = []
        self.initialized = True
        self.settings = settings_manager.settings.indexer

    def run(self, item: MediaItem):
        imdb_id = item.imdb_id
        item = create_item_from_imdb_id(imdb_id)
        if item and item.type == "show":
            seasons = get_show(imdb_id)
            for season in seasons:
                if season.number == 0:
                    continue
                season_item = _map_item_from_data(season, "season", item.item_id)
                for episode in season.episodes:
                    episode_item = _map_item_from_data(episode, "episode", season_item.item_id)
                    season_item.add_episode(episode_item)
                item.add_season(season_item)
        item.indexed_at = datetime.now()
        yield item

    @staticmethod
    def should_submit_item(item: MediaItem) -> bool:
        if not item.indexed_at:
            return True
        settings = settings_manager.settings.indexer
        interval = timedelta(seconds=settings.update_interval)
        return item.indexed_at < datetime.now() - interval

def _map_item_from_data(data, item_type, parent_id: Optional[ItemId] = None) -> MediaItem:
    """Map trakt.tv API data to MediaItemContainer"""
    if item_type not in ["movie", "show", "season", "episode"]:
        logger.debug(
            "Unknown item type %s for %s not found in list of acceptable objects",
            item_type,
            data.title,
        )
        return None
    formatted_aired_at = None
    if getattr(data, "first_aired", None) and (
        item_type == "show"
        or (item_type == "season" and data.aired_episodes == data.episode_count)
        or item_type == "episode"
    ):
        aired_at = data.first_aired
        formatted_aired_at = datetime.strptime(aired_at, "%Y-%m-%dT%H:%M:%S.%fZ")
    if getattr(data, "released", None):
        released_at = data.released
        formatted_aired_at = datetime.strptime(released_at, "%Y-%m-%d")
    item = {
        "title": getattr(data, "title", None),  # 'Game of Thrones'
        "year": getattr(data, "year", None),  # 2011
        "status": getattr(
            data, "status", None
        ),  # 'ended', 'released', 'returning series'
        "aired_at": formatted_aired_at,  # datetime.datetime(2011, 4, 17, 0, 0)
        "imdb_id": getattr(data.ids, "imdb", None),  # 'tt0496424'
        "tvdb_id": getattr(data.ids, "tvdb", None),  # 79488
        "tmdb_id": getattr(data.ids, "tmdb", None),  # 1399
        "genres": getattr(
            data, "genres", None
        ),  # ['Action', 'Adventure', 'Drama', 'Fantasy']
        "network": getattr(data, "network", None),  # 'HBO'
        "country": getattr(data, "country", None),  # 'US'
        "language": getattr(data, "language", None),  # 'en'
        "requested_at": datetime.now(),  # datetime.datetime(2021, 4, 17, 0, 0)
        "is_anime": "anime" in getattr(data, "genres", []),
    }

    match item_type:
        case "movie":
            return_item = Movie(item)
        case "show":
            return_item = Show(item)
        case "season":
            item["number"] = getattr(data, "number")
            return_item = Season(item, parent_id)
        case "episode":
            item["number"] = getattr(data, "number")
            return_item = Episode(item, parent_id)
        case _:
            logger.debug("Unknown item type %s for %s", item_type, data.title)
            return_item = None
    return return_item


# API METHODS


def get_show(imdb_id: str):
    """Wrapper for trakt.tv API show method"""
    url = f"https://api.trakt.tv/shows/{imdb_id}/seasons?extended=episodes,full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok:
        if response.data:
            return response.data
    return []


def create_item_from_imdb_id(imdb_id: str) -> MediaItem:
    """Wrapper for trakt.tv API search method"""
    if imdb_id is None:
        return None
    url = f"https://api.trakt.tv/search/imdb/{imdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok and len(response.data) > 0:
        try:
            media_type = response.data[0].type
            if media_type == "movie":
                data = response.data[0].movie
            elif media_type == "show":
                data = response.data[0].show
            elif media_type == "season":
                data = response.data[0].season
            elif media_type == "episode":
                data = response.data[0].episode
            if data:
                return _map_item_from_data(data, media_type)
        except UnboundLocalError:
            logger.error("Unknown item %s with response %s", imdb_id, response.content)
            return None
    return None


def get_imdbid_from_tvdb(tvdb_id: str) -> str | None:
    """Get IMDb ID from TVDB ID in Trakt"""
    url = f"https://api.trakt.tv/search/tvdb/{tvdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok and len(response.data) > 0:
        # noticing there are multiple results for some TVDB IDs
        # TODO: Need to check item.type and compare to the resulting types..
        return response.data[0].show.ids.imdb
    return None


def get_imdbid_from_tmdb(tmdb_id: str) -> str | None:
    """Get IMDb ID from TMDB ID in Trakt"""
    url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok and len(response.data) > 0:
        return response.data[0].movie.ids.imdb
    return None
