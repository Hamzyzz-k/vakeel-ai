import { useEffect, useRef } from "react";
import { Scale, ChevronRight, AlertTriangle, Clock, RotateCcw, FileText } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import SourcePanel from "./SourcePanel.jsx";
import EvidenceBar from "./EvidenceBar.jsx";

const QUICK_PROMPTS = [
  "A supplier breached a contract to deliver goods on time. What compensation can I claim?",
  "What are my rights if a seller ships goods that don't match the description?",
  "My landlord won't return my security deposit. What can I do?",
  "What is the punishment for murder under Section 302 IPC?",
];

// IRAC section headers (spec section 18) render on their own line in
// Research mode's final_answer -- bold them so the structure is scannable,
// same way the mockup's ** markdown got bolded, just driven by the
// backend's actual known header set instead of free-form markdown.
const IRAC_HEADERS = new Set(["ISSUE", "RULE", "AUTHORITIES", "APPLICATION", "COUNTERARGUMENT", "CONCLUSION"]);

function renderContent(text) {
  return text.split("\n").map((line, i) => {
    if (IRAC_HEADERS.has(line.trim())) {
      return (
        <div key={i} className="mt-3 first:mt-0 text-[10px] font-semibold uppercase tracking-widest text-black/35">
          {line.trim()}
        </div>
      );
    }
    return line ? <div key={i}>{line}</div> : <div key={i} className="h-2" />;
  });
}

function WelcomeView({ mode, onQuickPrompt }) {
  return (
    <motion.div
      key="welcome"
      initial={{ opacity: 0, y: 32 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col items-center justify-center h-full px-6 text-center select-none"
    >
      <div className="w-14 h-14 rounded-2xl bg-black flex items-center justify-center mb-6 shadow-lg">
        <Scale className="w-7 h-7 text-white" />
      </div>
      <h2 className="text-3xl font-semibold text-black mb-2 tracking-tight font-serif">Your AI Legal Advisor</h2>
      <p className="text-black/42 text-sm max-w-sm mb-10 leading-relaxed">
        Ask legal questions about Indian law, review documents, and get cited, verifiable answers — currently in{" "}
        <span className="font-semibold text-black/60">{mode}</span> mode.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-md w-full">
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onQuickPrompt(prompt)}
            className="text-left px-4 py-3.5 rounded-2xl border border-black/10 text-sm text-black/58 hover:border-black/28 hover:text-black/80 hover:bg-black/2 transition-all duration-150 group"
          >
            <span>{prompt}</span>
            <ChevronRight className="inline w-3.5 h-3.5 ml-1 opacity-35 group-hover:opacity-60 transition-opacity" />
          </button>
        ))}
      </div>
    </motion.div>
  );
}

function AbstainNotice({ reason }) {
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <div>
        <span className="font-medium">Couldn't answer confidently. </span>
        {reason}
      </div>
    </div>
  );
}

function ConflictNotice({ conflicts }) {
  if (!conflicts || conflicts.length === 0) return null;
  return (
    <div className="mt-2.5 space-y-1.5">
      {conflicts.map((c, i) => (
        <div key={i} className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <div>
            <span className="font-medium">Conflicting authority: </span>
            {c.reason}
            {c.stronger && <span className="text-red-700/80"> — {c.stronger} is the stronger authority.</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function TemporalNotes({ notes }) {
  if (!notes || notes.length === 0) return null;
  return (
    <div className="mt-2.5 space-y-1.5">
      {notes.map((n, i) => (
        <div key={i} className="flex items-start gap-2 rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2 text-xs text-black/60">
          <Clock className="w-3.5 h-3.5 mt-0.5 shrink-0 text-black/35" />
          <span>{n}</span>
        </div>
      ))}
    </div>
  );
}

function DocumentAnalysisCard({ analysis }) {
  return (
    <div className="mt-1 space-y-2.5">
      <p className="text-sm text-black/70">
        Analyzed <span className="font-medium text-black">{analysis.filename}</span> — {analysis.n_clauses} clause
        {analysis.n_clauses === 1 ? "" : "s"} detected.
      </p>
      {analysis.detected_topics.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-black/35 mb-1">Covered</p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.detected_topics.map((t) => (
              <span key={t} className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {analysis.missing_topics.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-black/35 mb-1">Not addressed</p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.missing_topics.map((t) => (
              <span key={t} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs font-medium text-black/45 hover:text-black transition-colors duration-150">
          Clause-by-clause detail
        </summary>
        <ul className="mt-2 space-y-1.5">
          {analysis.clauses.map((c, i) => (
            <li key={i} className="rounded-xl border border-black/10 bg-black/[0.02] px-3 py-2 text-xs">
              <div className="font-medium text-black/75">
                {c.heading || (c.number ? `Clause ${c.number}` : "Clause")}
              </div>
              <div className="mt-0.5 text-black/40 line-clamp-2">{c.text}</div>
              {c.detected_topics.length > 0 && (
                <div className="mt-1 text-black/35">{c.detected_topics.join(", ")}</div>
              )}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function MessageBubble({ msg, onRetry }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        className="flex justify-end"
      >
        <div className="max-w-[72%] px-4 py-3 text-sm leading-relaxed bg-black text-white rounded-3xl rounded-br-lg">
          {msg.text}
        </div>
      </motion.div>
    );
  }

  if (msg.error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-start items-end gap-2.5"
      >
        <div className="w-7 h-7 rounded-full bg-black flex items-center justify-center flex-shrink-0 mb-0.5">
          <Scale className="w-3.5 h-3.5 text-white" />
        </div>
        <div className="max-w-[80%] px-4 py-3 text-sm bg-red-50 border border-red-200 text-red-800 rounded-3xl rounded-bl-lg">
          <p>{msg.error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-100 transition-colors duration-150"
            >
              <RotateCcw className="w-3 h-3" /> Retry
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="flex justify-start items-end gap-2.5"
    >
      <div className="w-7 h-7 rounded-full bg-black flex items-center justify-center flex-shrink-0 mb-0.5">
        {msg.isDocumentAnalysis ? (
          <FileText className="w-3.5 h-3.5 text-white" />
        ) : (
          <Scale className="w-3.5 h-3.5 text-white" />
        )}
      </div>
      <div className="flex flex-col items-start max-w-[85%]">
        {msg.mode && !msg.isDocumentAnalysis && (
          <span className="inline-flex items-center text-[10px] font-semibold uppercase tracking-widest text-black/35 mb-1.5 px-2.5 py-0.5 border border-black/12 rounded-full bg-white">
            {msg.mode}
          </span>
        )}
        <div className="px-4 py-3 text-sm leading-relaxed bg-white border border-black/10 text-black rounded-3xl rounded-bl-lg shadow-sm w-full">
          {msg.isDocumentAnalysis ? (
            <DocumentAnalysisCard analysis={msg.analysis} />
          ) : (
            <>
              <div>{renderContent(msg.text)}</div>
              {msg.abstained && <AbstainNotice reason={msg.abstain_reason} />}
              <ConflictNotice conflicts={msg.conflicts} />
              <TemporalNotes notes={msg.temporal_notes} />
              <SourcePanel sources={msg.sources} />
              <EvidenceBar score={msg.evidence_score} />
              {msg.legal_domain && (
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-black/40">
                  <span className="rounded-full border border-black/10 px-2 py-0.5 capitalize">{msg.legal_domain}</span>
                  {msg.jurisdiction?.state && (
                    <span className="rounded-full border border-black/10 px-2 py-0.5">{msg.jurisdiction.state}, India</span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function ChatArea({ activeId, messages, isTyping, mode, onQuickPrompt, onRetry }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const isWelcome = activeId === null;

  return (
    <div className="flex-1 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden relative">
      <AnimatePresence mode="wait">
        {isWelcome ? (
          <WelcomeView key="welcome" mode={mode} onQuickPrompt={onQuickPrompt} />
        ) : (
          <motion.div
            key={activeId}
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
            className="max-w-2xl mx-auto px-4 py-8 space-y-6"
          >
            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} onRetry={msg.retryQuestion ? () => onRetry(msg) : null} />
            ))}

            {isTyping && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex items-end gap-2.5 justify-start">
                <div className="w-7 h-7 rounded-full bg-black flex items-center justify-center flex-shrink-0">
                  <Scale className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="px-4 py-3.5 bg-white border border-black/10 rounded-3xl rounded-bl-lg shadow-sm">
                  <div className="flex gap-1 items-center">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-black/30 animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.9s" }}
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            )}

            <div ref={bottomRef} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
