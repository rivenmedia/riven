from typing import List

from apprise import Apprise
from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.settings.models import NotificationsModel

ntfy = Apprise()
settings: NotificationsModel = settings_manager.settings.notifications
on_item_type: List[str] = settings.on_item_type


for service_url in settings.service_urls:
    try:
        if "discord" in service_url:
            service_url = f"{service_url}?format=markdown"
        ntfy.add(service_url)
    except Exception as e:
        logger.debug(f"Failed to add service URL {service_url}: {e}")
        continue


def notify(title: str, body: str) -> None:
    """Send notifications to all services in settings."""
    try:
        ntfy.notify(title=title, body=body)
    except Exception as e:
        logger.debug(f"Failed to send notification: {e}")

def notify_on_complete(item: MediaItem) -> None:
    """Send notifications to all services in settings."""
    if item.type not in on_item_type:
        return

    title = f"Riven completed a {item.type.title()}!"
    body = f"**{item.log_string}** ({item.aired_at.year})"
    notify(title, body)
