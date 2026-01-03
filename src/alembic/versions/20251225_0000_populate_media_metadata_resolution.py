"""populate_media_metadata_resolution

Populate media_metadata for MediaEntry objects that are missing resolution data.
Re-parses original_filename using RTN to extract resolution and other metadata.

For entries where resolution cannot be determined from filename parsing:
- Updates media_metadata with parsed data (without resolution)
- Ensures probed_at is null so MediaAnalysisService will run ffprobe later

This migration does NOT delete entries - ffprobe will be used at runtime
to get actual resolution from the video stream for entries without resolution.

Revision ID: a1b2c3d4e5f6
Revises: b1345f835923
Create Date: 2025-12-25 00:00:00

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Table, MetaData

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "b1345f835923"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Populate media_metadata for MediaEntry objects missing resolution data.

    For each MediaEntry:
    1. If media_metadata is missing or has no video resolution, re-parse original_filename
    2. Update media_metadata with parsed data (resolution if available, other metadata always)
    3. Entries without resolution from parsing will have probed_at=null so ffprobe runs later
    """
    import json
    from datetime import datetime, timezone

    # Import RTN for parsing
    try:
        from RTN import parse
    except ImportError:
        print("RTN not available, skipping migration")
        return

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Case-insensitive check for table existence
    mediaentry_exists = any(t.lower() == "mediaentry" for t in tables)

    if not mediaentry_exists:
        return

    # Preserve actual casing of the table name
    entry_table_name = next(
        (t for t in tables if t.lower() == "mediaentry"), "MediaEntry"
    )

    metadata = MetaData()
    media_entry_table = Table(entry_table_name, metadata, autoload_with=connection)

    # Select all MediaEntry rows
    stmt = sa.select(
        media_entry_table.c.id,
        media_entry_table.c.original_filename,
        media_entry_table.c.media_metadata,
    )
    result = connection.execute(stmt)

    entries_to_update: list[tuple[int, dict]] = []
    entries_needing_ffprobe: list[int] = []

    for row in result:
        entry_id = row[0]
        original_filename = row[1]
        media_metadata = row[2]

        # Check if we need to process this entry
        needs_update = False
        already_probed = False

        if media_metadata is None:
            needs_update = True
        elif isinstance(media_metadata, dict):
            # Check if already probed (has actual resolution from ffprobe)
            if media_metadata.get("probed_at"):
                already_probed = True
            video = media_metadata.get("video")
            if video is None:
                needs_update = True
            elif not video.get("resolution_width") and not video.get("resolution_height"):
                needs_update = True
        elif isinstance(media_metadata, str):
            try:
                parsed_meta = json.loads(media_metadata)
                if isinstance(parsed_meta, dict) and parsed_meta.get("probed_at"):
                    already_probed = True
                video = parsed_meta.get("video") if isinstance(parsed_meta, dict) else None
                if video is None:
                    needs_update = True
                elif not video.get("resolution_width") and not video.get("resolution_height"):
                    needs_update = True
            except Exception:
                needs_update = True

        # Skip already probed entries - they have real resolution data
        if already_probed:
            continue

        if not needs_update:
            continue

        # Try to parse the original filename
        if not original_filename:
            # No filename to parse - entry will need ffprobe later
            # Create minimal metadata with probed_at=null
            entries_to_update.append((entry_id, {"data_source": "parsed", "probed_at": None}))
            entries_needing_ffprobe.append(entry_id)
            continue

        try:
            parsed_data = parse(original_filename)
        except Exception:
            # Parse failed - create minimal metadata, ffprobe will fill in later
            entries_to_update.append((entry_id, {
                "filename": original_filename,
                "data_source": "parsed",
                "probed_at": None
            }))
            entries_needing_ffprobe.append(entry_id)
            continue

        # Build new media_metadata from parsed data
        new_metadata = _build_media_metadata(parsed_data, original_filename)
        entries_to_update.append((entry_id, new_metadata))

        # Track entries that still need ffprobe for resolution
        video = new_metadata.get("video")
        if not video or (not video.get("resolution_width") and not video.get("resolution_height")):
            entries_needing_ffprobe.append(entry_id)

    # Apply updates
    for entry_id, new_metadata in entries_to_update:
        connection.execute(
            sa.update(media_entry_table)
            .where(media_entry_table.c.id == entry_id)
            .values(media_metadata=new_metadata)
        )

    updated_with_resolution = len(entries_to_update) - len(entries_needing_ffprobe)
    print(f"Migration complete: {updated_with_resolution} entries updated with resolution, "
          f"{len(entries_needing_ffprobe)} entries will use ffprobe for resolution at runtime")


def _build_media_metadata(parsed_data, filename: str) -> dict:
    """
    Build a media_metadata dict from RTN ParsedData.
    Mirrors the logic in MediaMetadata.from_parsed_data().
    """
    from datetime import datetime, timezone

    resolution_width = None
    resolution_height = None
    res = parsed_data.resolution

    if res == "2160p":
        resolution_width = 3840
        resolution_height = 2160
    elif res == "1440p":
        resolution_width = 2560
        resolution_height = 1440
    elif res == "1080p":
        resolution_width = 1920
        resolution_height = 1080
    elif res == "720p":
        resolution_width = 1280
        resolution_height = 720
    elif res == "480p":
        resolution_width = 640
        resolution_height = 480
    elif res == "360p":
        resolution_width = 480
        resolution_height = 360

    bit_depth = parsed_data.bit_depth
    codec = parsed_data.codec

    # Join HDR types into a single string
    hdr_type = None
    hdr = parsed_data.hdr
    if hdr:
        hdr_type = "+".join(hdr)

    # Create video metadata if we have any video info
    video = None
    if resolution_height or codec or bit_depth or hdr_type:
        video = {
            "codec": codec,
            "resolution_width": resolution_width,
            "resolution_height": resolution_height,
            "bit_depth": bit_depth,
            "hdr_type": hdr_type,
        }

    # Extract audio tracks
    audio_tracks = []
    if parsed_data.audio:
        for audio_codec in parsed_data.audio:
            audio_tracks.append({"codec": audio_codec})

    # Extract subtitle tracks
    subtitle_tracks = []
    if parsed_data.subbed:
        for lang in parsed_data.languages:
            subtitle_tracks.append({"language": lang})

    quality_source = parsed_data.quality
    qs = quality_source.lower() if quality_source else None

    _edition = parsed_data.edition or ""
    if _edition:
        _edition = _edition.lower()

    return {
        "filename": filename or parsed_data.raw_title,
        "parsed_title": parsed_data.parsed_title,
        "year": parsed_data.year or None,
        "video": video,
        "audio_tracks": audio_tracks,
        "subtitle_tracks": subtitle_tracks,
        "quality_source": quality_source,
        "is_remux": "remux" in qs if qs else False,
        "is_proper": parsed_data.proper,
        "is_repack": parsed_data.repack,
        "is_remastered": "remastered" in _edition if _edition else False,
        "is_upscaled": parsed_data.upscaled,
        "is_directors_cut": "directors" in _edition if _edition else False,
        "is_extended": "extended" in _edition if _edition else False,
        "seasons": parsed_data.seasons,
        "episodes": parsed_data.episodes,
        "data_source": "parsed",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def downgrade() -> None:
    """No-op. We do not remove populated metadata on downgrade."""
    pass

