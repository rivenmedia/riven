"""Composite indexer that uses TMDB for movies and TVDB for TV shows"""

from loguru import logger
from sqlalchemy import select

from program.db.db import db_session
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.services.indexers.base import BaseIndexer
from program.services.indexers.tmdb_indexer import TMDBIndexer
from program.services.indexers.tvdb_indexer import TVDBIndexer
from program.core.runner import MediaItemGenerator


class IndexerService(BaseIndexer):
    """Entry point to indexing. Composite indexer that delegates to appropriate service based on media type."""

    def __init__(self):
        super().__init__()

        self.tmdb_indexer = TMDBIndexer()
        self.tvdb_indexer = TVDBIndexer()

    @classmethod
    def get_key(cls) -> str:
        return "indexer"

    def run(
        self,
        in_item: MediaItem,
        log_msg: bool = True,
    ) -> MediaItemGenerator:
        """Run the appropriate indexer based on item type."""

        if isinstance(in_item, Movie) or (in_item.tmdb_id and not in_item.tvdb_id):
            yield from self.tmdb_indexer.run(
                in_item=in_item,
                log_msg=log_msg,
            )
        elif isinstance(in_item, (Show, Season, Episode)) or (
            in_item.tvdb_id and not in_item.tmdb_id
        ):
            yield from self.tvdb_indexer.run(
                in_item=in_item,
                log_msg=log_msg,
            )
        else:
            item = None

            if not item:
                movie_result = self.tmdb_indexer.run(
                    in_item=in_item,
                    log_msg=False,
                )
                item = next(movie_result, None)

            if not item:
                show_result = self.tvdb_indexer.run(
                    in_item=in_item,
                    log_msg=False,
                )
                item = next(show_result, None)

            if item:
                yield item
                return

        logger.warning(
            f"Unknown item type, cannot index {in_item.log_string}.. skipping"
        )

        return

    def reindex_ongoing(self) -> int:
        """
        Reindex all ongoing/unreleased movies and shows by updating them in-place.

        Returns the number of items reindexed.
        """

        try:
            with db_session() as session:
                # Gather two sets: (1) ongoing/unreleased movies & shows, (2) shows missing tvdb_status
                items_state = (
                    session.execute(
                        select(MediaItem)
                        .where(MediaItem.type.in_(["movie", "show"]))
                        .where(
                            MediaItem.last_state.in_(
                                [States.Ongoing, States.Unreleased]
                            )
                        )
                    )
                    .unique()
                    .scalars()
                    .all()
                )

                # For now to populate missing fields for existing shows, this can be removed later on.
                shows_missing_status = (
                    session.execute(select(Show).where(Show.tvdb_status.is_(None)))
                    .unique()
                    .scalars()
                    .all()
                )

                # Combine and deduplicate by id
                items_map = {i.id: i for i in items_state}

                for sh in shows_missing_status:
                    items_map.setdefault(sh.id, sh)

                items = list(items_map.values())

                if not items:
                    logger.debug("No ongoing/unreleased items to reindex")
                    return 0

                logger.debug(f"Reindexing {len(items)} ongoing/unreleased items")

                count = 0

                for item in items:
                    try:
                        updated = next(self.run(item, log_msg=False), None)

                        if updated:
                            with session.no_autoflush:
                                session.merge(updated)

                            count += 1
                    except Exception as e:
                        logger.error(f"Failed reindexing {item.log_string}: {e}")
                        continue

                try:
                    session.commit()
                except Exception as e:
                    logger.debug(
                        f"Commit failed during reindex (likely item was deleted): {e}"
                    )
                    session.rollback()

                return count
        except Exception as e:
            logger.error(f"Error during reindex_ongoing: {e}")
            return 0
