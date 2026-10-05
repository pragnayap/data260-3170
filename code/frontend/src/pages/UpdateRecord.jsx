/**
 * HW5 Part 1.III - Update Screen.
 *
 * Spec: "Build a form to update an existing record (select by ID)."
 *
 * The record comes out of Redux state via a selector rather than from a prop.
 * That is the whole point of the migration: this screen can be opened
 * directly at /update/42 and still find its data, because the store is not
 * owned by any particular parent component.
 */

import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";

import IncidentForm from "../components/IncidentForm";
import { selectIncidentById, updateIncident } from "../store/incidentsSlice";

export default function UpdateRecord() {
  const { id } = useParams();
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const incident = useSelector((state) => selectIncidentById(state, id));

  if (!incident) {
    return <p>Incident {id} not found (it may have been deleted).</p>;
  }

  const handleSubmit = async (data) => {
    await dispatch(updateIncident({ id: incident.id, incident: data })).unwrap();
    navigate("/");
  };

  return (
    <div className="form-page">
      <h1>Update Incident #{incident.id}</h1>
      <IncidentForm
        initialValues={incident}
        submitLabel="Save Changes"
        onSubmit={handleSubmit}
      />
    </div>
  );
}
