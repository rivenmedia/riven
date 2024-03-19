""" Jackett scraper module """

from program.media.item import Show
from program.settings.manager import settings_manager
from program.versions.parser import ParsedTorrents, Torrent
from requests import ReadTimeout, RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping


class Jackett:
    """Scraper for `Jackett`"""

    def __init__(self):
        self.key = "jackett"
        self.api_key = None
        self.settings = settings_manager.settings.scraping.jackett
        self.initialized = self.validate()
        if not self.initialized and not self.api_key:
            return
        self.parse_logging = False
        self.minute_limiter = RateLimiter(
            max_calls=1000, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        logger.info("Jackett initialized!")

    def validate(self) -> bool:
        """Validate Jackett settings."""
        if not self.settings.enabled:
            logger.debug("Jackett is set to disabled.")
            return False
        if self.settings.url and self.settings.api_key:
            self.api_key = self.settings.api_key
            try:
                url = f"{self.settings.url}/api/v2.0/indexers/!status:failing,test:passed/results/torznab?apikey={self.api_key}&cat=2000&t=movie&q=test"
                response = ping(url=url, timeout=60)
                if response.ok:
                    return True
            except ReadTimeout:
                return True
            except Exception as e:
                logger.error("Jackett failed to initialize with API Key: %s", e)
                return False
        logger.info("Jackett is not configured and will not be used.")
        return False

    def run(self, item):
        """Scrape the jackett site for the given media items
        and update the object with scraped streams"""
        if item is None or isinstance(item, Show):
            yield item
        try:
            yield self._scrape_item(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            logger.warn("Jackett rate limit hit for item: %s", item.log_string)
        except RequestException as e:
            logger.debug("Jackett request exception: %s", e)
        except Exception as e:
            logger.error("Jackett failed to scrape item: %s", e)
        return item

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data.torrents)
            logger.debug(
                "Found %s streams out of %s for %s",
                len(data),
                stream_count,
                item.log_string,
            )
        else:
            logger.debug("Could not find streams for %s", item.log_string)
        return item

    def api_scrape(self, item) -> tuple[ParsedTorrents, int]:
        """Wrapper for `Jackett` scrape method"""
        # https://github.com/Jackett/Jackett/wiki/Jackett-Categories
        with self.minute_limiter:
            query = ""
            if item.type == "movie":
                query = f"cat=2000&t=movie&q={item.title}&year{item.aired_at.year}"
            if item.type == "season":
                query = (
                    f"cat=5000&t=tvsearch&q={item.parent.title}&season={item.number}"
                )
            if item.type == "episode":
                query = f"cat=5000&t=tvsearch&q={item.parent.parent.title}&season={item.parent.number}&ep={item.number}"
            url = f"{self.settings.url}/api/v2.0/indexers/all/results/torznab?apikey={self.api_key}&{query}"
            with self.second_limiter:
                response = get(url=url, retry_if_failed=False, timeout=60)
            if (
                not response.is_ok
                or response.data["rss"]["channel"].get("item", []) <= 0
            ):
                return {}, 0
            streams = response.data["rss"]["channel"].get("item", [])
            if not streams:
                return {}, 0
            scraped_torrents = ParsedTorrents()
            for stream in streams:
                attr = stream.get("torznab:attr", [])
                infohash_attr = next(
                    (a for a in attr if a.get("@name") == "infohash"), None
                )
                if infohash_attr:
                    infohash = infohash_attr.get("@value")
                    torrent: Torrent = Torrent(
                        item=item, raw_title=stream.get("title"), infohash=infohash
                    )
                    if torrent and torrent.parsed_data.fetch:
                        scraped_torrents.add(torrent)
            scraped_torrents.sort()
            return scraped_torrents, len(response.data.data.streams)
