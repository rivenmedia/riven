""" Jackett scraper module """

import requests
import threading
import time
import xml.etree.ElementTree as ET
import queue

from typing import Dict, Generator

from program.media.item import MediaItem, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import ReadTimeout, RequestException
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get, ping

class JackettIndexer:
    def __init__(self):
        self.title = None
        self.id = None
        self.link = None
        self.type = None
        self.language = None
        self.tv_search_capatabilities = None
        self.movie_search_capatabilities = None

class Jackett:
    """Scraper for `Jackett`"""

    def __init__(self, hash_cache):
        self.key = "jackett"
        self.api_key = None
        self.indexers = []
        self.settings = settings_manager.settings.scraping.jackett
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.initialized = self.validate()
        if not self.initialized and not self.api_key:
            return
        self.parse_logging = False
        self.minute_limiter = RateLimiter(
            max_calls=1000, period=3600, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        logger.success("Jackett initialized!")

    def validate(self) -> bool:
        """Validate Jackett settings."""
        if not self.settings.enabled:
            logger.warning("Jackett is set to disabled.")
            return False
        if self.settings.url and self.settings.api_key:
            self.api_key = self.settings.api_key

        try:
            self.indexers = self._get_indexers()
            if len(self.indexers) == 0:
                logger.error("No Jackett indexers configured.")
                return False
            return True
        except ReadTimeout:
            logger.exception("Jackett request timed out. Check your indexers, they may be too slow to respond.")
        except Exception as e:
            logger.exception(f"Jackett failed to initialize with API Key: {e}")

        logger.info("Jackett is not configured and will not be used.")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Scrape the Jackett site for the given media items
        and update the object with scraped streams"""
        if not item or isinstance(item, Show):
            yield item
            return
        
        try:
            yield self.scrape(item)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            logger.warning(f"Jackett rate limit hit for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Jackett request exception: {e}")
        except Exception as e:
            logger.exception(f"Jackett failed to scrape item with error: {e}")
        yield item

    def scrape(self, item: MediaItem) -> MediaItem:
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if data:
            item.streams.update(data)
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        elif stream_count > 0:
            logger.log("NOT_FOUND", f"Could not find good streams for {item.log_string} out of {stream_count}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
        return item

    def api_scrape(self, item: MediaItem) -> tuple[Dict[str, Torrent], int]:
        """Wrapper for `Jackett` scrape method"""

        threads = []
        results_queue = queue.Queue()  # Create a Queue instance to hold the results

        # Define a wrapper function that calls the actual target function and stores its return value in the queue
        def thread_target(item: MediaItem, indexer):
            logger.debug(f"Searching on {indexer.title}")
            start_time = time.time()

            # Call the actual function
            if item.type == "movie":
                result = self._search_movie_indexer(item, indexer)
            elif item.type == "season" or item.type == "episode":
                result = self._search_series_indexer(item, indexer)
            else:
                raise TypeError("Only Movie and Series is allowed!")

            logger.debug(
                f"Search on {indexer.title} took {time.time() - start_time} seconds and found {len(result)} results")

            results_queue.put(result)  # Put the result in the queue

        for indexer in self.indexers:
            # Pass the wrapper function as the target to Thread, with necessary arguments
            threads.append(threading.Thread(target=thread_target, args=(item, indexer)))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        results = []

        # Retrieve results from the queue and append them to the results list
        while not results_queue.empty():
            results.extend(results_queue.get())

        # logger.info(results)

        torrents = set()
        correct_title = item.get_top_title()
        if not correct_title:
            logger.debug(f"Correct title not found for {item.log_string}")
            return {}, 0

        for item in results:
            if item[1] is None or self.hash_cache.is_blacklisted(item[1]):
                continue

            try:
                torrent: Torrent = self.rtn.rank(
                    raw_title=item[0], infohash=item[1], correct_title=correct_title, remove_trash=True
                )
            except GarbageTorrent:
                continue
            
            if torrent and torrent.fetch:
                torrents.add(torrent)
            
        scraped_torrents = sort_torrents(torrents)
        return scraped_torrents, len(scraped_torrents)

    def _search_movie_indexer(self, item: MediaItem, indexer):
        has_imdb_search_capability = (indexer.movie_search_capatabilities is not None and 'imdbid' in indexer.movie_search_capatabilities)

        results = []

        params = {
            'apikey': self.api_key,
            't': 'movie',
            'cat': '2000',
            'q': item.title,
            'year': item.aired_at.year if hasattr(item.aired_at, "year") and item.aired_at.year else None
        }

        if has_imdb_search_capability:
            params['imdbid'] = item.imdb_id

        url = f"{self.settings.url}/api/v2.0/indexers/{indexer.id}/results/torznab/api"

        try:
            response = requests.get(url=url, params=params)
            response.raise_for_status()
            results = self._get_torrents_from_xml(response.text)
        except Exception as e:
            logger.error(
                f"An exception occured while searching for a movie on Jackett with indexer {indexer.title}.")
            logger.error(e)

        return results

    def _search_series_indexer(self, item: MediaItem, indexer):
    
        if item.type == "season":
            q = item.parent.title
            season = item.number
            ep = None
        elif item.type == "episode":
            q = item.parent.parent.title
            season = item.parent.number
            ep = item.number


        has_imdb_search_capability = (indexer.tv_search_capatabilities is not None
                                      and 'imdbid' in indexer.tv_search_capatabilities)
        

        params = {
            'apikey': self.__api_key,
            't': 'tvsearch',
            'cat': '5000',
            'q': q,
            'season': season,
            'ep': ep
        }

        if has_imdb_search_capability:
            params['imdbid'] = item.imdb_id

        url = f"{self.settings.url}/api/v2.0/indexers/{indexer.id}/results/torznab/api"

        try:
            response = requests.get(url=url, params=params)
            response.raise_for_status()

            data = self._get_torrents_from_xml(response.text)
            return data
        except Exception:
            logger.info(
                f"An exception occured while searching for a series on Jackett with indexer {indexer.title}.")

        return []


    def _get_indexers(self):
        url = f"{self.settings.url}/api/v2.0/indexers/all/results/torznab/api?apikey={self.api_key}&t=indexers&configured=true"

        try:
            response = requests.get(url)
            response.raise_for_status()
            return self._get_indexer_from_xml(response.text)
        except Exception as e:
            logger.error("An exception occured while getting indexers from Jackett.")
            logger.error(e)
            return []

    def _get_indexer_from_xml(self, xml_content):
        xml_root = ET.fromstring(xml_content)

        indexer_list = []
        for item in xml_root.findall('.//indexer'):
            indexer = JackettIndexer()

            indexer.title = item.find('title').text
            indexer.id = item.attrib['id']
            indexer.link = item.find('link').text
            indexer.type = item.find('type').text
            indexer.language = item.find('language').text.split('-')[0]

            logger.debug(f"Indexer: {indexer.title} - {indexer.link} - {indexer.type}")

            movie_search = item.find('.//searching/movie-search[@available="yes"]')
            tv_search = item.find('.//searching/tv-search[@available="yes"]')

            if movie_search is not None:
                indexer.movie_search_capatabilities = movie_search.attrib['supportedParams'].split(',')
            else:
                logger.debug(f"Movie search not available for {indexer.title}")

            if tv_search is not None:
                indexer.tv_search_capatabilities = tv_search.attrib['supportedParams'].split(',')
            else:
                logger.debug(f"TV search not available for {indexer.title}")

            indexer_list.append(indexer)

        return indexer_list

    def _get_torrents_from_xml(self, xml_content):        
        xml_root = ET.fromstring(xml_content)

        result_list = []
        for item in xml_root.findall('.//item'):
            infoHash = item.find('.//torznab:attr[@name="infohash"]',
                                 namespaces={'torznab': 'http://torznab.com/schemas/2015/feed'})

            if infoHash is None:
                continue

            result_list.append((item.find('.//title').text, infoHash.attrib['value']))

        return result_list