import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import AIProductFinderCard from "../components/AIProductFinderCard";
import { useAuth } from "../AuthContext";
import { formatMatchLabel, sortByMatchScore } from "../formatMatchScore";
import MatchExplain from "../components/MatchExplain";
import { canSendMatchRequest } from "../matchRequest";
import { supplierProfilePath } from "../supplierProfile";
import { ApiError, cancelRequirement, createRfq, getNotifications, getRequirements } from "../api";

function clearedMatchKey(userId) {
  return `neocube.clientMatchesCleared.${userId}`;
}

function loadClearedMatchIds(userId) {
  if (!userId) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(clearedMatchKey(userId)) || "[]");
    return Array.isArray(parsed) ? parsed.map(Number).filter(Number.isFinite) : [];
  } catch {
    return [];
  }
}

function groupMatchesByRequirement(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = row.requirement.id;
    if (!groups.has(key)) {
      groups.set(key, {
        requirement: row.requirement,
        rows: [],
      });
    }
    groups.get(key).rows.push(row);
  }
  return [...groups.values()].map((group) => ({
    ...group,
    rows: sortByMatchScore(group.rows, (row) => row.match.final_score),
  }));
}

export default function ClientDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [requirements, setRequirements] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [error, setError] = useState("");
  const [sendingId, setSendingId] = useState(null);
  const [clearedMatchIds, setClearedMatchIds] = useState(() => loadClearedMatchIds(user?.id));

  useEffect(() => {
    setClearedMatchIds(loadClearedMatchIds(user?.id));
  }, [user?.id]);

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
  const clearedIdSet = new Set(clearedMatchIds);
  const supplierMatches = requirements.flatMap((item) =>
    (item.matches || [])
      .filter((match) => !clearedIdSet.has(Number(match.id)))
      .map((match) => ({ requirement: item, match })),
  );
  const matchGroups = groupMatchesByRequirement(supplierMatches);

  function clearMatches() {
    if (supplierMatches.length === 0) return;
    if (!window.confirm("Clear matches from this dashboard? New matches will still appear.")) return;
    const next = [...new Set([...clearedMatchIds, ...supplierMatches.map((row) => Number(row.match.id))])];
    localStorage.setItem(clearedMatchKey(user.id), JSON.stringify(next));
    setClearedMatchIds(next);
  }

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
      <section className="profile-hero client-dashboard-hero">
        <div className="client-dashboard-hero__head">
          <div>
            <p className="eyebrow">Client portal</p>
            <div className="client-dashboard-hero__title-row">
              <h1>{user.company_name || user.full_name}</h1>
              <AIProductFinderCard placement="hero" />
            </div>
            <p className="role-chip">{user.role}</p>
          </div>
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
          {supplierMatches.length > 0 && (
            <button className="btn btn-clear" type="button" onClick={clearMatches}>
              Clear history
            </button>
          )}
        </div>
        {supplierMatches.length === 0 ? (
          <p className="lede">No supplier matches yet.</p>
        ) : (
          <div className="match-history-groups">
            {matchGroups.map((group) => (
              <div className="match-history-group" key={group.requirement.id}>
                <h3 className="match-history-group__title">{group.requirement.product_requirement}</h3>
                <p className="match-history-group__lede">
                  {group.rows.length} {group.rows.length === 1 ? "match" : "matches"} for this requirement
                </p>
                <div className="card-grid tile-grid">
                  {group.rows.map(({ requirement, match }) => (
                    <article className="product-card portal-card tile-card" key={`${requirement.id}-${match.id}`}>
                      <div className="product-copy">
                        <div className="tile-text">
                          <MatchExplain
                            score={match.final_score}
                            reasons={match.explanation}
                            semanticScore={match.semantic_score}
                          />
                          <h3>{match.product_offered}</h3>
                          <p>
                            {match.supplier_name} · {match.location} · {match.rfq_status || match.match_status}
                          </p>
                        </div>
                        <div className="actions-row">
                          {supplierProfilePath(match.supplier_id, match) && (
                            <Link className="btn" to={supplierProfilePath(match.supplier_id, match)}>
                              View Supplier Profile
                            </Link>
                          )}
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
              </div>
            ))}
          </div>
        )}
      </section>
    </Layout>
  );
}
