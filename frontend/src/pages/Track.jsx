import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { ApiError, getRfqs, markRfqPaid, markRfqShipped, refreshRfqOtp, verifyRfqOtp } from "../api";
import { isTrackable, nextTrackAction, sortTrackItems, TRACK_STEPS, trackStatus, trackStepIndex } from "../trackFlow";

export default function Track() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [otpById, setOtpById] = useState({});
  const isSupplier = user.role === "SUPPLIER";
  const tracked = sortTrackItems(items.filter((item) => isTrackable(trackStatus(item))));

  useEffect(() => {
    let cancelled = false;
    getRfqs()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Unable to load tracking");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function replaceItem(updated) {
    setItems((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
  }

  async function run(item, task) {
    setError("");
    setBusyId(item.id);
    try {
      replaceItem(await task());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update tracking");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">{isSupplier ? "Supplier portal" : "Client portal"}</p>
          <h1 className="page-title">Track</h1>
        </div>
        <dl className="profile-facts kpi-facts">
          <div>
            <dt>Orders</dt>
            <dd>{tracked.length}</dd>
          </div>
        </dl>
      </section>
      <section className="featured">
        {error && <p className="banner banner-error">{error}</p>}
        {tracked.length === 0 ? (
          <p className="lede">No accepted requests to track yet.</p>
        ) : (
          <div className="history-list">
            {tracked.map((item) => {
              const status = trackStatus(item);
              const step = trackStepIndex(status);
              const action = nextTrackAction(status, user.role);
              const tracking = item.tracking || {};
              const completed = tracking.completed || step >= 3;
              return (
                <article className="history-item" key={item.id}>
                  <span className={`history-mark${completed ? " is-complete" : ""}`} aria-hidden="true" />
                  <div className="history-body">
                    <div className="history-top">
                      <h3>{item.product_requirement || item.product_offered || `Request ${item.id}`}</h3>
                      <p className="history-date">{completed ? "COMPLETED" : status}</p>
                    </div>
                    <p className="history-meta">
                      {isSupplier ? item.client_name || "Client" : item.supplier_name || "Supplier"}
                      {item.location ? ` · ${item.location}` : ""}
                      {item.quantity != null ? ` · qty ${item.quantity}` : ""}
                    </p>
                    <ol className="track-flow">
                      {TRACK_STEPS.map((label, index) => (
                        <li className={index <= step ? "is-done" : ""} key={label}>
                          {label}
                        </li>
                      ))}
                    </ol>
                    {step === 0 && !isSupplier && (
                      <p className="history-meta">Demo Payment — No real money will be charged.</p>
                    )}
                    {step === 1 && isSupplier && (
                      <p className="history-meta">Demo Shipment — Shipping simulation for demonstration.</p>
                    )}
                    {tracking.shipment_code && (
                      <p className="history-meta">Demo shipment {tracking.shipment_code}</p>
                    )}
                    {step === 2 && !isSupplier && tracking.demo_otp && (
                      <p className="history-meta">Demo OTP — Use this code to confirm receipt: {tracking.demo_otp}</p>
                    )}
                    {tracking.otp_expired && !isSupplier && (
                      <p className="history-meta">OTP has expired. Please generate a new OTP.</p>
                    )}
                    {completed && <p className="banner banner-success">Order completed.</p>}
                    <div className="actions-row">
                      <Link className="btn" to={`/rfqs/${item.id}`}>
                        View request
                      </Link>
                      {action && (
                        <button
                          className="btn"
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() =>
                            run(item, () => (action.method === "pay" ? markRfqPaid(item.id) : markRfqShipped(item.id)))
                          }
                        >
                          {action.label}
                        </button>
                      )}
                      {step === 2 && !isSupplier && !completed && (
                        <>
                          <input
                            value={otpById[item.id] || ""}
                            onChange={(event) => setOtpById((current) => ({ ...current, [item.id]: event.target.value }))}
                            placeholder="Enter OTP"
                            inputMode="numeric"
                            maxLength={6}
                            aria-label="Enter OTP"
                          />
                          <button
                            className="btn"
                            type="button"
                            disabled={busyId === item.id}
                            onClick={() => run(item, () => verifyRfqOtp(item.id, otpById[item.id] || ""))}
                          >
                            Verify OTP
                          </button>
                          {tracking.otp_expired && (
                            <button
                              className="btn btn-ghost"
                              type="button"
                              disabled={busyId === item.id}
                              onClick={() => run(item, () => refreshRfqOtp(item.id))}
                            >
                              Generate new OTP
                            </button>
                          )}
                        </>
                      )}
                    </div>
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
