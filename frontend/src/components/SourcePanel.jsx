import { useState } from "react";
import { IconChevron, IconExternal } from "./icons.jsx";

// Citation panel (spec section 34): lists the labelled sources a message's
// citations point back to. Labels here (S1, S2, ...) are exactly the ones
// the backend enforces in verify_answer -- see
// backend/app/pipeline/citation.py -- so this list is never a guess about
// what the model might have meant.
//
// Each source's exact text is expandable inline (the backend returns it
// untruncated for statute SECTIONs -- see chat.py's _source_out), and an
// "Official source" link opens the India Code PDF the text was extracted
// from. Added in response to user feedback: sources previously showed only
// a title, with no way to see the actual text of a cited section or verify
// it against the original.
function SourceItem({ s }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <li className="rounded-lg border border-ink-700/70 bg-ink-900/50 px-3 py-2 text-xs transition-colors duration-150">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 shrink-0 rounded-md bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-brass-300">
          {s.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-ink-200">{s.title}</div>
          <div className="mt-0.5 text-ink-500">
            {s.source_type}
            {s.act_name && s.section_no ? ` · ${s.act_name}, s.${s.section_no}` : ""}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            {s.text && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-1 font-medium text-brass-400 transition-colors duration-150 hover:text-brass-300"
              >
                <IconChevron className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
                {expanded ? "Hide text" : "Show exact text"}
              </button>
            )}
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 font-medium text-ink-400 transition-colors duration-150 hover:text-ink-200"
              >
                Official source <IconExternal />
              </a>
            )}
          </div>
        </div>
      </div>
      {expanded && s.text && (
        <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-ink-800 bg-ink-950 p-2.5 text-[11px] leading-relaxed text-ink-300">
          {s.text}
        </pre>
      )}
    </li>
  );
}

export default function SourcePanel({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <details className="mt-3.5 group" open>
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-xs font-medium text-ink-400 transition-colors duration-150 hover:text-ink-200">
        <IconChevron className="transition-transform duration-200 group-open:rotate-180" />
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
