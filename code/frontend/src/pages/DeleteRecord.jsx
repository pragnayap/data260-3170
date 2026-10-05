/**
 * HW5 Part 1.III - Delete confirmation screen.
 *
 * The assignment's delete requirement is satisfied by the inline button on
 * the Home screen, which dispatches deleteIncident directly from the list.
 * This page is kept as the detailed confirmation route (/delete/:id) because
 * HW4's table linked to it, and it shows the full record before removing it.
 *
 * Both paths dispatch the same thunk, so the store update is identical.
 */

import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";

import { deleteIncident, selectIncidentById } from "../store/incidentsSlice";

export default function DeleteRecord() {
  const { id } = useParams();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const incident = useSelector((state) => selectIncidentById(state, id));

  if (!incident) {
    return <p>Incident {id} not found (it may already be deleted).</p>;
  }

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await dispatch(deleteIncident(incident.id)).unwrap();
      navigate("/");
    } catch (message) {
      // unwrap() rejects with the thunk's rejectWithValue payload, which is
      // already the API's `detail` string.
      setError(message ?? "Failed to delete this record.");
      setDeleting(false);
    }
  };

  return (
    <div className="form-page">
      <h1>Delete Incident #{incident.id}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="mono">{incident.incident_code}</p>
      <p>
        <strong>{incident.route_id}</strong> at {incident.location} -- {incident.category}
      </p>
      <p>{incident.description}</p>
      <p className="muted">Riders affected: {incident.riders_affected}</p>
      <div className="actions-cell">
        <button className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
          {deleting ? "Deleting..." : "Delete"}
        </button>
        <button className="btn" onClick={() => navigate("/")} disabled={deleting}>
          Cancel
        </button>
      </div>
    </div>
  );
}
