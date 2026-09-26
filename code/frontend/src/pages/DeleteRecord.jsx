import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function DeleteRecord({ incidents, onDelete }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const incident = incidents.find((i) => String(i.id) === id);

  if (!incident) {
    return <p>Incident {id} not found (it may already be deleted).</p>;
  }

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onDelete(incident.id);
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Failed to delete this record.");
      setDeleting(false);
    }
  };

  return (
    <div className="form-page">
      <h1>Delete Incident #{incident.id}</h1>
      {error && <div className="alert alert-error">{error}</div>}
      <p>
        <strong>{incident.route_id}</strong> at {incident.location} -- {incident.category}
      </p>
      <p>{incident.description}</p>
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
