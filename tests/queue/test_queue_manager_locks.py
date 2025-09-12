import types
import pytest

from program.queue.queue_manager import QueueManager


class StubShow:
    def __init__(self, sid: str):
        self.type = "show"
        self.id = sid
        self.tmdb_id = None
        self.tvdb_id = None
        self.imdb_id = None
        self.log_string = f"Show({sid})"


class StubSeason:
    def __init__(self, sid: str, parent=None):
        self.type = "season"
        self.id = sid
        self.parent = parent
        self.tmdb_id = None
        self.tvdb_id = None
        self.imdb_id = None
        self.log_string = f"Season({sid})"


class StubEpisode:
    def __init__(self, eid: str, parent=None):
        self.type = "episode"
        self.id = eid
        self.parent = parent
        self.tmdb_id = None
        self.tvdb_id = None
        self.imdb_id = None
        self.log_string = f"Episode({eid})"


@pytest.fixture
def qm():
    return QueueManager()


@pytest.fixture(autouse=True)
def patch_monitoring(monkeypatch):
    # Patch dependency manager and queue monitor methods used
    locked_ids = set()

    def get_item_locks(item_id: str):
        return {"jobX"} if item_id in locked_ids else set()

    # Attach our stateful set to the function for tests to mutate
    get_item_locks.locked_ids = locked_ids  # type: ignore[attr-defined]

    # queue_monitor duplicate checker -> always no duplicate in these tests
    def get_duplicate_job_info(**kwargs):
        return None

    import program.queue.monitoring as monitoring
    monkeypatch.setattr(monitoring.dependency_manager, "get_item_locks", get_item_locks)
    monkeypatch.setattr(monitoring.queue_monitor, "get_duplicate_job_info", get_duplicate_job_info)

    return get_item_locks


def test_season_blocked_by_show_lock(qm, patch_monitoring):
    get_item_locks = patch_monitoring
    show = StubShow("SHOW1")
    season = StubSeason("S1", parent=show)

    # Lock the show, season should be considered already queued/locked
    get_item_locks.locked_ids.add("SHOW1")
    assert qm._is_item_already_queued(season) is True

    # Unlock, season should be allowed
    get_item_locks.locked_ids.discard("SHOW1")
    assert qm._is_item_already_queued(season) is False


def test_episode_blocked_by_season_or_show_lock(qm, patch_monitoring):
    get_item_locks = patch_monitoring
    show = StubShow("SHOW2")
    season = StubSeason("S2", parent=show)
    episode = StubEpisode("E1", parent=season)

    # Lock season -> episode blocked
    get_item_locks.locked_ids.add("S2")
    assert qm._is_item_already_queued(episode) is True
    get_item_locks.locked_ids.discard("S2")

    # Lock show -> episode blocked
    get_item_locks.locked_ids.add("SHOW2")
    assert qm._is_item_already_queued(episode) is True
    get_item_locks.locked_ids.discard("SHOW2")

    # No locks -> episode allowed
    assert qm._is_item_already_queued(episode) is False

