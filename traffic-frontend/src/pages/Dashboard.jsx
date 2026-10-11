import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import {
  deleteDetectionEvent,
  getDetectionEvents,
  getStats,
  resolveImageUrl,
} from "../api/client.js";
import StatCard from "../components/StatCard.jsx";
import Loader from "../components/Loader.jsx";

const FEATURE_LABELS = {
  helmet: "Helmet",
  traffic: "Traffic",
  garbage: "Garbage",
  pothole: "Pothole",
};

const EVENT_FILTERS = {
  traffic: { label: "Traffic events", params: { feature: "traffic" } },
  helmet: { label: "Helmet violations", params: { feature: "helmet" } },
  garbage: { label: "Garbage detections", params: { feature: "garbage" } },
  pothole: { label: "Pothole detections", params: { feature: "pothole" } },
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [previewUrl, setPreviewUrl] = useState(null);
  const [selectedFilter, setSelectedFilter] = useState(null);

  const load = useCallback(async (filter = selectedFilter) => {
    setLoading(true);
    setError("");

    try {
      const eventParams = {
        limit: 500,
        ...(filter?.params || {}),
      };
      const [s, e] = await Promise.all([
        getStats(),
        getDetectionEvents(eventParams),
      ]);

      setStats(s.data);
      setEvents(e.data);
    } catch {
      setError(
        "We couldn't load the dashboard. The detection service may be unavailable."
      );
    } finally {
      setLoading(false);
    }
  }, [selectedFilter]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => load(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  const toggleFilter = (filterKey) => {
    const nextFilter = selectedFilter?.key === filterKey
      ? null
      : { key: filterKey, ...EVENT_FILTERS[filterKey] };
    setSelectedFilter(nextFilter);
  };

  const removeEvent = async (event) => {
    const featureLabel = FEATURE_LABELS[event.feature] || event.feature;
    if (!window.confirm(`Delete this ${featureLabel.toLowerCase()} detection event and its saved frame? This cannot be undone.`)) {
      return;
    }

    setError("");
    try {
      await deleteDetectionEvent(event.feature, event.id);
      setEvents((current) => current.filter((item) => item.id !== event.id));
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail || "The detection event couldn't be deleted."
      );
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">

      <div className="flex items-center justify-between mb-8">

        <div>
          <h1 className="font-display text-3xl font-semibold">
            Detection Overview
          </h1>

          <p className="text-sm text-muted mt-1">
            Recent activity across the detection tools
          </p>
        </div>

        <button
          onClick={load}
          className="rounded-full border border-line px-4 py-2 text-sm"
        >
          Reload data
        </button>

      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-alert/30 bg-alert/5 px-4 py-3 text-sm text-alert font-mono">
          {error}
        </div>
      )}

      {/* MAIN STATS */}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">

        <StatCard
          label="Traffic Events"
          value={stats?.traffic_events ?? 0}
          accent="safe"
          onClick={() => toggleFilter("traffic")}
          selected={selectedFilter?.key === "traffic"}
        />

        <StatCard
          label="Helmet Violations"
          value={stats?.total_violations ?? 0}
          accent="alert"
          onClick={() => toggleFilter("helmet")}
          selected={selectedFilter?.key === "helmet"}
        />

        <StatCard
          label="Garbage Detected"
          value={stats?.garbage_detected ?? 0}
          accent="scan"
          onClick={() => toggleFilter("garbage")}
          selected={selectedFilter?.key === "garbage"}
        />

        <StatCard
          label="Potholes Detected"
          value={stats?.potholes_detected ?? 0}
          accent="alert"
          onClick={() => toggleFilter("pothole")}
          selected={selectedFilter?.key === "pothole"}
        />

      </div>

      {/* VIOLATIONS */}

      <div className="rounded-xl border border-line bg-panel">

        <div className="flex items-center justify-between gap-3 border-b border-line p-5">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted">
              Recent Events
            </h2>
            {selectedFilter && (
              <p className="mt-1 text-xs text-safe">
                Showing: {selectedFilter.label}
              </p>
            )}
          </div>
          {selectedFilter && (
            <button
              type="button"
              onClick={() => toggleFilter(selectedFilter.key)}
              className="rounded-full border border-line px-3 py-1.5 text-xs text-muted hover:bg-panel2"
            >
              Clear filter
            </button>
          )}
        </div>

        {loading ? (
          <Loader label="Loading recent detections..." />
        ) : events.length === 0 ? (

          <div className="py-16 text-center text-muted text-sm font-mono">
            {selectedFilter
              ? `No ${selectedFilter.label.toLowerCase()} logs were found.`
              : "Nothing has been recorded yet."}
          </div>

        ) : (

          <div className="divide-y divide-line max-h-[500px] overflow-y-auto">

            {events.map((event) => (

              <div
                key={`${event.feature}-${event.id}`}
                className="flex flex-wrap items-center gap-3 px-5 py-3"
              >

                <button
                  onClick={() => {
                    if (event.image_url) {
                      setPreviewUrl(resolveImageUrl(event.image_url));
                    }
                  }}
                  disabled={!event.image_url}
                  className="h-10 w-14 rounded border border-line bg-panel2 text-xs text-muted disabled:opacity-40"
                >
                  View image
                </button>

                <span className="rounded-full border border-line px-2.5 py-1 text-[10px] font-mono uppercase text-muted">
                  {FEATURE_LABELS[event.feature] || event.feature}
                </span>

                <span className="min-w-32 flex-1 truncate text-sm font-medium">
                  {event.summary}
                </span>

                <span className="flex-1 truncate text-sm text-muted font-mono">
                  {event.source}
                </span>

                <span className="font-mono text-xs text-muted">
                  {new Date(event.timestamp).toLocaleString()}
                </span>

                <button
                  type="button"
                  onClick={() => removeEvent(event)}
                  aria-label={`Delete ${FEATURE_LABELS[event.feature] || event.feature} event`}
                  title="Delete event"
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-alert/30 text-alert hover:bg-alert/5"
                >
                  <Trash2 size={16} aria-hidden="true" />
                </button>

              </div>

            ))}

          </div>

        )}

      </div>

      {previewUrl && (
        <div
          onClick={() => setPreviewUrl(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
        >
          <img
            src={previewUrl}
            alt="detection frame"
            className="max-h-[85vh] max-w-[90vw] rounded-lg border border-line"
          />
        </div>
      )}

    </div>
  );
}