import threading
from datetime import datetime
from typing import Dict, Generator, List, Set, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.scrapers.annatar import Annatar
from program.scrapers.jackett import Jackett
from program.scrapers.knightcrawler import Knightcrawler
from program.scrapers.mediafusion import Mediafusion
from program.scrapers.orionoid import Orionoid
from program.scrapers.prowlarr import Prowlarr
from program.scrapers.torbox import TorBoxScraper
from program.scrapers.torrentio import Torrentio
from program.settings.manager import settings_manager
from program.settings.versions import models
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger


class Scraping:
    def __init__(self, hash_cache):
        self.key = "scraping"
        self.initialized = False
        self.settings = settings_manager.settings.scraping
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        self.services = {
            Annatar: Annatar(),
            Torrentio: Torrentio(),
            Knightcrawler: Knightcrawler(),
            Orionoid: Orionoid(),
            Jackett: Jackett(),
            TorBoxScraper: TorBoxScraper(),
            Mediafusion: Mediafusion(),
            Prowlarr: Prowlarr()
        }
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self):
        return any(service.initialized for service in self.services.values())

    def yield_incomplete_children(self, item: MediaItem) -> Union[List[Season], List[Episode]]:
        if isinstance(item, Season):
            res = [e for e in item.episodes if e.state not in [States.Completed] and e.is_released]
            return res
        if isinstance(item, Show):
            res = [s for s in item.seasons if s.state not in [States.Completed] and s.is_released]
            return res
        return None

    def partial_state(self, item: MediaItem) -> bool:
        if item.state != States.PartiallyCompleted:
            return False
        if isinstance(item, Show):
            sres = [s for s in item.seasons if s.state not in [States.Completed] and s.is_released ]
            res = []
            for s in sres:
                if all(episode.is_released == True and episode.state != States.Completed for episode in s.episodes):
                    res.append(s)
                else:
                    res = res + [e for e in s.episodes if e.is_released == True and e.state != States.Completed]
            return res
        if isinstance(item, Season):
            return [e for e in s.episodes if e.is_release == True]
        return item

    def run(self, item: Union[Show, Season, Episode, Movie]) -> Generator[Union[Show, Season, Episode, Movie], None, None]:
        """Scrape an item."""
        if not item or not self.can_we_scrape(item):
            yield self.yield_incomplete_children(item)
            return

        partial_state = self.partial_state(item)
        if partial_state != False:
            yield partial_state
            return

        threads: List[threading.Thread] = []
        results: Dict[str, str] = {}
        results_lock = threading.Lock()  # Add a lock for thread-safe updates

        def run_service(service, item):
            service_results = service.run(item)
            with results_lock:
                results.update(service_results)

        for service_name, service in self.services.items():
            if service.initialized:
                thread = threading.Thread(target=run_service, args=(service, item), name=service_name.__name__)
                threads.append(thread)
                thread.start()

        for thread in threads:
            thread.join(timeout=60)

        # Parse the results into Torrent objects
        sorted_streams: Dict[str, Torrent] = self._parse_results(item, results)

        # For debug purposes:
        if sorted_streams and settings_manager.settings.debug:
            item_type = item.type.title()
            for _, sorted_tor in sorted_streams.items():
                if isinstance(item, (Season, Episode)):
                    logger.debug(f"[{item_type} {item.number}] Parsed '{sorted_tor.data.parsed_title}' with rank {sorted_tor.rank} and ratio {sorted_tor.lev_ratio:.2f}: '{sorted_tor.raw_title}'")
                else:
                    logger.debug(f"[{item_type}] Parsed '{sorted_tor.data.parsed_title}' with rank {sorted_tor.rank} and ratio {sorted_tor.lev_ratio:.2f}: '{sorted_tor.raw_title}'")

        # Set the streams and yield the item
        item.streams.update(sorted_streams)
        item.set("scraped_at", datetime.now())
        item.set("scraped_times", item.scraped_times + 1)

        if not item.get("streams", {}):
            logger.debug(f"Scraped zero items for {item.log_string}")
            yield self.yield_incomplete_children(item)
            return

        yield item

    @classmethod
    def can_we_scrape(cls, item: MediaItem) -> bool:
        """Check if we can scrape an item."""
        return item.is_released and cls.should_submit(item)

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """Check if an item should be submitted for scraping."""
        settings = settings_manager.settings.scraping
        scrape_time = 5 * 60  # 5 minutes by default

        if item.scraped_times >= 2 and item.scraped_times <= 5:
            scrape_time = settings.after_2 * 60 * 60
        elif item.scraped_times > 5 and item.scraped_times <= 10:
            scrape_time = settings.after_5 * 60 * 60
        elif item.scraped_times > 10:
            scrape_time = settings.after_10 * 60 * 60

        return (
            not item.scraped_at
            or (datetime.now() - item.scraped_at).total_seconds() > scrape_time
        )

    def _parse_results(self, item: MediaItem, results: Dict[str, str]) -> Dict[str, Torrent]:
        """Parse the results from the scrapers into Torrent objects."""
        torrents: Set[Torrent] = set()
        processed_infohashes: Set[str] = set()
        correct_title: str = item.get_top_title()

        if isinstance(item, Show):
            needed_seasons = [season.number for season in item.seasons]

        for infohash, raw_title in results.items():
            if infohash in processed_infohashes or self.hash_cache.is_blacklisted(infohash):
                continue

            try:
                torrent: Torrent = self.rtn.rank(
                    raw_title=raw_title,
                    infohash=infohash,
                    correct_title=correct_title,
                    remove_trash=True
                )

                if not torrent or not torrent.fetch:
                    continue

                if isinstance(item, Movie):
                    if hasattr(item, 'aired_at'):
                        # If the item has an aired_at date and it's not in the future, we can check the year
                        if item.aired_at <= datetime.now() and item.aired_at.year == torrent.data.year:
                            torrents.add(torrent)
                    else:
                        # This is a questionable move. 
                        torrents.add(torrent)

                elif isinstance(item, Show):
                    if not needed_seasons:
                        logger.error(f"No seasons found for {item.log_string}")
                        break
                    if (
                        hasattr(torrent.data, 'season')
                        and len(torrent.data.season) >= (len(needed_seasons) - 1)
                        and (
                            not hasattr(torrent.data, 'episode')
                            or len(torrent.data.episode) == 0
                        )
                        or torrent.data.is_complete
                    ):
                        torrents.add(torrent)

                elif isinstance(item, Season):
                    if (
                        len(getattr(torrent.data, 'season', [])) == 1
                        and item.number in torrent.data.season
                        and (
                            not hasattr(torrent.data, 'episode')
                            or len(torrent.data.episode) == 0
                        )
                        or torrent.data.is_complete
                    ):
                        torrents.add(torrent)

                elif isinstance(item, Episode):
                    if (
                        item.number in torrent.data.episode
                        and (
                            not hasattr(torrent.data, 'season')
                            or item.parent.number in torrent.data.season
                        )
                        or torrent.data.is_complete
                    ):
                        torrents.add(torrent)

                processed_infohashes.add(infohash)

            except (ValueError, AttributeError) as e:
                logger.error(f"Failed to parse {raw_title}: {e}")
                continue
            except GarbageTorrent:
                continue

        return sort_torrents(torrents)
