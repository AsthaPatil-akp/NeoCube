import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../AuthContext";
import Layout from "../components/Layout";

export default function RoleRoute({ roles }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <Layout>
        <p className="status-copy">Loading your account.</p>
      </Layout>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!roles.includes(user.role)) {
    return <Navigate to="/profile" replace />;
  }

  return <Outlet />;
}
