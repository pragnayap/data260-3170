import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { authApi, incidentsApi } from "./api/incidentsApi";
import Home from "./pages/Home";
import Login from "./pages/Login";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";
import DeleteRecord from "./pages/DeleteRecord";
import "./App.css";

function NavBar({ user, onLogout }) {
  const navigate = useNavigate();

  const handleLogout = async () => {
    await onLogout();
    navigate("/login");
  };

  return (
    <nav className="navbar">
      <Link to="/" className="brand">
        Transit Incidents
      </Link>
      <div className="nav-links">
        {user ? (
          <>
            <Link to="/create">Add Record</Link>
            <span className="nav-user">{user.email}</span>
            <button onClick={handleLogout}>Logout</button>
          </>
        ) : (
          <Link to="/login">Login</Link>
        )}
      </div>
    </nav>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [incidents, setIncidents] = useState([]);
  const [loadingIncidents, setLoadingIncidents] = useState(false);
  const [error, setError] = useState(null);

  const refreshIncidents = useCallback(async () => {
    setLoadingIncidents(true);
    setError(null);
    try {
      const page = await incidentsApi.list(1, 100, "fixed");
      setIncidents(page.items);
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Failed to load incidents");
    } finally {
      setLoadingIncidents(false);
    }
  }, []);

  useEffect(() => {
    authApi
      .me()
      .then((me) => setUser(me))
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (user) refreshIncidents();
  }, [user, refreshIncidents]);

  const handleLogin = async (email, password) => {
    const me = await authApi.login(email, password);
    setUser(me);
  };

  const handleLogout = async () => {
    await authApi.logout();
    setUser(null);
    setIncidents([]);
  };

  const handleCreate = async (incidentData) => {
    await incidentsApi.create(incidentData);
    await refreshIncidents();
  };

  const handleUpdate = async (id, incidentData) => {
    await incidentsApi.update(id, incidentData);
    await refreshIncidents();
  };

  const handleDelete = async (id) => {
    await incidentsApi.remove(id);
    await refreshIncidents();
  };

  if (!authChecked) {
    return <div className="page-loading">Checking session...</div>;
  }

  return (
    <BrowserRouter>
      <NavBar user={user} onLogout={handleLogout} />
      <main className="container">
        {error && <div className="alert alert-error">{error}</div>}
        <Routes>
          <Route
            path="/"
            element={<Home user={user} incidents={incidents} loading={loadingIncidents} />}
          />
          <Route
            path="/login"
            element={user ? <Navigate to="/" replace /> : <Login onLogin={handleLogin} />}
          />
          <Route
            path="/create"
            element={
              user ? <CreateRecord onCreate={handleCreate} /> : <Navigate to="/login" replace />
            }
          />
          <Route
            path="/update/:id"
            element={
              user ? (
                <UpdateRecord incidents={incidents} onUpdate={handleUpdate} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/delete/:id"
            element={
              user ? (
                <DeleteRecord incidents={incidents} onDelete={handleDelete} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
