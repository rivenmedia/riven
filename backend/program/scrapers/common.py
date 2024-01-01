from datetime import datetime
from requests.exceptions import RequestException
from utils.request import RateLimitExceeded


class BaseScraper:
    """
    Base class for scrapers initalized in `Scraping`.

    Methods:
    - run(item): Runs the scraper on the given media item.
    - _can_we_scrape(item): Checks if the given media item can be scraped.
    - _is_released(item): Checks if the given media item has been released.
    - _needs_new_scrape(item): Checks if the given media item needs to be scraped again.
    - _build_log_string(item): Builds a log string for the given media item.
    - api_scrape(item): Abstract method to be implemented by subclasses.
    """

    def _can_we_scrape(self, item) -> bool:
        """Check if we can scrape the given media item"""
        return self._is_released(item) and self._needs_new_scrape(item)

    def _is_released(self, item) -> bool:
        """Check if the given media item has been released"""
        return item.aired_at is not None and item.aired_at < datetime.now()
    
    def _needs_new_scrape(self, item) -> bool:
        """Check if the given media item needs to be scraped again"""
        return (
            datetime.now().timestamp() - item.scraped_at
            > 60 * 30  # 30 minutes between scrapes
            or item.scraped_at == 0
        )

    def _build_log_string(self, item) -> str:
        """Build a log string for the given media item"""
        if item.type == "season":
            return f"{item.parent.title} S{item.number}"
        if item.type == "episode":
            return f"{item.parent.parent.title} S{item.parent.number}E{item.number}"
        return item.title

    def api_scrape(self, item):
        """Required abstract method to be implemented by subclasses."""
        raise NotImplementedError("Subclass must implement api_scrape method")

    def _scrape_item(self, item):
        """Required abstract method to be implemented by subclasses."""
        raise NotImplementedError("Subclass must implement _scrape_item method")

    def validate_settings(self) -> bool:
        """Required abstract method to be implemented by subclasses."""
        raise NotImplementedError("Subclass must implement validate_settings method")