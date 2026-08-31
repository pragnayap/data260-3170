# Domain Schema - Municipal Transit Incidents

**DOMAIN_ID:** 2 (SID4 3170 mod 8 = 2)
**PREFIX:** s3170

## Entity: Transit Incident
| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` (primary) | text | yes | The bus/train line or route affected, e.g. "Line 22" or "BART Red Line" |
| `location` (secondary) | text | yes | Stop, station, or intersection where the incident occurred |
| `submitterEmail` | email | yes | Email of the person reporting the incident |
| `description` (content) | textarea | yes | Free-text description of what happened; must be > 25 characters |
| `category` | select (1 of 4) | yes | See category values below |
| `agreeTerms` | checkbox | yes | "I agree to the terms and conditions." |

## Category values
1. `Delay` — Service running behind schedule
2. `Mechanical Failure` — Vehicle breakdown or equipment malfunction
3. `Accident/Collision` — Collision involving a transit vehicle
4. `Safety Hazard` — Unsafe condition (e.g. blocked platform, broken signal)

## Derived submission object (client-side)
```json
{
  "routeId": "Line 22",
  "location": "Downtown Transit Center",
  "submitterEmail": "rider@example.com",
  "description": "Bus arrived 40 minutes late with no announcement or updated signage at the stop.",
  "category": "Delay",
  "agreeTerms": true,
  "submissionDate": "2026-08-27T22:10:00.000Z"
}
```