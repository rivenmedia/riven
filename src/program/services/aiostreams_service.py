"""AIOStreams Service - Direct Content Provider

This service acts as a unified scraper+downloader for AIOStreams.
Unlike traditional scrapers that only find torrents, AIOStreams provides
direct download URLs, so this service:
1. Scrapes streams from AIOStreams API
2. Ranks and selects the best stream using RTN
3. Creates MediaEntry directly with the download URL
4. Bypasses the traditional Downloader service entirely
"""

import re
from typing import Dict, Generator, Optional
from urllib.parse import unquote

from loguru import logger
from RTN import Torrent

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.media_entry import MediaEntry
from program.media.state import States
from program.media.stream import Stream
from program.services.library_profile_matcher import LibraryProfileMatcher
from program.services.scrapers.shared import _parse_results
from program.settings.manager import settings_manager
from program.settings.models import AIOStreamsConfig
from program.utils.request import SmartSession


class AIOStreamsService:
    """
    AIOStreams service that handles both scraping and MediaEntry creation.

    This service replaces the traditional Scraping + Downloader flow for AIOStreams,
    providing direct download URLs that are immediately usable by FilesystemService.
    """

    def __init__(self):
        self.key = "aiostreams"
        self.settings: AIOStreamsConfig = settings_manager.settings.scraping.aiostreams
        self.timeout: int = self.settings.timeout or 30
        self.initialized = False

        self.session = SmartSession(retries=3, backoff_factor=0.3)
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.library_matcher = LibraryProfileMatcher()

        self._initialize()

    def _initialize(self) -> None:
        """Initialize the service by validating settings."""
        try:
            if self.validate():
                self.initialized = True
                logger.success("AIOStreamsService initialized")
        except Exception as e:
            logger.error(f"AIOStreamsService initialization failed: {e}")

    def validate(self) -> bool:
        """Validate the AIOStreams settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.manifest_url:
            logger.error("AIOStreams manifest URL is not configured")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("AIOStreams timeout is not set or invalid")
            return False

        try:
            # Validate manifest URL
            response = self.session.get(
                self.settings.manifest_url, timeout=10, headers=self.headers
            )
            if response.ok:
                return True
        except Exception as e:
            logger.error(f"AIOStreams failed to validate: {e}")
            return False

        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """
        Process a MediaItem through AIOStreams.

        This method:
        1. Scrapes streams from AIOStreams API
        2. Ranks and selects the best stream
        3. Creates MediaEntry with the direct download URL
        4. Sets item state to Downloaded (ready for FilesystemService)

        Args:
            item: MediaItem to process (Movie or Episode only)

        Yields:
            The processed MediaItem
        """
        # Only process movies and episodes (leaf items)
        if item.type not in ("movie", "episode"):
            logger.debug(f"Skipping non-leaf item: {item.log_string}")
            yield item
            return

        try:
            # Scrape streams from AIOStreams
            streams_data = self._scrape_streams(item)

            if not streams_data:
                logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
                item.scraped_at = None  # Mark as not scraped
                item.scraped_times = (item.scraped_times or 0) + 1
                item.failed_attempts = (item.failed_attempts or 0) + 1
                yield item
                return

            # Parse and rank streams using RTN
            sorted_streams = self._rank_streams(item, streams_data)

            if not sorted_streams:
                logger.log(
                    "NOT_FOUND", f"No valid streams after ranking for {item.log_string}"
                )
                item.scraped_at = None
                item.scraped_times = (item.scraped_times or 0) + 1
                item.failed_attempts = (item.failed_attempts or 0) + 1
                yield item
                return

            # Select best stream
            best_stream = list(sorted_streams.values())[0]
            direct_url = streams_data[best_stream.infohash]["url"]
            filename = streams_data[best_stream.infohash]["filename"]
            provider = streams_data[best_stream.infohash]["provider"]

            logger.debug(
                f"Selected stream for {item.log_string}: {best_stream.raw_title} "
                f"(rank: {best_stream.rank}, provider: {provider})"
            )

            # Create MediaEntry
            success = self._create_media_entry(
                item, filename, direct_url, provider, best_stream
            )

            if success:
                # Store the stream for reference
                item.streams.append(best_stream)

                # Set active stream
                item.active_stream = {
                    "infohash": best_stream.infohash,
                    "id": "aiostreams",
                }

                logger.debug(
                    f"Created MediaEntry for {item.log_string} with provider {provider}"
                )
            else:
                logger.error(f"Failed to create MediaEntry for {item.log_string}")
                item.failed_attempts = (item.failed_attempts or 0) + 1

        except Exception as e:
            logger.error(f"AIOStreams exception for {item.log_string}: {e}")
            item.failed_attempts = (item.failed_attempts or 0) + 1

        yield item

    def _scrape_streams(self, item: MediaItem) -> Dict[str, Dict[str, str]]:
        """
        Scrape streams from AIOStreams API.

        Returns:
            Dict mapping infohash to stream data:
            {
                "infohash": {
                    "title": "stream title",
                    "url": "direct download URL",
                    "filename": "extracted filename",
                    "provider": "service name (realdebrid, torbox, etc.)"
                }
            }
        """
        # Get Stremio identifier
        identifier, scrape_type, imdb_id = self._get_stremio_identifier(item)
        if not imdb_id:
            logger.debug(f"No IMDb ID for {item.log_string}")
            return {}

        # Build API URL
        base_url = self.settings.manifest_url.replace("/manifest.json", "")
        url = f"{base_url}/stream/{scrape_type}/{imdb_id}"
        if identifier:
            url += identifier

        # Fetch streams
        try:
            response = self.session.get(
                f"{url}.json",
                timeout=self.timeout,
                headers=self.headers,
            )
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"AIOStreams rate limit exceeded for {item.log_string}")
            else:
                logger.exception(f"AIOStreams request failed: {e}")
            return {}

        if (
            not response.ok
            or not hasattr(response.data, "streams")
            or not response.data.streams
        ):
            return {}

        # Parse streams
        streams_data: Dict[str, Dict[str, str]] = {}
        for stream in response.data.streams:
            # Extract infohash and URL
            if not hasattr(stream, "url") or not stream.url:
                continue

            parsed = self._parse_aiostreams_url(stream.url)
            if not parsed:
                continue
            provider = parsed["provider"]
            infohash = parsed["infohash"]
            filename = parsed["filename"]

            streams_data[infohash] = {
                "title": stream.description,
                "url": stream.url,
                "filename": filename,
                "provider": provider,
            }

        return streams_data

    def _rank_streams(
        self, item: MediaItem, streams_data: Dict[str, Dict[str, str]]
    ) -> Dict[str, Stream]:
        """
        Rank streams using RTN.

        Args:
            item: MediaItem being processed
            streams_data: Raw stream data from AIOStreams

        Returns:
            Dict of ranked Stream objects, sorted by quality
        """
        # Convert to format expected by _parse_results
        torrents_dict = {
            infohash: data["title"] for infohash, data in streams_data.items()
        }

        # Use shared ranking logic
        return _parse_results(item, torrents_dict, log_msg=True)

    def _create_media_entry(
        self,
        item: MediaItem,
        filename: str,
        download_url: str,
        provider: str,
        stream: Stream,
        file_size: int = 0,
    ) -> bool:
        """
        Create MediaEntry for the item with the AIOStreams download URL.

        Args:
            item: MediaItem to attach entry to
            filename: Original filename
            download_url: Direct download URL from AIOStreams
            provider: Provider service name (realdebrid, torbox, etc.)
            stream: Selected Stream object
            file_size: File size in bytes from behaviorHints.videoSize

        Returns:
            True if successful, False otherwise
        """
        try:
            # Match library profiles
            library_profiles = self.library_matcher.get_matching_profiles(item)

            # Create MediaEntry
            entry = MediaEntry.create_virtual_entry(
                original_filename=filename,
                download_url=download_url,
                provider=provider,
                provider_download_id=stream.infohash,  # Store infohash for re-scraping
                file_size=file_size,  # From behaviorHints.videoSize
                parsed_data=(
                    stream.parsed_data.model_dump() if stream.parsed_data else None
                ),
            )

            # Set library profiles
            entry.library_profiles = library_profiles

            # Attach to item
            item.filesystem_entries.clear()
            item.filesystem_entries.append(entry)

            return True

        except Exception as e:
            logger.error(f"Failed to create MediaEntry: {e}")
            return False

    @staticmethod
    def _get_stremio_identifier(item: MediaItem) -> tuple[str | None, str, str]:
        """Get the Stremio identifier for a given item."""
        if isinstance(item, Show):
            return ":1:1", "series", item.imdb_id
        elif isinstance(item, Season):
            return f":{item.number}:1", "series", item.parent.imdb_id
        elif isinstance(item, Episode):
            return (
                f":{item.parent.number}:{item.number}",
                "series",
                item.parent.parent.imdb_id,
            )
        elif isinstance(item, Movie):
            return None, "movie", item.imdb_id
        else:
            return None, None, None

    @staticmethod
    def _parse_aiostreams_url(url: str) -> Optional[Dict[str, str]]:
        """
        Parse AIOStreams URL to extract provider, infohash, and filename.

        URL format: https://torrentio.strem.fun/resolve/{provider}/{token}/{infohash}/null/{fileIdx}/{filename}

        Args:
            url: AIOStreams stream URL

        Returns:
            Dict with 'provider', 'infohash', 'filename' keys, or None if parsing fails
        """
        try:
            # Extract provider from URL
            # URL format: .../resolve/{provider}/{token}/...
            provider_match = re.search(r"/resolve/([^/]+)/", url)
            provider = provider_match.group(1) if provider_match else "unknown"

            # Extract infohash (40 character hex string)
            infohash_match = re.search(r"/([a-fA-F0-9]{40})/", url)
            if not infohash_match:
                logger.debug(f"No infohash found in URL: {url}")
                return None
            infohash = infohash_match.group(1)

            # Extract filename (last part of URL, URL-decoded)
            parts = url.split("/")
            if len(parts) >= 2:
                filename = unquote(parts[-1])
            else:
                filename = "unknown.mkv"

            return {
                "provider": provider,
                "infohash": infohash,
                "filename": filename,
            }
        except Exception as e:
            logger.debug(f"Failed to parse AIOStreams URL: {e}")
            return None
