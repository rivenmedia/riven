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
        # Extract resolution from parsed data
        resolution_height = None
        bit_depth = None
        if parsed_data.get("resolution"):
            # RTN returns resolution as string (e.g., "1080p", "2160p")
            # Handle both string and list for backward compatibility
            resolution = parsed_data["resolution"]
            resolutions = [resolution] if isinstance(resolution, str) else resolution

            for res in resolutions:
                if "2160" in res or "4K" in res.upper() or "UHD" in res.upper():
                    resolution_height = 2160
                elif "1440" in res:
                    resolution_height = 1440
                elif "1080" in res or "FHD" in res.upper():
                    resolution_height = 1080
                elif "720" in res or "HD" in res.upper():
                    resolution_height = 720
                elif "480" in res or "SD" in res.upper():
                    resolution_height = 480
                if resolution_height:
                    break

        if parsed_data.get("bit_depth"):
            # RTN returns bit_depth as string (e.g., "10bit")
            # Handle both string and list for backward compatibility
            bd = parsed_data["bit_depth"]
            if isinstance(bd, list):
                bit_depth = bd[0] if bd else None
            else:
                # Extract numeric value from string like "10bit"
                bit_depth = int(bd.replace("bit", "")) if bd and "bit" in bd else bd

        # Extract codec from parsed data
        codec = None
        if parsed_data.get("codec"):
            # RTN returns codec as string (e.g., "hevc", "h264")
            # Handle both string and list for backward compatibility
            c = parsed_data["codec"]
            codec = c[0] if isinstance(c, list) else c

        # Extract HDR type
        # RTN returns hdr as list (e.g., ["DV", "HDR10"])
        # Join them into a single string for storage
        hdr_type = None
        hdr = parsed_data.get("hdr")
        if hdr:
            if isinstance(hdr, list):
                hdr_type = "+".join(hdr) if hdr else None
            else:
                hdr_type = hdr

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
            # RTN returns audio as list like ["AAC", "DTS"]
            for audio_codec in parsed_data["audio"]:
                audio_tracks.append(AudioMetadata(codec=audio_codec))

        # Extract subtitle tracks from parsed data
        subtitle_tracks = []
        if parsed_data.get("subtitles"):
            # RTN returns subtitles as list like ["eng", "spa"]
            for lang in parsed_data["subtitles"]:
                subtitle_tracks.append(SubtitleMetadata(language=lang))

        # Extract quality source
        quality_source = None
        if parsed_data.get("quality"):
            # RTN returns quality as string (e.g., "WEB-DL", "BluRay")
            # Handle both string and list for backward compatibility
            quality = parsed_data["quality"]
            if isinstance(quality, list):
                quality_source = quality[0] if quality else None
            else:
                quality_source = quality

        return cls(
            filename=filename or parsed_data.get("raw_title"),
            parsed_title=parsed_data.get("parsed_title"),
            year=parsed_data.get("year") or None,
            video=video,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
            quality_source=quality_source,
            is_remux=parsed_data.get("remux", False),
            is_proper=parsed_data.get("proper", False),
            is_repack=parsed_data.get("repack", False),
            is_remastered=parsed_data.get("remastered", False),
            is_upscaled=parsed_data.get("upscaled", False),
            is_directors_cut=parsed_data.get("directorsCut", False),
            is_extended=parsed_data.get("extended", False),
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
