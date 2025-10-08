"""
Subtitle service for Riven.

Handles subtitle fetching from various providers and stores them in the database
for serving via RivenVFS.

Key features:
- Multi-provider support (OpenSubtitles, extensible for more)
- Multi-language subtitle fetching
- Embedded subtitle detection (skips already-embedded languages)
- OpenSubtitles hash-based matching for accuracy
- Subtitle content stored in database (served via VFS)
- ISO 639-3 language codes

Subtitles are stored as SubtitleEntry objects in the database and served
through RivenVFS alongside video files.
"""

from typing import List, Optional
import io

from loguru import logger

from program.db.db import db
from program.media.item import MediaItem
from program.media.subtitle_entry import SubtitleEntry
from program.media.parsed_media_data import ParsedMediaData
from program.settings.manager import settings_manager
from .providers.opensubtitles import OpenSubtitlesProvider
from .utils import calculate_opensubtitles_hash, generate_subtitle_path


class SubtitleService:
    """
    Service for fetching and managing subtitles.

    Fetches subtitles from configured providers (OpenSubtitles, etc.) and stores
    them in the database for serving via RivenVFS.

    Features:
    - Multi-provider support with score-based ranking
    - Multi-language fetching (ISO 639-3 codes)
    - Embedded subtitle detection (skips redundant downloads)
    - OpenSubtitles hash matching for accuracy
    - Metadata-based search (IMDB ID, season/episode, release group)

    Attributes:
        key: Service identifier ("subtitle").
        settings: Subtitle settings from settings_manager.
        initialized: True if service is properly configured.
        providers: List of initialized subtitle provider instances.
        languages: List of ISO 639-3 language codes to fetch.
    """
    """Service for fetching and managing subtitles."""

    def __init__(self):
        """
        Initialize the SubtitleService.

        Initializes providers and parses language configuration.
        Service is only initialized if enabled and properly configured.
        """
        self.key = "subtitle"
        self.settings = settings_manager.settings.post_processing.subtitle
        self.initialized = False

        if not self.settings.enabled:
            logger.debug("Subtitle service is disabled")
            return

        # Initialize providers
        self.providers = []
        self._initialize_providers()

        if not self.providers:
            logger.warning("No subtitle providers initialized")
            return

        # Parse language codes
        self.languages = self._parse_languages(self.settings.languages)
        if not self.languages:
            logger.warning("No valid languages configured for subtitles")
            return

        self.initialized = True
        logger.info(f"Subtitle service initialized with {len(self.providers)} provider(s) and {len(self.languages)} language(s)")

    def _initialize_providers(self):
        """
        Initialize configured subtitle providers.

        Currently supports:
        - OpenSubtitles (legacy API)

        Future providers can be added here.
        """
        provider_configs = self.settings.providers

        # Initialize OpenSubtitles provider
        if provider_configs.opensubtitles.enabled:
            try:
                provider = OpenSubtitlesProvider()
                self.providers.append(provider)
                logger.debug("OpenSubtitles provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenSubtitles provider: {e}")

        # Add more providers here in the future
        # if provider_configs.get("opensubtitlescom", {}).get("enabled"):
        #     ...

    def _parse_languages(self, language_codes: List[str]) -> List[str]:
        """
        Parse and validate language codes.

        Args:
            language_codes: List of language codes (ISO 639-1, ISO 639-2, or ISO 639-3)

        Returns:
            List of valid ISO 639-3 language codes
        """
        from .providers.opensubtitles import _normalize_language_to_alpha3

        valid_languages = []
        for lang_code in language_codes:
            try:
                normalized = _normalize_language_to_alpha3(lang_code)
                if normalized and normalized != 'eng' or lang_code.lower() in ['en', 'eng']:
                    valid_languages.append(normalized)
                elif normalized == 'eng' and lang_code.lower() not in ['en', 'eng']:
                    # Only add 'eng' if it was explicitly requested
                    logger.warning(f"Language code '{lang_code}' normalized to 'eng' (fallback)")
                else:
                    valid_languages.append(normalized)
            except Exception as e:
                logger.error(f"Failed to parse language code '{lang_code}': {e}")

        return list(set(valid_languages))  # Remove duplicates

    @property
    def enabled(self) -> bool:
        """
        Check if the subtitle service is enabled.

        Returns:
            bool: True if enabled in settings and properly initialized.
        """
        return self.settings.enabled and self.initialized

    def run(self, entry):
        """
        Fetch and store subtitles for a specific MediaEntry.

        Args:
            entry: MediaEntry to fetch subtitles for
        """
        if not self.enabled:
            logger.debug(f"Subtitle service not enabled, skipping {entry.log_string}")
            return

        if not entry.media_item:
            logger.error(f"MediaEntry {entry.id} has no associated MediaItem")
            return

        item = entry.media_item

        try:
            logger.debug(f"Fetching subtitles for {entry.log_string}")

            # Get existing embedded subtitles from parsed_data
            embedded_subtitle_languages = self._get_embedded_subtitle_languages_from_entry(entry)
            if embedded_subtitle_languages:
                logger.debug(f"Found {len(embedded_subtitle_languages)} embedded subtitle language(s) in {entry.log_string}: {', '.join(embedded_subtitle_languages)}")

            # Get video file information
            video_path = entry.path
            video_hash = self._calculate_video_hash_from_entry(entry)
            original_filename = entry.original_filename

            # Build search tags from parsed_data
            search_tags = self._build_search_tags_from_entry(entry)

            # Get IMDB ID
            imdb_id = item.imdb_id

            # Get season/episode info for TV shows
            season = None
            episode = None
            if item.type == "episode":
                season = item.parent.number if item.parent else None
                episode = item.number

            # Get file size
            file_size = entry.file_size

            # Search for subtitles in each language
            for language in self.languages:
                # Skip if language already exists as embedded subtitle
                if language in embedded_subtitle_languages:
                    logger.debug(f"Skipping {language} subtitle for {entry.log_string} - already embedded in video")
                    continue

                try:
                    self._fetch_subtitle_for_language(
                        entry=entry,
                        item=item,
                        language=language,
                        video_path=video_path,
                        video_hash=video_hash,
                        file_size=file_size,
                        original_filename=original_filename,
                        search_tags=search_tags,
                        imdb_id=imdb_id,
                        season=season,
                        episode=episode
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch {language} subtitle for {entry.log_string}: {e}")

            logger.debug(f"Finished fetching subtitles for {entry.log_string}")

        except Exception as e:
            logger.error(f"Failed to fetch subtitles for {entry.log_string}: {e}")

    def _fetch_subtitle_for_language(
        self,
        entry,
        item: MediaItem,
        language: str,
        video_path: str,
        video_hash: Optional[str],
        file_size: Optional[int],
        original_filename: str,
        search_tags: Optional[str],
        imdb_id: Optional[str],
        season: Optional[int],
        episode: Optional[int]
    ):
        """
        Fetch subtitle for a specific language.

        Args:
            entry: MediaEntry to fetch subtitle for
            item: MediaItem (for metadata like imdb_id)
            language: ISO 639-3 language code
            video_path: Virtual VFS path of the video
            video_hash: OpenSubtitles hash of the video
            file_size: Size of the video file in bytes
            original_filename: Original filename of the video
            search_tags: Comma-separated tags (release group, format) for OpenSubtitles
            imdb_id: IMDB ID of the media
            season: Season number (for TV shows)
            episode: Episode number (for TV shows)
        """
        # Check if subtitle already exists
        existing_subtitle = self._get_existing_subtitle(item, language)
        if existing_subtitle:
            logger.debug(f"Subtitle for {language} already exists for {item.log_string}")
            return

        # Search for subtitles across all providers
        all_results = []
        for provider in self.providers:
            try:
                results = provider.search_subtitles(
                    imdb_id=imdb_id or "",
                    video_hash=video_hash,
                    file_size=file_size,
                    filename=original_filename,
                    search_tags=search_tags,
                    season=season,
                    episode=episode,
                    language=language
                )
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Provider {provider.name} failed to search subtitles: {e}")

        if not all_results:
            logger.debug(f"No {language} subtitles found for {item.log_string}")
            return

        # Sort by score (highest first)
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)

        # Try to download the best subtitle
        for subtitle_info in all_results[:3]:  # Try top 3 results
            try:
                provider_name = subtitle_info.get('provider')
                provider = next((p for p in self.providers if p.name == provider_name), None)

                if not provider:
                    continue

                # Download subtitle content
                content = provider.download_subtitle(subtitle_info)
                if not content:
                    continue

                # Generate subtitle path
                subtitle_path = generate_subtitle_path(video_path, language)

                # Create SubtitleEntry and store in database
                subtitle_entry = SubtitleEntry.create_subtitle_entry(
                    path=subtitle_path,
                    language=language,
                    content=content,
                    file_hash=video_hash,
                    video_file_size=item.filesystem_entry.file_size,
                    opensubtitles_id=subtitle_info.get('id')
                )

                # Associate with media item
                subtitle_entry.media_item_id = item.id
                subtitle_entry.available_in_vfs = True

                # Save to database
                with db.Session() as session:
                    session.add(subtitle_entry)
                    session.commit()

                logger.debug(f"Downloaded and stored {language} subtitle for {item.log_string}")
                return

            except Exception as e:
                logger.error(f"Failed to download subtitle from {subtitle_info.get('provider')}: {e}")

        logger.warning(f"Failed to download any {language} subtitle for {item.log_string}")

    def _get_existing_subtitle(self, item: MediaItem, language: str) -> Optional[SubtitleEntry]:
        """
        Check if a subtitle already exists for the item and language.

        Args:
            item: MediaItem to check
            language: ISO 639-3 language code

        Returns:
            Existing SubtitleEntry or None
        """
        try:
            with db.Session() as session:
                subtitle = session.query(SubtitleEntry).filter_by(
                    media_item_id=item.id,
                    language=language
                ).first()
                return subtitle
        except Exception as e:
            logger.error(f"Failed to check for existing subtitle: {e}")
            return None

    def _get_embedded_subtitle_languages_from_entry(self, entry) -> set[str]:
        """
        Extract embedded subtitle languages from MediaEntry's parsed_data.

        Args:
            entry: MediaEntry with parsed_data

        Returns:
            Set of ISO 639-3 language codes
        """
        embedded_languages = set()

        try:
            if not entry.parsed_data:
                return embedded_languages

            # Parse the dict into typed data
            parsed_data = ParsedMediaData.from_dict(entry.parsed_data)
            if not parsed_data or not parsed_data.ffprobe_data:
                return embedded_languages

            subtitle_tracks = parsed_data.ffprobe_data.subtitles or []

            for track in subtitle_tracks:
                # track is now a SubtitleTrack object
                lang = track.language
                if lang and lang != 'unknown':
                    embedded_languages.add(lang)

        except Exception as e:
            logger.warning(f"Failed to extract embedded subtitle languages for {entry.log_string}: {e}")

        return embedded_languages

    def _build_search_tags_from_entry(self, entry) -> Optional[str]:
        """
        Build comma-separated search tags from MediaEntry's parsed_data.

        Args:
            entry: MediaEntry with parsed_data

        Returns:
            Comma-separated tags string or None
        """
        tags = []

        try:
            if not entry.parsed_data:
                return None

            # Parse the dict into typed data
            parsed_data = ParsedMediaData.from_dict(entry.parsed_data)
            if not parsed_data or not parsed_data.parsed_filename:
                return None

            parsed_filename = parsed_data.parsed_filename

            # Add release group if available
            release_group = parsed_filename.group
            if release_group:
                tags.append(release_group)

            # Add quality/format tag
            quality = parsed_filename.quality
            if quality:
                tags.append(quality)

            # Note: ParsedFilenameData doesn't have 'proper' or 'repack' fields
            # These would need to be added to the model if needed

        except Exception as e:
            logger.warning(f"Failed to build search tags for {entry.log_string}: {e}")

        return ','.join(tags) if tags else None

    def _calculate_video_hash_from_entry(self, entry) -> Optional[str]:
        """
        Calculate OpenSubtitles hash for a MediaEntry's video file.

        Args:
            entry: MediaEntry with path and file_size

        Returns:
            OpenSubtitles hash string or None
        """
        try:
            file_size = entry.file_size
            if not file_size:
                logger.debug(f"No file size for {entry.log_string}, cannot calculate hash")
                return None

            # Get the mounted VFS path
            from program.settings.manager import settings_manager
            mount_path = settings_manager.settings.filesystem.mount_path
            vfs_path = entry.path

            # Construct the full path on the host filesystem
            import os
            full_path = os.path.join(mount_path, vfs_path.lstrip('/'))

            # Check if file exists and is accessible
            if not os.path.exists(full_path):
                logger.debug(f"VFS file not accessible at {full_path} for {entry.log_string}")
                return None

            # Calculate hash using the mounted VFS file
            with open(full_path, 'rb') as f:
                video_hash = calculate_opensubtitles_hash(f, file_size)
                logger.debug(f"Calculated OpenSubtitles hash for {entry.log_string}: {video_hash}")
                return video_hash

        except Exception as e:
            logger.warning(f"Failed to calculate video hash for {entry.log_string}: {e}")
            return None


