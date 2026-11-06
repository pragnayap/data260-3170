# ruff: noqa: I001  (import order matters here: common.py puts the web_application folder on sys.path first)
#!/usr/bin/env python3
"""HW9 Part 1 - test the Redis view counter: 25 accesses to one incident."""
from __future__ import annotations

import sys

from common import banner  # noqa: I001
from cache_db import IncidentCache  # noqa: E402
from sqlalchemy import text  # noqa: E402


def main() -> int:
    banner("part1_counter.py")
    incident_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    cache = IncidentCache()
    cache.redis_client.delete(cache.views_key(incident_id))          # start the demo from zero
    with cache.session_factory() as db:
        db.execute(text("UPDATE incidents SET view_count = 0 WHERE id = :i"), {"i": incident_id})
        db.commit()
    print(f"key = {cache.views_key(incident_id)}\n\n=== Testing Counter ===\n")
    for n in range(1, 26):
        total = cache.increment_incident_views(incident_id)
        print(f"Access #{n}: Total = {total}", flush=True)
        if cache.last_synced == total:                 # set by the method when it wrote to MySQL
            print("✓ Synced views to database", flush=True)
    with cache.session_factory() as db:
        row = db.execute(text("SELECT view_count FROM incidents WHERE id = :i"), {"i": incident_id}).scalar()
    print(f"\nRedis {cache.views_key(incident_id)} = {cache.redis_client.get(cache.views_key(incident_id))}")
    print(f"MySQL incidents.view_count (id={incident_id}) = {row}   (last synced at the 20th access)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
