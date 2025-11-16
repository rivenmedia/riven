import subprocess
import orjson
from pathlib import Path
from fractions import Fraction
from pydantic import BaseModel, Field


class VideoTrack(BaseModel):
    """Model representing video track metadata"""

    codec: str | None = Field(default="", description="Codec of the video track")
    width: int = Field(default=0, description="Width of the video track")
    height: int = Field(default=0, description="Height of the video track")
    frame_rate: float = Field(
        default=0.0,
        description="Frame rate of the video track",
        decimal_places=2,
    )


class AudioTrack(BaseModel):
    """Model representing audio track metadata"""

    codec: str | None = Field(default="", description="Codec of the audio track")
    channels: int = Field(
        default=0, description="Number of channels in the audio track"
    )
    sample_rate: int = Field(default=0, description="Sample rate of the audio track")
    language: str | None = Field(default="", description="Language of the audio track")


class SubtitleTrack(BaseModel):
    """Model representing subtitle track metadata"""

    codec: str | None = Field(default="", description="Codec of the subtitle track")
    language: str | None = Field(
        default="", description="Language of the subtitle track"
    )


class MediaMetadata(BaseModel):
    """Model representing complete media file metadata"""

    filename: str = Field(default="", description="Name of the media file")
    file_size: int = Field(default=0, description="Size of the media file in bytes")
    video: VideoTrack = Field(default=VideoTrack(), description="Video track metadata")
    duration: float = Field(
        default=0.0,
        description="Duration of the video in seconds",
        decimal_places=2,
    )
    format: list[str] = Field(default=[], description="Format of the video")
    bitrate: int = Field(
        default=0, description="Bitrate of the video in bits per second"
    )
    audio: list[AudioTrack] = Field(default=[], description="Audio tracks in the video")
    subtitles: list[SubtitleTrack] = Field(
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


def parse_media_file(file_path: str | Path) -> MediaMetadata:
    """
    Parse a media file using ffprobe and return its metadata.

    Args:
        file_path: Path to the media file

    Returns:
        MediaMetadata object

    Raises:
        FileNotFoundError: If the file doesn't exist
        subprocess.CalledProcessError: If ffprobe returns an error
        ValueError: If an unexpected error occurs while parsing the file
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File {path} does not exist.")

    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]

        result = subprocess.check_output(cmd, text=True)
        probe_data = orjson.loads(result)

        format_info = probe_data.get("format", {})
        metadata = MediaMetadata(
            filename=path.name,
            file_size=int(format_info.get("size", 0)),
            duration=round(float(format_info.get("duration", 0)), 2),
            format=(
                format_info.get("format_name", "unknown").split(",")
                if format_info.get("format_name")
                else []
            ),
            bitrate=int(format_info.get("bit_rate", 0)),
        )

        audio_tracks = []
        subtitle_tracks = []
        video_data = None

        for stream in probe_data.get("streams", []):
            codec_type = stream.get("codec_type")

            if codec_type == "video":
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
                        language=stream.get("tags", {}).get("language", None),
                    )
                )

        if video_data:
            metadata.video = video_data

        if audio_tracks:
            metadata.audio = audio_tracks

        if subtitle_tracks:
            metadata.subtitles = subtitle_tracks

        return metadata
    except FileNotFoundError as e:
        raise FileNotFoundError(f"ffprobe FileNotFound: {e}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error during ffprobe of {file_path}: {e}")
