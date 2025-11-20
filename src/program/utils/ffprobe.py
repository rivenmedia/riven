import subprocess
import orjson
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


def extract_filename_from_url(download_url: str) -> str:
    """
    Extract a UTF-8 decoded filename from a URL.

    This will:
    - Take the last path segment
    - URL-decode percent-encoded characters (e.g. `%20` -> space)
    - Assume UTF-8, which is the standard for URL encoding
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(download_url)
    path = parsed.path or ""
    if not path:
        return ""

    raw_name = path.rsplit("/", 1)[-1]
    return unquote(raw_name, encoding="utf-8", errors="replace")


def parse_media_url(download_url: str) -> Optional[MediaMetadata]:
    """
    Parse a media file using ffprobe and return its metadata.

    Args:
        file_path: Path to the media file

    Returns:
        MediaMetadata object if successful, None if file doesn't exist or can't be parsed

    Raises:
        FileNotFoundError: If the file doesn't exist
        subprocess.CalledProcessError: If ffprobe returns an error
        ValueError: If an unexpected error occurs while parsing the file
    """
    if not download_url:
        raise ValueError("No download URL provided")

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-analyzeduration",
            "2M",
            "-probesize",
            "10M",
            "-print_format",
            "json=compact=1",
            "-show_entries",
            (
                "format=filename,size,duration,bit_rate,format_name:"
                "stream=index,codec_name,codec_type,width,height,"
                "r_frame_rate,channels,sample_rate,bit_rate:"
                "stream_tags=language,title"
            ),
            "-i",
            download_url,
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # keep bytes for orjson
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
            raise RuntimeError(
                f"ffprobe error while probing {download_url}: {stderr}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Unexpected error invoking ffprobe for {download_url}: {exc}"
            ) from exc

        try:
            probe_data = orjson.loads(result.stdout)
        except Exception as exc:
            raise ValueError(
                f"Failed to parse ffprobe JSON output for {download_url}: {exc}"
            ) from exc

        if not probe_data:
            raise ValueError(f"ffprobe returned no data for {download_url}")

        format_info = probe_data.get("format", {}) or {}
        metadata_dict = {
            "filename": extract_filename_from_url(download_url),
            "file_size": int(format_info.get("size", 0)),
            "duration": round(float(format_info.get("duration", 0)), 2),
            "format": (
                format_info.get("format_name", "unknown").split(",")
                if format_info.get("format_name")
                else []
            ),
            "bitrate": int(format_info.get("bit_rate", 0)),
        }

        audio_tracks = []
        subtitle_tracks = []
        video_data = None

        for stream in probe_data.get("streams", []):
            codec_type = stream.get("codec_type")

            if codec_type == "video" and not video_data:
                # apparently theres multiple video codecs..
                # the first one should always be correct though.
                frame_rate = stream.get("r_frame_rate", "0/1")
                fps = (
                    float(Fraction(frame_rate))
                    if "/" in frame_rate
                    else float(frame_rate)
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

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error during ffprobe of {download_url}: {e}")
