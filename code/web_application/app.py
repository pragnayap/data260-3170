"""
HW2 Part 2 - FastAPI backend for the transit-incident domain.

Serves the HW1 form and a REST API over an in-memory list of incidents:
create, read, update, delete, and search by the primary field (routeId) or the
secondary field (location).

Storage is a module-level list, so everything resets when the process restarts.
That is deliberate for this assignment -- no database is required -- but it does
mean the seed records come back on every boot.

Run:
    uvicorn app:app --reload --port 8470     (from this directory)
"""

from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

PORT_BASE = 8470  # 8000 + (3170 mod 900), fixed for the semester

app = FastAPI(title="Transit Incident API", version="2.0.0")

# Serve files directly from this folder (no separate static/ subfolder, no
# renaming) so the existing HW1 files stay exactly where/what they are.
app.mount("/static", StaticFiles(directory="."), name="static")


# --- Pydantic models ---

class TransitIncidentBase(BaseModel):
    routeId: str = Field(..., min_length=1, description="Primary field")
    location: str = Field(..., min_length=1, description="Secondary field")
    submitterEmail: EmailStr
    description: str = Field(..., min_length=25)
    category: str

    model_config = {"str_strip_whitespace": True}


class TransitIncidentCreate(TransitIncidentBase):
    """POST body -- same as the full record minus the server-assigned id."""


class TransitIncidentUpdate(TransitIncidentBase):
    """PUT body -- a full replacement of the mutable fields."""


class TransitIncident(TransitIncidentBase):
    """A stored record, including its id."""

    id: int


# --- In-memory storage ---

incidents: List[TransitIncident] = [
    TransitIncident(
        id=1,
        routeId="Line 22",
        location="Downtown Transit Center",
        submitterEmail="rider@example.com",
        description="The 7:15am bus never arrived and riders waited forty minutes with no announcement.",
        category="Delay",
    ),
    TransitIncident(
        id=2,
        routeId="BART Red Line",
        location="Civic Center Station",
        submitterEmail="commuter@example.com",
        description="Both elevators at the station entrance were out of service for the whole morning.",
        category="Mechanical Failure",
    ),
]


def find_incident(incident_id: int) -> TransitIncident:
    """Return the record with this id, or raise 404."""
    for incident in incidents:
        if incident.id == incident_id:
            return incident
    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")


def no_store(response: Optional[Response]) -> None:
    """Stop the browser serving a stale list after a create/update/delete."""
    if response is not None:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"


# --- Pages ---

@app.get("/", include_in_schema=False)
async def read_root():
    return FileResponse("HW1-PragnayaPriyadarshini.html")


@app.get("/styles.css", include_in_schema=False)
async def serve_styles():
    return FileResponse("styles.css", media_type="text/css")


@app.get("/hw1.js", include_in_schema=False)
async def serve_hw1_js():
    return FileResponse("hw1.js", media_type="application/javascript")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Browsers request this on every page load; no icon is defined for this
    assignment, so answer 'nothing here' rather than letting it log a 404."""
    return Response(status_code=204)


# --- REST API ---

@app.get("/api/incidents", response_model=List[TransitIncident])
async def get_incidents(search: Optional[str] = None, response: Response = None):
    """List incidents, optionally filtered by primary or secondary field.

    The search is a case-insensitive substring match against routeId and
    location, which is what the form's search box offers.
    """
    no_store(response)

    if not search or not search.strip():
        return incidents

    term = search.strip().lower()
    return [
        incident
        for incident in incidents
        if term in incident.routeId.lower() or term in incident.location.lower()
    ]


@app.get("/api/incidents/{incident_id}", response_model=TransitIncident)
async def get_incident(incident_id: int, response: Response = None):
    no_store(response)
    return find_incident(incident_id)


@app.post("/api/incidents", response_model=TransitIncident, status_code=201)
async def create_incident(incident_data: TransitIncidentCreate, response: Response = None):
    """Add a record. The client redirects to the list view once this returns."""
    no_store(response)

    # Max+1 rather than len+1: after a delete, len+1 can collide with a live id.
    new_id = max((i.id for i in incidents), default=0) + 1

    incident = TransitIncident(id=new_id, **incident_data.model_dump())
    incidents.append(incident)
    return incident


@app.put("/api/incidents/{incident_id}", response_model=TransitIncident)
async def update_incident(
    incident_id: int, incident_data: TransitIncidentUpdate, response: Response = None
):
    """Replace the mutable fields of one record, keeping its id."""
    no_store(response)

    existing = find_incident(incident_id)
    updated = TransitIncident(id=existing.id, **incident_data.model_dump())
    incidents[incidents.index(existing)] = updated
    return updated


@app.delete("/api/incidents/{incident_id}", response_model=TransitIncident)
async def delete_incident(incident_id: int, response: Response = None):
    """Delete one record and return it, so the client can confirm what went."""
    no_store(response)

    incident = find_incident(incident_id)
    incidents.remove(incident)
    return incident


@app.get("/api/incidents-highest-id", response_model=Optional[int])
async def highest_incident_id(response: Response = None):
    """Id the 'delete newest' button targets, so the client needn't compute it."""
    no_store(response)
    return max((i.id for i in incidents), default=None)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT_BASE)
