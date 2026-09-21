import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { ApiError, getNotifications } from "../api";
import { notificationHref } from "../matchRequest";

export default function Notifications() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getNotifications()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load notifications");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Inbox</p>
          <h1 className="page-title">Notifications</h1>
        </div>
        <dl className="profile-facts kpi-facts">
          <div>
            <dt>Notifications</dt>
            <dd>{items.length}</dd>
          </div>
        </dl>
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {items.length === 0 ? (
          <p className="lede">No notifications yet.</p>
        ) : (
          <div className="card-grid tile-grid">
            {items.map((item) => {
              const href = notificationHref(item);
              return (
                <article className="product-card portal-card tile-card" key={item.id}>
                  <div className="product-copy">
                    <div className="tile-text">
                      <h3>{item.title}</h3>
                      <p>{item.message}</p>
                    </div>
                    {href ? (
                      <Link className="btn" to={href}>
                        View details
                      </Link>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </Layout>
  );
}
