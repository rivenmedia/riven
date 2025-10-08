"""
Type classes for parsed media data stored in MediaEntry.

These classes provide type safety and validation for the parsed_data field
which stores FFprobe analysis results and filename parsing metadata.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ParsedFilenameData(BaseModel):
    """
    Parsed metadata from filename using RTN.
    
    This data is populated by the downloader when processing torrents.
    """
    resolution: Optional[str] = Field(default=None, description="Resolution (e.g., '2160p', '1080p', '720p')")
    quality: Optional[str] = Field(default=None, description="Quality (e.g., 'REMUX', 'BluRay', 'WEB-DL')")
    codec: Optional[str] = Field(default=None, description="Video codec (e.g., 'x265', 'x264', 'AV1')")
    hdr: Optional[str] = Field(default=None, description="HDR info (e.g., 'HDR', 'HDR10+', 'DV')")
    audio: Optional[str] = Field(default=None, description="Audio codec (e.g., 'DTS-HD MA', 'TrueHD Atmos')")
    group: Optional[str] = Field(default=None, description="Release group")


class SubtitleTrack(BaseModel):
    """Represents a subtitle track from FFprobe."""
    index: int = Field(description="Track index")
    codec_name: Optional[str] = Field(default=None, description="Subtitle codec")
    language: Optional[str] = Field(default=None, description="Language code")
    title: Optional[str] = Field(default=None, description="Track title")
    forced: bool = Field(default=False, description="Whether this is a forced subtitle")
    hearing_impaired: bool = Field(default=False, description="Whether this is for hearing impaired")


class AudioTrack(BaseModel):
    """Represents an audio track from FFprobe."""
    index: int = Field(description="Track index")
    codec_name: Optional[str] = Field(default=None, description="Audio codec")
    language: Optional[str] = Field(default=None, description="Language code")
    channels: Optional[int] = Field(default=None, description="Number of audio channels")
    channel_layout: Optional[str] = Field(default=None, description="Channel layout (e.g., '5.1', '7.1')")
    sample_rate: Optional[int] = Field(default=None, description="Sample rate in Hz")
    bit_rate: Optional[int] = Field(default=None, description="Bit rate in bits/s")
    title: Optional[str] = Field(default=None, description="Track title")


class VideoTrack(BaseModel):
    """Represents a video track from FFprobe."""
    index: int = Field(description="Track index")
    codec_name: Optional[str] = Field(default=None, description="Video codec")
    width: Optional[int] = Field(default=None, description="Video width in pixels")
    height: Optional[int] = Field(default=None, description="Video height in pixels")
    bit_rate: Optional[int] = Field(default=None, description="Bit rate in bits/s")
    frame_rate: Optional[str] = Field(default=None, description="Frame rate (e.g., '23.976', '24')")
    color_space: Optional[str] = Field(default=None, description="Color space")
    color_transfer: Optional[str] = Field(default=None, description="Color transfer characteristics")
    color_primaries: Optional[str] = Field(default=None, description="Color primaries")
    hdr_format: Optional[str] = Field(default=None, description="HDR format if present")


class FFprobeData(BaseModel):
    """
    FFprobe analysis data from RTN's parse_media_file.
    
    This is a simplified representation of the MediaMetadata model from RTN.
    """
    duration: Optional[float] = Field(default=None, description="Duration in seconds")
    size: Optional[int] = Field(default=None, description="File size in bytes")
    bit_rate: Optional[int] = Field(default=None, description="Overall bit rate in bits/s")
    
    # Track information
    video: Optional[List[VideoTrack]] = Field(default_factory=list, description="Video tracks")
    audio: Optional[List[AudioTrack]] = Field(default_factory=list, description="Audio tracks")
    subtitles: Optional[List[SubtitleTrack]] = Field(default_factory=list, description="Subtitle tracks")
    
    # Format information
    format_name: Optional[str] = Field(default=None, description="Container format")
    
    # Raw ffprobe output (for advanced use cases)
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Raw ffprobe JSON output")


class ParsedMediaData(BaseModel):
    """
    Complete parsed media data stored in MediaEntry.parsed_data.
    
    This combines FFprobe analysis with filename parsing metadata.
    """
    analyzed_at: str = Field(description="ISO 8601 timestamp of when analysis was performed")
    ffprobe_data: Optional[FFprobeData] = Field(default=None, description="FFprobe analysis results")
    parsed_filename: Optional[ParsedFilenameData] = Field(default=None, description="Parsed filename metadata")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["ParsedMediaData"]:
        """
        Create ParsedMediaData from a dictionary.
        
        Args:
            data: Dictionary representation of parsed media data
            
        Returns:
            ParsedMediaData instance or None if data is invalid
        """
        if not data:
            return None
            
        try:
            return cls(**data)
        except Exception:
            # If validation fails, return None
            # This handles legacy data that might not match the schema
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for storage in database.
        
        Returns:
            Dictionary representation suitable for JSON storage
        """
        return self.model_dump(exclude_none=True)
    
    @classmethod
    def create_empty(cls) -> "ParsedMediaData":
        """
        Create an empty ParsedMediaData with current timestamp.
        
        Returns:
            ParsedMediaData with only analyzed_at set
        """
        return cls(
            analyzed_at=datetime.now().isoformat(),
            ffprobe_data=None,
            parsed_filename=None
        )

