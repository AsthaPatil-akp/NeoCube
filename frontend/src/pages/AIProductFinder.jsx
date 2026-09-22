import { useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { ApiError, getAiProductFinderStatus, searchAiProductFinder } from "../api";
import { formatVisualSimilarity, isAllowedProductImage } from "../aiProductFinder";
import "../components/AIProductFinderCard.css";

export default function AIProductFinder() {
  const navigate = useNavigate();
  const inputId = useId();
  const fileInputRef = useRef(null);
  const [status, setStatus] = useState(null);
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getAiProductFinderStatus()
      .then((payload) => {
        if (cancelled) return;
        if (payload?.enabled === false) {
          navigate("/dashboard", { replace: true });
          return;
        }
        setStatus(payload);
      })
      .catch(() => {
        if (!cancelled) {
          setStatus({
            enabled: true,
            model_available: false,
            message: "Unable to check AI Product Finder status.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function resetResults() {
    setResults(null);
    setError("");
  }

  function clearImage() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl("");
    resetResults();
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function onPickFile(event) {
    const next = event.target.files?.[0];
    if (!next) return;
    if (!isAllowedProductImage(next)) {
      setError("Supported formats: JPG, JPEG, PNG, WEBP (max 5 MB).");
      clearImage();
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(next);
    setPreviewUrl(URL.createObjectURL(next));
    resetResults();
  }

  async function findSuppliers() {
    if (!file) {
      setError("Choose a product image first.");
      return;
    }
    setLoading(true);
    setError("");
    setResults(null);
    try {
      const payload = await searchAiProductFinder(file);
      setResults(payload);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to run AI Product Finder");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <section className="profile-hero">
        <div>
          <p className="eyebrow">Client portal</p>
          <h1 className="page-title">✨ AI Product Finder</h1>
        </div>
      </section>

      <section className="featured ai-product-finder ai-product-finder--page">
        <p className="lede">
          Find suppliers using a product image. Our computer-vision model analyzes the image and ranks
          suppliers by visual similarity. This is separate from requirement-based match scores.
        </p>

        {status && !status.model_available && (
          <p className="banner banner-error">
            {status.message || "The AI Product Finder model is currently unavailable."}
          </p>
        )}

        <div className="ai-product-finder__upload">
          <label htmlFor={inputId}>Upload Product Image</label>
          <input
            id={inputId}
            ref={fileInputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            onChange={onPickFile}
          />
          <p className="ai-product-finder__hint">Supported: JPG / JPEG / PNG / WEBP</p>
          {previewUrl && (
            <div className="ai-product-finder__preview">
              <img src={previewUrl} alt="Selected product preview" />
              <button className="btn btn-ghost" type="button" onClick={clearImage}>
                Remove image
              </button>
            </div>
          )}
          <div className="actions-row">
            <button
              className="btn"
              type="button"
              disabled={loading || !file || (status && !status.model_available)}
              onClick={findSuppliers}
            >
              {loading ? "Finding suppliers…" : "Find Suppliers"}
            </button>
            <Link className="btn btn-ghost" to="/dashboard">
              Back to dashboard
            </Link>
          </div>
        </div>

        {error && <p className="banner banner-error">{error}</p>}

        {results && (
          <div className="ai-product-finder__results">
            <h2>AI Product Finder Results</h2>
            {previewUrl && (
              <div className="ai-product-finder__preview">
                <img src={previewUrl} alt="Uploaded product" />
              </div>
            )}
            {results.message && <p className="lede">{results.message}</p>}
            {!results.message && (
              <p className="lede">{results.result_count} visually similar suppliers found.</p>
            )}
            <div className="card-grid tile-grid">
              {(results.results || []).map((item) => (
                <article className="product-card portal-card tile-card" key={item.offering_id}>
                  <div className="product-copy">
                    <div className="tile-text">
                      <p className="match-score-label">
                        Visual Similarity {formatVisualSimilarity(item.visual_similarity)}
                      </p>
                      <h3>{item.supplier_name}</h3>
                      <p>
                        {item.product_offered} · {item.category_name} · {item.location} · Qty{" "}
                        {item.available_quantity}
                        {item.quantity_unit ? ` ${item.quantity_unit}` : ""}
                      </p>
                    </div>
                    <Link className="btn" to={`/suppliers/${item.supplier_id}`}>
                      View Supplier
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </Layout>
  );
}
