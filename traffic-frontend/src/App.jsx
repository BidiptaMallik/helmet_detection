import { Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./AuthContext.jsx";
import { getRoleHome } from "./authUtils.js";
import { useAuth } from "./useAuth.js";
import Navbar from "./components/Navbar.jsx";
import Loader from "./components/Loader.jsx";

import Welcome from "./pages/Welcome.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import MultiStream from "./pages/MultiStream.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import NewReport from "./pages/NewReport.jsx";
import AdminReports from "./pages/AdminReports.jsx";
import AdminCreateAccount from "./pages/AdminCreateAccount.jsx";

export default function App() {
  return (
    <AuthProvider>
      <Application />
    </AuthProvider>
  );
}

function RoleRoute({ role, children }) {
  const { user } = useAuth();
  if (!user) {
    return <Navigate to={role === "admin" ? "/admin/login" : "/login"} replace />;
  }
  if (user.role !== role) {
    return <Navigate to={getRoleHome(user)} replace />;
  }
  return children;
}

function Application() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return <Loader label="Checking your account..." />;
  }

  return (
    <div className="min-h-screen flex flex-col">

      <Navbar user={user} onLogout={logout} />

      <main className="flex-1">

        <Routes>
          <Route path="/" element={<Navigate to={user ? getRoleHome(user) : "/login"} replace />} />
          <Route path="/login" element={user ? <Navigate to={getRoleHome(user)} replace /> : <Login />} />
          <Route path="/admin/login" element={user ? <Navigate to={getRoleHome(user)} replace /> : <Login adminOnly />} />
          <Route path="/admin/register" element={user ? <Navigate to={getRoleHome(user)} replace /> : <AdminCreateAccount />} />
          <Route path="/register" element={user ? <Navigate to={getRoleHome(user)} replace /> : <Register />} />
          <Route path="/report" element={<RoleRoute role="user"><NewReport /></RoleRoute>} />
          <Route path="/welcome" element={<RoleRoute role="admin"><Welcome /></RoleRoute>} />
          <Route path="/dashboard" element={<RoleRoute role="admin"><Dashboard /></RoleRoute>} />
          <Route path="/multistream" element={<RoleRoute role="admin"><MultiStream /></RoleRoute>} />
          <Route path="/admin/reports" element={<RoleRoute role="admin"><AdminReports /></RoleRoute>} />
          <Route path="*" element={<Navigate to={user ? getRoleHome(user) : "/login"} replace />} />
        </Routes>

      </main>

      <footer className="border-t border-line py-6 text-center font-mono text-[11px] text-muted">
        Traffic · rider safety · waste · road conditions
      </footer>

    </div>
  );
}