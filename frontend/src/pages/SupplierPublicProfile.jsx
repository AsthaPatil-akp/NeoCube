import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError, createRfq, getSupplierProfile } from "../api";
import { formatAverageRating } from "../supplierProfile";

function priceLabel(item) {
  if (item.price_amount != null) {
    const basis =
      item.price_basis === "PER_UNIT" ? "per unit" : item.price_basis === "TOTAL" ? "total" : item.price_basis;
    return `${item.price_amount}${item.price_currency ? ` ${item.price_currency}` : ""}${basis ? ` · ${basis}` : ""}`;
  }
  return item.pricing_details || "—";
}

function stars(value) {
  const rating = Number(value) || 0;
  return "★".repeat(rating) + "☆".repeat(Math.max(0, 5 - rating));
}

export default function SupplierPublicProfile() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const matchId = params.get("match");
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSupplierProfile(id)
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load supplier profile");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function sendRequest() {
    if (!matchId) return;
    setError("");
    setSending(true);
    try {
      const rfq = await createRfq({ match_id: Number(matchId) });
      navigate(`/rfqs/${rfq.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to send request");
      setSending(false);
    }
  }

  const average = formatAverageRating(profile?.average_rating);

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Supplier</p>
          <h1>{profile?.company_name || "Supplier profile"}</h1>
          {profile && average ? (
            <p className="lede">
              ★ {average} / 5
              {profile.review_count ? ` · Based on ${profile.review_count} review${profile.review_count === 1 ? "" : "s"}` : ""}
            </p>
          ) : (
            profile && <p className="lede">No reviews yet</p>
          )}
          {profile?.categories?.length > 0 && <p className="role-chip">{profile.categories.join(" · ")}</p>}
        </div>
      </section>

      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        <div className="actions-row">
          <button className="btn" type="button" onClick={() => navigate(-1)}>
            Back
          </button>
          {user?.role === "CLIENT" && matchId && (
            <button className="btn" type="button" disabled={sending} onClick={sendRequest}>
              Send Request
            </button>
          )}
        </div>
      </section>

      <section className="featured">
        <div className="section-head">
          <h2>Offerings</h2>
        </div>
        {!profile ? (
          <p className="lede">Loading supplier details.</p>
        ) : profile.offerings.length === 0 ? (
          <p className="lede">No active offerings.</p>
        ) : (
          <div className="card-grid tile-grid">
            {profile.offerings.map((item) => (
              <article className="product-card portal-card tile-card" key={item.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <h3>{item.product_offered}</h3>
                    <p>
                      {item.category_name} · {item.location} · qty {item.available_quantity}
                      {item.quantity_unit ? ` ${item.quantity_unit}` : ""}
                    </p>
                    <dl className="profile-facts">
                      <div>
                        <dt>Price</dt>
                        <dd>{priceLabel(item)}</dd>
                      </div>
                      <div>
                        <dt>Delivery</dt>
                        <dd>{item.delivery_capability || "—"}</dd>
                      </div>
                    </dl>
                    {item.additional_notes && <p>{item.additional_notes}</p>}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="featured">
        <div className="section-head">
          <h2>Client Reviews</h2>
        </div>
        {profile && profile.reviews.length === 0 ? (
          <p className="lede">No reviews yet</p>
        ) : (
          profile && (
            <div className="history-list">
              {profile.reviews.map((item) => (
                <article className="history-item" key={item.id}>
                  <span className="history-mark is-complete" aria-hidden="true" />
                  <div className="history-body">
                    <div className="history-top">
                      <h3>{stars(item.rating)}</h3>
                      <p className="history-date">{item.verified ? "Verified Client" : item.client_name}</p>
                    </div>
                    {item.feedback && <p className="history-meta">{item.feedback}</p>}
                    <p className="history-meta">{item.client_name}</p>
                  </div>
                </article>
              ))}
            </div>
          )
        )}
      </section>
    </Layout>
  );
}
