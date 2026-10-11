import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../useAuth.js";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    const form = new FormData(event.currentTarget);
    try {
      await register({
        name: form.get("name"),
        email: form.get("email"),
        phone: form.get("phone"),
        password: form.get("password"),
      });
      navigate("/report", { replace: true });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "We couldn't create your account. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-9rem)] max-w-md items-center px-6 py-12">
      <section className="w-full rounded-xl border border-line bg-panel p-6 sm:p-8">
        <p className="mb-2 font-mono text-xs uppercase text-safe">Community reports</p>
        <h1 className="font-display text-3xl font-semibold">Create an account</h1>
        <p className="mt-2 text-sm text-muted">
          Your contact details will be included with the reports you send.
        </p>

        {error && (
          <p role="alert" className="mt-5 rounded-lg border border-alert/30 bg-alert/5 px-3 py-2 text-sm text-alert">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <label className="block text-sm">
            Full name
            <input name="name" autoComplete="name" maxLength={100} required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Email address
            <input name="email" type="email" autoComplete="email" required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Mobile number
            <input name="phone" type="tel" autoComplete="tel" required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Password
            <input name="password" type="password" autoComplete="new-password" minLength={10} required className="mt-1.5 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5" />
            <span className="mt-1 block text-xs text-muted">Use at least 10 characters.</span>
          </label>
          <button type="submit" disabled={submitting} className="w-full rounded-full bg-safe px-4 py-3 font-semibold text-base disabled:opacity-50">
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-5 text-sm text-muted">
          Already registered? <Link className="text-safe underline" to="/login">Sign in</Link>
        </p>
      </section>
    </div>
  );
}