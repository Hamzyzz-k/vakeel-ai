import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";

// Citation panel (spec section 34): lists the labelled sources a message's
// citations point back to. Labels here (S1, S2, ...) are exactly the ones
// the backend enforces in verify_answer -- see
// backend/app/pipeline/citation.py -- so this list is never a guess about
// what the model might have meant.
function SourceItem({ s }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <li className="rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2 text-xs">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 shrink-0 rounded-md bg-black/8 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-black/70">
          {s.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-black/80">{s.title}</div>
          <div className="mt-0.5 text-black/40">
            {s.source_type}
            {s.act_name && s.section_no ? ` · ${s.act_name}, s.${s.section_no}` : ""}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            {s.text && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1 font-medium text-black/55 hover:text-black transition-colors duration-150"
              >
                <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
                {expanded ? "Hide text" : "Show exact text"}
              </button>
            )}
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 font-medium text-black/40 hover:text-black transition-colors duration-150"
              >
                Official source <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </div>
        </div>
      </div>
      {expanded && s.text && (
        <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-black/10 bg-white p-2.5 text-[11px] leading-relaxed text-black/70">
          {s.text}
        </pre>
      )}
    </li>
  );
}

export default function SourcePanel({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <details className="mt-3 group" open>
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-xs font-medium text-black/45 hover:text-black transition-colors duration-150">
        <ChevronDown className="w-3 h-3 transition-transform duration-200 group-open:rotate-180" />
        Sources ({sources.length})
      </summary>
      <ul className="mt-2 space-y-1.5">
        {sources.map((s) => (
          <SourceItem key={s.label} s={s} />
        ))}
      </ul>
    </details>
  );
}
