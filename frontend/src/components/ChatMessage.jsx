import SourcePanel from "./SourcePanel.jsx";
import EvidenceBar from "./EvidenceBar.jsx";
import { IconWarning, IconClock, IconRetry } from "./icons.jsx";

function AbstainNotice({ reason }) {
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-amber-800/40 bg-amber-950/25 px-3 py-2 text-xs text-amber-300">
      <IconWarning className="mt-0.5 shrink-0" />
      <div>
        <span className="font-medium">Couldn't answer confidently. </span>
        {reason}
      </div>
    </div>
  );
}

// Spec section 20's conflict detection -- an OVERRULES/DISTINGUISHES edge
// found between two retrieved sources. Computed by the backend since Phase
// 7 but never rendered until now (the frontend silently dropped the field).
function ConflictNotice({ conflicts }) {
  if (!conflicts || conflicts.length === 0) return null;
  return (
    <div className="mt-2.5 space-y-1.5">
      {conflicts.map((c, i) => (
        <div key={i} className="flex items-start gap-2 rounded-lg border border-red-900/40 bg-red-950/20 px-3 py-2 text-xs text-red-300">
          <IconWarning className="mt-0.5 shrink-0" />
          <div>
            <span className="font-medium">Conflicting authority: </span>
            {c.reason}
            {c.stronger && <span className="text-red-400/80"> — {c.stronger} is the stronger authority.</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

// The IPC-to-BNS temporal bridge (Phase 9) -- also previously computed and
// discarded. Shown in a distinct "informational" tone, not a warning: it's
// context, not a problem with the answer.
function TemporalNotes({ notes }) {
  if (!notes || notes.length === 0) return null;
  return (
    <div className="mt-2.5 space-y-1.5">
      {notes.map((n, i) => (
        <div key={i} className="flex items-start gap-2 rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2 text-xs text-ink-300">
          <IconClock className="mt-0.5 shrink-0 text-brass-400" />
          <span>{n}</span>
        </div>
      ))}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-1">
      <span className="h-1.5 w-1.5 rounded-full bg-ink-400 animate-dot1" />
      <span className="h-1.5 w-1.5 rounded-full bg-ink-400 animate-dot2" />
      <span className="h-1.5 w-1.5 rounded-full bg-ink-400 animate-dot3" />
    </div>
  );
}

export default function ChatMessage({ message, onRetry }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-rise">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-brass-500 px-4 py-2.5 text-sm text-ink-950 shadow-bubble">
          {message.text}
        </div>
      </div>
    );
  }

  if (message.pending) {
    return (
      <div className="flex justify-start animate-rise">
        <div className="max-w-[75%] rounded-2xl rounded-bl-md bg-ink-850 px-4 py-3 shadow-bubble">
          <TypingIndicator />
        </div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div className="flex justify-start animate-rise">
        <div className="max-w-[75%] rounded-2xl rounded-bl-md border border-red-900/50 bg-red-950/30 px-4 py-2.5 text-sm text-red-300 shadow-bubble">
          <p>{message.error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-red-800/60 px-2.5 py-1 text-xs font-medium text-red-300 transition-colors duration-150 hover:bg-red-900/30"
            >
              <IconRetry /> Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start animate-rise">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-ink-850 px-4 py-3.5 text-sm text-ink-100 shadow-bubble">
        <p className="whitespace-pre-wrap leading-relaxed">{message.text}</p>
        {message.abstained && <AbstainNotice reason={message.abstain_reason} />}
        <ConflictNotice conflicts={message.conflicts} />
        <TemporalNotes notes={message.temporal_notes} />
        <SourcePanel sources={message.sources} />
        <EvidenceBar score={message.evidence_score} />
        {message.legal_domain && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-ink-500">
            <span className="rounded-full border border-ink-700 px-2 py-0.5 capitalize">{message.legal_domain}</span>
            {message.jurisdiction?.state && (
              <span className="rounded-full border border-ink-700 px-2 py-0.5">{message.jurisdiction.state}, India</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
