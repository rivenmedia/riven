from fnmatch import fnmatch
from typing import Any, Union

from pydantic import BaseModel

from .ranks import (
    BestOverallRanking,
    BestRemuxRanking,
    BestResolutionRanking,
    BestWebRanking,
    DefaultRanking,
)


class Rank(BaseModel):
    name: str
    preference: list[str | bool] = []
    require: str | bool | None = None
    exclude: list[str] = []


class RankingConfig(BaseModel):
    rankings: list[Rank]


def match_criteria(
    value: Union[None, str, bool, list[str], list[bool]], pattern: str | bool
) -> bool:
    if value is None:
        return False
    if isinstance(value, bool) and isinstance(pattern, bool):
        return value == pattern
    if isinstance(pattern, bool) or isinstance(value, bool):
        raise ValueError(f"Invalid boolean comparison on {pattern} and {value}")
    if isinstance(value, list):
        return any(match_criteria(v, pattern) for v in value)
    # glob match pattern
    return fnmatch(str(value), pattern)


def rank_items(
    items: list[dict[str, Any]],
    ranking_config: RankingConfig,
) -> list[dict[str, Any]]:
    ranked_items = items.copy()

    for rank_position, rank in enumerate(ranking_config.rankings):
        if rank.require is not None:
            ranked_items = [
                item
                for item in ranked_items
                if rank.name in item and match_criteria(item[rank.name], rank.require)
            ]
        for exclude in rank.exclude:
            ranked_items = [
                item
                for item in ranked_items
                if rank.name not in item or not match_criteria(item[rank.name], exclude)
            ]

        for item in ranked_items:
            for pref_pos, preference in enumerate(rank.preference):
                if rank.name not in item:
                    break
                if match_criteria(item[rank.name], preference):
                    rank_score = len(ranking_config.rankings) - rank_position + 1
                    score = (len(rank.preference) - pref_pos) * 10 * rank_score
                    item["rank"] = item.get("rank", 0) + score
                    break

    sorted_list = sorted(ranked_items, key=lambda x: x.get("rank", 0), reverse=True)
    for s in sorted_list:
        s.pop("rank", None)
    return sorted_list