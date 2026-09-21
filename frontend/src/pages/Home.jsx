import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";

export default function Home() {
  const { user } = useAuth();

  return (
    <Layout>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Clients · Suppliers · AI matching</p>
          <h1>
            Find the
            <br />
            right partner.
          </h1>
          <p className="kicker">A web platform that connects clients with suitable suppliers using AI-powered matching.</p>
          {user ? (
            <Link to="/profile" className="btn">
              View profile →
            </Link>
          ) : (
            <Link to="/register" className="btn">
              Create an account →
            </Link>
          )}
          <p className="hero-meta">Register · Profile · Match</p>
        </div>
        <div className="hero-photo">
          <img
            src="https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=1600&q=80"
            alt="Team collaborating in a bright office"
          />
        </div>
      </section>

      <section className="band">
        <p className="band-aside">Clients Suppliers Matching</p>
        <h2>Built for better partnerships.</h2>
        <p className="band-copy">
          Start with a secure account. Publish a requirement or offering and the matching engine ranks eligible partners in the database.
        </p>
      </section>

      <section className="featured">
        <div className="section-head">
          <p className="eyebrow">How it works</p>
          <Link to={user ? "/profile" : "/register"}>Get started →</Link>
        </div>
        <div className="card-grid">
          <article className="product-card">
            <img
              src="https://images.unsplash.com/photo-1600880292203-757bb62b4baf?auto=format&fit=crop&w=900&q=80"
              alt="Client team in a business meeting"
            />
            <div className="product-copy">
              <h3>For clients</h3>
              <p>Submit a product requirement. Eligible suppliers are ranked with scores, explanations, and RFQ follow-up.</p>
            </div>
          </article>
          <article className="product-card">
            <img
              src="https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=900&q=80"
              alt="Supplier warehouse and logistics"
            />
            <div className="product-copy">
              <h3>For suppliers</h3>
              <p>Publish what you can supply. Active offerings feed matching, notifications, and the RFQ workflow.</p>
            </div>
          </article>
          <article className="product-card">
            <img
              src="https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=900&q=80"
              alt="Updating a company profile on a laptop"
            />
            <div className="product-copy">
              <h3>Your account</h3>
              <p>Sign in, update your details, and stay authenticated across the matching platform.</p>
            </div>
          </article>
        </div>
      </section>

      <section className="split">
        <div className="split-copy">
          <p className="eyebrow">AI matching</p>
          <h2>
            Made
            <br />
            to connect.
          </h2>
          <p>
            NeoCube matches clients with eligible suppliers using structured constraints, semantic embeddings, and a trained compatibility model.
          </p>
          <Link to={user ? "/profile" : "/register"} className="btn btn-ghost">
            {user ? "Go to profile →" : "Join as client or supplier →"}
          </Link>
        </div>
        <div className="split-photo">
          <img
            src="https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=1400&q=80"
            alt="Handshake between business partners"
          />
        </div>
      </section>
    </Layout>
  );
}
