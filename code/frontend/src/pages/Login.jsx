import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onLogin(email, password);
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.detail ?? "Invalid email or password");
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
