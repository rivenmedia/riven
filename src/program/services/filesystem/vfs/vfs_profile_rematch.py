"""Shared library-profile rematch for VFS full sync (RivenVFS + mock inventory)."""

from __future__ import annotations

from dataclasses import dataclass

from program.db.db import db_session
from program.media.media_entry import MediaEntry
from program.services.library_profile_matcher import LibraryProfileMatcher
from program.settings import settings_manager
from program.utils.logging import logger


@dataclass(frozen=True)
class VfsProfileRematchResult:
    """Outcome of the profile-rematch phase before rebuilding VFS state."""

    skipped_profiles_unchanged: bool
    item_ids: list[int]
    rematched_count: int
    profile_hash: int | None


def compute_filesystem_profile_hash() -> int | None:
    try:
        profiles = settings_manager.settings.filesystem.library_profiles or {}
        return hash(
            frozenset(
                (k, hash(frozenset(v.filter_rules.model_dump().items())))
                for k, v in profiles.items()
            )
        )
    except Exception:
        return None


def rematch_profiles_collect_item_ids(
    *,
    last_profile_hash: int | None,
) -> VfsProfileRematchResult:
    """
    Re-match MediaEntry rows to library profiles and collect MediaItem ids to register.

    If filesystem profile settings are unchanged since ``last_profile_hash``,
    returns ``skipped_profiles_unchanged=True`` and callers should skip rebuild.
    """

    current_profile_hash = compute_filesystem_profile_hash()

    if (
        current_profile_hash is not None
        and current_profile_hash == last_profile_hash
    ):
        logger.debug("Library profiles unchanged, skipping re-matching")
        return VfsProfileRematchResult(
            skipped_profiles_unchanged=True,
            item_ids=[],
            rematched_count=0,
            profile_hash=current_profile_hash,
        )

    matcher = LibraryProfileMatcher()
    item_ids: list[int] = []
    rematched_count = 0

    with db_session() as session:
        entries = (
            session.query(MediaEntry).filter(MediaEntry.is_directory.is_(False)).all()
        )

        for entry in entries:
            item = entry.media_item

            if not item:
                logger.warning(
                    f"MediaEntry {entry.id} has no associated MediaItem, skipping"
                )
                continue

            new_profiles = matcher.get_matching_profiles(item)
            old_profiles = entry.library_profiles or []

            if set(new_profiles) != set(old_profiles):
                entry.library_profiles = new_profiles
                rematched_count += 1

            if item.id not in item_ids:
                item_ids.append(item.id)

        session.commit()

    logger.debug(f"Re-matched {rematched_count} entries with updated profiles")

    return VfsProfileRematchResult(
        skipped_profiles_unchanged=False,
        item_ids=item_ids,
        rematched_count=rematched_count,
        profile_hash=current_profile_hash,
    )
