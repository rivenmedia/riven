from pathlib import Path
from typing import List

from apprise import Apprise
from loguru import logger

from program.media.item import MediaItem, Stream
from program.settings.manager import settings_manager
from program.settings.models import NotificationsModel
from program.utils import root_dir

ntfy = Apprise()
settings: NotificationsModel = settings_manager.settings.notifications
on_item_type: List[str] = settings.on_item_type
riven_logo: Path = root_dir / "assets" / "riven-light.png"


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
        ntfy.notify(
            title=title,
            body=body,
        )
    except Exception as e:
        logger.debug(f"Failed to send notification: {e}")

def _build_notification_body(item: MediaItem) -> str:
    """Build a notification for the given item using markdown that lists the files completed."""
    notification_message = f"### [{item.type.title()}] **{item.log_string}** ({item.aired_at.year})\n"
    stream: Stream = next((stream for stream in item.streams if stream.infohash == item.active_stream.get("infohash")), None)
    if stream:
        notification_message += f"- {stream.raw_title}\n"
    return notification_message

def notify_on_complete(item: MediaItem) -> None:
    """Send notifications to all services in settings."""
    if item.type not in on_item_type:
        return

    title = "Riven completed something!" if not settings.title else settings.title
    body = _build_notification_body(item)
    notify(title, body)
