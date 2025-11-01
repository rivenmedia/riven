"""replace_parsed_probed_with_media_metadata

Replace separate parsed_data and probed_data columns with unified media_metadata column.

This migration:
1. Adds new media_metadata column to MediaEntry
2. Migrates existing data from parsed_data and probed_data to media_metadata
3. Drops the old parsed_data and probed_data columns

The new media_metadata column stores a unified MediaMetadata model that combines
both parsed (RTN) and probed (ffprobe) data with clear precedence rules.

Revision ID: f109995eb51e
Revises: 4f327e05c40f
Create Date: 2025-10-31 08:08:05.872007

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f109995eb51e"
down_revision: Union[str, None] = "4f327e05c40f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add media_metadata column and drop old parsed_data/probed_data columns."""
    from datetime import datetime, timezone

    # Add new media_metadata column
    op.add_column(
        "MediaEntry",
        sa.Column(
            "media_metadata",
            sa.JSON(),
            nullable=True,
            comment="Unified media metadata combining parsed (RTN) and probed (ffprobe) data",
        ),
    )

    # Migrate existing data from parsed_data and probed_data to media_metadata
    connection = op.get_bind()

    # Check if the MediaEntry table exists and has the old columns
    # This handles both fresh installs and upgrades
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Check if MediaEntry table exists (case-insensitive check)
    mediaentry_exists = any(t.lower() == "mediaentry" for t in tables)

    if not mediaentry_exists:
        # Fresh install - no data to migrate
        # Drop old columns (they don't exist, but this is for consistency)
        with op.batch_alter_table("MediaEntry", schema=None) as batch_op:
            pass  # Nothing to drop on fresh install
        return

    # Get the actual table name (preserve case)
    actual_table_name = next(
        (t for t in tables if t.lower() == "mediaentry"), "MediaEntry"
    )

    # Check if old columns exist
    columns = [col["name"] for col in inspector.get_columns(actual_table_name)]
    has_parsed_data = "parsed_data" in columns
    has_probed_data = "probed_data" in columns

    if not has_parsed_data and not has_probed_data:
        # Old columns don't exist - nothing to migrate
        return

    # Get all MediaEntry rows with parsed_data or probed_data
    result = connection.execute(
        sa.text(
            f'SELECT id, original_filename, parsed_data, probed_data FROM "{actual_table_name}" WHERE parsed_data IS NOT NULL OR probed_data IS NOT NULL'
        )
    )

    for row in result:
        entry_id = row[0]
        original_filename = row[1]
        parsed_data = row[2]  # JSON string or dict
        probed_data = row[3]  # JSON string or dict

        # Import json to handle parsing if needed
        import json

        # Parse JSON if it's a string
        if isinstance(parsed_data, str):
            parsed_data = json.loads(parsed_data) if parsed_data else None
        if isinstance(probed_data, str):
            probed_data = json.loads(probed_data) if probed_data else None

        # Build media_metadata from parsed_data and probed_data
        media_metadata = {}

        if parsed_data:
            # Extract parsed data fields
            media_metadata["filename"] = original_filename or parsed_data.get(
                "raw_title"
            )
            media_metadata["parsed_title"] = parsed_data.get("parsed_title")
            media_metadata["year"] = parsed_data.get("year")

            # Video metadata from parsed data
            if parsed_data.get("resolution"):
                resolutions = parsed_data["resolution"]
                resolution = (
                    resolutions[0]
                    if isinstance(resolutions, list) and resolutions
                    else resolutions
                )
                media_metadata["video"] = {
                    "resolution": resolution,
                    "codec": (
                        parsed_data.get("codec", [None])[0]
                        if isinstance(parsed_data.get("codec"), list)
                        else parsed_data.get("codec")
                    ),
                    "hdr": parsed_data.get("hdr", []),
                    "bit_depth": (
                        parsed_data.get("bitDepth", [None])[0]
                        if isinstance(parsed_data.get("bitDepth"), list)
                        else parsed_data.get("bitDepth")
                    ),
                }

            # Audio tracks from parsed data
            if parsed_data.get("audio"):
                audio_list = (
                    parsed_data["audio"]
                    if isinstance(parsed_data["audio"], list)
                    else [parsed_data["audio"]]
                )
                media_metadata["audio_tracks"] = [
                    {"codec": codec} for codec in audio_list if codec
                ]
            else:
                media_metadata["audio_tracks"] = []

            # Subtitle tracks from parsed data
            if parsed_data.get("languages"):
                media_metadata["subtitle_tracks"] = [
                    {"language": lang} for lang in parsed_data["languages"] if lang
                ]
            else:
                media_metadata["subtitle_tracks"] = []

            # Release metadata
            media_metadata["quality_source"] = parsed_data.get("quality")
            media_metadata["is_remux"] = parsed_data.get("remux", False)
            media_metadata["is_proper"] = parsed_data.get("proper", False)
            media_metadata["is_repack"] = parsed_data.get("repack", False)
            media_metadata["is_remastered"] = parsed_data.get("remastered", False)
            media_metadata["is_upscaled"] = parsed_data.get("upscaled", False)
            media_metadata["is_directors_cut"] = parsed_data.get("directorsCut", False)
            media_metadata["is_extended"] = parsed_data.get("extended", False)

            # Episode information
            media_metadata["seasons"] = parsed_data.get("season", [])
            media_metadata["episodes"] = parsed_data.get("episode", [])

            # Tracking
            media_metadata["data_source"] = "parsed"
            media_metadata["parsed_at"] = datetime.now(timezone.utc).isoformat()

        if probed_data:
            # Update with probed data (overrides parsed where applicable)
            if not media_metadata.get("filename") and probed_data.get("filename"):
                media_metadata["filename"] = probed_data["filename"]

            # File properties
            media_metadata["duration"] = probed_data.get("duration")
            media_metadata["file_size"] = probed_data.get("file_size")
            media_metadata["bitrate"] = probed_data.get("bitrate")
            media_metadata["container_format"] = probed_data.get("format", [])

            # Video metadata from probed data (overrides parsed)
            if probed_data.get("video"):
                video_track = (
                    probed_data["video"][0]
                    if isinstance(probed_data["video"], list)
                    else probed_data["video"]
                )
                media_metadata["video"] = {
                    "resolution": video_track.get("resolution"),
                    "width": video_track.get("width"),
                    "height": video_track.get("height"),
                    "codec": video_track.get("codec"),
                    "hdr": video_track.get("hdr", []),
                    "bit_depth": video_track.get("bit_depth"),
                    "frame_rate": video_track.get("frame_rate"),
                }

            # Audio tracks from probed data (overrides parsed)
            if probed_data.get("audio"):
                media_metadata["audio_tracks"] = [
                    {
                        "codec": track.get("codec"),
                        "channels": track.get("channels"),
                        "sample_rate": track.get("sample_rate"),
                        "language": track.get("language"),
                    }
                    for track in probed_data["audio"]
                ]

            # Subtitle tracks from probed data (overrides parsed)
            if probed_data.get("subtitles"):
                media_metadata["subtitle_tracks"] = [
                    {
                        "codec": track.get("codec"),
                        "language": track.get("language"),
                    }
                    for track in probed_data["subtitles"]
                ]

            # Update data source and timestamp
            if media_metadata.get("data_source") == "parsed":
                media_metadata["data_source"] = "hybrid"
            else:
                media_metadata["data_source"] = "probed"
            media_metadata["probed_at"] = datetime.now(timezone.utc).isoformat()

        # Update the row with migrated data
        if media_metadata:
            connection.execute(
                sa.text(
                    f'UPDATE "{actual_table_name}" SET media_metadata = :metadata WHERE id = :id'
                ),
                {"metadata": json.dumps(media_metadata), "id": entry_id},
            )

    # Drop old columns (only if they exist)
    with op.batch_alter_table("MediaEntry", schema=None) as batch_op:
        if has_parsed_data:
            batch_op.drop_column("parsed_data")
        if has_probed_data:
            batch_op.drop_column("probed_data")


def downgrade() -> None:
    """Restore parsed_data and probed_data columns, drop media_metadata."""
    # Add back old columns
    op.add_column(
        "MediaEntry",
        sa.Column(
            "probed_data",
            sa.JSON(),
            nullable=True,
            comment="Cached ffprobe media analysis data (video, audio, subtitles, etc.)",
        ),
    )
    op.add_column(
        "MediaEntry",
        sa.Column(
            "parsed_data",
            sa.JSON(),
            nullable=True,
            comment="Cached parsed filename data from PTT (item_type, season, episodes)",
        ),
    )

    # Note: Data migration on downgrade is not supported
    # Downgrading will lose all media_metadata data

    # Drop new column
    with op.batch_alter_table("MediaEntry", schema=None) as batch_op:
        batch_op.drop_column("media_metadata")
