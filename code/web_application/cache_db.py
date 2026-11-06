"""
HW9 Part 1 - Redis-backed view counter for the primary entity (a Transit Incident).

Every Redis key starts with PREFIX ("s3170"). The ONE new method is increment_incident_views().
"""
from __future__ import annotations

import logging
import os

import redis
from sqlalchemy import text

PREFIX = "s3170"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
SYNC_EVERY = 10

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("s3170.cache")


class IncidentCache:
    """Database/cache class: a Redis client plus a SQLAlchemy session factory."""

    def __init__(self, redis_client=None, session_factory=None):
        self.redis_client = redis_client or redis.Redis.from_url(REDIS_URL, decode_responses=True,
                                                                 socket_connect_timeout=1, socket_timeout=1)
        if session_factory is None:
            from database import db_session_basede26 as session_factory
        self.session_factory = session_factory
        self.last_synced = 0          # count at the most recent DB sync (read by the test script)

    @staticmethod
    def views_key(incident_id: int) -> str:
        return f"{PREFIX}:views:incident:{incident_id}"

    def increment_incident_views(self, incident_id: int) -> int:
        """INCR the Redis counter; on every 10th view write it to incidents.view_count; return the count."""
        count = int(self.redis_client.incr(self.views_key(incident_id)))
        if count % SYNC_EVERY == 0:
            with self.session_factory() as db:
                # Raw UPDATE on purpose: the ORM would fire updated_at's onupdate, and a view is not
                # a content change (updated_at is the data-version marker used by the HW9 semantic cache).
                db.execute(text("UPDATE incidents SET view_count = :c WHERE id = :i"),
                           {"c": count, "i": incident_id})
                db.commit()
            log.info("Synced views to database (incident %s = %s)", incident_id, count)
            self.last_synced = count
        return count


_cache: IncidentCache | None = None


def get_incident_cache() -> IncidentCache:
    global _cache
    if _cache is None:
        _cache = IncidentCache()
    return _cache
