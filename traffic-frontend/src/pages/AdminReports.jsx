import { useEffect, useState } from "react";
import { Image, MapPin, Phone, RefreshCw, Trash2, X } from "lucide-react";
import ReportUpdatePhoto from "../components/ReportUpdatePhoto.jsx";
import {
  getAdminReports,
  getAdminReportPhoto,
  getAdminReportUpdates,
  createAdminReportUpdate,
  deleteAdminReport,
} from "../api/client.js";

const STATUS_LABELS = {
  new: "New",
  in_progress: "In progress",
  resolved: "Resolved",
};

const ISSUE_LABELS = {
  traffic: "Traffic congestion",
  garbage: "Garbage",
  pothole: "Pothole / road damage",
};

export default function AdminReports() {
  const [reports, setReports] = useState([]);
  const [issueFilter, setIssueFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [photoPreview, setPhotoPreview] = useState(null);
  const [photoLoading, setPhotoLoading] = useState("");
  const [updatesByReport, setUpdatesByReport] = useState({});
  const [updateStatus, setUpdateStatus] = useState({});

  const removeReport = async (report) => {
    const issueLabel = ISSUE_LABELS[report.issue_type] || report.issue_type;
    if (!window.confirm(`Delete this ${issueLabel.toLowerCase()} report and all its photos and updates? This cannot be undone.`)) {
      return;
    }

    setError("");
    try {
      await deleteAdminReport(report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
      setUpdatesByReport((current) => {
        const next = { ...current };
        delete next[report.id];
        return next;
      });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "The report couldn't be deleted."
      );
    }
  };

  useEffect(() => {
    let active = true;
    const params = {};
    if (issueFilter !== "all") params.issue_type = issueFilter;
    if (statusFilter !== "all") params.status = statusFilter;

    getAdminReports(params)
      .then(async ({ data }) => {
        if (active) {
          setReports(data);
          setError("");
        }
        const updateEntries = await Promise.all(
          data.map(async (report) => {
            const response = await getAdminReportUpdates(report.id);
            return [report.id, response.data];
          })
        );
        if (active) setUpdatesByReport(Object.fromEntries(updateEntries));
      })
      .catch((requestError) => {
        if (active) {
          setError(
            requestError.response?.data?.detail || "Reports couldn't be loaded."
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [issueFilter, statusFilter, refreshKey]);

  useEffect(() => () => {
    if (photoPreview?.url) URL.revokeObjectURL(photoPreview.url);
  }, [photoPreview]);

  const openPhoto = async (report) => {
    setPhotoLoading(report.id);
    setError("");
    try {
      const { data } = await getAdminReportPhoto(report.id);
      setPhotoPreview({
        url: URL.createObjectURL(data),
        name: `${ISSUE_LABELS[report.issue_type]} photo`,
      });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "The report photo couldn't be opened."
      );
    } finally {
      setPhotoLoading("");
    }
  };

  const submitUpdate = async (event, report) => {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const formData = new FormData(form);
    const submittedStatus = formData.get("status");
    const selectedPhoto = form.querySelector('input[name="photo"]').files[0];
    formData.delete("photo");
    if (selectedPhoto) formData.append("photo", selectedPhoto);

    try {
      await createAdminReportUpdate(report.id, formData);
      form.reset();
      setUpdateStatus((current) => ({ ...current, [report.id]: submittedStatus }));
      setLoading(true);
      setRefreshKey((current) => current + 1);
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "The report update couldn't be sent."
      );
    }
  };

  const openResolutionPhoto = async (report) => {
    setPhotoLoading(`${report.id}-resolution`);
    setError("");
    try {
      const { data } = await getAdminReportPhoto(report.id, "resolution");
      setPhotoPreview({
        url: URL.createObjectURL(data),
        name: `${ISSUE_LABELS[report.issue_type]} completed work`,
      });
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "The completion photo couldn't be opened."
      );
    } finally {
      setPhotoLoading("");
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase text-alert">Admin workspace</p>
          <h1 className="font-display text-3xl font-semibold">Community reports</h1>
          <p className="mt-2 text-sm text-muted">
            Contact details, locations, and photos submitted by residents.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            setRefreshKey((current) => current + 1);
          }}
          className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm hover:bg-panel"
        >
          <RefreshCw size={15} aria-hidden="true" />
          Refresh reports
        </button>
      </header>

      <div className="mb-5 flex flex-wrap gap-3 border-y border-line py-4">
        <label className="text-sm text-muted">
          Issue
          <select
            value={issueFilter}
            onChange={(event) => setIssueFilter(event.target.value)}
            className="ml-2 rounded-lg border border-line bg-panel px-3 py-2 text-ink"
          >
            <option value="all">All issues</option>
            {Object.entries(ISSUE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-muted">
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="ml-2 rounded-lg border border-line bg-panel px-3 py-2 text-ink"
          >
            <option value="all">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <p role="alert" className="mb-5 rounded-lg border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="py-12 text-center text-sm text-muted">Loading reports...</p>
      ) : reports.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted">No reports match these filters.</p>
      ) : (
        <div className="divide-y divide-line border-y border-line">
          {reports.map((report) => (
            <article key={report.id} className="grid gap-4 py-5 md:grid-cols-[1fr_auto] md:items-start">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-display text-lg font-semibold">
                    {ISSUE_LABELS[report.issue_type] || report.issue_type}
                  </h2>
                  <span className="rounded-full border border-line px-2.5 py-1 text-xs text-muted">
                    {STATUS_LABELS[report.status] || report.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {new Date(report.created_at).toLocaleString()}
                </p>
                <p className="mt-4 text-sm font-semibold">{report.name}</p>
                <a href={`tel:${report.phone}`} className="mt-1 inline-flex items-center gap-2 text-sm text-safe">
                  <Phone size={14} aria-hidden="true" />
                  {report.phone}
                </a>
                <p className="mt-3 flex items-start gap-2 text-sm">
                  <MapPin size={15} className="mt-0.5 shrink-0 text-alert" aria-hidden="true" />
                  <span>{report.location}</span>
                </p>
                <p className="mt-3 max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-muted">
                  {report.description}
                </p>
                {report.latest_update_message && (
                  <div className="mt-4 border-l-2 border-safe pl-3">
                    <p className="text-xs font-semibold uppercase text-muted">Latest update sent</p>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{report.latest_update_message}</p>
                  </div>
                )}
                {report.rating && (
                  <p className="mt-3 text-sm text-safe">
                    Resident rating: {"★".repeat(report.rating)}{"☆".repeat(5 - report.rating)}
                    {report.rating_comment ? ` · ${report.rating_comment}` : ""}
                  </p>
                )}
                {updatesByReport[report.id]?.length > 0 && (
                  <details className="mt-4 text-sm">
                    <summary className="cursor-pointer text-muted">
                      Update history ({updatesByReport[report.id].length})
                    </summary>
                    <ol className="mt-2 space-y-2 border-l border-line pl-4">
                      {updatesByReport[report.id].map((update) => (
                        <li key={update.id}>
                          <p className="text-xs text-muted">
                            {STATUS_LABELS[update.status]} · {new Date(update.created_at).toLocaleString()}
                          </p>
                          <p className="mt-1 whitespace-pre-wrap">{update.message}</p>
                          {update.photo_url && (
                            <ReportUpdatePhoto
                              reportId={report.id}
                              updateId={update.id}
                              admin
                            />
                          )}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </div>

              <div className="flex flex-col gap-3 md:items-end">
                <div className="flex flex-wrap items-center gap-2 md:justify-end">
                <button
                  type="button"
                  onClick={() => removeReport(report)}
                  aria-label={`Delete ${ISSUE_LABELS[report.issue_type]} report`}
                  title="Delete report"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-alert/30 text-alert hover:bg-alert/5"
                >
                  <Trash2 size={16} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => openPhoto(report)}
                  disabled={photoLoading === report.id}
                  className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50"
                >
                  <Image size={15} aria-hidden="true" />
                  {photoLoading === report.id ? "Loading photo..." : "View photo"}
                </button>
                {report.resolution_photo_url && (
                  <button
                    type="button"
                    onClick={() => openResolutionPhoto(report)}
                    disabled={photoLoading === `${report.id}-resolution`}
                    className="inline-flex items-center gap-2 rounded-full border border-safe/30 px-3 py-2 text-sm text-safe hover:bg-safe/5 disabled:opacity-50"
                  >
                    <Image size={15} aria-hidden="true" />
                    View completed photo
                  </button>
                )}
                </div>

                <form
                  onSubmit={(event) => submitUpdate(event, report)}
                  className="w-full space-y-2 rounded-lg border border-line p-3 md:w-80"
                >
                  <label className="block text-xs text-muted" htmlFor={`message-${report.id}`}>
                    Update for resident
                  </label>
                  <textarea
                    id={`message-${report.id}`}
                    name="message"
                    maxLength={2000}
                    rows={3}
                    required
                    placeholder="Share progress or describe the completed work"
                    className="w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm"
                  />
                  <label className="sr-only" htmlFor={`status-${report.id}`}>Report status</label>
                  <select
                    id={`status-${report.id}`}
                    name="status"
                    value={updateStatus[report.id] || report.status}
                    onChange={(event) => setUpdateStatus((current) => ({
                      ...current,
                      [report.id]: event.target.value,
                    }))}
                    className="w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm"
                  >
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <label className="block text-xs text-muted">
                    {((updateStatus[report.id] || report.status) === "resolved"
                      ? "Completion photo (required)"
                      : "Photo for this update (optional)")}
                    <input
                      name="photo"
                      type="file"
                      accept="image/*"
                      required={(updateStatus[report.id] || report.status) === "resolved"}
                      className="mt-1 block w-full text-xs"
                    />
                  </label>
                  <button
                    type="submit"
                    className="w-full rounded-full bg-safe px-3 py-2 text-sm font-semibold text-base"
                  >
                    Send update
                  </button>
                </form>
              </div>
            </article>
          ))}
        </div>
      )}

      {photoPreview && (
        <div
          role="presentation"
          onClick={() => setPhotoPreview(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-5"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={photoPreview.name}
            onClick={(event) => event.stopPropagation()}
            className="relative max-h-full max-w-5xl"
          >
            <button
              type="button"
              onClick={() => setPhotoPreview(null)}
              aria-label="Close photo"
              className="absolute -right-3 -top-3 rounded-full border border-line bg-panel p-2"
            >
              <X size={18} aria-hidden="true" />
            </button>
            <img src={photoPreview.url} alt={photoPreview.name} className="max-h-[85vh] max-w-full rounded-lg" />
          </div>
        </div>
      )}
    </div>
  );
}