// Evidence-strength indicator (spec section 31): a rubric over retrieval
// and verification quality, deliberately not phrased as "N% correct" --
// see backend/app/pipeline/evidence_score.py for why.
export default function EvidenceBar({ score }) {
  if (!score || typeof score.overall !== "number") return null;

  const overall = score.overall;
  const tone =
    overall >= 70
      ? { bar: "bg-emerald-400", text: "text-emerald-400" }
      : overall >= 40
      ? { bar: "bg-brass-400", text: "text-brass-400" }
      : { bar: "bg-red-400", text: "text-red-400" };

  return (
    <div className="mt-3.5 rounded-lg border border-ink-700/70 bg-ink-900/50 p-2.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ink-300">Evidence strength</span>
        <span className={`font-mono font-semibold ${tone.text}`}>{overall}<span className="text-ink-500">/100</span></span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
        <div
          className={`h-full rounded-full ${tone.bar} transition-all duration-500 ease-out`}
          style={{ width: `${Math.max(0, Math.min(100, overall))}%` }}
        />
      </div>
      {score.components && (
        <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-ink-800 pt-2 text-[11px] text-ink-500">
          {Object.entries(score.components).map(([key, val]) => (
            <div key={key} className="flex justify-between">
              <span className="capitalize">{key.replace(/_/g, " ")}</span>
              <span className="font-mono text-ink-400">{val}</span>
            </div>
          ))}
        </div>
      )}
      {score.note && <p className="mt-2 text-[11px] italic text-ink-600">{score.note}</p>}
    </div>
  );
}
