"""Notification service for Riven"""

import json
from datetime import datetime

from apprise import Apprise
from loguru import logger

from program.managers.sse_manager import sse_manager
from program.media.item import MediaItem
from program.media.state import States
from program.settings.manager import settings_manager


class NotificationService:
    """
    Unified notification service that handles all notification types:
    - SSE state change notifications (real-time UI updates)
    - SSE completion notifications (frontend notification popups)
    - External notifications via Apprise (Discord, etc.)
    """

    def __init__(self):
        self.key = "notifications"
        self.initialized = False
        self.settings = settings_manager.settings.notifications
        self.apprise = Apprise()
        self._initialize_apprise()
        self.initialized = True

    def _initialize_apprise(self):
        """Initialize Apprise with configured service URLs."""
        if not self.settings.enabled:
            logger.debug("Notifications are disabled in settings")
            return

        for service_url in self.settings.service_urls:
            try:
                # Add markdown format for Discord webhooks
                if "discord" in service_url:
                    service_url = f"{service_url}?format=markdown"
                self.apprise.add(service_url)
                logger.debug(f"Added notification service: {service_url[:50]}...")
            except Exception as e:
                logger.debug(f"Failed to add service URL {service_url}: {e}")
                continue

        if len(self.apprise) > 0:
            logger.success(
                f"NotificationService initialized with {len(self.apprise)} service(s)"
            )

    def validate(self) -> bool:
        """Validate that the notification service is properly configured."""
        return True  # Service is always valid, even if no external services configured

    def run(
        self,
        item: MediaItem,
        previous_state: States | None = None,
        new_state: States | None = None,
    ):
        """
        Main entry point for sending notifications.

        Automatically determines what notifications to send based on the item's state:
        - If previous_state and new_state are provided: sends state change notification
        - If item.last_state is Completed: sends completion notification

        For episodes/seasons, also checks if the parent show is complete and notifies.

        Args:
            item: The MediaItem to notify about
            previous_state: Optional previous state (for state change notifications)
            new_state: Optional new state (for state change notifications)
        """
        # Handle state change notifications
        if previous_state is not None and new_state is not None:
            self._notify_state_change(item, previous_state, new_state)

        item_to_notify = item

        if item.type == "episode":
            item_to_notify = item.parent.parent
        elif item.type == "season":
            item_to_notify = item.parent

        # Handle completion notifications
        if item_to_notify.last_state == States.Completed:
            self._notify_completion(item_to_notify)

    def _notify_state_change(
        self, item: MediaItem, previous_state: States, new_state: States
    ):
        """
        Notify about a state change via SSE.

        This is called automatically from MediaItem.store_state() to provide
        real-time updates to the frontend.

        Args:
            item: The MediaItem that changed state
            previous_state: The previous state
            new_state: The new state
        """
        if previous_state and previous_state != new_state:
            state_change_data = {
                "last_state": previous_state.name,
                "new_state": new_state.name,
                "item_id": item.id,
            }
            sse_manager.publish_event("item_update", json.dumps(state_change_data))
            logger.debug(
                f"State change notification: {item.log_string} {previous_state.name} -> {new_state.name}"
            )

    def _notify_completion(self, item: MediaItem):
        """
        Notify about item completion via SSE and external services.

        This sends:
        1. Success log message
        2. SSE event for frontend notification popup
        3. External notifications (Discord, etc.) if enabled

        Args:
            item: The completed MediaItem
        """
        # Calculate completion duration
        duration = round((datetime.now() - item.requested_at).total_seconds())
        logger.success(f"{item.log_string} has been completed in {duration} seconds.")

        # Publish SSE notification event for frontend
        notification_data = {
            "title": item.title or "Unknown",
            "type": item.type,
            "year": item.aired_at.year if item.aired_at else None,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "log_string": item.log_string,
            "imdb_id": item.imdb_id,
        }
        sse_manager.publish_event("notifications", json.dumps(notification_data))
        logger.debug(f"SSE notification published for {item.log_string}")

        # Send external notifications if enabled
        if self.settings.enabled:
            self._send_external_notification(item)

    def _send_external_notification(self, item: MediaItem):
        """
        Send external notifications via Apprise (Discord, etc.).

        Args:
            item: The MediaItem to notify about
        """
        # Check if this item type should trigger notifications
        if item.type not in self.settings.on_item_type:
            logger.debug(
                f"Skipping external notification for {item.type} (not in on_item_type)"
            )
            return

        # Build notification message
        title = f"Riven completed a {item.type.title()}!"
        body = (
            f"**{item.log_string}** ({item.aired_at.year})"
            if item.aired_at
            else f"**{item.log_string}**"
        )

        # Send via Apprise
        try:
            if len(self.apprise) > 0:
                self.apprise.notify(title=title, body=body)
                logger.debug(f"External notification sent for {item.log_string}")
            else:
                logger.debug("No external notification services configured")
        except Exception as e:
            logger.debug(f"Failed to send external notification: {e}")

    def _notify_generic(self, title: str, body: str):
        """
        Send a generic notification to all configured services.

        This is a private utility method for sending custom notifications that aren't
        tied to a specific MediaItem.

        Args:
            title: Notification title
            body: Notification body
        """
        if not self.settings.enabled:
            logger.debug("Notifications disabled, skipping generic notification")
            return

        try:
            if len(self.apprise) > 0:
                self.apprise.notify(title=title, body=body)
                logger.debug(f"Generic notification sent: {title}")
            else:
                logger.debug("No external notification services configured")
        except Exception as e:
            logger.debug(f"Failed to send generic notification: {e}")


notification_service = NotificationService()
