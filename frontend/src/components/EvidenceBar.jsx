// Evidence-strength indicator (spec section 31): a rubric over retrieval
// and verification quality, deliberately not phrased as "N% correct" --
// see backend/app/pipeline/evidence_score.py for why.
export default function EvidenceBar({ score }) {
  if (!score || typeof score.overall !== "number") return null;

  const overall = score.overall;
  const barColor = overall >= 70 ? "bg-emerald-500" : overall >= 40 ? "bg-amber-500" : "bg-red-500";
  const textColor = overall >= 70 ? "text-emerald-700" : overall >= 40 ? "text-amber-700" : "text-red-700";

  return (
    <div className="mt-3 rounded-xl border border-black/10 bg-black/[0.02] p-2.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-black/60">Evidence strength</span>
        <span className={`font-mono font-semibold ${textColor}`}>{overall}<span className="text-black/30">/100</span></span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-black/8">
        <div
          className={`h-full rounded-full ${barColor} transition-all duration-500 ease-out`}
          style={{ width: `${Math.max(0, Math.min(100, overall))}%` }}
        />
      </div>
      {score.components && (
        <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-black/8 pt-2 text-[11px] text-black/40">
          {Object.entries(score.components).map(([key, val]) => (
            <div key={key} className="flex justify-between">
              <span className="capitalize">{key.replace(/_/g, " ")}</span>
              <span className="font-mono text-black/55">{val}</span>
            </div>
          ))}
        </div>
      )}
      {score.note && <p className="mt-2 text-[11px] italic text-black/30">{score.note}</p>}
    </div>
  );
}
