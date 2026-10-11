import { Link } from "react-router-dom";

const modules = [
  {
    key: "traffic",
    title: "Traffic Congestion",
    body: "Review vehicles in video, webcam, or CCTV footage and check traffic density.",
    to: "/multistream?feature=traffic",
    tag: "Road traffic",
    accent: "border-safe/30 hover:border-safe/60",
    dot: "bg-safe",
  },
  {
    key: "helmet",
    title: "Helmet & Plate Detection",
    body: "Review helmet use and number plates in video, webcam, or CCTV footage.",
    to: "/multistream?feature=helmet",
    tag: "Rider safety",
    accent: "border-alert/30 hover:border-alert/60",
    dot: "bg-alert",
  },
  {
    key: "garbage",
    title: "Garbage Detection",
    body: "Find litter and dumped waste in video, webcam, or CCTV footage.",
    to: "/multistream?feature=garbage",
    tag: "Street cleanliness",
    accent: "border-scan/30 hover:border-scan/60",
    dot: "bg-scan",
  },
  {
    key: "pothole",
    title: "Pothole Detection",
    body: "Review video, webcam, or CCTV footage for potholes and road damage.",
    to: "/multistream?feature=pothole",
    tag: "Road maintenance",
    accent: "border-alert/30 hover:border-alert/60",
    dot: "bg-alert",
  },
];

export default function Welcome() {
  return (
    <div className="max-w-6xl mx-auto px-6 py-20 text-center">

      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-line bg-panel font-mono text-[11px] text-scan mb-6">
        <span className="h-1.5 w-1.5 rounded-full bg-scan animate-blink" />
        SMART CITY WORKSPACE
      </div>

      <h1 className="font-display text-5xl sm:text-6xl font-semibold tracking-tight mb-6 leading-[1.05]">
        Smart City
      </h1>

      <p className="text-muted max-w-2xl mx-auto mb-14 text-base leading-relaxed">
        Review traffic, helmet use, litter, and road damage from recorded videos,
        webcams, or CCTV feeds.
      </p>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-left mb-14">

        {modules.map((m) => (
          <Link
            key={m.title}
            to={m.to}
            className={`group rounded-xl border bg-panel p-6 transition-all hover:-translate-y-1 ${m.accent}`}
          >

            <div className="flex items-center gap-2 mb-4">

              <span
                className={`h-1.5 w-1.5 rounded-full ${m.dot}`}
              />

              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                {m.tag}
              </span>

            </div>

            <h3 className="font-display font-semibold text-lg mb-2 text-ink">
              {m.title}
            </h3>

            <p className="text-sm text-muted leading-relaxed mb-4">
              {m.body}
            </p>

            <span className="text-sm font-medium text-ink/70 group-hover:text-ink transition-colors">
              View tools →
            </span>

          </Link>
        ))}

      </div>

      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 rounded-full bg-safe text-base font-semibold px-6 py-3"
      >
        View recent activity
      </Link>

    </div>
  );
}