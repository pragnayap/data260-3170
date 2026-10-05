/**
 * HW5 Part 1.III - Login, dispatching the auth thunk.
 *
 * email/password stay in useState: they are form-field state belonging to
 * this one component, not application state anyone else reads. Putting every
 * keystroke through the store is a common Redux over-correction -- the rule
 * worth keeping is that shared state goes in the store, local UI state
 * does not.
 */

import { useState } from "react";
import { useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";

import { login } from "../store/authSlice";

export default function Login() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await dispatch(login({ email, password })).unwrap();
      navigate("/");
    } catch (message) {
      setError(message ?? "Invalid email or password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="form-page">
      <h1>Login</h1>
      {error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={handleSubmit} className="record-form">
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Signing in..." : "Login"}
        </button>
      </form>
    </div>
  );
}
