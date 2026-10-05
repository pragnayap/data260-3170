/**
 * HW5 Part 1.III - Create Screen.
 *
 * Spec: "On submission, dispatch the correct Redux thunk and show the updated
 * results on the Home Screen."
 *
 * dispatch() on an async thunk returns a promise that always RESOLVES, even
 * when the request failed -- it resolves to a rejected action rather than
 * throwing. unwrap() is what converts that back into normal promise
 * behaviour, so a 409 or 422 from the API lands in the catch block here
 * instead of silently navigating away as if the save had worked.
 */

import { useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";

import IncidentForm from "../components/IncidentForm";
import { createIncident } from "../store/incidentsSlice";

export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const handleSubmit = async (data) => {
    await dispatch(createIncident(data)).unwrap();  // throws on 409/422
    navigate("/");                                   // only runs if it saved
  };

  return (
    <div className="form-page">
      <h1>Report a New Incident</h1>
      <IncidentForm submitLabel="Add Record" onSubmit={handleSubmit} />
    </div>
  );
}
