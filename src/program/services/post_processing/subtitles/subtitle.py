"""
Subtitle service for Riven.

Handles subtitle fetching from various providers and stores them in the database
for serving via RivenVFS.
"""

from typing import List, Optional
from sqlalchemy.orm import object_session
from loguru import logger

from program.db.db import db
from program.media.item import MediaItem
from program.media.subtitle_entry import SubtitleEntry
from program.settings.manager import settings_manager
from program.services.filesystem.filesystem_service import FilesystemService
from program.core.runner import Runner
from program.settings.models import SubtitleConfig
from .providers.opensubtitles import OpenSubtitlesProvider
from .utils import calculate_opensubtitles_hash


class SubtitleService(Runner[SubtitleConfig]):
    """Service for fetching and managing subtitles."""

    def __init__(self):
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
        logger.info(
            f"Subtitle service initialized with {len(self.providers)} provider(s) and {len(self.languages)} language(s)"
        )

    def _initialize_providers(self):
        """Initialize configured subtitle providers."""
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
                if (
                    normalized
                    and normalized != "eng"
                    or lang_code.lower() in ["en", "eng"]
                ):
                    valid_languages.append(normalized)
                elif normalized == "eng" and lang_code.lower() not in ["en", "eng"]:
                    # Only add 'eng' if it was explicitly requested
                    logger.warning(
                        f"Language code '{lang_code}' normalized to 'eng' (fallback)"
                    )
                else:
                    valid_languages.append(normalized)
            except Exception as e:
                logger.error(f"Failed to parse language code '{lang_code}': {e}")

        return list(set(valid_languages))  # Remove duplicates

    @property
    def enabled(self) -> bool:
        """Check if the subtitle service is enabled."""
        return self.settings.enabled and self.initialized

    def run(self, item: MediaItem):
        """
        Fetch and store subtitles for a media item.

        Note: Caller (PostProcessing) is responsible for checking should_submit()
        and ensuring item type is movie/episode.

        Args:
            item: MediaItem to fetch subtitles for (must be movie or episode)
        """
        if not self.enabled:
            logger.debug(f"Subtitle service not enabled, skipping {item.log_string}")
            return

        if not item.filesystem_entry:
            logger.warning(
                f"No filesystem entry for {item.log_string}, cannot fetch subtitles"
            )
            return

        try:
            logger.debug(f"Fetching subtitles for {item.log_string}")

            # Get existing embedded subtitles from media_metadata
            embedded_subtitle_languages = self._get_embedded_subtitle_languages(item)
            if embedded_subtitle_languages:
                logger.debug(
                    f"Found {len(embedded_subtitle_languages)} embedded subtitle language(s) in {item.log_string}: {', '.join(embedded_subtitle_languages)}"
                )

            # Get video file information
            # Get VFS paths (use base path for video_path)
            vfs_paths = item.filesystem_entry.get_all_vfs_paths()
            if not vfs_paths:
                logger.warning(
                    f"No VFS paths for {item.log_string}, cannot fetch subtitles"
                )
                return

            video_path = vfs_paths[0]  # Use base path
            video_hash = self._calculate_video_hash(item)
            original_filename = item.filesystem_entry.get_original_filename()

            # Build search tags from media_metadata for better OpenSubtitles matching
            # Tags are release group names and format identifiers (BluRay, HDTV, etc.)
            # NOT full filenames - see https://trac.opensubtitles.org/opensubtitles/wiki/XMLRPC#Supportedtags
            search_tags = self._build_search_tags(item)

            # Get IMDB ID
            imdb_id = item.imdb_id

            # Get season/episode info for TV shows
            season = None
            episode = None
            if item.type == "episode":
                season = item.parent.number if item.parent else None
                episode = item.number

            # Get file size
            file_size = (
                item.filesystem_entry.file_size if item.filesystem_entry else None
            )

            # Search for subtitles in each language
            for language in self.languages:
                # Skip if language already exists as embedded subtitle
                if language in embedded_subtitle_languages:
                    logger.debug(
                        f"Skipping {language} subtitle for {item.log_string} - already embedded in video"
                    )
                    continue

                try:
                    self._fetch_subtitle_for_language(
                        item=item,
                        language=language,
                        video_path=video_path,
                        video_hash=video_hash,
                        file_size=file_size,
                        original_filename=original_filename,
                        search_tags=search_tags,
                        imdb_id=imdb_id,
                        season=season,
                        episode=episode,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to fetch {language} subtitle for {item.log_string}: {e}"
                    )

            logger.debug(f"Finished fetching subtitles for {item.log_string}")

        except Exception as e:
            logger.error(f"Failed to fetch subtitles for {item.log_string}: {e}")

    def _get_embedded_subtitle_languages(self, item: MediaItem) -> set[str]:
        """
        Extract embedded subtitle languages from media_metadata.

        Checks the media_metadata.subtitle_tracks array from MediaAnalysisService
        and returns a set of ISO 639-3 language codes.

        Args:
            item: MediaItem with filesystem_entry containing media_metadata

        Returns:
            Set of ISO 639-3 language codes (e.g., {'eng', 'spa', 'fre'})
        """
        embedded_languages = set()

        try:
            if not item.filesystem_entry or not item.filesystem_entry.media_metadata:
                return embedded_languages

            media_metadata = item.filesystem_entry.media_metadata
            subtitle_tracks = media_metadata.get("subtitle_tracks", [])

            for track in subtitle_tracks:
                lang = track.get("language")
                if lang and lang != "unknown":
                    # Convert to ISO 639-3 if needed
                    # FFprobe typically returns ISO 639-2 (3-letter codes)
                    # which are compatible with our language list
                    embedded_languages.add(lang)

        except Exception as e:
            logger.warning(
                f"Failed to extract embedded subtitle languages for {item.log_string}: {e}"
            )

        return embedded_languages

    def _build_search_tags(self, item: MediaItem) -> Optional[str]:
        """
        Build comma-separated search tags from media_metadata for OpenSubtitles.

        Tags are specific identifiers like release groups (AXXO, KILLERS) and
        format tags (BluRay, HDTV, DVD, etc.), NOT full filenames.

        See: https://trac.opensubtitles.org/opensubtitles/wiki/XMLRPC#Supportedtags

        Args:
            item: MediaItem with media_metadata

        Returns:
            Comma-separated tags string (e.g., "BluRay,ETRG") or None
        """
        tags = []

        try:
            if not item.filesystem_entry or not item.filesystem_entry.media_metadata:
                return None

            # MediaMetadata stores parsed data from RTN at the top level
            # No need to access nested parsed_filename - fields are directly accessible
            from RTN import parse

            # Re-parse the original filename to get release group and quality info
            # This is necessary because MediaMetadata doesn't store all RTN fields
            original_filename = item.filesystem_entry.original_filename
            if not original_filename:
                return None

            parsed = parse(original_filename)
            if not parsed:
                return None

            # Add release group if available
            release_group = parsed.group
            if release_group:
                tags.append(release_group)

            # Add quality/format tag (BluRay, HDTV, DVD, etc.)
            quality = parsed.quality
            if quality:
                tags.append(quality)

            # Add other relevant tags
            if parsed.proper:
                tags.append("Proper")
            if parsed.repack:
                tags.append("Repack")
            if parsed.remux:
                tags.append("Remux")
            if parsed.extended:
                tags.append("Extended")
            if parsed.unrated:
                tags.append("Unrated")

            if tags:
                tags_str = ",".join([t.lower() for t in tags])
                logger.debug(f"Built search tags for {item.log_string}: {tags_str}")
                return tags_str

        except Exception as e:
            logger.warning(f"Failed to build search tags for {item.log_string}: {e}")

        return None

    def _calculate_video_hash(self, item: MediaItem) -> Optional[str]:
        """
        Calculate OpenSubtitles hash for the video file.

        Args:
            item: MediaItem with filesystem entry

        Returns:
            OpenSubtitles hash or None if calculation fails
        """
        try:
            assert item.filesystem_entry

            # Get file size from filesystem entry
            file_size = item.filesystem_entry.file_size

            if not file_size or file_size < 128 * 1024:  # 128KB minimum
                logger.debug(
                    f"File too small ({file_size} bytes) to calculate hash for {item.log_string}"
                )
                return None

            # Get the mounted VFS path
            from program.settings.manager import settings_manager

            mount_path = settings_manager.settings.filesystem.mount_path

            # Get VFS paths from MediaEntry (use base path)
            vfs_paths = item.filesystem_entry.get_all_vfs_paths()
            if not vfs_paths:
                logger.debug(
                    f"No VFS paths for {item.log_string}, cannot calculate hash"
                )
                return None

            vfs_path = vfs_paths[0]  # Use base path

            # Construct the full path on the host filesystem
            import os

            full_path = os.path.join(mount_path, vfs_path.lstrip("/"))

            # Check if file exists and is accessible
            if not os.path.exists(full_path):
                logger.debug(
                    f"VFS file not accessible at {full_path} for {item.log_string}"
                )
                return None

            # Calculate hash using the mounted VFS file
            with open(full_path, "rb") as f:
                video_hash = calculate_opensubtitles_hash(f, file_size)
                logger.debug(
                    f"Calculated OpenSubtitles hash for {item.log_string}: {video_hash}"
                )
                return video_hash

        except FileNotFoundError:
            logger.debug(
                f"VFS file not found for {item.log_string}, cannot calculate hash"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to calculate video hash for {item.log_string}: {e}")
            return None

    def _fetch_subtitle_for_language(
        self,
        item: MediaItem,
        language: str,
        video_path: str,
        video_hash: Optional[str],
        file_size: Optional[int],
        original_filename: str,
        search_tags: Optional[str],
        imdb_id: Optional[str],
        season: Optional[int],
        episode: Optional[int],
    ):
        """
        Fetch subtitle for a specific language.

        Args:
            item: MediaItem to fetch subtitle for
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
            logger.debug(
                f"Subtitle for {language} already exists for {item.log_string}"
            )
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
                    language=language,
                )
                all_results.extend(results)
            except Exception as e:
                logger.error(
                    f"Provider {provider.name} failed to search subtitles: {e}"
                )

        if not all_results:
            logger.debug(f"No {language} subtitles found for {item.log_string}")
            return

        # Sort by score (highest first)
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Try to download the best subtitle
        for subtitle_info in all_results[:3]:  # Try top 3 results
            try:
                provider_name = subtitle_info.get("provider")
                provider = next(
                    (p for p in self.providers if p.name == provider_name), None
                )

                if not provider:
                    continue

                # Download subtitle content
                content = provider.download_subtitle(subtitle_info)

                if not content:
                    continue

                assert item.filesystem_entry

                # Get parent MediaEntry's original_filename
                parent_original_filename = item.filesystem_entry.original_filename

                if not parent_original_filename:
                    logger.error(
                        f"MediaEntry for {item.log_string} has no original_filename, cannot create subtitle"
                    )
                    continue

                # Create SubtitleEntry and store in database
                subtitle_entry = SubtitleEntry.create_subtitle_entry(
                    language=language,
                    parent_original_filename=parent_original_filename,
                    content=content,
                    file_hash=video_hash,
                    video_file_size=item.filesystem_entry.file_size,
                    opensubtitles_id=subtitle_info.get("id"),
                )

                # Associate with media item
                subtitle_entry.media_item_id = item.id
                subtitle_entry.available_in_vfs = True

                # Save to database
                session = object_session(item)

                assert session

                session.add(subtitle_entry)

                # Flush to synchronize relationships before VFS sync
                # This ensures item.subtitles includes the new subtitle
                session.flush()

                logger.debug(
                    f"Downloaded and stored {language} subtitle for {item.log_string}"
                )

                from program.program import riven

                assert riven.services

                filesystem_service = riven.services.filesystem

                if filesystem_service and filesystem_service.riven_vfs:
                    filesystem_service.riven_vfs.sync(item)

                return

            except Exception as e:
                logger.error(
                    f"Failed to download subtitle from {subtitle_info.get('provider')}: {e}"
                )

        logger.warning(
            f"Failed to download any {language} subtitle for {item.log_string}"
        )

    def _get_existing_subtitle(
        self, item: MediaItem, language: str
    ) -> Optional[SubtitleEntry]:
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
                subtitle = (
                    session.query(SubtitleEntry)
                    .filter_by(media_item_id=item.id, language=language)
                    .first()
                )
                return subtitle
        except Exception as e:
            logger.error(f"Failed to check for existing subtitle: {e}")
            return None

    def should_submit(self, item: MediaItem) -> bool:
        """
        Check if subtitles should be fetched for an item.

        Checks if:
        1. Item is a movie or episode
        2. Item has a filesystem entry
        3. At least one wanted language is missing (not embedded and not already downloaded)

        Args:
            item: MediaItem to check

        Returns:
            True if subtitles should be fetched
        """
        # Only fetch subtitles for movies and episodes
        if item.type not in ["movie", "episode"]:
            return False

        # Check if item has a filesystem entry
        if not item.filesystem_entry:
            return False

        # If subtitle service is not enabled, don't submit
        if not self.enabled:
            return False

        # Get embedded subtitle languages from media_metadata (ffprobe)
        embedded_languages = self._get_embedded_subtitle_languages(item)

        # Get already downloaded subtitle languages from database
        downloaded_languages = set()
        try:
            with db.Session() as session:
                existing_subtitles = (
                    session.query(SubtitleEntry).filter_by(media_item_id=item.id).all()
                )
                downloaded_languages = {sub.language for sub in existing_subtitles}
        except Exception as e:
            logger.warning(
                f"Failed to check existing subtitles for {item.log_string}: {e}"
            )

        # Combine embedded and downloaded languages
        available_languages = embedded_languages | downloaded_languages

        # Check if any wanted language is missing
        missing_languages = set(self.languages) - available_languages

        if not missing_languages:
            logger.debug(
                f"All wanted subtitle languages already available for {item.log_string} "
                f"(embedded: {embedded_languages}, downloaded: {downloaded_languages})"
            )
            return False

        logger.debug(
            f"Missing subtitle languages for {item.log_string}: {missing_languages} "
            f"(embedded: {embedded_languages}, downloaded: {downloaded_languages})"
        )
        return True
