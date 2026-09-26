import { useEffect, useState } from "react";
import { routesApi } from "../api/incidentsApi";

const CATEGORIES = ["Delay", "Mechanical Failure", "Accident-Collision", "Safety Hazard"];

const emptyForm = {
  route_id: "",
  location: "",
  submitter_email: "",
  description: "",
  category: CATEGORIES[0],
  related_route_id: "",
};

export default function IncidentForm({ initialValues, submitLabel, onSubmit }) {
  const [form, setForm] = useState({ ...emptyForm, ...initialValues });
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
    try {
      await onSubmit({ ...form, related_route_id: Number(form.related_route_id) });
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="record-form">
      {error && <div className="alert alert-error">{error}</div>}

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
        <input type="email" value={form.submitter_email} onChange={update("submitter_email")} required />
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
    </form>
  );
}
