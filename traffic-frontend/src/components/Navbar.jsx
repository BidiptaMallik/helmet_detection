import { NavLink } from "react-router-dom";
import { LogOut } from "lucide-react";

const linkClass = ({ isActive }) =>
  `px-3 py-1.5 text-sm font-medium rounded-full transition-colors ${
    isActive
      ? "bg-safe/10 text-safe"
      : "text-muted hover:text-ink"
  }`;

const ADMIN_LINKS = [
  ["/welcome", "Home"],
  ["/dashboard", "Overview"],
  ["/multistream", "Multiple videos"],
  ["/admin/reports", "Reports"],
];

export default function Navbar({ user, onLogout }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-base/90 backdrop-blur">
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-6 py-2">

        <NavLink
          to="/"
          className="font-display font-semibold text-lg whitespace-nowrap"
        >
          Smart<span className="text-safe">City AI</span>
        </NavLink>

        <nav className="flex max-w-[65vw] items-center gap-1 overflow-x-auto rounded-full border border-line bg-panel p-1">
          {user?.role === "admin" ? ADMIN_LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} className={linkClass}>
              {label}
            </NavLink>
          )) : user ? (
            <NavLink to="/report" className={linkClass}>
              Report an issue
            </NavLink>
          ) : (
            <>
              <NavLink to="/login" className={linkClass}>User sign in</NavLink>
              <NavLink to="/register" className={linkClass}>Create account</NavLink>
              <NavLink to="/admin/login" className={linkClass}>Admin sign in</NavLink>
              <NavLink to="/admin/register" className={linkClass}>Admin create account</NavLink>
            </>
          )}
        </nav>

        {user && (
          <div className="flex shrink-0 items-center gap-3">
            <span className="hidden max-w-36 truncate text-xs text-muted sm:block" title={user.name}>
              {user.name}
            </span>
            <button
              type="button"
              onClick={onLogout}
              aria-label="Sign out"
              title="Sign out"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted hover:text-ink"
            >
              <LogOut size={16} aria-hidden="true" />
            </button>
          </div>
        )}

      </div>
    </header>
  );
}