export default function StatCard({
  label,
  value,
  accent = "safe",
  onClick,
  selected = false,
}) {
  const colors = {
    safe: "text-safe border-safe/30",
    alert: "text-alert border-alert/30",
    scan: "text-scan border-scan/30",
  };

  const className = `w-full rounded-xl border bg-panel p-5 text-left transition-colors ${colors[accent]} ${
    onClick ? "cursor-pointer hover:bg-panel2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-safe" : ""
  } ${selected ? "ring-2 ring-safe" : ""}`;

  const content = (
    <>
      <div className="text-xs uppercase tracking-widest text-muted font-mono">
        {label}
      </div>

      <div className="mt-2 font-display text-3xl font-semibold">
        {value}
      </div>
    </>
  );

  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={className}
    >
      {content}
    </button>
  ) : (
    <div className={className}>{content}</div>
  );
}