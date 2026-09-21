import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { portalPath } from "../portalPath";
import { profileInitials } from "../profileDisplay";

export default function Layout({ children }) {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const isAuth = location.pathname === "/login" || location.pathname === "/register";

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className={`page-shell${isHome ? " is-home" : ""}${isAuth ? " is-auth" : ""}`}>
      <header className="site-header">
        <Link to="/" className="brand">
          NeoCube
        </Link>
        <nav className="site-nav">
          <NavLink to="/" end>
            Home
          </NavLink>
          {!loading && user ? (
            <>
              <NavLink to={portalPath(user)}>Dashboard</NavLink>
              {user.role !== "ADMIN" && <NavLink to="/rfqs">Requests</NavLink>}
              {user.role !== "ADMIN" && <NavLink to="/track">Track</NavLink>}
              <NavLink to="/notifications">Notifications</NavLink>
            </>
          ) : (
            <NavLink to="/register">Register</NavLink>
          )}
        </nav>
        <div className="header-actions">
          {!loading && user ? (
            <>
              <NavLink to="/profile" className="profile-icon" aria-label="Profile" title="Profile">
                {user.profile_photo_url ? (
                  <img src={user.profile_photo_url} alt="" />
                ) : (
                  <span>{profileInitials(user.full_name)}</span>
                )}
              </NavLink>
              <button type="button" className="text-btn" onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="btn btn-header">
              Login
            </Link>
          )}
        </div>
      </header>

      <main>{children}</main>

      <footer className="site-footer">
        <div className="footer-grid">
          <div>
            <p className="footer-brand">NeoCube</p>
            <p className="footer-tag">AI-powered client and supplier matching.</p>
          </div>
          <div>
            <p className="footer-heading">Platform</p>
            <Link to="/">Home</Link>
            <Link to="/register">Register</Link>
            <Link to="/login">Login</Link>
          </div>
          <div>
            <p className="footer-heading">Account</p>
            <Link to="/profile">Profile</Link>
            <Link to="/rfqs">Requests</Link>
            <Link to="/track">Track</Link>
            <Link to="/notifications">Notifications</Link>
            <p>Clients and suppliers</p>
          </div>
          <div>
            <p className="footer-heading">Matching</p>
            <p>Requirements, offerings, ranked matches, RFQs, and quotations.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
