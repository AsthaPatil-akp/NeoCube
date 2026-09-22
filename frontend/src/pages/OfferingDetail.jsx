import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { formatMatchLabel, sortByMatchScore } from "../formatMatchScore";
import { ApiError, deactivateOffering, getOffering, updateOffering } from "../api";

export default function OfferingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getOffering(id)
      .then((data) => {
        if (!cancelled) setItem(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load offering");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleDeactivate() {
    setError("");
    try {
      setItem(await deactivateOffering(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to deactivate offering");
    }
  }

  async function setStatus(status) {
    setError("");
    try {
      setItem(await updateOffering(id, { status }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update offering");
    }
  }

  if (!item && !error) {
    return (
      <Layout>
        <p className="status-copy">Loading offering.</p>
      </Layout>
    );
  }

  return (
    <Layout>
      <section className="profile-hero detail-hero">
        <div>
          <p className="eyebrow">Offering</p>
          <h1>{item ? item.product_offered : "Unavailable"}</h1>
          {item && <p className="role-chip">{item.status}</p>}
        </div>
        {item && (
          <dl className="profile-facts kpi-facts">
            <div>
              <dt>Supplier</dt>
              <dd>{item.supplier_name}</dd>
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
                <dt>Available quantity</dt>
                <dd>{item.available_quantity}</dd>
              </div>
              <div>
                <dt>Pricing</dt>
                <dd>
                  {item.price_amount != null
                    ? `${item.price_amount}${item.price_currency ? ` ${item.price_currency}` : ""}${
                        item.price_basis ? ` · ${item.price_basis === "PER_UNIT" ? "per unit" : "total"}` : ""
                      }`
                    : item.pricing_details || "—"}
                </dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{item.location}</dd>
              </div>
              <div>
                <dt>Delivery capability</dt>
                <dd>{item.delivery_capability}</dd>
              </div>
              <div>
                <dt>Notes</dt>
                <dd>{item.additional_notes || "—"}</dd>
              </div>
              <div>
                <dt>Product Image</dt>
                <dd>
                  {item.has_product_image ? (
                    <>
                      {item.product_image_url && (
                        <img
                          src={item.product_image_url}
                          alt="Product"
                          style={{ maxWidth: 160, display: "block", marginBottom: "0.5rem", borderRadius: 8 }}
                        />
                      )}
                      Source:{" "}
                      {item.product_image_source === "DOCUMENT_EXTRACTION"
                        ? "Extracted from Document"
                        : "Direct Upload"}
                    </>
                  ) : (
                    "None"
                  )}
                </dd>
              </div>
            </dl>
            <div className="actions-row">
              {["DRAFT", "ACTIVE", "UNAVAILABLE"].includes(item.status) && (
                <Link className="btn" to={`/offerings/${item.id}/edit`}>
                  Edit
                </Link>
              )}
              {item.status === "ACTIVE" && (
                <button className="btn btn-ghost" type="button" onClick={() => setStatus("UNAVAILABLE")}>
                  Mark unavailable
                </button>
              )}
              {item.status === "UNAVAILABLE" && (
                <button className="btn btn-ghost" type="button" onClick={() => setStatus("ACTIVE")}>
                  Mark active
                </button>
              )}
              {item.status === "ACTIVE" && (
                <button className="btn btn-ghost" type="button" onClick={() => setStatus("EXPIRED")}>
                  Mark expired
                </button>
              )}
              {item.status !== "DEACTIVATED" && item.status !== "EXPIRED" && (
                <button className="btn btn-ghost" type="button" onClick={handleDeactivate}>
                  Deactivate
                </button>
              )}
              {["DEACTIVATED", "EXPIRED"].includes(item.status) && (
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={async () => {
                    if (!window.confirm("Remove this offering from your dashboard?")) return;
                    try {
                      await deactivateOffering(id);
                      navigate("/supplier");
                    } catch (err) {
                      setError(err instanceof ApiError ? err.message : "Unable to delete offering");
                    }
                  }}
                >
                  ✕ Delete
                </button>
              )}
              <button className="text-btn" type="button" onClick={() => navigate("/supplier")}>
                Back to dashboard
              </button>
            </div>
          </>
        )}
      </section>
      {item && item.matches.length > 0 && (
        <section className="featured">
          <div className="section-head">
            <h2>Matching requirements</h2>
          </div>
          <div className="card-grid tile-grid">
            {sortByMatchScore(item.matches).map((match) => (
              <article className="product-card portal-card tile-card" key={match.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <p className="match-score-label">{formatMatchLabel(match.final_score)}</p>
                    <h3>{match.product_requirement}</h3>
                    <p>
                      {match.company_name} · {match.location} · {match.status}
                    </p>
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
