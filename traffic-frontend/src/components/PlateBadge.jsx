export default function PlateBadge({
  plate,
  fresh = false,
}) {
  const isUnknown =
    plate === "NO PLATE FOUND" ||
    plate === "UNREADABLE";

  return (
    <span
      className={`inline-flex items-center px-4 py-1.5 rounded border-2 font-mono font-bold tracking-wider text-sm
        ${
          isUnknown
            ? "border-scan/50 text-scan bg-scan/5"
            : "border-ink/25 text-ink bg-panel2"
        }
        ${fresh ? "animate-flash" : ""}`}
    >
      {plate}
    </span>
  );
}