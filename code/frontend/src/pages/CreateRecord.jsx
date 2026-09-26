import { useNavigate } from "react-router-dom";
import IncidentForm from "../components/IncidentForm";

export default function CreateRecord({ onCreate }) {
  const navigate = useNavigate();

  const handleSubmit = async (data) => {
    await onCreate(data);
    navigate("/");
  };

  return (
    <div className="form-page">
      <h1>Report a New Incident</h1>
      <IncidentForm submitLabel="Add Record" onSubmit={handleSubmit} />
    </div>
  );
}
