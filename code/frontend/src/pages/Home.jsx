import { Link } from "react-router-dom";

export default function Home({ user, incidents, loading }) {
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

  if (loading) {
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

  return (
    <div>
      <h1>Transit Incidents</h1>
      <div className="table-wrap">
        <table className="incident-table">
          <thead>
            <tr>
              <th>Route ID</th>
              <th>Location</th>
              <th>Category</th>
              <th>Description</th>
              <th>Related route</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id}>
                <td>{incident.route_id}</td>
                <td>{incident.location}</td>
                <td>
                  <span className={`badge badge-${incident.category.split(/[- ]/)[0].toLowerCase()}`}>
                    {incident.category}
                  </span>
                </td>
                <td className="description-cell">{incident.description}</td>
                <td>{incident.route ? incident.route.route_name : incident.related_route_id}</td>
                <td>
                  <div className="actions">
                    <Link to={`/update/${incident.id}`} className="btn btn-small">
                      Edit
                    </Link>
                    <Link to={`/delete/${incident.id}`} className="btn btn-small btn-danger">
                      Delete
                    </Link>
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
