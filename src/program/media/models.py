"""
Unified media metadata models for MediaEntry.

This module provides Pydantic models for storing media metadata that combines
both parsed data (from filename parsing via RTN) and probed data (from file
inspection via ffprobe) into a single, coherent structure.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """Source of metadata"""

    PARSED = "parsed"  # From filename parsing (RTN)
    PROBED = "probed"  # From file inspection (ffprobe)
    HYBRID = "hybrid"  # Mix of both


class VideoMetadata(BaseModel):
    """Video track metadata"""

    codec: Optional[str] = None  # e.g., "h264", "hevc"
    resolution_width: Optional[int] = None  # e.g., 1920
    resolution_height: Optional[int] = None  # e.g., 1080
    frame_rate: Optional[float] = None  # e.g., 23.976
    bit_depth: Optional[int] = None  # e.g., 10
    hdr_type: Optional[str] = None  # e.g., "HDR10", "DolbyVision"

    @property
    def resolution_label(self) -> Optional[str]:
        """
        Get resolution label (e.g., '1080p', '4K').

        Uses width for better ultrawide detection - ultrawide 4K videos
        (e.g., 3840×1600) are correctly identified as 4K instead of 1440p.
        """
        if self.resolution_width and self.resolution_height:
            # Use width for better ultrawide detection
            # Ultrawide 4K is typically 3840×1600-1800
            if self.resolution_width >= 3840 or self.resolution_height >= 2160:
                return "4K"
            elif self.resolution_width >= 2560 or self.resolution_height >= 1440:
                return "1440p"
            elif self.resolution_width >= 1920 or self.resolution_height >= 1080:
                return "1080p"
            elif self.resolution_width >= 1280 or self.resolution_height >= 720:
                return "720p"
            else:
                return "SD"
        elif self.resolution_height:
            # Fallback to height-only detection
            if self.resolution_height >= 2160:
                return "4K"
            elif self.resolution_height >= 1440:
                return "1440p"
            elif self.resolution_height >= 1080:
                return "1080p"
            elif self.resolution_height >= 720:
                return "720p"
            else:
                return "SD"
        return None


class AudioMetadata(BaseModel):
    """Audio track metadata"""

    codec: Optional[str] = None  # e.g., "aac", "dts", "truehd"
    channels: Optional[int] = None  # e.g., 2, 6, 8
    sample_rate: Optional[int] = None  # e.g., 48000
    language: Optional[str] = None  # e.g., "eng", "spa"


class SubtitleMetadata(BaseModel):
    """Subtitle track metadata"""

    codec: Optional[str] = None  # e.g., "srt", "ass"
    language: Optional[str] = None  # e.g., "eng", "spa"


class MediaMetadata(BaseModel):
    """
    Unified media metadata model combining parsed and probed data.

    This model consolidates filename-parsed data (RTN) and file-probed data (ffprobe)
    into a single, coherent structure. When both sources provide the same attribute,
    probed data takes precedence as the source of truth.

    Attributes:
        filename: Original filename
        parsed_title: Clean title extracted from filename
        year: Release year
        video: Video track metadata (codec, resolution, HDR, etc.)
        audio_tracks: List of audio tracks with codec, channels, language
        subtitle_tracks: List of subtitle tracks with codec, language
        duration: Duration in seconds (probed only)
        file_size: File size in bytes (probed only)
        bitrate: Overall bitrate in bits/sec (probed only)
        container_format: Container format(s) (probed only)
        quality_source: Source quality (BluRay, WEB-DL, etc.) (parsed only)
        is_remux: Whether this is a remux release (parsed only)
        is_proper: Whether this is a proper release (parsed only)
        is_repack: Whether this is a repack release (parsed only)
        is_remastered: Whether this is remastered (parsed only)
        is_upscaled: Whether this is upscaled (parsed only)
        is_directors_cut: Whether this is director's cut (parsed only)
        is_extended: Whether this is extended edition (parsed only)
        seasons: Season numbers (for shows) (parsed only)
        episodes: Episode numbers (for shows) (parsed only)
        data_source: Source of the metadata (parsed, probed, or hybrid)
        parsed_at: ISO timestamp when filename was parsed
        probed_at: ISO timestamp when file was probed
    """

    # === Core Identification ===
    filename: Optional[str] = None
    parsed_title: Optional[str] = None
    year: Optional[int] = None

    # === Video Properties ===
    video: Optional[VideoMetadata] = None

    # === Audio Properties ===
    audio_tracks: List[AudioMetadata] = Field(default_factory=list)

    # === Subtitle Properties ===
    subtitle_tracks: List[SubtitleMetadata] = Field(default_factory=list)

    # === File Properties (probed only) ===
    duration: Optional[float] = None  # seconds
    file_size: Optional[int] = None  # bytes
    bitrate: Optional[int] = None  # bits/sec
    container_format: List[str] = Field(
        default_factory=list
    )  # e.g., ["matroska", "webm"]

    # === Release Metadata (parsed only) ===
    quality_source: Optional[str] = None  # e.g., "BluRay", "WEB-DL", "HDTV"
    is_remux: bool = False
    is_proper: bool = False
    is_repack: bool = False
    is_remastered: bool = False
    is_upscaled: bool = False
    is_directors_cut: bool = False
    is_extended: bool = False

    # === Episode Information (parsed only) ===
    seasons: List[int] = Field(default_factory=list)
    episodes: List[int] = Field(default_factory=list)

    # === Metadata Tracking ===
    data_source: DataSource = DataSource.PARSED
    parsed_at: Optional[str] = None  # ISO timestamp
    probed_at: Optional[str] = None  # ISO timestamp

    @classmethod
    def from_parsed_data(
        cls, parsed_data: dict, filename: Optional[str] = None
    ) -> "MediaMetadata":
        """
        Create MediaMetadata from RTN ParsedData dict.

        Args:
            parsed_data: Dictionary from RTN parse() result (ParsedData.model_dump())
            filename: Optional filename to store

        Returns:
            MediaMetadata instance with parsed data populated
        """
        resolution_height = None
        if parsed_data.get("resolution", "unknown"):
            res = parsed_data["resolution"].lower()
            match res:
                case "2160p" | "2160i":
                    resolution_height = 2160
                case "1440p" | "1440i":
                    resolution_height = 1440
                case "1080p" | "1080i":
                    resolution_height = 1080
                case "720p" | "720i":
                    resolution_height = 720
                case "480p" | "480i":
                    resolution_height = 480

        bit_depth = None
        if parsed_data.get("bit_depth"):
            bd = parsed_data.get("bit_depth")
            if bd:
                try:
                    bit_depth = int(bd.replace("bit", ""))
                except (ValueError, TypeError):
                    # PTT/RTN should only return `10bit` or `8bit` 99% of the time
                    # but let's add a failsafe just in case
                    from program.utils import logger

                    logger.debug(f"Failed to parse bit_depth '{bd}' as int")
                    bit_depth = None

        codec = parsed_data.get("codec")

        # Join them into a single string for storage
        hdr_type = None
        hdr = parsed_data.get("hdr")
        if hdr:
            hdr_type = "+".join(hdr)

        # Create video metadata if we have any video info
        video = None
        if resolution_height or codec or bit_depth or hdr_type:
            video = VideoMetadata(
                codec=codec,
                resolution_height=resolution_height,
                bit_depth=bit_depth,
                hdr_type=hdr_type,
            )

        # Extract audio tracks from parsed data
        audio_tracks = []
        if parsed_data.get("audio"):
            for audio_codec in parsed_data["audio"]:
                audio_tracks.append(AudioMetadata(codec=audio_codec))

        # Extract subtitle tracks from parsed data
        subtitle_tracks = []
        if parsed_data.get("subbed", False):
            for lang in parsed_data["languages"]:
                subtitle_tracks.append(SubtitleMetadata(language=lang))

        quality_source = parsed_data["quality"]
        _edition = parsed_data.get("edition", "").lower()

        return cls(
            filename=filename or parsed_data.get("raw_title"),
            parsed_title=parsed_data.get("parsed_title"),
            year=parsed_data.get("year") or None,
            video=video,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
            quality_source=quality_source,
            is_remux="remux" in quality_source.lower(),
            is_proper=parsed_data.get("proper", False),
            is_repack=parsed_data.get("repack", False),
            is_remastered="remastered" in _edition,
            is_upscaled=parsed_data.get("upscaled", False),
            is_directors_cut="directors" in _edition,
            is_extended="extended" in _edition,
            seasons=parsed_data.get("season", []),
            episodes=parsed_data.get("episode", []),
            data_source=DataSource.PARSED,
            parsed_at=datetime.utcnow().isoformat(),
        )

    def update_from_probed_data(self, probed_data: dict) -> None:
        """
        Update MediaMetadata with ffprobe data, overriding parsed data where applicable.

        Args:
            probed_data: Dictionary from ffprobe MediaMetadata.model_dump()
        """
        # Update filename if not set
        if not self.filename and probed_data.get("filename"):
            self.filename = probed_data["filename"]

        # Update file properties (probed only)
        self.duration = probed_data.get("duration")
        self.file_size = probed_data.get("file_size")
        self.bitrate = probed_data.get("bitrate")
        self.container_format = probed_data.get("format", [])

        # Update video metadata (probed data overrides parsed)
        if probed_data.get("video"):
            video_data = probed_data["video"]
            if self.video:
                # Update existing video metadata
                self.video.codec = video_data.get("codec") or self.video.codec
                self.video.resolution_width = video_data.get("width")
                self.video.resolution_height = video_data.get("height")
                self.video.frame_rate = video_data.get("frame_rate")
                # Keep parsed bit_depth and hdr_type if not in probed data
            else:
                # Create new video metadata
                self.video = VideoMetadata(
                    codec=video_data.get("codec"),
                    resolution_width=video_data.get("width"),
                    resolution_height=video_data.get("height"),
                    frame_rate=video_data.get("frame_rate"),
                )

        # Update audio tracks (probed data replaces parsed)
        if probed_data.get("audio"):
            self.audio_tracks = [
                AudioMetadata(
                    codec=track.get("codec"),
                    channels=track.get("channels"),
                    sample_rate=track.get("sample_rate"),
                    language=track.get("language"),
                )
                for track in probed_data["audio"]
            ]

        # Update subtitle tracks (probed data replaces parsed)
        if probed_data.get("subtitles"):
            self.subtitle_tracks = [
                SubtitleMetadata(
                    codec=track.get("codec"), language=track.get("language")
                )
                for track in probed_data["subtitles"]
            ]

        # Update data source and timestamp
        if self.data_source == DataSource.PARSED:
            self.data_source = DataSource.HYBRID
        elif self.data_source == DataSource.PROBED:
            pass  # Already probed
        self.probed_at = datetime.utcnow().isoformat()
