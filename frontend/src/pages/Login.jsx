import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api";
import { portalPath } from "../portalPath";

export default function Login() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const registered = location.state?.registered;

  useEffect(() => {
    setEmail("");
    setPassword("");
    const timer = window.setTimeout(() => {
      setEmail("");
      setPassword("");
    }, 150);
    return () => window.clearTimeout(timer);
  }, []);

  if (!loading && user) {
    return <Navigate to={portalPath(user)} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const data = await login(email, password);
      navigate(portalPath(data), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout>
      <section className="auth-layout">
        <div className="auth-panel">
          <p className="eyebrow">Welcome back</p>
          <h1>Sign in.</h1>
          <p className="lede">Sign in to your client or supplier account.</p>
          {registered && <p className="banner banner-success">Account created. Please sign in.</p>}
          {error && <p className="banner banner-error">{error}</p>}
          <form className="stack-form compact-form login-form" onSubmit={handleSubmit} autoComplete="off">
            <label>
              Email
              <input
                type="email"
                name="neocube-email"
                autoComplete="off"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                name="neocube-password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="btn" type="submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in →"}
            </button>
          </form>
          <p className="form-foot">
            New here? <Link to="/register">Create an account</Link>
          </p>
        </div>
        <div className="auth-photo">
          <img
            src="https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=1400&q=80"
            alt="Client and supplier teams working together"
          />
        </div>
      </section>
    </Layout>
  );
}
