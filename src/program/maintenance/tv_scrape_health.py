"""Analyze TV library scrape health and identify show/season reset candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from program.media.item import Season, Show
from program.media.state import States
from program.services.scrapers.episode_streams import (
    episode_should_skip_scrape,
    individually_scraped_episode_counts,
    streamless_episode_counts,
)
from program.utils import naive_local_datetime

ReasonCode = Literal[
    "empty_season",
    "sparse_season",
    "streamless_majority",
    "streamless_show",
    "incomplete_pack_scrape",
    "incomplete_pack_show",
]

_REASON_SEVERITY: dict[str, int] = {
    "streamless_show": 0,
    "incomplete_pack_show": 1,
    "empty_season": 2,
    "streamless_majority": 3,
    "incomplete_pack_scrape": 4,
    "sparse_season": 5,
}


@dataclass(frozen=True)
class TvScrapeHealthCandidate:
    item_id: int
    item_type: Literal["show", "season"]
    title: str
    reason: ReasonCode
    episode_count: int
    streamless_count: int
    streamless_ratio: float
    recommended_reset: Literal["show", "season"]
    show_id: int | None
    details: str


@dataclass(frozen=True)
class _SeasonIssue:
    season: Season
    reason: ReasonCode
    actionable_count: int
    streamless_count: int
    streamless_ratio: float


def _pack_scrape_attempted(item: Show | Season) -> bool:
    return naive_local_datetime(item.scraped_at) is not None


def _is_excluded_state(item: Show | Season) -> bool:
    return item.last_state in (States.Paused, States.Failed)


def _season_has_active_downloads(season: Season) -> bool:
    if season.filesystem_entry is not None:
        return True
    episodes = season.episodes
    if not episodes:
        return False
    on_disk = sum(1 for episode in episodes if episode_should_skip_scrape(episode))
    return on_disk > len(episodes) / 2


def _show_has_active_downloads(show: Show) -> bool:
    if show.filesystem_entry is not None:
        return True
    for season in show.seasons:
        if _season_has_active_downloads(season):
            return True
    return False


def _season_title(season: Season, show: Show) -> str:
    if season.number is not None:
        return f"{show.title} — Season {season.number}"
    return f"{show.title} — Season"


def _pack_scrape_complete(item: Show | Season) -> bool:
    return item.is_scraped()


def _incomplete_pack_recommended_reset(show: Show, season: Season) -> Literal["show", "season"]:
    if _pack_scrape_complete(show):
        return "season"
    if _pack_scrape_attempted(show) and not _pack_scrape_complete(show):
        return "show"
    if not _pack_scrape_attempted(show) and not _pack_scrape_attempted(season):
        return "show"
    return "season"


def _classify_incomplete_pack_scrape(
    season: Season,
    show: Show,
    *,
    scraped_threshold: float,
    min_individually_scraped: int,
    sparse_episode_max: int,
) -> _SeasonIssue | None:
    """
    Season/show pack streams missing while per-episode scrape has already started.

    Reset consolidates work onto show/season pack scrape + pack download.
    """

    if _pack_scrape_complete(season):
        return None

    pipeline_count, scraped_count, scraped_ratio = individually_scraped_episode_counts(
        season
    )
    if pipeline_count == 0 or scraped_count == 0:
        return None

    qualifies = False
    if pipeline_count <= sparse_episode_max:
        qualifies = scraped_count == pipeline_count
    elif scraped_count >= min_individually_scraped:
        qualifies = scraped_ratio >= scraped_threshold

    if not qualifies:
        return None

    return _SeasonIssue(
        season=season,
        reason="incomplete_pack_scrape",
        actionable_count=pipeline_count,
        streamless_count=scraped_count,
        streamless_ratio=scraped_ratio,
    )


def _classify_season(
    season: Season,
    show: Show,
    *,
    streamless_threshold: float,
    sparse_episode_max: int,
) -> _SeasonIssue | None:
    if _is_excluded_state(season) or _is_excluded_state(show):
        return None
    if _season_has_active_downloads(season):
        return None

    if len(season.episodes) == 0:
        return _SeasonIssue(
            season=season,
            reason="empty_season",
            actionable_count=0,
            streamless_count=0,
            streamless_ratio=0.0,
        )

    incomplete = _classify_incomplete_pack_scrape(
        season,
        show,
        scraped_threshold=streamless_threshold,
        min_individually_scraped=3,
        sparse_episode_max=sparse_episode_max,
    )
    if incomplete is not None:
        return incomplete

    if not _pack_scrape_attempted(season) and not _pack_scrape_attempted(show):
        return None

    actionable_count, streamless_count, streamless_ratio = streamless_episode_counts(
        season
    )
    if actionable_count == 0:
        return None

    total_episodes = len(season.episodes)
    if (
        total_episodes <= sparse_episode_max
        and streamless_count == actionable_count
        and streamless_count > 0
    ):
        return _SeasonIssue(
            season=season,
            reason="sparse_season",
            actionable_count=actionable_count,
            streamless_count=streamless_count,
            streamless_ratio=streamless_ratio,
        )

    if actionable_count >= 3 and streamless_ratio >= streamless_threshold:
        return _SeasonIssue(
            season=season,
            reason="streamless_majority",
            actionable_count=actionable_count,
            streamless_count=streamless_count,
            streamless_ratio=streamless_ratio,
        )

    return None


def _show_totals(show: Show) -> tuple[int, int]:
    actionable_total = 0
    streamless_total = 0
    for season in show.seasons:
        count, streamless, _ = streamless_episode_counts(season)
        actionable_total += count
        streamless_total += streamless
    return actionable_total, streamless_total


def _collapse_show_candidate(
    show: Show,
    issues: list[_SeasonIssue],
    *,
    reason: ReasonCode = "streamless_show",
) -> TvScrapeHealthCandidate:
    empty = [i for i in issues if i.reason == "empty_season"]
    majority = [i for i in issues if i.reason == "streamless_majority"]
    sparse = [i for i in issues if i.reason == "sparse_season"]
    incomplete = [i for i in issues if i.reason == "incomplete_pack_scrape"]

    detail_parts: list[str] = []
    if incomplete:
        detail_parts.append(
            f"{len(incomplete)} season(s) with per-episode scrape but no season pack"
        )
    if majority:
        detail_parts.append(
            f"{len(majority)} season(s) with majority streamless episodes"
        )
    if empty:
        nums = [
            str(i.season.number)
            for i in empty
            if i.season.number is not None
        ]
        if nums:
            detail_parts.append(f"{len(empty)} empty season(s) (S{', S'.join(nums)})")
        else:
            detail_parts.append(f"{len(empty)} empty season(s)")
    if sparse:
        detail_parts.append(f"{len(sparse)} sparse season(s) with no streams")

    if reason == "incomplete_pack_show":
        pipeline_total = 0
        scraped_total = 0
        for season in show.seasons:
            count, scraped, _ = individually_scraped_episode_counts(season)
            pipeline_total += count
            scraped_total += scraped
        ratio = (
            scraped_total / pipeline_total if pipeline_total > 0 else 0.0
        )
        episode_count = pipeline_total
        streamless_count = scraped_total
        streamless_ratio = ratio
    else:
        actionable_total, streamless_total = _show_totals(show)
        episode_count = actionable_total
        streamless_count = streamless_total
        streamless_ratio = (
            streamless_total / actionable_total if actionable_total > 0 else 0.0
        )

    return TvScrapeHealthCandidate(
        item_id=int(show.id),
        item_type="show",
        title=show.title or f"Show {show.id}",
        reason=reason,
        episode_count=episode_count,
        streamless_count=streamless_count,
        streamless_ratio=streamless_ratio,
        recommended_reset="show",
        show_id=None,
        details="; ".join(detail_parts) if detail_parts else "Multiple season issues",
    )


def _season_candidate(
    show: Show,
    issue: _SeasonIssue,
) -> TvScrapeHealthCandidate:
    season = issue.season
    if issue.reason == "empty_season":
        recommended: Literal["show", "season"] = "show"
    elif issue.reason == "incomplete_pack_scrape":
        recommended = _incomplete_pack_recommended_reset(show, season)
    else:
        recommended = "season"

    details = ""
    if issue.reason == "empty_season":
        num = season.number
        details = (
            f"Season {num} has no episodes — reset show to re-index"
            if num is not None
            else "Season has no episodes — reset show to re-index"
        )
    elif issue.reason == "incomplete_pack_scrape":
        details = (
            f"{issue.streamless_count}/{issue.actionable_count} episodes scraped "
            "individually; no season pack streams — reset for pack scrape + download"
        )
    elif issue.reason == "sparse_season":
        details = (
            f"{issue.streamless_count}/{issue.actionable_count} episodes "
            "missing streams after pack scrape"
        )
    else:
        details = (
            f"{issue.streamless_count}/{issue.actionable_count} episodes "
            "missing streams (majority)"
        )

    return TvScrapeHealthCandidate(
        item_id=int(season.id),
        item_type="season",
        title=_season_title(season, show),
        reason=issue.reason,
        episode_count=issue.actionable_count,
        streamless_count=issue.streamless_count,
        streamless_ratio=issue.streamless_ratio,
        recommended_reset=recommended,
        show_id=int(show.id),
        details=details,
    )


def analyze_tv_scrape_health(
    session: Session,
    *,
    streamless_threshold: float = 0.5,
    sparse_episode_max: int = 2,
) -> list[TvScrapeHealthCandidate]:
    """
    Scan TV shows for broken pack-scrape / fan-out states.

    Returns de-duplicated candidates (show-level rows subsume their seasons).
    """

    shows = (
        session.execute(
            select(Show).options(
                selectinload(Show.seasons).selectinload(Season.episodes),
            )
        )
        .scalars()
        .unique()
        .all()
    )

    candidates: list[TvScrapeHealthCandidate] = []

    for show in shows:
        if _is_excluded_state(show) or _show_has_active_downloads(show):
            continue

        season_issues: list[_SeasonIssue] = []
        for season in show.seasons:
            issue = _classify_season(
                season,
                show,
                streamless_threshold=streamless_threshold,
                sparse_episode_max=sparse_episode_max,
            )
            if issue is not None:
                season_issues.append(issue)

        if not season_issues:
            continue

        empty_count = sum(1 for i in season_issues if i.reason == "empty_season")
        majority_count = sum(
            1 for i in season_issues if i.reason == "streamless_majority"
        )
        incomplete_count = sum(
            1 for i in season_issues if i.reason == "incomplete_pack_scrape"
        )

        if empty_count >= 1 or majority_count >= 2:
            candidates.append(_collapse_show_candidate(show, season_issues))
            continue

        if incomplete_count >= 2:
            candidates.append(
                _collapse_show_candidate(
                    show,
                    season_issues,
                    reason="incomplete_pack_show",
                )
            )
            continue

        if len(season_issues) == 1 and season_issues[0].reason == "incomplete_pack_scrape":
            issue = season_issues[0]
            if _incomplete_pack_recommended_reset(show, issue.season) == "show":
                candidates.append(
                    _collapse_show_candidate(
                        show,
                        season_issues,
                        reason="incomplete_pack_show",
                    )
                )
            else:
                candidates.append(_season_candidate(show, issue))
            continue

        for issue in season_issues:
            candidates.append(_season_candidate(show, issue))

    candidates.sort(
        key=lambda c: (
            _REASON_SEVERITY.get(c.reason, 99),
            -c.streamless_ratio,
            c.title.lower(),
        )
    )
    return candidates
