"""
HW6 - PyMongo connection for the s3170_doc database.

One MongoClient per process (PyMongo clients are thread-safe and pool their own
connections). Part 1's collection (`transit_incidents`) and Part 2's three
collections (`messages`, `summaries`, `episodes`) all live in the same
database; this module is the only place that knows the URI and the names.

The database is created lazily by MongoDB on first write, so `ensure_indexes`
and `ensure_validators` run at app startup to make the schema rules exist even
before the first insert.
"""

import os

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid

PREFIX = "s3170"
MONGO_URI = os.environ.get("S3170_MONGO_URI", "mongodb://localhost:27017")
DB_NAME = f"{PREFIX}_doc"

INCIDENT_STATUSES = ["Open", "Investigating", "Resolved"]
INCIDENT_CATEGORIES = ["Delay", "Mechanical Failure", "Accident-Collision", "Safety Hazard"]

# serverSelectionTimeoutMS keeps a missing mongod from hanging every request
# for the 30 s default; the routes turn the resulting error into a 503.
_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_db():
    return _client[DB_NAME]


def get_client() -> MongoClient:
    return _client


# Server-side mirror of the Pydantic rules. Pydantic is the first line of
# defence and gives the readable 422s; $jsonSchema is the backstop that keeps
# bad documents out even if something writes to the collection directly
# (Compass, mongosh, a future script).
INCIDENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["routeId", "category", "status", "occurredAt", "createdAt", "updatedAt"],
        "properties": {
            "routeId": {"bsonType": "string", "minLength": 1, "maxLength": 100},
            "location": {"bsonType": ["string", "null"], "maxLength": 200},
            "description": {"bsonType": ["string", "null"], "maxLength": 2000},
            "status": {"enum": INCIDENT_STATUSES},
            "category": {"enum": INCIDENT_CATEGORIES},
            "occurredAt": {"bsonType": "date"},
            "createdAt": {"bsonType": "date"},
            "updatedAt": {"bsonType": "date"},
        },
    }
}


def ensure_schema() -> None:
    """Create collections with validators and indexes. Idempotent."""
    db = get_db()
    try:
        db.create_collection(
            "transit_incidents", validator=INCIDENT_VALIDATOR, validationAction="error"
        )
    except CollectionInvalid:
        db.command("collMod", "transit_incidents", validator=INCIDENT_VALIDATOR)
    for name in ("messages", "summaries", "episodes"):
        if name not in db.list_collection_names():
            db.create_collection(name)
    db.transit_incidents.create_index([("routeId", ASCENDING)])
    db.transit_incidents.create_index([("createdAt", DESCENDING)])
    db.messages.create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)])
    db.summaries.create_index([("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)])
    db.episodes.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
