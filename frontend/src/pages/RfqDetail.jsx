import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { formatMatchScore } from "../formatMatchScore";
import { ApiError, acceptRfq, createQuotation, getRfq, rejectRfq } from "../api";

export default function RfqDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    unit_price: "",
    quantity: "",
    shipping: "0",
    tax: "0",
    additional_charges: "0",
    delivery: "",
    validity_days: "14",
    payment_terms: "Net 30",
    notes: "",
  });

  useEffect(() => {
    let cancelled = false;
    getRfq(id)
      .then((data) => {
        if (!cancelled) {
          setItem(data);
          setForm((current) => ({ ...current, quantity: data.quotations[0]?.quantity || data.quantity || current.quantity }));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load RFQ");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleQuote(event) {
    event.preventDefault();
    setError("");
    try {
      await createQuotation(id, {
        unit_price: Number(form.unit_price),
        quantity: Number(form.quantity),
        shipping: Number(form.shipping),
        tax: Number(form.tax),
        additional_charges: Number(form.additional_charges),
        delivery: form.delivery,
        validity_days: Number(form.validity_days),
        payment_terms: form.payment_terms,
        notes: form.notes.trim() || null,
      });
      setItem(await getRfq(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to submit quotation");
    }
  }

  async function handleDecision(action) {
    setError("");
    setBusy(true);
    try {
      setItem(action === "accept" ? await acceptRfq(item.id) : await rejectRfq(item.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : action === "accept" ? "Unable to accept request" : "Unable to decline request");
    } finally {
      setBusy(false);
    }
  }

  if (!item && !error) {
    return (
      <Layout>
        <p className="status-copy">Loading RFQ.</p>
      </Layout>
    );
  }

  const supplierCanDecide = user?.role === "SUPPLIER" && item && ["SENT", "VIEWED"].includes(item.status);
  const supplierCanQuote =
    user?.role === "SUPPLIER" &&
    item &&
    !["RESPONDED", "ACCEPTED", "PAID", "SHIPPED", "RECEIVED", "REJECTED", "CANCELLED", "EXPIRED"].includes(item.status);

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">RFQ</p>
          <h1>{item ? item.product_requirement || item.product_offered : "Unavailable"}</h1>
          {item && <p className="role-chip">{item.status}</p>}
        </div>
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {item && (
          <dl className="profile-facts">
            <div>
              <dt>Client</dt>
              <dd>{item.client_name || "—"}</dd>
            </div>
            <div>
              <dt>Supplier</dt>
              <dd>{item.supplier_name || "—"}</dd>
            </div>
            <div>
              <dt>Category</dt>
              <dd>{item.category_name || "—"}</dd>
            </div>
            <div>
              <dt>Quantity</dt>
              <dd>{item.quantity != null ? item.quantity : "—"}</dd>
            </div>
            <div>
              <dt>Budget</dt>
              <dd>
                {item.budget != null ? item.budget : "—"}
                {item.budget_currency ? ` ${item.budget_currency}` : ""}
              </dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>{item.location || "—"}</dd>
            </div>
            <div>
              <dt>Delivery</dt>
              <dd>{item.delivery_timeline || "—"}</dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>{item.additional_notes || item.notes || "—"}</dd>
            </div>
            <div>
              <dt>Match score</dt>
              <dd>{formatMatchScore(item.match_score)}</dd>
            </div>
          </dl>
        )}
        {item && item.quotations.length > 0 && (
          <div className="card-grid tile-grid">
            {item.quotations.map((quote) => (
              <article className="product-card portal-card tile-card" key={quote.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <h3>Quotation {quote.id}</h3>
                    <p>
                      Total {quote.total} · unit {quote.unit_price} · qty {quote.quantity} · {quote.status}
                    </p>
                    <p>
                      Subtotal {quote.subtotal} · shipping {quote.shipping} · tax {quote.tax}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
        {supplierCanDecide && (
          <div className="actions-row">
            <button className="btn" type="button" disabled={busy} onClick={() => handleDecision("accept")}>
              Accept
            </button>
            <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => handleDecision("reject")}>
              Decline
            </button>
          </div>
        )}
        {supplierCanQuote && (
          <form className="stack-form compact-form" onSubmit={handleQuote}>
            <div className="form-grid">
              <label>
                Unit price
                <input
                  type="number"
                  min="1"
                  value={form.unit_price}
                  onChange={(event) => setForm({ ...form, unit_price: event.target.value })}
                  required
                />
              </label>
              <label>
                Quantity
                <input
                  type="number"
                  min="1"
                  value={form.quantity}
                  onChange={(event) => setForm({ ...form, quantity: event.target.value })}
                  required
                />
              </label>
              <label>
                Shipping
                <input
                  type="number"
                  min="0"
                  value={form.shipping}
                  onChange={(event) => setForm({ ...form, shipping: event.target.value })}
                />
              </label>
              <label>
                Tax
                <input
                  type="number"
                  min="0"
                  value={form.tax}
                  onChange={(event) => setForm({ ...form, tax: event.target.value })}
                />
              </label>
              <label>
                Additional charges
                <input
                  type="number"
                  min="0"
                  value={form.additional_charges}
                  onChange={(event) => setForm({ ...form, additional_charges: event.target.value })}
                />
              </label>
              <label>
                Delivery
                <input
                  value={form.delivery}
                  onChange={(event) => setForm({ ...form, delivery: event.target.value })}
                  required
                />
              </label>
              <label>
                Validity days
                <input
                  type="number"
                  min="1"
                  value={form.validity_days}
                  onChange={(event) => setForm({ ...form, validity_days: event.target.value })}
                  required
                />
              </label>
              <label>
                Payment terms
                <input
                  value={form.payment_terms}
                  onChange={(event) => setForm({ ...form, payment_terms: event.target.value })}
                  required
                />
              </label>
            </div>
            <button className="btn" type="submit">
              Submit quotation →
            </button>
          </form>
        )}
        {item && user.role === "CLIENT" && item.status === "RESPONDED" && (
          <div className="actions-row">
            <button
              className="btn"
              type="button"
              onClick={async () => {
                try {
                  setItem(await acceptRfq(item.id));
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : "Unable to accept RFQ");
                }
              }}
            >
              Accept quotation →
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={async () => {
                try {
                  setItem(await rejectRfq(item.id));
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : "Unable to reject RFQ");
                }
              }}
            >
              Reject
            </button>
          </div>
        )}
        <div className="actions-row">
          {item?.supplier_id && user.role === "CLIENT" && (
            <Link className="btn" to={`/suppliers/${item.supplier_id}`}>
              View Supplier Profile
            </Link>
          )}
          <button className="text-btn" type="button" onClick={() => navigate(user.role === "SUPPLIER" ? "/supplier" : "/dashboard")}>
            Back to dashboard
          </button>
        </div>
      </section>
    </Layout>
  );
}
