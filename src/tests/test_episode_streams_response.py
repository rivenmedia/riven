from types import SimpleNamespace

from program.media.item import Episode
from program.media.models import ActiveStream
from routers.secure.items import (
    _episode_has_stream_override,
    _episode_scoped_streams,
    _is_episode_scoped_stream,
    _resolve_season_pinned_stream,
    _stream_relation_scope,
)


def _stream_with_parents(stream_id: int, infohash: str, parent_ids: list[int]):
    return SimpleNamespace(
        id=stream_id,
        infohash=infohash,
        parents=[SimpleNamespace(id=pid) for pid in parent_ids],
    )


def test_resolve_season_pinned_stream_matches_active_infohash():
    pinned = _stream_with_parents(1, "aaa111", [10])
    other = _stream_with_parents(2, "bbb222", [10])
    season = SimpleNamespace(
        streams=[other, pinned],
        blacklisted_streams=[],
        active_stream=ActiveStream(infohash="aaa111", id="tid-1"),
    )

    assert _resolve_season_pinned_stream(season) is pinned


def test_resolve_season_pinned_stream_from_blacklisted():
    blacklisted = _stream_with_parents(3, "ccc333", [10])
    season = SimpleNamespace(
        streams=[],
        blacklisted_streams=[blacklisted],
        active_stream=ActiveStream(infohash="ccc333", id="tid-3"),
    )

    assert _resolve_season_pinned_stream(season) is blacklisted


def test_resolve_season_pinned_stream_none_without_active():
    season = SimpleNamespace(
        streams=[_stream_with_parents(1, "aaa111", [10])],
        blacklisted_streams=[],
        active_stream=None,
    )

    assert _resolve_season_pinned_stream(season) is None


def test_is_episode_scoped_stream():
    episode_id = 5
    season_id = 10
    on_episode = _stream_with_parents(1, "ep1", [episode_id])
    on_season = _stream_with_parents(2, "s1", [season_id])
    on_both = _stream_with_parents(3, "both", [episode_id, season_id])

    assert _is_episode_scoped_stream(on_episode, episode_id, season_id) is True
    assert _is_episode_scoped_stream(on_season, episode_id, season_id) is False
    assert _is_episode_scoped_stream(on_both, episode_id, season_id) is True


def test_episode_scoped_streams_filters_season_only():
    episode_id = 5
    season_id = 10
    ep_stream = _stream_with_parents(1, "ep1", [episode_id])
    season_stream = _stream_with_parents(2, "s1", [season_id])
    all_streams = [ep_stream, season_stream]

    scoped = _episode_scoped_streams(all_streams, episode_id, season_id)
    assert scoped == [ep_stream]
    assert _stream_relation_scope(ep_stream, episode_id, season_id) == "episode"
    assert _stream_relation_scope(season_stream, episode_id, season_id) == "season"


def test_episode_override_detection():
    episode = Episode({"number": 1})
    season = SimpleNamespace(active_stream=ActiveStream(infohash="season-pack", id="s1"))

    assert _episode_has_stream_override(episode, season) is False

    episode.active_stream = ActiveStream(infohash="season-pack", id="e1")
    assert _episode_has_stream_override(episode, season) is False

    episode.active_stream = ActiveStream(infohash="solo-ep", id="e2")
    assert _episode_has_stream_override(episode, season) is True

    episode.active_stream = ActiveStream(infohash="solo-ep", id="e2")
    assert _episode_has_stream_override(episode, None) is True
