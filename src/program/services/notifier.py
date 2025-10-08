"""Notifier service for sending completion notifications."""
import json
from datetime import datetime
from typing import List

from apprise import Apprise
from loguru import logger

from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.media.entry_state import EntryState


class Notifier:
    """
    Notifier service that sends completion notifications for movies and shows.
    
    This service operates at the MediaItem level (not MediaEntry level) and sends
    notifications when all entries for a specific profile are complete.
    """
    
    def __init__(self):
        self.key = "notifier"
        self.ntfy = Apprise()
        self.settings = settings_manager.settings.notifications
        self.on_item_type: List[str] = self.settings.on_item_type
        for service_url in self.settings.service_urls:
            try:
                if "discord" in service_url:
                    service_url = f"{service_url}?format=markdown"
                self.ntfy.add(service_url)
            except Exception as e:
                logger.debug(f"Failed to add service URL {service_url}: {e}")
                continue
        self.initialized = True
    
    def run(self, item: MediaItem) -> None:
        """
        Send notification for a completed item+profile combination.

        Args:
            item: MediaItem (movie or show) to notify about
        """
        # Send notification
        self.notify_sse(item)
        profiles = self._get_item_profile_to_notify(item)
        for profile in profiles:
            self.log_for_item(item, profile)
            self.notify_ntfy(item, profile)
    
    def notify_sse(self, item: MediaItem):
        """
        Send notification for a completed item profile.
        
        Args:
            item: MediaItem (movie or show)
            profile_name: Name of the scraping profile that completed
        """
        duration = round((datetime.now() - item.requested_at).total_seconds())
        
        # Publish SSE notification event
        notification_data = {
            "title": item.title or "Unknown",
            "state": item.last_state.name,
            "type": item.type,
            "year": item.aired_at.year if item.aired_at else None,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "log_string": f"{item.log_string}",
            "imdb_id": item.imdb_id,
            "tmdb_id": item.tmdb_id,
            "tvdb_id": item.tvdb_id,
        }
        sse_manager.publish_event("notifications", json.dumps(notification_data))

    def log_for_item(self, item: MediaItem, profile_name: str):
        logger.success(f"Completed {item.log_string} for profile '{profile_name}'")
    
    def notify_ntfy(self, item: MediaItem, profile_name: str):
        if item.type not in self.on_item_type:
            return
        title = f"Riven completed a {item.type.title()}!"
        body = f"**{item.log_string} ({profile_name})** ({item.aired_at.year})"
        try:
            self.ntfy.notify(title=title, body=body)
        except Exception as e:
            logger.debug(f"Failed to send notification: {e}")
    
    def _get_item_profile_to_notify(self, item: MediaItem) -> List[str]:
        profiles = []
        for profile in settings_manager.settings.scraping_profiles:
            profile_name = profile.name
            # Get all entries for this profile
            profile_entries = [entry for entry in item.filesystem_entries if entry.scraping_profile_name == profile_name]
            # Only notify if there are entries AND all are completed
            if profile_entries and all(entry.state == EntryState.Completed for entry in profile_entries):
                profiles.append(profile_name)
        return profiles