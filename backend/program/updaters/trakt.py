"""Trakt updater module"""
from datetime import datetime
from os import path
from utils.logger import get_data_path, logger
from utils.request import get
from program.media.container import MediaItemContainer
from program.media.item import Movie, Show, Season, Episode

CLIENT_ID = "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3"


class Updater:
    """Trakt updater class"""

    def __init__(self):
        self.trakt_data = MediaItemContainer()
        self.pkl_file = path.join(get_data_path(), "trakt_data.pkl")
        self.ids = []

    def create_items(self, imdb_ids):
        """Update media items to state where they can start downloading"""
        self.trakt_data.load(self.pkl_file)
        new_items = MediaItemContainer()
        get_items = MediaItemContainer()
        for imdb_id in imdb_ids:
            if imdb_id not in [item.imdb_id for item in self.trakt_data.items if item]:
                item = self._create_item(imdb_id)
                if item:
                    new_items += item
                get_items.append(item)
            else:
                get_items.append(self.trakt_data.get_item("imdb_id", imdb_id))
        added_items = self.trakt_data.extend(new_items)
        if len(added_items) > 0:
            for added_item in added_items:
                logger.debug("Added %s", added_item.title)
            self.trakt_data.extend(added_items)
            self.trakt_data.save(self.pkl_file)

        return get_items

    def _create_item(self, imdb_id):
        item = create_item_from_imdb_id(imdb_id)
        if item and item.type == "show":
            seasons = get_show(imdb_id)
            for season in seasons:
                if season.number != 0:
                    new_season = _map_item_from_data(season, "season")
                    for episode in season.episodes:
                        new_episode = _map_item_from_data(episode, "episode")
                        new_season.add_episode(new_episode)
                    item.add_season(new_season)
        return item


def _map_item_from_data(data, item_type):
    """Map trakt.tv API data to MediaItemContainer"""
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
        "title": getattr(data, "title", None),
        "year": getattr(data, "year", None),
        "imdb_id": getattr(data.ids, "imdb", None),
        "aired_at": formatted_aired_at,
        "genres": getattr(data, "genres", None),
        "requested_at": datetime.now(),
    }
    match item_type:
        case "movie":
            return_item = Movie(item)
        case "show":
            return_item = Show(item)
        case "season":
            item["number"] = getattr(data, "number")
            return_item = Season(item)
        case "episode":
            item["number"] = getattr(data, "number")
            return_item = Episode(item)
        case _:
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


def create_item_from_imdb_id(imdb_id: str):
    """Wrapper for trakt.tv API search method"""
    url = f"https://api.trakt.tv/search/imdb/{imdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok:
        if len(response.data) > 0:
            media_type = response.data[0].type
            if media_type == "movie":
                data = response.data[0].movie
            else:
                data = response.data[0].show
            if data:
                return _map_item_from_data(data, media_type)
    return None

def get_imdb_id_from_tvdb(tvdb_id: str) -> str:
    """Get IMDb ID from TVDB ID in Trakt"""
    url = f"https://api.trakt.tv/search/tvdb/{tvdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok and len(response.data) > 0:
            return response.data[0].show.ids.imdb
    return None
