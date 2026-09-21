import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { formatMatchLabel, sortByMatchScore } from "../formatMatchScore";
import { canSendMatchRequest } from "../matchRequest";
import { ApiError, cancelRequirement, createRfq, getRequirement, updateRequirement } from "../api";

function priceLabel(match) {
  if (match.price_amount != null) {
    const basis = match.price_basis === "PER_UNIT" ? "per unit" : match.price_basis === "TOTAL" ? "total" : match.price_basis;
    return `${match.price_amount}${match.price_currency ? ` ${match.price_currency}` : ""}${basis ? ` · ${basis}` : ""}`;
  }
  return match.pricing_details || "—";
}

export default function RequirementDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [sendingId, setSendingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getRequirement(id)
      .then((data) => {
        if (!cancelled) setItem(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load requirement");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleCancel() {
    setError("");
    try {
      const updated = await cancelRequirement(id);
      setItem(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to cancel requirement");
    }
  }

  async function setStatus(status) {
    setError("");
    try {
      setItem(await updateRequirement(id, { status }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update requirement");
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

  if (!item && !error) {
    return (
      <Layout>
        <p className="status-copy">Loading requirement.</p>
      </Layout>
    );
  }

  return (
    <Layout>
      <section className="profile-hero detail-hero">
        <div>
          <p className="eyebrow">Requirement</p>
          <h1>{item ? item.product_requirement : "Unavailable"}</h1>
          {item && <p className="role-chip">{item.status}</p>}
        </div>
        {item && (
          <dl className="profile-facts kpi-facts">
            <div>
              <dt>Company</dt>
              <dd>{item.company_name}</dd>
            </div>
            <div>
              <dt>Category</dt>
              <dd>{item.category_name}</dd>
            </div>
            <div>
              <dt>Matches</dt>
              <dd>{item.match_count}</dd>
            </div>
          </dl>
        )}
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {item && (
          <>
            <dl className="profile-facts">
              <div>
                <dt>Quantity</dt>
                <dd>{item.quantity}</dd>
              </div>
              <div>
                <dt>Budget</dt>
                <dd>
                  {item.budget}
                  {item.budget_currency ? ` ${item.budget_currency}` : ""}
                  {item.budget_basis ? ` · ${item.budget_basis === "PER_UNIT" ? "per unit" : "total"}` : ""}
                </dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{item.location}</dd>
              </div>
              <div>
                <dt>Delivery timeline</dt>
                <dd>{item.delivery_timeline}</dd>
              </div>
              <div>
                <dt>Notes</dt>
                <dd>{item.additional_notes || "—"}</dd>
              </div>
            </dl>
            <div className="actions-row">
              {["DRAFT", "SUBMITTED", "PROCESSING"].includes(item.status) && (
                <Link className="btn" to={`/requirements/${item.id}/edit`}>
                  Edit
                </Link>
              )}
              {item.status === "MATCHED" && (
                <button className="btn btn-ghost" type="button" onClick={() => setStatus("RFQ_SENT")}>
                  Mark RFQ sent
                </button>
              )}
              {["MATCHED", "RFQ_SENT"].includes(item.status) && (
                <button className="btn btn-ghost" type="button" onClick={() => setStatus("CLOSED")}>
                  Close requirement
                </button>
              )}
              {!["CLOSED", "CANCELLED"].includes(item.status) && (
                <button className="btn btn-ghost" type="button" onClick={handleCancel}>
                  Cancel requirement
                </button>
              )}
              {["CLOSED", "CANCELLED"].includes(item.status) && (
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={async () => {
                    if (!window.confirm("Remove this requirement from your dashboard?")) return;
                    try {
                      await cancelRequirement(id);
                      navigate("/dashboard");
                    } catch (err) {
                      setError(err instanceof ApiError ? err.message : "Unable to delete requirement");
                    }
                  }}
                >
                  ✕ Delete
                </button>
              )}
              <button className="text-btn" type="button" onClick={() => navigate("/dashboard")}>
                Back to dashboard
              </button>
            </div>
          </>
        )}
      </section>
      {item && item.matches.length > 0 && (
        <section className="featured">
          <div className="section-head">
            <h2>Matches</h2>
          </div>
          <div className="card-grid tile-grid">
            {sortByMatchScore(item.matches).map((match) => (
              <article className="product-card portal-card tile-card" key={match.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <p className="match-score-label">{formatMatchLabel(match.final_score)}</p>
                    <h3>{match.product_offered}</h3>
                    <p>
                      {match.supplier_name} · {match.location} · {match.rfq_status || match.match_status}
                    </p>
                    {match.explanation?.length > 0 && <p>{match.explanation.join(" · ")}</p>}
                    {expandedId === match.id && (
                      <dl className="profile-facts">
                        <div>
                          <dt>Category</dt>
                          <dd>{match.category_name || "—"}</dd>
                        </div>
                        <div>
                          <dt>Available quantity</dt>
                          <dd>
                            {match.available_quantity != null ? match.available_quantity : "—"}
                            {match.quantity_unit ? ` ${match.quantity_unit}` : ""}
                          </dd>
                        </div>
                        <div>
                          <dt>Price</dt>
                          <dd>{priceLabel(match)}</dd>
                        </div>
                        <div>
                          <dt>Delivery</dt>
                          <dd>{match.delivery_capability || "—"}</dd>
                        </div>
                        <div>
                          <dt>Status</dt>
                          <dd>{match.rfq_status || match.match_status}</dd>
                        </div>
                      </dl>
                    )}
                  </div>
                  <div className="actions-row">
                    <button
                      className="btn"
                      type="button"
                      onClick={() => setExpandedId((current) => (current === match.id ? null : match.id))}
                    >
                      View details
                    </button>
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
        </section>
      )}
    </Layout>
  );
}
