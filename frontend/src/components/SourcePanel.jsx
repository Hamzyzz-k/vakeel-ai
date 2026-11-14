import { useEffect, useRef, useState } from "react";
import { ArrowSquareOut, CaretDown } from "@phosphor-icons/react";

// Citation panel (spec section 34): lists the labelled sources a message's
// citations point back to. Labels here (S1, S2, ...) are exactly the ones
// the backend enforces in verify_answer -- see
// backend/app/pipeline/citation.py -- so this list is never a guess about
// what the model might have meant.
function SourceItem({ s, focus }) {
  const [expanded, setExpanded] = useState(false);
  const [flash, setFlash] = useState(false);
  const itemRef = useRef(null);

  // Clicking an inline citation in the answer opens that section's exact
  // text here and marks it briefly, so the reader sees what was cited.
  useEffect(() => {
    if (!focus || focus.label !== s.label) return undefined;
    setExpanded(true);
    setFlash(true);
    itemRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    const timer = window.setTimeout(() => setFlash(false), 1400);
    return () => window.clearTimeout(timer);
  }, [focus, s.label]);

  return (
    <li
      ref={itemRef}
      className={`rounded-[2px] border px-3 py-2.5 text-xs transition-colors duration-500 ${
        flash ? "border-[var(--ink)] bg-[var(--sage-soft)]" : "border-[var(--line)] bg-[var(--canvas)]"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-px shrink-0 rounded-[2px] border border-[var(--line-strong)] bg-[var(--paper)] px-1.5 py-0.5 font-mono text-[10px] font-medium text-[var(--ink)]">
          {s.label}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-medium leading-snug text-[var(--ink)]">{s.title}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
            {s.text && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
                className="flex items-center gap-1 font-medium text-[var(--ink-muted)] transition-colors duration-150 hover:text-[var(--ink)]"
              >
                <CaretDown size={12} weight="bold" className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
                {expanded ? "Hide exact text" : "Show exact text"}
              </button>
            )}
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 font-medium text-[var(--ink-muted)] transition-colors duration-150 hover:text-[var(--ink)]"
              >
                Official source <ArrowSquareOut size={11} weight="bold" />
              </a>
            )}
          </div>
        </div>
      </div>
      {expanded && s.text && (
        <pre className="mt-2.5 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-[2px] border border-[var(--line)] bg-[var(--paper)] p-3 font-sans text-[11.5px] leading-relaxed text-[var(--ink)]">
          {s.text}
        </pre>
      )}
    </li>
  );
}

// Always open: the cited law is the product's evidence, not an extra.
export default function SourcePanel({ sources, focus }) {
  if (!sources || sources.length === 0) return null;

  return (
    <section aria-label="Cited law" className="mt-4 border-t border-[var(--line)] pt-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
        Cited law
      </h3>
      <ul className="mt-2 space-y-1.5">
        {sources.map((s) => (
          <SourceItem key={s.label} s={s} focus={focus} />
        ))}
      </ul>
    </section>
  );
}
