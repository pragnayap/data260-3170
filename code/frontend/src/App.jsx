/**
 * HW5 Part 1.III - App after the Redux migration.
 *
 * Compare with the HW4 version. App used to hold five useState hooks, a
 * useCallback refresh function and five handler functions, and it passed all
 * of them down as props to Home, Login, CreateRecord, UpdateRecord and
 * DeleteRecord. None of that is here any more: each screen reads the store
 * directly, so App's only remaining job is routing and the shell.
 */

import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import Home from "./pages/Home";
import Login from "./pages/Login";
import CreateRecord from "./pages/CreateRecord";
import UpdateRecord from "./pages/UpdateRecord";
import DeleteRecord from "./pages/DeleteRecord";

import { fetchMe, logout, selectAuthChecked, selectUser } from "./store/authSlice";
import {
  cleared,
  errorDismissed,
  fetchIncidents,
  selectIncidentsError,
} from "./store/incidentsSlice";

import "./App.css";

function NavBar() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const user = useSelector(selectUser);

  const handleLogout = async () => {
    await dispatch(logout());
    dispatch(cleared());          // drop the previous user's rows from the store
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
  const dispatch = useDispatch();
  const user = useSelector(selectUser);
  const authChecked = useSelector(selectAuthChecked);
  const error = useSelector(selectIncidentsError);

  // Ask the server who we are, once, on boot.
  useEffect(() => {
    dispatch(fetchMe());
  }, [dispatch]);

  // Load the list as soon as we know there is a session. Every later refresh
  // is handled by the create/update/delete reducers updating state in place,
  // so this is the only place a full list fetch is dispatched.
  useEffect(() => {
    if (user) dispatch(fetchIncidents());
  }, [user, dispatch]);

  if (!authChecked) {
    return <div className="page-loading">Checking session...</div>;
  }

  return (
    <BrowserRouter>
      <NavBar />
      <main className="container">
        {error && (
          <div className="alert alert-error" onClick={() => dispatch(errorDismissed())}>
            {error}
          </div>
        )}
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
          <Route
            path="/create"
            element={user ? <CreateRecord /> : <Navigate to="/login" replace />}
          />
          <Route
            path="/update/:id"
            element={user ? <UpdateRecord /> : <Navigate to="/login" replace />}
          />
          <Route
            path="/delete/:id"
            element={user ? <DeleteRecord /> : <Navigate to="/login" replace />}
          />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
