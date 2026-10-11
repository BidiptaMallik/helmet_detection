export default function Loader({ label = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10">
      <div className="h-10 w-10 rounded-full border-2 border-line border-t-safe animate-spin" />

      <span className="font-mono text-xs text-muted">
        {label}
      </span>
    </div>
  );
}