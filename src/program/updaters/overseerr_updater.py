"""Overseerr Updater module"""

from program.content.overseerr import Overseerr
from program.media.item import Season
from program.media import MediaItem, States, OverseerrStatus
from utils.logger import logger


class OverseerrUpdater:
    """Content class for overseerr updater"""

    def __init__(self, is_overseerr_init: bool):
        self.key = "overseerrupdater"
        self.initialized = is_overseerr_init
        if not self.initialized:
            logger.warning("Overseerr is not initialized, skipping.")
            return
        self.pending = set()
        logger.success("OverseerrUpdater initialized!")

    def run(self, item: MediaItem):
        """Update media `Overseerr` status."""
        if not item:
            logger.error("Invalid item sent to OverseerrUpdater: None")
            return

        if not self.initialized:
            item.last_overseerr_status = None
            yield item
            return

        # we update overseerr itself based on the parent(Movie, Show) state
        parent = item.get_parent()

        if (
            parent.last_overseerr_status is not None
            and parent.last_overseerr_status != parent.overseerr_status.name
        ):
            logger.debug(
                f"PARENT: {parent.log_string}: {parent.last_overseerr_status} -> {parent.overseerr_status.name}"
            )
            if parent.overseerr_status == OverseerrStatus.Available:
                if Overseerr.mark_available(item.overseerr_id):
                    parent.last_overseerr_status = OverseerrStatus.Available.name
                else:
                    self.pending.add(parent)
            elif parent.overseerr_status == OverseerrStatus.PartiallyAvailable:
                if Overseerr.mark_partially_available(item.overseerr_id):
                    parent.last_overseerr_status = (
                        OverseerrStatus.PartiallyAvailable.name
                    )
                else:
                    self.pending.add(parent)
            # unfortunetely `Processing` status has no visual representation in overseerr so we use pending to mean processing
            elif parent.overseerr_status == OverseerrStatus.Pending:
                if Overseerr.mark_pending(item.overseerr_id):
                    parent.last_overseerr_status = OverseerrStatus.Pending.name
                else:
                    self.pending.add(parent)
            else:
                parent.last_overseerr_status = parent.overseerr_status.name

        # we need to retry the parents first since they reflect on the server
        if len(self.pending) > 0:
            yield self.pending.pop()

        if item == parent:
            # yield parent since we already updated it
            yield parent
        else:
            # season episodes are not updated if we scrape the whole season at once instead of individual episodes
            # and since they are not part of the event queue we update them and move on
            if isinstance(item, Season):
                for ep in item.episodes:
                    if (
                        ep.last_overseerr_status is not None
                        and ep.last_overseerr_status != ep.overseerr_status.name
                    ):
                        logger.debug(
                            f"{ep.log_string}: {ep.last_overseerr_status} -> {ep.overseerr_status.name}"
                        )
                        ep.last_overseerr_status = ep.overseerr_status.name
            # don't interfere with rest of the process
            logger.debug(
                f"ITEM: {item.log_string}: {item.last_overseerr_status} -> {item.overseerr_status.name}"
            )
            item.last_overseerr_status = item.overseerr_status.name
            yield item


# Statuses for Media Requests endpoint /api/v1/request:
# item.status:
# 1 = PENDING APPROVAL,
# 2 = APPROVED,
# 3 = DECLINED

# Statuses for Media Info endpoint /api/v1/media:
# item.media.status:
# 1 = UNKNOWN,
# 2 = PENDING,
# 3 = PROCESSING,
# 4 = PARTIALLY_AVAILABLE,
# 5 = AVAILABLE
