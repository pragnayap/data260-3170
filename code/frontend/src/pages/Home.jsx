/**
 * HW5 Part 1.III - Home Screen.
 *
 * Spec: "Display all records by reading from Redux state; the list updates
 * automatically when records are created, updated, or deleted."
 *
 * There are no props. Everything comes from useSelector, which subscribes
 * this component to the store: when a create/update/delete reducer changes
 * state.incidents.items, React re-renders this table on its own. Nothing in
 * App has to tell it to.
 */

import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";

import { selectUser } from "../store/authSlice";
import {
  deleteIncident,
  selectIncidents,
  selectIncidentsStatus,
} from "../store/incidentsSlice";

export default function Home() {
  const dispatch = useDispatch();
  const user = useSelector(selectUser);
  const incidents = useSelector(selectIncidents);
  const status = useSelector(selectIncidentsStatus);

  // Which row is awaiting delete confirmation. Local UI state, not app state,
  // so it stays in useState rather than going into the store.
  const [confirmingId, setConfirmingId] = useState(null);

  if (!user) {
    return (
      <div className="empty-state">
        <p>Login required to view transit incident records.</p>
        <Link to="/login" className="btn btn-primary">
          Go to login
        </Link>
      </div>
    );
  }

  if (status === "loading") {
    return <p>Loading incidents...</p>;
  }

  if (incidents.length === 0) {
    return (
      <div className="empty-state">
        <p>No incidents yet.</p>
        <Link to="/create" className="btn btn-primary">
          Add the first record
        </Link>
      </div>
    );
  }

  // Spec: "Add a delete button next to each record in the list. On click,
  // dispatch the delete thunk and update Redux state to remove the record."
  const handleDelete = (id) => {
    dispatch(deleteIncident(id));
    setConfirmingId(null);
  };

  return (
    <div>
      <h1>Transit Incidents</h1>
      <p className="muted">
        {incidents.length} record{incidents.length === 1 ? "" : "s"} in Redux state
      </p>
      <div className="table-wrap">
        <table className="incident-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Route ID</th>
              <th>Location</th>
              <th>Category</th>
              <th>Riders</th>
              <th>Description</th>
              <th>Related route</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id}>
                <td className="mono">{incident.incident_code}</td>
                <td>{incident.route_id}</td>
                <td>{incident.location}</td>
                <td>
                  <span
                    className={`badge badge-${incident.category
                      .split(/[- ]/)[0]
                      .toLowerCase()}`}
                  >
                    {incident.category}
                  </span>
                </td>
                <td className="num">{incident.riders_affected}</td>
                <td className="description-cell">{incident.description}</td>
                <td>
                  {incident.route ? incident.route.route_name : incident.related_route_id}
                </td>
                <td>
                  <div className="actions">
                    <Link to={`/update/${incident.id}`} className="btn btn-small">
                      Edit
                    </Link>
                    {confirmingId === incident.id ? (
                      <>
                        <button
                          className="btn btn-small btn-danger"
                          onClick={() => handleDelete(incident.id)}
                        >
                          Confirm
                        </button>
                        <button
                          className="btn btn-small"
                          onClick={() => setConfirmingId(null)}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => setConfirmingId(incident.id)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
