import { useNavigate, useParams } from "react-router-dom";
import IncidentForm from "../components/IncidentForm";

export default function UpdateRecord({ incidents, onUpdate }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const incident = incidents.find((i) => String(i.id) === id);

  if (!incident) {
    return <p>Incident {id} not found (it may have been deleted).</p>;
  }

  const handleSubmit = async (data) => {
    await onUpdate(incident.id, data);
    navigate("/");
  };

  return (
    <div className="form-page">
      <h1>Update Incident #{incident.id}</h1>
      <IncidentForm initialValues={incident} submitLabel="Save Changes" onSubmit={handleSubmit} />
    </div>
  );
}
