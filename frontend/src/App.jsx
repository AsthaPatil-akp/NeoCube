import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./AuthContext";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Notifications from "./pages/Notifications";
import ProtectedRoute from "./pages/ProtectedRoute";
import Register from "./pages/Register";
import RoleRoute from "./pages/RoleRoute";
import ClientDashboard from "./pages/ClientDashboard";
import AIProductFinder from "./pages/AIProductFinder";
import RequirementForm from "./pages/RequirementForm";
import RequirementDetail from "./pages/RequirementDetail";
import SupplierDashboard from "./pages/SupplierDashboard";
import OfferingForm from "./pages/OfferingForm";
import OfferingDetail from "./pages/OfferingDetail";
import AdminDashboard from "./pages/AdminDashboard";
import RfqList from "./pages/RfqList";
import RfqDetail from "./pages/RfqDetail";
import Track from "./pages/Track";
import SupplierPublicProfile from "./pages/SupplierPublicProfile";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/profile" element={<Profile />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/suppliers/:id" element={<SupplierPublicProfile />} />
          </Route>
          <Route element={<RoleRoute roles={["CLIENT"]} />}>
            <Route path="/dashboard" element={<ClientDashboard />} />
            <Route path="/ai-product-finder" element={<AIProductFinder />} />
            <Route path="/requirements/new" element={<RequirementForm />} />
            <Route path="/requirements/:id" element={<RequirementDetail />} />
            <Route path="/requirements/:id/edit" element={<RequirementForm />} />
          </Route>
          <Route element={<RoleRoute roles={["SUPPLIER"]} />}>
            <Route path="/supplier" element={<SupplierDashboard />} />
            <Route path="/offerings/new" element={<OfferingForm />} />
            <Route path="/offerings/:id" element={<OfferingDetail />} />
            <Route path="/offerings/:id/edit" element={<OfferingForm />} />
          </Route>
          <Route element={<RoleRoute roles={["CLIENT", "SUPPLIER"]} />}>
            <Route path="/rfqs" element={<RfqList />} />
            <Route path="/rfqs/:id" element={<RfqDetail />} />
            <Route path="/track" element={<Track />} />
          </Route>
          <Route element={<RoleRoute roles={["ADMIN"]} />}>
            <Route path="/admin" element={<AdminDashboard />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
