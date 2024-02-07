"""Trakt updater module"""
import math
import concurrent.futures
from datetime import datetime
from utils.logger import logger
from utils.request import get
from utils import data_dir_path
from program.media.container import MediaItemContainer
from program.media.item import Movie, Show, Season, Episode

CLIENT_ID = "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3"


class Updater:
    """Trakt updater class"""

    def __init__(self):
        self.trakt_data = MediaItemContainer()
        self.pkl_file = data_dir_path / "trakt_data.pkl"
        self.ids = []

    def create_items(self, imdb_ids):
        """Update media items to state where they can start downloading"""
        if len(imdb_ids) == 0:
            return MediaItemContainer()

        self.trakt_data.load(self.pkl_file)
        new_items = MediaItemContainer()
        get_items = MediaItemContainer()

        existing_imdb_ids = {item.imdb_id for item in self.trakt_data.items if item}

        # This is to calculate 10% batch sizes to speed up the process
        batch_size = math.ceil(len(imdb_ids) * 0.1) or 1
        imdb_id_batches = [imdb_ids[i:i + batch_size] for i in range(0, len(imdb_ids), batch_size)]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for imdb_id_batch in imdb_id_batches:
                future_items = {executor.submit(self._create_item, imdb_id): imdb_id for imdb_id in imdb_id_batch if imdb_id not in existing_imdb_ids or imdb_id is not None}
                for future in concurrent.futures.as_completed(future_items):
                    item = future.result()
                    if item:
                        new_items += item
                    get_items.append(item)

        for imdb_id in imdb_ids:
            if imdb_id in existing_imdb_ids:
                get_items.append(self.trakt_data.get_item("imdb_id", imdb_id))

        added_items = self.trakt_data.extend(new_items)
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.debug("Updated metadata for %s", item.log_string)
        elif length > 5:
            logger.debug("Updated metadata for %s items", len(added_items))
        if length > 0:
            self.trakt_data.extend(added_items)
            self.trakt_data.save(self.pkl_file)
        return get_items

    def _create_item(self, imdb_id):
        item = create_item_from_imdb_id(imdb_id)
        if item is None:
            logger.info(f"Removed request with IMDb ID {imdb_id}, unable to create item.")
            self.trakt_data.remove(imdb_id)
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
    if item_type not in ["movie", "show", "season", "episode"]:
        logger.debug("Unknown item type %s for %s not found in list of acceptable objects", item_type, data.title)
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
        "title": getattr(data, "title", None),              # 'Game of Thrones'
        "year": getattr(data, "year", None),                # 2011
        "status": getattr(data, "status", None),            # 'ended', 'released', 'returning series'
        "aired_at": formatted_aired_at,                     # datetime.datetime(2011, 4, 17, 0, 0)
        "imdb_id": getattr(data.ids, "imdb", None),         # 'tt0496424'
        "tvdb_id": getattr(data.ids, "tvdb", None),         # 79488
        "tmdb_id": getattr(data.ids, "tmdb", None),         # 1399
        "genres": getattr(data, "genres", None),            # ['Action', 'Adventure', 'Drama', 'Fantasy']
        "network": getattr(data, "network", None),          # 'HBO'
        "country": getattr(data, "country", None),          # 'US'
        "language": getattr(data, "language", None),        # 'en'
        "requested_at": datetime.now(),                     # datetime.datetime(2021, 4, 17, 0, 0)
        "is_anime": "anime" in getattr(data, "genres", [])
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

def create_item_from_imdb_id(imdb_id: str):
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
    logger.error("Unable to create item from IMDb ID %s, skipping..", imdb_id)
    return None

def get_imdbid_from_tvdb(tvdb_id: str) -> str:
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

def get_imdbid_from_tmdb(tmdb_id: str) -> str:
    """Get IMDb ID from TMDB ID in Trakt"""
    url = f"https://api.trakt.tv/search/tmdb/{tmdb_id}?extended=full"
    response = get(
        url,
        additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
    )
    if response.is_ok and len(response.data) > 0:
            return response.data[0].movie.ids.imdb
    return None