import subprocess
import orjson
from pathlib import Path
from typing import Optional, List
from fractions import Fraction
from pydantic import BaseModel, Field


class VideoTrack(BaseModel):
    """Model representing video track metadata"""

    codec: Optional[str] = Field(default="", description="Codec of the video track")
    width: int = Field(default=0, description="Width of the video track")
    height: int = Field(default=0, description="Height of the video track")
    frame_rate: float = Field(
        default=0.0, round=2, description="Frame rate of the video track"
    )


class AudioTrack(BaseModel):
    """Model representing audio track metadata"""

    codec: Optional[str] = Field(default="", description="Codec of the audio track")
    channels: int = Field(
        default=0, description="Number of channels in the audio track"
    )
    sample_rate: int = Field(default=0, description="Sample rate of the audio track")
    language: Optional[str] = Field(
        default="", description="Language of the audio track"
    )


class SubtitleTrack(BaseModel):
    """Model representing subtitle track metadata"""

    codec: Optional[str] = Field(default="", description="Codec of the subtitle track")
    language: Optional[str] = Field(
        default="", description="Language of the subtitle track"
    )


class MediaMetadata(BaseModel):
    """Model representing complete media file metadata"""

    filename: str = Field(default="", description="Name of the media file")
    file_size: int = Field(default=0, description="Size of the media file in bytes")
    video: VideoTrack = Field(default=VideoTrack(), description="Video track metadata")
    duration: float = Field(
        default=0.0, round=2, description="Duration of the video in seconds"
    )
    format: List[str] = Field(default=[], description="Format of the video")
    bitrate: int = Field(
        default=0, description="Bitrate of the video in bits per second"
    )
    audio: List[AudioTrack] = Field(default=[], description="Audio tracks in the video")
    subtitles: List[SubtitleTrack] = Field(
        default=[], description="Subtitles in the video"
    )

    @property
    def size_in_mb(self) -> float:
        """Return the file size in MB, rounded to 2 decimal places"""
        return round(self.file_size / (1024 * 1024), 2)

    @property
    def duration_in_mins(self) -> float:
        """Return the duration in minutes, rounded to 2 decimal places"""
        return round(self.duration / 60, 2)


def _build_metadata_from_probe(probe_data: dict, display_name: str) -> MediaMetadata:
    """Build a MediaMetadata object from ffprobe JSON output.

    Args:
        probe_data: Parsed ffprobe JSON
        display_name: Filename to record in metadata
    """
    format_info = probe_data.get("format", {})

    metadata_dict = {
        "filename": display_name,
        "file_size": int(format_info.get("size", 0)),
        "duration": round(float(format_info.get("duration", 0)), 2),
        "format": (
            format_info.get("format_name", "unknown").split(",")
            if format_info.get("format_name")
            else []
        ),
        "bitrate": int(format_info.get("bit_rate", 0)),
    }

    audio_tracks: list[AudioTrack] = []
    subtitle_tracks: list[SubtitleTrack] = []
    video_data: VideoTrack | None = None

    for stream in probe_data.get("streams", []):
        codec_type = stream.get("codec_type")

        if codec_type == "video":
            frame_rate = stream.get("r_frame_rate", "0/1")
            fps = (
                float(Fraction(frame_rate)) if "/" in frame_rate else float(frame_rate)
            )
            video_data = VideoTrack(
                codec=stream.get("codec_name", "unknown"),
                width=stream.get("width", 0),
                height=stream.get("height", 0),
                frame_rate=round(fps, 2),
            )

        elif codec_type == "audio":
            audio_tracks.append(
                AudioTrack(
                    codec=stream.get("codec_name", None),
                    channels=int(stream.get("channels", 0)),
                    sample_rate=int(stream.get("sample_rate", 0)),
                    language=stream.get("tags", {}).get("language", None),
                )
            )

        elif codec_type == "subtitle":
            subtitle_tracks.append(
                SubtitleTrack(
                    codec=stream.get("codec_name", "unknown"),
                    title=stream.get("tags", {}).get("title", None),
                    language=stream.get("tags", {}).get("language", None),
                )
            )

    if video_data:
        metadata_dict["video"] = video_data
    if audio_tracks:
        metadata_dict["audio"] = audio_tracks
    if subtitle_tracks:
        metadata_dict["subtitles"] = subtitle_tracks

    return MediaMetadata(**metadata_dict)


def parse_media_file(file_path: str | Path) -> Optional[MediaMetadata]:
    """
    Parse a local media file using ffprobe and return metadata.

    Args:
        file_path: Local filesystem path

    Raises:
        FileNotFoundError: If the file doesn't exist
        RuntimeError: If ffprobe returns an error
        ValueError: For unexpected errors
    """
    s = str(file_path)
    path = Path(s)
    if s.startswith(("http://", "https://")):
        raise ValueError(
            "parse_media_file received a URL; use parse_media_url or probe_media_path"
        )
    if not path.exists():
        raise FileNotFoundError(f"File {s} does not exist.")

    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            s,
        ]
        result = subprocess.check_output(cmd, text=True)
        probe_data = orjson.loads(result)
        return _build_metadata_from_probe(probe_data, display_name=path.name)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"ffprobe FileNotFound: {e}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error during ffprobe of {file_path}: {e}")


def parse_media_url(url: str) -> Optional[MediaMetadata]:
    """Parse a media URL (http/https) using ffprobe and return metadata."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("parse_media_url requires an http(s) URL string")

    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            url,
        ]
        result = subprocess.check_output(cmd, text=True)
        probe_data = orjson.loads(result)
        base = url.split("?", 1)[0].rstrip("/")
        display_name = base.rsplit("/", 1)[-1] if "/" in base else base
        return _build_metadata_from_probe(probe_data, display_name=display_name)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error during ffprobe of {url}: {e}")


def probe_media_path(path_or_url: str | Path) -> Optional[MediaMetadata]:
    """
    Wrapper that probes either a local filesystem path or an HTTP/HTTPS URL.

    Args:
        path_or_url: Local path or URL
    """
    s = str(path_or_url)
    if s.startswith(("http://", "https://")):
        return parse_media_url(s)
    return parse_media_file(s)
