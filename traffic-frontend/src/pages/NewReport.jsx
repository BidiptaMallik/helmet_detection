import { useEffect, useRef, useState } from "react";
import { Star, Trash2 } from "lucide-react";
import ReportUpdatePhoto from "../components/ReportUpdatePhoto.jsx";
import { createIssueReport } from "../api/client.js";
import {
  getMyReports,
  getMyReportUpdates,
  getMyReportPhoto,
  rateResolvedReport,
  deleteMyReport,
} from "../api/client.js";
import { useAuth } from "../useAuth.js";

const ISSUE_LABELS = {
  traffic: "Traffic congestion",
  garbage: "Garbage",
  pothole: "Pothole / road damage",
};

const STATUS_LABELS = {
  new: "Received",
  in_progress: "In progress",
  resolved: "Resolved",
};

export default function NewReport() {
  const { user } = useAuth();
  const [reportsError, setReportsError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submitInProgress = useRef(false);
  const [reports, setReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [ratingDrafts, setRatingDrafts] = useState({});
  const [ratingSaving, setRatingSaving] = useState("");
  const [photoPreview, setPhotoPreview] = useState(null);
  const [photoLoading, setPhotoLoading] = useState("");

  useEffect(() => {
    let active = true;
    getMyReports()
      .then(async ({ data }) => {
        const reportsWithUpdates = await Promise.all(
          data.map(async (report) => {
            const response = await getMyReportUpdates(report.id);
            return { ...report, updates: response.data };
          })
        );
        if (active) setReports(reportsWithUpdates);
      })
      .catch((requestError) => {
        if (active) {
          setReportsError(
            requestError.response?.data?.detail || "Your reports couldn't be loaded."
          );
        }
      })
      .finally(() => {
        if (active) setReportsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshKey]);

  useEffect(() => () => {
    if (photoPreview?.url) URL.revokeObjectURL(photoPreview.url);
  }, [photoPreview]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setRefreshKey((current) => current + 1);
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitInProgress.current) return;
    submitInProgress.current = true;
    setSubmitting(true);
    setSubmitError("");
    setSuccess("");

    try {
      const { data } = await createIssueReport(new FormData(event.currentTarget));
      setSubmitError("");
      setSuccess(`Report received. Reference number: ${data.id}`);
      event.currentTarget.reset();
      setReportsLoading(true);
      setRefreshKey((current) => current + 1);
    } catch (requestError) {
      setSubmitError(
        requestError.response?.data?.detail || "We couldn't send your report. Please try again."
      );
    } finally {
      submitInProgress.current = false;
      setSubmitting(false);
    }
  };

  const showPhoto = async (report, kind) => {
    setPhotoLoading(`${report.id}-${kind}`);
    setReportsError("");
    try {
      const { data } = await getMyReportPhoto(report.id, kind);
      setPhotoPreview({
        url: URL.createObjectURL(data),
        alt: `${ISSUE_LABELS[report.issue_type]} ${kind} photo`,
      });
    } catch (requestError) {
      setReportsError(
        requestError.response?.data?.detail || "The report photo couldn't be opened."
      );
    } finally {
      setPhotoLoading("");
    }
  };

  const submitRating = async (event, report) => {
    event.preventDefault();
    const draft = ratingDrafts[report.id] || {};
    if (!draft.rating) return;

    setRatingSaving(report.id);
    setReportsError("");
    try {
      await rateResolvedReport(report.id, draft.rating, draft.comment || "");
      setReportsLoading(true);
      setRefreshKey((current) => current + 1);
    } catch (requestError) {
      setReportsError(
        requestError.response?.data?.detail || "Your rating couldn't be saved."
      );
    } finally {
      setRatingSaving("");
    }
  };

  const removeReport = async (report) => {
    if (!window.confirm("Delete this report, its update history, and all attached photos? This cannot be undone.")) {
      return;
    }

    setReportsError("");
    try {
      await deleteMyReport(report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
      setSuccess("Your report and its attached photos were deleted.");
    } catch (requestError) {
      setReportsError(
        requestError.response?.data?.detail || "Your report couldn't be deleted."
      );
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-8">
        <p className="mb-2 font-mono text-xs uppercase text-safe">Community report</p>
        <h1 className="font-display text-3xl font-semibold">Report a local issue</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Share a traffic congestion, garbage, or pothole concern. Include a clear location and photo so the response team can find it.
        </p>
      </header>

      {submitError && <p role="alert" className="mb-5 rounded-lg border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert">{submitError}</p>}
      {success && <p role="status" className="mb-5 rounded-lg border border-safe/30 bg-safe/5 px-4 py-3 text-sm text-safe">{success}</p>}

      <form onSubmit={handleSubmit} className="space-y-5">
        <section className="grid gap-4 border-y border-line py-5 sm:grid-cols-2">
          <label className="block text-sm">
            Your name
            <input name="name" defaultValue={user?.name || ""} maxLength={100} required className="mt-1.5 w-full rounded-lg border border-line bg-panel px-3 py-2.5" />
          </label>
          <label className="block text-sm">
            Mobile number
            <input name="phone" type="tel" defaultValue={user?.phone || ""} required className="mt-1.5 w-full rounded-lg border border-line bg-panel px-3 py-2.5" />
          </label>
        </section>

        <label className="block text-sm">
          Issue type
          <select name="issue_type" required defaultValue="traffic" className="mt-1.5 w-full rounded-lg border border-line bg-panel px-3 py-2.5">
            <option value="traffic">Traffic congestion</option>
            <option value="garbage">Garbage or dumped waste</option>
            <option value="pothole">Pothole or road damage</option>
          </select>
        </label>

        <label className="block text-sm">
          Location
          <input name="location" maxLength={500} placeholder="Street, area, nearby landmark" required className="mt-1.5 w-full rounded-lg border border-line bg-panel px-3 py-2.5" />
        </label>

        <label className="block text-sm">
          What did you notice?
          <textarea name="description" maxLength={2000} rows={4} required className="mt-1.5 w-full resize-y rounded-lg border border-line bg-panel px-3 py-2.5" />
        </label>

        <label className="block text-sm">
          Photo of the area
          <input name="photo" type="file" accept="image/*" required className="mt-1.5 block w-full text-sm text-muted file:mr-3 file:rounded-full file:border-0 file:bg-panel2 file:px-4 file:py-2 file:text-sm file:text-ink" />
          <span className="mt-1 block text-xs text-muted">A photo helps the response team identify the exact issue. Maximum size: 8 MB.</span>
        </label>

        <button type="submit" disabled={submitting} className="rounded-full bg-safe px-6 py-3 font-semibold text-base disabled:opacity-50">
          {submitting ? "Sending report..." : "Send report"}
        </button>
      </form>

      <section className="mt-14 border-t border-line pt-8">
        <header className="mb-5 flex items-end justify-between gap-3">
          <div>
            <p className="mb-1 font-mono text-xs uppercase text-muted">Follow-up</p>
            <h2 className="font-display text-2xl font-semibold">Your reports</h2>
          </div>
          <button
            type="button"
            onClick={() => {
              setReportsLoading(true);
              setRefreshKey((current) => current + 1);
            }}
            className="rounded-full border border-line px-3 py-2 text-sm hover:bg-panel"
          >
            Refresh
          </button>
        </header>

        {reportsError && (
          <p role="alert" className="mb-5 rounded-lg border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert">
            {reportsError}
          </p>
        )}

        {reportsLoading ? (
          <p className="py-8 text-sm text-muted">Loading your reports...</p>
        ) : reports.length === 0 ? (
          <p className="py-8 text-sm text-muted">Reports you send will appear here with updates from the response team.</p>
        ) : (
          <div className="divide-y divide-line border-y border-line">
            {reports.map((report) => (
              <article key={report.id} className="py-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-display text-lg font-semibold">
                      {ISSUE_LABELS[report.issue_type] || report.issue_type}
                    </h3>
                    <p className="mt-1 text-xs text-muted">
                      {report.location} · {new Date(report.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full border px-3 py-1 text-xs ${report.status === "resolved" ? "border-safe/30 text-safe" : "border-line text-muted"}`}>
                      {STATUS_LABELS[report.status] || report.status}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeReport(report)}
                      aria-label={`Delete ${ISSUE_LABELS[report.issue_type]} report`}
                      title="Delete report"
                      className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-alert/30 text-alert hover:bg-alert/5"
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </button>
                  </div>
                </div>

                <p className="mt-3 whitespace-pre-wrap text-sm text-muted">{report.description}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => showPhoto(report, "original")}
                    disabled={photoLoading === `${report.id}-original`}
                    className="rounded-full border border-line px-3 py-1.5 text-xs hover:bg-panel disabled:opacity-50"
                  >
                    {photoLoading === `${report.id}-original` ? "Loading..." : "View submitted photo"}
                  </button>
                  {report.resolution_photo_url && (
                    <button
                      type="button"
                      onClick={() => showPhoto(report, "resolution")}
                      disabled={photoLoading === `${report.id}-resolution`}
                      className="rounded-full border border-safe/30 px-3 py-1.5 text-xs text-safe hover:bg-safe/5 disabled:opacity-50"
                    >
                      {photoLoading === `${report.id}-resolution` ? "Loading..." : "View completed work"}
                    </button>
                  )}
                </div>

                {report.updates?.length > 0 && (
                  <ol className="mt-5 space-y-4 border-l border-line pl-4">
                    {report.updates.map((update) => (
                      <li key={update.id}>
                        <p className="text-xs text-muted">
                          {STATUS_LABELS[update.status] || update.status} · {new Date(update.created_at).toLocaleString()}
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-sm">{update.message}</p>
                        {update.is_resolution_photo && (
                          <span className="mt-1 inline-block text-xs text-safe">Completed work</span>
                        )}
                        {update.photo_url && (
                          <ReportUpdatePhoto
                            reportId={report.id}
                            updateId={update.id}
                          />
                        )}
                      </li>
                    ))}
                  </ol>
                )}

                {report.status === "resolved" && report.resolution_photo_url && (
                  <div className="mt-5 border-t border-line pt-4">
                    {report.rating ? (
                      <p className="text-sm text-safe">
                        Your rating: {"★".repeat(report.rating)}{"☆".repeat(5 - report.rating)}
                        {report.rating_comment ? ` · ${report.rating_comment}` : ""}
                      </p>
                    ) : (
                      <form onSubmit={(event) => submitRating(event, report)} className="space-y-3">
                        <p className="text-sm font-semibold">How was the completed work?</p>
                        <div className="flex items-center gap-1" role="radiogroup" aria-label="Rate the completed work">
                          {[1, 2, 3, 4, 5].map((rating) => (
                            <button
                              key={rating}
                              type="button"
                              role="radio"
                              aria-checked={ratingDrafts[report.id]?.rating === rating}
                              aria-label={`${rating} out of 5 stars`}
                              onClick={() => setRatingDrafts((current) => ({
                                ...current,
                                [report.id]: { ...current[report.id], rating },
                              }))}
                              className={`p-1 ${ratingDrafts[report.id]?.rating >= rating ? "text-safe" : "text-muted"}`}
                            >
                              <Star size={20} fill={ratingDrafts[report.id]?.rating >= rating ? "currentColor" : "none"} aria-hidden="true" />
                            </button>
                          ))}
                        </div>
                        <textarea
                          rows={2}
                          maxLength={1000}
                          value={ratingDrafts[report.id]?.comment || ""}
                          onChange={(event) => setRatingDrafts((current) => ({
                            ...current,
                            [report.id]: { ...current[report.id], comment: event.target.value },
                          }))}
                          placeholder="Optional comment"
                          className="block w-full max-w-xl rounded-lg border border-line bg-panel px-3 py-2 text-sm"
                        />
                        <button
                          type="submit"
                          disabled={!ratingDrafts[report.id]?.rating || ratingSaving === report.id}
                          className="rounded-full bg-safe px-4 py-2 text-sm font-semibold text-base disabled:opacity-50"
                        >
                          {ratingSaving === report.id ? "Saving..." : "Send rating"}
                        </button>
                      </form>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      {photoPreview && (
        <div
          role="presentation"
          onClick={() => setPhotoPreview(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-5"
        >
          <div role="dialog" aria-modal="true" aria-label={photoPreview.alt} onClick={(event) => event.stopPropagation()} className="relative max-w-5xl">
            <button type="button" onClick={() => setPhotoPreview(null)} aria-label="Close photo" className="absolute -right-3 -top-3 rounded-full border border-line bg-panel p-2">×</button>
            <img src={photoPreview.url} alt={photoPreview.alt} className="max-h-[85vh] max-w-full rounded-lg" />
          </div>
        </div>
      )}
    </div>
  );
}