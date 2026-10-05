/**
 * HW5 Part 1 - the shared create/update form.
 *
 * Changes from HW4:
 *   * two new fields, matching the new columns: incident_code (unique,
 *     format-validated) and riders_affected (numeric, defaults to 0)
 *   * routesApi.list() now returns a paginated page, so the dropdown reads
 *     .items (handled in api/incidentsApi.js)
 *   * only the seven writable fields are submitted. The record in Redux also
 *     carries id, created_at, updated_at and a nested route object; sending
 *     those back would be noise at best and confusing in a request log.
 */

import { useEffect, useState } from "react";

import { routesApi } from "../api/incidentsApi";

const CATEGORIES = ["Delay", "Mechanical Failure", "Accident-Collision", "Safety Hazard"];

// The exact set the API accepts. Anything else in state is display-only.
const FIELD_KEYS = [
  "incident_code",
  "route_id",
  "location",
  "submitter_email",
  "description",
  "category",
  "riders_affected",
  "related_route_id",
];

/**
 * Suggest a unique code in the required INC-3170-NNNNN format.
 *
 * The seeded rows occupy INC-3170-00001 through INC-3170-05000, so new codes
 * are drawn from 90000-99999 to stay clear of them. It is only a suggestion --
 * the field is editable, and a genuine collision still comes back from the
 * API as a 409, which is worth demonstrating.
 */
function suggestIncidentCode() {
  const n = 90000 + Math.floor(Math.random() * 10000);
  return `INC-3170-${n}`;
}

const emptyForm = {
  incident_code: "",
  route_id: "",
  location: "",
  submitter_email: "",
  description: "",
  category: CATEGORIES[0],
  riders_affected: 0,
  related_route_id: "",
};

export default function IncidentForm({ initialValues, submitLabel, onSubmit }) {
  const isEdit = Boolean(initialValues);

  const [form, setForm] = useState(() => ({
    ...emptyForm,
    ...(initialValues ?? {}),
    // On create, pre-fill a valid-looking code so the format is obvious.
    incident_code: initialValues?.incident_code ?? suggestIncidentCode(),
  }));
  const [routeOptions, setRouteOptions] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    routesApi
      .list()
      .then((rows) => {
        setRouteOptions(rows);
        setForm((prev) =>
          prev.related_route_id ? prev : { ...prev, related_route_id: rows[0]?.id ?? "" }
        );
      })
      .catch(() => setRouteOptions([]));
  }, []);

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    // Pick only the writable fields, and coerce the two numerics -- an <input>
    // always hands back a string, and related_route_id must be an int or the
    // API answers 422.
    const payload = {};
    for (const key of FIELD_KEYS) payload[key] = form[key];
    payload.related_route_id = Number(payload.related_route_id);
    payload.riders_affected = Number(payload.riders_affected) || 0;

    try {
      await onSubmit(payload);
    } catch (message) {
      // The parent dispatches with .unwrap(), so what arrives here is already
      // the API's `detail` string (409 duplicate code, 404 missing route, ...).
      setError(
        typeof message === "string"
          ? message
          : message?.response?.data?.detail ?? "Something went wrong. Please try again."
      );
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="record-form">
      {error && <div className="alert alert-error">{error}</div>}

      <label>
        Incident code (unique, format INC-3170-NNNNN)
        <input
          value={form.incident_code}
          onChange={update("incident_code")}
          pattern="^INC-\d{4}-\d{5}$"
          title="Format: INC-3170-00001"
          required
        />
      </label>

      <label>
        Route ID (primary field)
        <input value={form.route_id} onChange={update("route_id")} required />
      </label>

      <label>
        Location (secondary field)
        <input value={form.location} onChange={update("location")} required />
      </label>

      <label>
        Submitter email
        <input
          type="email"
          value={form.submitter_email}
          onChange={update("submitter_email")}
          required
        />
      </label>

      <label>
        Description (25+ characters)
        <textarea
          value={form.description}
          onChange={update("description")}
          minLength={25}
          required
          rows={3}
        />
      </label>

      <label>
        Category
        <select value={form.category} onChange={update("category")}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>

      <label>
        Riders affected (defaults to 0)
        <input
          type="number"
          min={0}
          value={form.riders_affected}
          onChange={update("riders_affected")}
        />
      </label>

      <label>
        Related route
        <select value={form.related_route_id} onChange={update("related_route_id")} required>
          {routeOptions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.route_code} - {r.route_name} ({r.agency})
            </option>
          ))}
        </select>
      </label>

      <button type="submit" className="btn btn-primary" disabled={submitting}>
        {submitting ? "Saving..." : submitLabel}
      </button>
      {isEdit && (
        <p className="muted">
          Changing the incident code to one that already exists returns 409 from the API.
        </p>
      )}
    </form>
  );
}
