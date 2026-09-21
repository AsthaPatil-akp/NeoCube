import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError, getAdminAuditLogs, getAdminSummary } from "../api";

export default function AdminDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAdminSummary(), getAdminAuditLogs()])
      .then(([data, logs]) => {
        if (!cancelled) {
          setSummary(data);
          setAuditLogs(logs);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load admin summary");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>{user.full_name}</h1>
          <p className="role-chip">{user.role}</p>
        </div>
        {summary && (
          <dl className="profile-facts kpi-facts">
            <div>
              <dt>Users</dt>
              <dd>{summary.users}</dd>
            </div>
            <div>
              <dt>Requirements</dt>
              <dd>{summary.requirements}</dd>
            </div>
            <div>
              <dt>Offerings</dt>
              <dd>{summary.offerings}</dd>
            </div>
          </dl>
        )}
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {summary && (
          <dl className="profile-facts kpi-facts">
            <div>
              <dt>Clients</dt>
              <dd>{summary.clients}</dd>
            </div>
            <div>
              <dt>Suppliers</dt>
              <dd>{summary.suppliers}</dd>
            </div>
            <div>
              <dt>Matches</dt>
              <dd>{summary.matches}</dd>
            </div>
            <div>
              <dt>RFQs</dt>
              <dd>{summary.rfqs}</dd>
            </div>
            <div>
              <dt>Quotations</dt>
              <dd>{summary.quotations}</dd>
            </div>
            <div>
              <dt>Audit logs</dt>
              <dd>{summary.audit_logs}</dd>
            </div>
          </dl>
        )}
        {auditLogs.length > 0 && (
          <>
            <div className="section-head">
              <h2>Recent audit events</h2>
            </div>
            <div className="card-grid tile-grid">
              {auditLogs.slice(0, 8).map((item) => (
                <article className="product-card portal-card tile-card" key={item.id}>
                  <div className="product-copy">
                    <div className="tile-text">
                      <h3>{item.action}</h3>
                      <p>
                        {item.entity_type || "system"}
                        {item.entity_id != null ? ` #${item.entity_id}` : ""}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </Layout>
  );
}
