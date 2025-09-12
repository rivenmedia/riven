import pytest

from program.queue.engine import decide_next_jobs
from program.queue.models import JobType
from program.media.state import States


class StubEpisode:
    def __init__(self, eid: str, state: States = States.Indexed):
        self.type = "episode"
        self.id = eid
        self._state = state
        self.last_state = None

    @property
    def state(self):
        return self._state


class StubSeason:
    def __init__(self, sid: str, episodes=None, state: States = States.Indexed, parent=None, is_scraped: bool = False):
        self.type = "season"
        self.id = sid
        self.episodes = episodes or []
        self._state = state
        self.last_state = None
        self.parent = parent
        self._is_scraped = is_scraped

    @property
    def state(self):
        return self._state

    def is_scraped(self):
        return bool(self._is_scraped)


class StubShow:
    def __init__(self, shid: str, seasons=None, state: States = States.Indexed, is_scraped: bool = False):
        self.type = "show"
        self.id = shid
        self.seasons = seasons or []
        self._state = state
        self.last_state = None
        self._is_scraped = is_scraped
        self.log_string = f"Show({shid})"

    @property
    def state(self):
        return self._state

    def is_scraped(self):
        return bool(self._is_scraped)


@pytest.fixture(autouse=True)
def patch_should_submit(monkeypatch):
    # Always allow scraping in these tests
    from program.services import scrapers
    monkeypatch.setattr(scrapers.Scraping, "should_submit", staticmethod(lambda obj: True))
    yield


def test_show_indexed_scrape_then_fanout(monkeypatch):
    # Show at Indexed with two seasons
    s1 = StubSeason("S1", state=States.Indexed)
    s2 = StubSeason("S2", state=States.Indexed)
    show = StubShow("SH", seasons=[s1, s2], state=States.Indexed, is_scraped=False)

    # 1) Not from Scraping -> enqueue show-level SCRAPE only
    reqs = decide_next_jobs(show, emitted_by="Manual")
    assert len(reqs) == 1
    assert reqs[0].job_type == JobType.SCRAPE
    assert reqs[0].item_id == "SH"

    # 2) From Scraping with no streams -> fan-out seasons
    reqs2 = decide_next_jobs(show, emitted_by="Scraping")
    # Expect two season scrapes
    ids = {r.item_id for r in reqs2}
    assert all(r.job_type == JobType.SCRAPE for r in reqs2)
    assert ids == {"S1", "S2"}


def test_season_indexed_scrape_then_fanout(monkeypatch):
    # Season at Indexed with two episodes
    e1 = StubEpisode("E1", state=States.Indexed)
    e2 = StubEpisode("E2", state=States.Indexed)
    season = StubSeason("S1", episodes=[e1, e2], state=States.Indexed, is_scraped=False)

    # 1) Not from Scraping -> enqueue season-level SCRAPE only
    reqs = decide_next_jobs(season, emitted_by="Manual")
    assert len(reqs) == 1
    assert reqs[0].job_type == JobType.SCRAPE
    assert reqs[0].item_id == "S1"

    # 2) From Scraping with no streams -> fan-out to episode scrapes
    reqs2 = decide_next_jobs(season, emitted_by="Scraping")
    ids = {r.item_id for r in reqs2}
    assert all(r.job_type == JobType.SCRAPE for r in reqs2)
    assert ids == {"E1", "E2"}


def test_linear_download_for_scraped():
    # When state is Scraped, linear mapping should schedule a DOWNLOAD
    class StubAny:
        def __init__(self):
            self.type = "show"
            self.id = "X"
            self._state = States.Scraped
            self.last_state = None
            self.log_string = "X"

        @property
        def state(self):
            return self._state

    item = StubAny()
    reqs = decide_next_jobs(item, emitted_by="Manual")
    assert len(reqs) == 1
    assert reqs[0].job_type == JobType.DOWNLOAD
    assert reqs[0].item_id == "X"

