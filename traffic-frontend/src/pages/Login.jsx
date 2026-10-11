import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getRoleHome } from "../authUtils.js";
import { useAuth } from "../useAuth.js";

export default function Login({ adminOnly = false }) {
  const { login, logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    const form = new FormData(event.currentTarget);
    try {
      const user = await login({
        email: form.get("email"),
        password: form.get("password"),
      });

      if (adminOnly && user.role !== "admin") {
        await logout();
        setError("This account does not have administrator access.");
        return;
      }

      if (!adminOnly && user.role === "admin") {
        await logout();
        setError("Use the admin sign-in page to open the detection workspace.");
        return;
      }

      navigate(getRoleHome(user), { replace: true });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "We couldn't sign you in. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-9rem)] max-w-md items-center px-6 py-12">
      <section className="w-full rounded-xl border border-line bg-panel p-6 sm:p-8">
        <p className="mb-2 font-mono text-xs uppercase text-safe">
          {adminOnly ? "Detection workspace" : "City issue reporting"}
        </p>
        <h1 className="font-display text-3xl font-semibold">
          {adminOnly ? "Admin sign in" : "User sign in"}
        </h1>
        <p className="mt-2 text-sm text-muted">
          {adminOnly
            ? "Sign in with your administrator account to access the detection tools and community reports."
            : "Sign in to submit and follow up on local issue reports."}
        </p>

        {error && (
          <p role="alert" className="mt-5 rounded-lg border border-alert/30 bg-alert/5 px-3 py-2 text-sm text-alert">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm">
            Email address
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5"
            />
          </label>
          <label className="block text-sm">
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5"
            />
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-full bg-safe px-4 py-3 font-semibold text-base disabled:opacity-50"
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        {adminOnly ? (
          <p className="mt-5 text-sm text-muted">
            First admin setup? <Link className="text-safe underline" to="/admin/register">Create admin account</Link>
          </p>
        ) : (
          <p className="mt-5 text-sm text-muted">
            Need a public account? <Link className="text-safe underline" to="/register">Create one</Link>
            <span className="mx-2 text-line">|</span>
            <Link className="text-safe underline" to="/admin/login">Admin sign in</Link>
          </p>
        )}
      </section>
    </div>
  );
}