import { useState } from "react";
import { ArrowSquareOut, CaretDown } from "@phosphor-icons/react";

// Citation panel (spec section 34): lists the labelled sources a message's
// citations point back to. Labels here (S1, S2, ...) are exactly the ones
// the backend enforces in verify_answer -- see
// backend/app/pipeline/citation.py -- so this list is never a guess about
// what the model might have meant.
function SourceItem({ s }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <li className="rounded-xl border border-[var(--line)] bg-[var(--taupe)]/35 px-3 py-2 text-xs">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 shrink-0 rounded-md bg-[var(--taupe)]/55 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[var(--ink)]">
          {s.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-[var(--ink)]">{s.title}</div>
          <div className="mt-0.5 text-[var(--ink-muted)]">
            {s.source_type}
            {s.act_name && s.section_no ? ` · ${s.act_name}, s.${s.section_no}` : ""}
          </div>
          {s.supports?.length > 0 && (
            <div className="mt-2 border-l-2 border-[var(--sage)] pl-2 text-[11px] leading-relaxed text-[var(--ink-muted)]">
              <span className="font-semibold text-[var(--olive)]">Supports: </span>
              {s.supports[0]}
              {s.supports.length > 1 && <span className="text-[var(--ink-muted)]/70"> +{s.supports.length - 1} more claim{s.supports.length > 2 ? "s" : ""}</span>}
            </div>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            {s.text && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1 font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-colors duration-150"
              >
                <CaretDown size={12} weight="bold" className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
                {expanded ? "Hide text" : "Show exact text"}
              </button>
            )}
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 font-medium text-[var(--ink-muted)]/80 hover:text-[var(--ink)] transition-colors duration-150"
              >
                Official source <ArrowSquareOut size={11} weight="bold" />
              </a>
            )}
          </div>
        </div>
      </div>
      {expanded && s.text && (
        <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--line)] bg-[var(--paper)] p-2.5 text-[11px] leading-relaxed text-[var(--ink)]">
          {s.text}
        </pre>
      )}
    </li>
  );
}

export default function SourcePanel({ sources, mode }) {
  if (!sources || sources.length === 0) return null;

  const isResearch = mode === "Research";

  return (
    <details className="mt-4 group border-t border-[var(--line)] pt-3" open={isResearch || undefined}>
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-xs font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-colors duration-150">
        <CaretDown size={12} weight="bold" className="transition-transform duration-200 group-open:rotate-180" />
        {isResearch ? "Research sources and exact notes" : "Sources used"} ({sources.length})
      </summary>
      <ul className="mt-2 space-y-1.5">
        {sources.map((s) => (
          <SourceItem key={s.label} s={s} />
        ))}
      </ul>
    </details>
  );
}
