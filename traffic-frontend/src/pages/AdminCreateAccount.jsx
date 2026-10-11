import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getRoleHome } from "../authUtils.js";
import { useAuth } from "../useAuth.js";

export default function AdminCreateAccount() {
  const { setupAdmin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    const form = new FormData(event.currentTarget);
    try {
      const user = await setupAdmin({
        setup_key: form.get("setup_key"),
        name: form.get("name"),
        email: form.get("email"),
        password: form.get("password"),
      });
      navigate(getRoleHome(user), { replace: true });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          "The administrator account could not be created. Check the setup key and try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-9rem)] max-w-md items-center px-6 py-12">
      <section className="w-full rounded-xl border border-line bg-panel p-6 sm:p-8">
        <p className="mb-2 font-mono text-xs uppercase text-alert">Initial setup</p>
        <h1 className="font-display text-3xl font-semibold">Create admin account</h1>
        <p className="mt-2 text-sm text-muted">
          This one-time setup needs the key configured by the site operator. Once an admin account is created, public setup closes.
        </p>

        {error && (
          <p role="alert" className="mt-5 rounded-lg border border-alert/30 bg-alert/5 px-3 py-2 text-sm text-alert">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm">
            One-time setup key
            <input
              name="setup_key"
              type="password"
              autoComplete="off"
              minLength={32}
              required
              className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5"
            />
          </label>
          <label className="block text-sm">
            Administrator name
            <input name="name" autoComplete="name" maxLength={100} required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Administrator email
            <input name="email" type="email" autoComplete="email" required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Password
            <input name="password" type="password" autoComplete="new-password" minLength={12} required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
            <span className="mt-1 block text-xs text-muted">Use at least 12 characters.</span>
          </label>
          <button type="submit" disabled={submitting} className="w-full rounded-full bg-alert px-4 py-3 font-semibold text-base disabled:opacity-50">
            {submitting ? "Creating admin account..." : "Create admin account"}
          </button>
        </form>

        <p className="mt-5 text-sm text-muted">
          Already have an admin account? <Link className="text-safe underline" to="/admin/login">Admin sign in</Link>
        </p>
      </section>
    </div>
  );
}