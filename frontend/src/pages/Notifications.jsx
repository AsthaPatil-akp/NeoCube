import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { ApiError, clearAllNotifications, clearSelectedNotifications, getNotifications } from "../api";
import { notificationHref } from "../matchRequest";

export default function Notifications() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getNotifications()
      .then((data) => {
        if (!cancelled) {
          setItems(data);
          setSelected(new Set());
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load notifications");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleOne(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function clearSelected() {
    if (!selected.size) {
      setError("Select at least one notification to clear.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const ids = [...selected];
      await clearSelectedNotifications(ids);
      setItems((current) => current.filter((item) => !selected.has(item.id)));
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to clear selected notifications");
    } finally {
      setBusy(false);
    }
  }

  async function clearAll() {
    if (!items.length) return;
    setError("");
    setBusy(true);
    try {
      await clearAllNotifications();
      setItems([]);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to clear notifications");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Inbox</p>
          <h1 className="page-title">Notifications</h1>
          {items.length > 0 && (
            <div className="actions-row notification-clear-actions">
              <button className="btn btn-clear" type="button" disabled={busy || !selected.size} onClick={clearSelected}>
                Clear selected
              </button>
              <button className="btn btn-clear" type="button" disabled={busy} onClick={clearAll}>
                Clear all
              </button>
            </div>
          )}
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
              const checked = selected.has(item.id);
              return (
                <article className="product-card portal-card tile-card" key={item.id}>
                  <div className="product-copy">
                    <label className="notification-select">
                      <input type="checkbox" checked={checked} onChange={() => toggleOne(item.id)} />
                      <span className="tile-text">
                        <h3>{item.title}</h3>
                        <p>{item.message}</p>
                      </span>
                    </label>
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
