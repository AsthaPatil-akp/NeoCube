import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAiProductFinderStatus } from "../api";
import "./AIProductFinderCard.css";

/** Dashboard launch control — opens AI Product Finder on its own page. */
export default function AIProductFinderCard({ placement = "default" }) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getAiProductFinderStatus()
      .then((payload) => {
        if (!cancelled && payload?.enabled === false) setVisible(false);
      })
      .catch(() => {
        /* Keep the button visible; the page reports status honestly. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible) return null;

  return (
    <div className={`ai-product-finder${placement === "hero" ? " ai-product-finder--hero" : ""}`}>
      <div className="ai-product-finder__launch">
        <Link className="btn" to="/ai-product-finder">
          ✨ AI Product Finder
        </Link>
      </div>
    </div>
  );
}
