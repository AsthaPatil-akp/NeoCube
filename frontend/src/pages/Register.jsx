import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api";
import { portalPath } from "../portalPath";

const INITIAL = {
  email: "",
  password: "",
  full_name: "",
  company_name: "",
  phone: "",
  role: "CLIENT",
};

export default function Register() {
  const { user, loading, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(INITIAL);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) {
    return <Navigate to={portalPath(user)} replace />;
  }

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register({
        ...form,
        phone: form.phone.trim() || null,
      });
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to register");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout>
      <section className="auth-layout">
        <div className="auth-panel">
          <p className="eyebrow">Join NeoCube</p>
          <h1>Create your account.</h1>
          <p className="lede">Join as a client or supplier. Admin registration is not available here.</p>
          {error && <p className="banner banner-error">{error}</p>}
          <form className="stack-form compact-form" onSubmit={handleSubmit}>
            <fieldset className="role-picker">
              <legend>I am a</legend>
              <label className={form.role === "CLIENT" ? "role-option active" : "role-option"}>
                <input
                  type="radio"
                  name="role"
                  value="CLIENT"
                  checked={form.role === "CLIENT"}
                  onChange={() => update("role", "CLIENT")}
                />
                <span>Client</span>
              </label>
              <label className={form.role === "SUPPLIER" ? "role-option active" : "role-option"}>
                <input
                  type="radio"
                  name="role"
                  value="SUPPLIER"
                  checked={form.role === "SUPPLIER"}
                  onChange={() => update("role", "SUPPLIER")}
                />
                <span>Supplier</span>
              </label>
            </fieldset>
            <div className="form-grid">
              <label>
                Full name
                <input
                  value={form.full_name}
                  onChange={(event) => update("full_name", event.target.value)}
                  required
                />
              </label>
              <label>
                Company name
                <input
                  value={form.company_name}
                  onChange={(event) => update("company_name", event.target.value)}
                  required
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                  required
                />
              </label>
              <label>
                Phone
                <input value={form.phone} onChange={(event) => update("phone", event.target.value)} />
              </label>
            </div>
            <label>
              Password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={form.password}
                onChange={(event) => update("password", event.target.value)}
                required
              />
            </label>
            <p className="field-hint">At least 8 characters.</p>
            <button className="btn" type="submit" disabled={submitting}>
              {submitting ? "Creating account…" : "Create account →"}
            </button>
          </form>
          <p className="form-foot">
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </div>
        <div className="auth-photo">
          <img
            src="https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=1400&q=80"
            alt="Business meeting between potential partners"
          />
        </div>
      </section>
    </Layout>
  );
}
