import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { formatMatchLabel, sortByMatchScore } from "../formatMatchScore";
import { canSendMatchRequest } from "../matchRequest";
import { ApiError, cancelRequirement, createRfq, getNotifications, getRequirements } from "../api";

export default function ClientDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [requirements, setRequirements] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [error, setError] = useState("");
  const [sendingId, setSendingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getRequirements(), getNotifications()])
      .then(([items, notes]) => {
        if (!cancelled) {
          setRequirements(items);
          setNotifications(notes);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Unable to load dashboard");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const matchCount = requirements.reduce((sum, item) => sum + (item.match_count || 0), 0);
  const supplierMatches = sortByMatchScore(
    requirements.flatMap((item) =>
      (item.matches || []).map((match) => ({ requirement: item, match })),
    ),
    (row) => row.match.final_score,
  );

  async function handleDelete(id) {
    if (!window.confirm("Remove this closed requirement from your dashboard?")) return;
    setError("");
    try {
      await cancelRequirement(id);
      setRequirements((rows) => rows.filter((row) => row.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to delete requirement");
    }
  }

  async function sendRequest(match) {
    setError("");
    setSendingId(match.id);
    try {
      const rfq = await createRfq({ match_id: match.id });
      navigate(`/rfqs/${rfq.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to send request");
      setSendingId(null);
    }
  }

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Client portal</p>
          <h1>{user.company_name || user.full_name}</h1>
          <p className="role-chip">{user.role}</p>
        </div>
        <dl className="profile-facts kpi-facts">
          <div>
            <dt>Requirements</dt>
            <dd>{requirements.length}</dd>
          </div>
          <div>
            <dt>Matches</dt>
            <dd>{matchCount}</dd>
          </div>
          <div>
            <dt>Notifications</dt>
            <dd>{notifications.length}</dd>
          </div>
        </dl>
      </section>

      <section className="featured">
        <div className="section-head">
          <h2>Requirements</h2>
          <Link to="/requirements/new" className="btn">
            + New requirement
          </Link>
        </div>
        {error && <p className="banner banner-error">{error}</p>}
        {requirements.length === 0 ? (
          <p className="lede">No requirements yet. Create one to start matching.</p>
        ) : (
          <div className="card-grid tile-grid">
            {requirements.map((item) => {
              const topMatch = sortByMatchScore(item.matches || [])[0];
              return (
              <article className="product-card portal-card tile-card" key={item.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <h3>{item.product_requirement}</h3>
                    <p>
                      {item.status} · {item.category_name} · {item.match_count} matches
                      {topMatch ? ` · ${formatMatchLabel(topMatch.final_score)}` : ""}
                    </p>
                  </div>
                  <Link className="btn" to={`/requirements/${item.id}`}>
                    View details
                  </Link>
                </div>
                {["CLOSED", "CANCELLED"].includes(item.status) && (
                  <button
                    className="delete-icon"
                    type="button"
                    aria-label="Delete requirement"
                    onClick={() => handleDelete(item.id)}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        fill="currentColor"
                        d="M18.3 5.7 13 11l5.3 5.3-1.4 1.4L11.6 12.4 6.3 17.7 4.9 16.3 10.2 11 4.9 5.7 6.3 4.3l5.3 5.3 5.3-5.3z"
                      />
                    </svg>
                  </button>
                )}
              </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="featured">
        <div className="section-head">
          <h2>Matches</h2>
        </div>
        {supplierMatches.length === 0 ? (
          <p className="lede">No supplier matches yet.</p>
        ) : (
          <div className="card-grid tile-grid">
            {supplierMatches.map(({ requirement, match }) => (
              <article className="product-card portal-card tile-card" key={`${requirement.id}-${match.id}`}>
                <div className="product-copy">
                  <div className="tile-text">
                    <p className="match-score-label">{formatMatchLabel(match.final_score)}</p>
                    <h3>{match.product_offered}</h3>
                    <p>
                      {match.supplier_name} · {match.location} · {requirement.product_requirement} ·{" "}
                      {match.rfq_status || match.match_status}
                    </p>
                  </div>
                  <div className="actions-row">
                    <Link className="btn" to={`/requirements/${requirement.id}`}>
                      View details
                    </Link>
                    {match.rfq_id ? (
                      <Link className="btn" to={`/rfqs/${match.rfq_id}`}>
                        View request
                      </Link>
                    ) : canSendMatchRequest(match) ? (
                      <button
                        className="btn"
                        type="button"
                        disabled={sendingId === match.id}
                        onClick={() => sendRequest(match)}
                      >
                        Send Request
                      </button>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </Layout>
  );
}
