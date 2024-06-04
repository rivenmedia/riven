import concurrent.futures
import os
import time
from datetime import datetime
from threading import Lock

from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.server import PlexServer
from program.media.item import Episode, Movie, Season, Show
from program.settings.manager import settings_manager
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3.exceptions import MaxRetryError, NewConnectionError, RequestError
from utils.logger import logger


class PlexLibrary:
    """Plex library class"""

    def __init__(self):
        self.key = "plexlibrary"
        self.initialized = False
        self.library_path = os.path.abspath(
            os.path.dirname(settings_manager.settings.symlink.library_path)
        )
        self.last_fetch_times = {}
        self.settings = settings_manager.settings.plex
        self.plex = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.lock = Lock()
        logger.success("Plex Library initialized!")

    def _get_last_fetch_time(self, section):
        return self.last_fetch_times.get(section.key, datetime(1800, 1, 1))

    def validate(self):
        """Validate Plex library"""
        if not self.settings.token:
            logger.error("Plex Library token is not set, this is required!")
            return False
        if not self.settings.url:
            logger.error("Plex URL is not set, this is required!")
            return False
        if not self.library_path:
            logger.error("Library path is not set, this is required!")
            return False
        if not os.path.exists(self.library_path):
            logger.error("Library path does not exist!")
            return False

        try:
            self.plex = PlexServer(self.settings.url, self.settings.token, timeout=60)
            self.initialized = True
            return True
        except Unauthorized:
            logger.error("Plex is not authorized!")
        except BadRequest as e:
            logger.error(f"Plex bad request received: {str(e)}")
        except MaxRetryError as e:
            logger.error(f"Plex max retries exceeded: {str(e)}")
        except NewConnectionError as e:
            logger.error(f"Plex new connection error: {str(e)}")
        except RequestsConnectionError as e:
            logger.error(f"Plex requests connection error: {str(e)}")
        except RequestError as e:
            logger.error(f"Plex request error: {str(e)}")
        except Exception as e:
            logger.exception(f"Plex exception thrown: {str(e)}")
        return False

    def run(self):
        """Run Plex library with synchronous processing and controlled chunking."""
        items = []
        sections = self.plex.library.sections()
        processed_sections = set()
        max_workers = os.cpu_count() // 2  # Use integer division for workers
        rate_limit = 5  # Process 5 chunks per minute

        # Create a synchronous executor
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Plex") as executor:
                futures = []
                for section in sections:
                    is_wanted = self._is_wanted_section(section)
                    if section.key in processed_sections or not is_wanted or section.refreshing:
                        continue

                    last_fetch_time = self._get_last_fetch_time(section)
                    filters = {"addedAt>>": last_fetch_time} if self.last_fetch_times else {}
                    items_to_process = section.search(libtype=section.type, filters=filters)

                    # Process in chunks to manage memory and rate limit
                    for chunk in self._chunked(items_to_process, 50):
                        try:
                            future = executor.submit(self._process_chunk, chunk)
                            futures.append(future)
                        except RuntimeError as e:
                            if 'cannot schedule new futures after shutdown' in str(e):
                                logger.warning("Executor has been shut down, stopping chunk processing.")
                                break
                            else:
                                logger.exception(f"Failed to process chunk: {e}")
                        except Exception as e:
                            logger.exception(f"Failed to process chunk: {e}")
                            continue
                        
                        if len(futures) % rate_limit == 0:
                            # Rate limit: process 5 chunks per minute
                            time.sleep(60)

                # Gather all results
                for future in concurrent.futures.as_completed(futures):
                    try:
                        chunk_results = future.result(timeout=2)  # Add timeout to speed up shutdown
                        items.extend(chunk_results)
                        with self.lock:
                            self.last_fetch_times[section.key] = datetime.now()
                        processed_sections.add(section.key)
                    except concurrent.futures.TimeoutError:
                        logger.warning("Timeout while waiting for chunk processing result.")
                    except Exception as e:
                        logger.exception(f"Failed to get chunk result: {e}")

            if not processed_sections:
                return []

            return items
        except Exception as e:
            logger.exception(f"Unexpected error occurred: {e}")
            return []

    def _process_chunk(self, chunk):
        """Process a chunk of items and create MediaItems."""
        return [self._create_item(item) for item in chunk]

    def _chunked(self, iterable, size):
        """Yield successive n-sized chunks from an iterable."""
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]

    def _create_item(self, raw_item):
        """Create a MediaItem from Plex API data."""
        item = _map_item_from_data(raw_item)
        if not item or raw_item.type != "show":
            return item
        for season in raw_item.seasons():
            if season.seasonNumber == 0:
                continue
            if not (season_item := _map_item_from_data(season)):
                continue
            episode_items = []
            for episode in season.episodes():
                episode_item = _map_item_from_data(episode)
                if episode_item:
                    episode_items.append(episode_item)
            season_item.episodes = episode_items
            item.seasons.append(season_item)
        return item

    def _is_wanted_section(self, section):
        section_located = any(
            self.library_path in location for location in section.locations
        )
        return section_located and section.type in ["movie", "show"]


def _map_item_from_data(item):
    """Map Plex API data to MediaItemContainer."""
    file = None
    guid = getattr(item, "guid", None)
    if item.type in ["movie", "episode"]:
        file = getattr(item, "locations", [None])[0].split("/")[-1]
    genres = [genre.tag for genre in getattr(item, "genres", [])]
    is_anime = "anime" in genres
    title = getattr(item, "title", None)
    key = getattr(item, "key", None) # super important!
    season_number = getattr(item, "seasonNumber", None)
    episode_number = getattr(item, "episodeNumber", None)
    art_url = getattr(item, "artUrl", None)
    imdb_id = None
    tvdb_id = None
    aired_at = None

    if item.type in ["movie", "show"]:
        guids = getattr(item, "guids", [])
        imdb_id = next(
            (guid.id.split("://")[-1] for guid in guids if "imdb" in guid.id), None
        )
        aired_at = getattr(item, "originallyAvailableAt", None)

    media_item_data = {
        "title": title,
        "imdb_id": imdb_id,
        "tvdb_id": tvdb_id,
        "aired_at": aired_at,
        "genres": genres,
        "key": key,
        "guid": guid,
        "art_url": art_url,
        "file": file,
        "is_anime": is_anime,
    }

    # Instantiate the appropriate subclass based on 'item_type'
    if item.type == "movie":
        return Movie(media_item_data)
    elif item.type == "show":
        return Show(media_item_data)
    elif item.type == "season":
        media_item_data["number"] = season_number
        return Season(media_item_data)
    elif item.type == "episode":
        media_item_data["number"] = episode_number
        media_item_data["season_number"] = season_number
        return Episode(media_item_data)
    else:
        # Specials may end up here..
        logger.error(f"Unknown Item: {item.title} with type {item.type}")
        return None
