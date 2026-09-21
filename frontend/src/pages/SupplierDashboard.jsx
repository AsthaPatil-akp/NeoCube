import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { formatMatchLabel, sortByMatchScore } from "../formatMatchScore";
import { ApiError, deactivateOffering, getNotifications, getOfferings, getRfqs } from "../api";

const HISTORY_STEPS = ["Matched", "Requested", "Quoted", "Closed"];

function historyStatus(match, rfq) {
  if (rfq?.status) return rfq.status;
  const matchStatus = String(match.match_status || "").toUpperCase();
  if (matchStatus && matchStatus !== "NEW") return match.match_status;
  return match.status || match.match_status;
}

function historyStepIndex(match, rfq) {
  if (rfq) {
    const status = String(rfq.status || "").toUpperCase();
    if (["ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED"].includes(status)) return 3;
    if (status === "RESPONDED" || (rfq.quotations || []).length > 0) return 2;
    return 1;
  }
  const matchStatus = String(match.match_status || "").toUpperCase();
  const reqStatus = String(match.status || "").toUpperCase();
  if (["ACCEPTED", "REJECTED"].includes(matchStatus) || ["CLOSED", "CANCELLED"].includes(reqStatus)) return 3;
  if (matchStatus === "RESPONDED") return 2;
  if (matchStatus === "RFQ_SENT" || reqStatus === "RFQ_SENT") return 1;
  return 0;
}

function formatHistoryDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function SupplierDashboard() {
  const { user } = useAuth();
  const [offerings, setOfferings] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [rfqs, setRfqs] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getOfferings(), getNotifications(), getRfqs()])
      .then(([items, notes, requests]) => {
        if (!cancelled) {
          setOfferings(items);
          setNotifications(notes);
          setRfqs(requests);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load dashboard");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const matchCount = offerings.reduce((sum, item) => sum + (item.match_count || 0), 0);
  const rfqsByMatchId = Object.fromEntries(
    rfqs.filter((item) => item.match_id != null).map((item) => [item.match_id, item]),
  );
  const rfqsByPair = Object.fromEntries(
    rfqs.map((item) => [`${item.offering_id}:${item.requirement_id}`, item]),
  );
  const historyRows = sortByMatchScore(
    offerings.flatMap((item) =>
      (item.matches || []).map((match) => ({
        offering: item,
        match,
        rfq:
          rfqsByMatchId[match.id] ||
          rfqsByPair[`${item.id}:${match.requirement_id}`] ||
          null,
      })),
    ),
    (row) => row.match.final_score,
  );

  async function handleDelete(id) {
    if (!window.confirm("Remove this offering from your dashboard?")) return;
    setError("");
    try {
      await deactivateOffering(id);
      setOfferings((rows) => rows.filter((row) => row.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to delete offering");
    }
  }

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Supplier portal</p>
          <h1>{user.company_name || user.full_name}</h1>
          <p className="role-chip">{user.role}</p>
        </div>
        <dl className="profile-facts kpi-facts">
          <div>
            <dt>Offerings</dt>
            <dd>{offerings.length}</dd>
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
          <h2>Offerings</h2>
          <Link to="/offerings/new" className="btn">
            + New offering
          </Link>
        </div>
        {error && <p className="banner banner-error">{error}</p>}
        {offerings.length === 0 ? (
          <p className="lede">No offerings yet. Publish one to appear in matching.</p>
        ) : (
          <div className="card-grid tile-grid">
            {offerings.map((item) => {
              const topMatch = sortByMatchScore(item.matches || [])[0];
              return (
              <article className="product-card portal-card tile-card" key={item.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <h3>{item.product_offered}</h3>
                    <p>
                      {item.status} · {item.category_name} · {item.match_count} matches
                      {topMatch ? ` · ${formatMatchLabel(topMatch.final_score)}` : ""}
                    </p>
                  </div>
                  <Link className="btn" to={`/offerings/${item.id}`}>
                    View details
                  </Link>
                </div>
                {["DEACTIVATED", "EXPIRED"].includes(item.status) && (
                  <button
                    className="delete-icon"
                    type="button"
                    aria-label="Delete offering"
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
          <h2>Match history</h2>
        </div>
        {historyRows.length === 0 ? (
          <p className="lede">No matching client requirements yet.</p>
        ) : (
          <div className="history-list">
            {historyRows.map(({ offering, match, rfq }) => {
              const step = historyStepIndex(match, rfq);
              const when = formatHistoryDate(rfq?.created_at);
              return (
                <article className="history-item" key={`${offering.id}-${match.id}`}>
                  <span className={`history-mark${step >= 3 ? " is-complete" : ""}`} aria-hidden="true" />
                  <div className="history-body">
                    <div className="history-top">
                      <h3>{match.product_requirement}</h3>
                      {when && <p className="history-date">{when}</p>}
                    </div>
                    <p className="history-meta">
                      {formatMatchLabel(match.final_score)} · {match.company_name} · {match.location} · qty{" "}
                      {match.quantity} · {historyStatus(match, rfq)}
                    </p>
                    <ol className="history-steps">
                      {HISTORY_STEPS.map((label, index) => (
                        <li className={index <= step ? "is-done" : ""} key={label}>
                          {label}
                        </li>
                      ))}
                    </ol>
                  </div>
                  {rfq ? (
                    <Link className="btn" to={`/rfqs/${rfq.id}`}>
                      View request
                    </Link>
                  ) : (
                    <Link className="btn" to={`/offerings/${offering.id}`}>
                      View details
                    </Link>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </Layout>
  );
}
