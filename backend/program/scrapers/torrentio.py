""" Torrentio scraper module """
from datetime import datetime
import re
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, get, RateLimiter
from utils.settings import settings_manager
from program.media import (
    MediaItem,
    MediaItemContainer,
    MediaItemState,
)


class Scraper:
    """Scraper for torrentio"""

    def __init__(self):
        self.settings = "torrentio"
        self.class_settings = settings_manager.get(self.settings)
        self.last_scrape = 0
        self.filters = self.class_settings["filter"]
        self.minute_limiter = RateLimiter(
            max_calls=140, period=60 * 5, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.initialized = True

    def scrape(self, media_items: MediaItemContainer):
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        logger.info("Scraping...")
        scraped_amount = 0
        items = [item for item in media_items if self._can_we_scrape(item)]
        for item in items:
            try:
                if item.type == "movie":
                    scraped_amount += self._scrape_items([item])
                else:
                    scraped_amount += self._scrape_show(item)
            except RequestException as exception:
                logger.error("%s, trying again next cycle", exception)
                break
            except RateLimitExceeded as exception:
                logger.error("%s, trying again next cycle", exception)
                break
        if scraped_amount > 0:
            logger.info("Scraped %s streams", scraped_amount)
        logger.info("Done!")

    def _scrape_show(self, item: MediaItem):
        scraped_amount = 0
        seasons = [season for season in item.seasons if self._can_we_scrape(season)]
        scraped_amount += self._scrape_items(seasons)
        episodes = [
            episode
            for season in item.seasons
            if season.state
            in [MediaItemState.SCRAPED_NOT_FOUND, MediaItemState.LIBRARY_ONGOING]
            for episode in season.episodes
            if self._can_we_scrape(episode)
        ]
        scraped_amount += self._scrape_items(episodes)
        return scraped_amount

    def _scrape_items(self, items: list):
        amount_scraped = 0
        for item in items:
            data = self.api_scrape(item)
            log_string = item.title
            if item.type == "season":
                log_string = f"{item.parent.title} season {item.number}"
            if item.type == "episode":
                log_string = f"{item.parent.parent.title} season {item.parent.number} episode {item.number}"
            if len(data) > 0:
                item.set("streams", data)
                # item.change_state(MediaItemState.SCRAPED)
                logger.debug("Found %s streams for %s", len(data), log_string)
                amount_scraped += 1
                continue
            logger.debug("Could not find streams for %s", log_string)
        return amount_scraped

    def _can_we_scrape(self, item: MediaItem) -> bool:
        def is_released():
            return (
                item.aired_at is not None
                and datetime.strptime(item.aired_at, "%Y-%m-%d:%H") < datetime.now()
            )

        def needs_new_scrape():
            return (
                datetime.now().timestamp() - item.scraped_at > 60 * 30
                or item.scraped_at == 0
            )

        if item.type == "show" and item.state in [
            MediaItemState.CONTENT,
            MediaItemState.LIBRARY_ONGOING,
        ]:
            return True

        if item.type in ["movie", "season", "episode"] and is_released():
            valid_states = {
                "movie": [MediaItemState.CONTENT],
                "season": [MediaItemState.CONTENT],
                "episode": [MediaItemState.CONTENT],
            }
            invalid_states = {
                "movie": [],
                "season": [MediaItemState.SCRAPED_NOT_FOUND],
                "episode": [],
            }
            if (
                item.state in valid_states[item.type]
                and item.state not in invalid_states[item.type]
            ):
                return needs_new_scrape()

        return False

    def api_scrape(self, item):
        """Wrapper for torrentio scrape method"""
        with self.minute_limiter:
            if item.type == "season":
                identifier = f":{item.number}:1"
                scrape_type = "show"
                imdb_id = item.parent.imdb_id
            elif item.type == "episode":
                identifier = f":{item.parent.number}:{item.number}"
                scrape_type = "show"
                imdb_id = item.parent.parent.imdb_id
            else:
                identifier = None
                scrape_type = "movie"
                imdb_id = item.imdb_id

            url = (
                f"https://torrentio.strem.fun/{self.filters}"
                + f"/stream/{scrape_type}/{imdb_id}"
            )
            if identifier:
                url += f"{identifier}"
            with self.second_limiter:
                response = get(f"{url}.json", retry_if_failed=False)
                item.set("scraped_at", datetime.now().timestamp())
            if response.is_ok:
                data = {}
                for stream in response.data.streams:
                    # lets get only 20 streams
                    if len(data) >= 20:
                        break
                    complete_title = stream.title.split("\n👤")[0]
                    folder = complete_title.split("\n")[0]
                    file = complete_title.split("\n")[-1]
                    if not _matches_formatting(item, file, folder):
                        continue
                    data[stream.infoHash] = {
                        "name": stream.title.split("\n👤")[0],
                        "seeds": re.search(r"👤\s*(\d*)\s*💾", stream.title).group(1),
                    }

                if len(data) > 0:
                    return data
            else:
                # item.change_state(MediaItemState.ERROR)
                pass
            return {}


def _matches_formatting(item: MediaItem, file: str, folder: str) -> bool:
    if not _matches_rclone_formatting(item, file, folder):
        return False

    def match_folder(folder: str):
        season_pattern = r"(S\d{2}|Season \d{1,2})"
        episode_pattern = r"(E\d{1,2}|Episode \d{1,2})"
        matches = re.finditer(season_pattern, folder, re.IGNORECASE)
        return [
            match.group()
            for match in matches
            if not re.search(episode_pattern, folder[match.start():])
        ]

    match (item.type):
        case "movie":
            pattern = r"^(?:(?!Season|Episode|Collection|S\d{1,2}|E\d{1,2}).)*$"
            return len(re.findall(pattern, file, re.IGNORECASE)) > 0
        case "season":
            return len(match_folder(folder)) > 0
        case "episode":
            if len(match_folder(folder)) == 0:
                return False
            pattern = r"(S\d{1,2}|Season \d{1,2}).*(E\d{1,2}|Episode \d{1,2})"
            return len(re.findall(pattern, file, re.IGNORECASE)) > 0
        case _:
            return False


def _matches_rclone_formatting(item, file, folder) -> bool:
    matching_string = file
    match (item.type):
        case "movie":
            pattern = r"(19|20)([0-9]{2} ?\.?)"
        case _:
            pattern = r"(S[0-9]{2}|SEASON|COMPLETE|[^457a-z\W\s]-[0-9]+)"
            matching_string = folder

    return len(re.findall(pattern, matching_string, re.IGNORECASE)) > 0
