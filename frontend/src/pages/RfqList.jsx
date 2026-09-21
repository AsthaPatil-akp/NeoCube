import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { formatMatchScore } from "../formatMatchScore";
import { ApiError, getRfqs } from "../api";

export default function RfqList() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const isSupplier = user.role === "SUPPLIER";

  useEffect(() => {
    let cancelled = false;
    getRfqs()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load requests");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">{isSupplier ? "Supplier portal" : "Client portal"}</p>
          <h1 className="page-title">Requests</h1>
        </div>
        <dl className="profile-facts kpi-facts">
          <div>
            <dt>Requests</dt>
            <dd>{items.length}</dd>
          </div>
        </dl>
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {items.length === 0 ? (
          <p className="lede">{isSupplier ? "No client requests yet." : "No supplier requests yet."}</p>
        ) : (
          <div className="card-grid tile-grid">
            {items.map((item) => (
              <article className="product-card portal-card tile-card" key={item.id}>
                <div className="product-copy">
                  <div className="tile-text">
                    <h3>{item.product_requirement || item.product_offered || `Request ${item.id}`}</h3>
                    <p>
                      {isSupplier ? (
                        <>
                          {item.client_name || "Client"} · {item.category_name || "—"} · qty {item.quantity ?? "—"}
                          {item.budget != null
                            ? ` · budget ${item.budget}${item.budget_currency ? ` ${item.budget_currency}` : ""}`
                            : ""}
                          {item.location ? ` · ${item.location}` : ""} · {item.status}
                        </>
                      ) : (
                        <>
                          {item.supplier_name || "Supplier"} · {item.status}
                          {item.match_score != null ? ` · score ${formatMatchScore(item.match_score)}` : ""}
                        </>
                      )}
                    </p>
                  </div>
                  <Link className="btn" to={`/rfqs/${item.id}`}>
                    View request
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </Layout>
  );
}
