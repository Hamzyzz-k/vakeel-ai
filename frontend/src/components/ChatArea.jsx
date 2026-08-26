import { useEffect, useRef } from "react";
import {
  ArrowCounterClockwise,
  ArrowRight,
  BookOpen,
  Clock,
  FileText,
  Question,
  Scales,
  Warning,
} from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import SourcePanel from "./SourcePanel.jsx";

const QUICK_PROMPTS = [
  "A supplier breached a contract to deliver goods on time. What compensation can I claim?",
  "What are my rights if a seller ships goods that don't match the description?",
  "A product I bought is defective and the seller refuses a refund. What does the law provide?",
  "What is the punishment for murder under Section 302 IPC?",
];

// IRAC section headers (spec section 18) render on their own line in
// Research mode's final_answer -- bold them so the structure is scannable,
// same way the mockup's ** markdown got bolded, just driven by the
// backend's actual known header set instead of free-form markdown.
const IRAC_HEADERS = new Set(["ISSUE", "RULE", "AUTHORITIES", "APPLICATION", "COUNTERARGUMENT", "CONCLUSION"]);

const ACT_NAMES = {
  contract_act_1872: "Indian Contract Act, 1872",
  sale_of_goods_act_1930: "Sale of Goods Act, 1930",
  consumer_protection_act_2019: "Consumer Protection Act, 2019",
  bns_2023: "Bharatiya Nyaya Sanhita, 2023",
};

function formatSourceId(sourceId) {
  const match = sourceId.match(/^indiacode:([^:]+):s(.+)$/);
  if (!match) return sourceId;
  return `${ACT_NAMES[match[1]] || match[1].replaceAll("_", " ")}, Section ${match[2]}`;
}

function renderContent(text) {
  return text.split("\n").map((line, i) => {
    if (IRAC_HEADERS.has(line.trim())) {
      return (
        <div key={i} className="mt-3 first:mt-0 text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]/70">
          {line.trim()}
        </div>
      );
    }
    return line ? <div key={i}>{line}</div> : <div key={i} className="h-2" />;
  });
}

function WelcomeView({ mode, onQuickPrompt }) {
  const isResearch = mode === "Research";
  return (
    <motion.div
      key="welcome"
      initial={{ opacity: 0, y: 32 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col justify-center h-full px-5 sm:px-8 select-none max-w-3xl mx-auto w-full"
    >
      <div className={`mb-6 flex h-12 w-12 items-center justify-center rounded-2xl shadow-[0_12px_32px_rgba(53,67,46,0.13)] ${isResearch ? "bg-[var(--olive-dark)] text-[var(--ivory)]" : "bg-[var(--taupe)] text-[var(--olive-dark)]"}`}>
        {isResearch ? <BookOpen size={26} weight="duotone" /> : <Scales size={27} weight="bold" />}
      </div>
      <h2 className="text-3xl sm:text-4xl font-semibold text-[var(--ink)] mb-3 tracking-[-0.035em]">
        {isResearch ? "Build a sourced legal research note" : "Tell me what happened"}
      </h2>
      <p className="text-[var(--ink-muted)] text-sm sm:text-base max-w-xl mb-6 leading-relaxed">
        {isResearch
          ? "Get a structured issue, rule, authorities, application, alternative view, and conclusion—with the exact source text open beside the note."
          : "Get a direct explanation of what the loaded law means for your facts, what you can do next, and which missing detail could change the answer."}
      </p>
      <div className="flex items-start gap-2.5 border-l-2 border-[var(--sage)] pl-3 mb-8 max-w-xl text-xs leading-relaxed text-[var(--ink-muted)]">
        <BookOpen className="w-4 h-4 mt-0.5 shrink-0 text-[var(--olive)]" />
        <span>Current coverage: Contract Act, Sale of Goods Act, Consumer Protection Act, and Bharatiya Nyaya Sanhita. Unsupported areas are refused instead of matched to unrelated law.</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-w-2xl w-full">
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onQuickPrompt(prompt)}
            className="text-left px-4 py-3.5 rounded-2xl border border-[var(--line)] bg-[var(--ivory)] text-sm text-[var(--ink-muted)] hover:border-[var(--olive)] hover:text-[var(--ink)] hover:bg-[var(--taupe)]/45 transition-all duration-200 active:scale-[0.99] group"
          >
            <span>{prompt}</span>
            <ArrowRight size={14} weight="bold" className="inline ml-1 opacity-35 group-hover:opacity-60 transition-opacity" />
          </button>
        ))}
      </div>
    </motion.div>
  );
}

function AbstainNotice({ reason }) {
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <Warning size={15} weight="fill" className="mt-0.5 shrink-0" />
      <div>
        <span className="font-medium">Reliability safeguard applied. </span>
        No unsupported answer or unrelated authority was substituted.
      </div>
    </div>
  );
}

function MissingInformation({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-3 border-t border-[var(--line)] pt-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]/75">
        <Question size={15} weight="bold" />
        To make this answer specific
      </div>
      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-[var(--ink-muted)]">
        {items.slice(0, 4).map((item, index) => <li key={index}>— {item}</li>)}
      </ul>
    </div>
  );
}

function GenerationNotice({ mode }) {
  if (mode !== "extractive_fallback") return null;
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-relaxed text-sky-900">
      <BookOpen size={15} weight="bold" className="mt-0.5 shrink-0" />
      <span><span className="font-semibold">Source-only mode.</span> The language model was unavailable for this response, so the app is showing exact retrieved law instead of guessing.</span>
    </div>
  );
}

function ConflictNotice({ conflicts }) {
  if (!conflicts || conflicts.length === 0) return null;
  return (
    <div className="mt-2.5 space-y-1.5">
      {conflicts.map((c, i) => (
        <div key={i} className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          <Warning size={15} weight="fill" className="mt-0.5 shrink-0" />
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
        <div key={i} className="flex items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--olive)]/[0.025] px-3 py-2 text-xs text-[var(--ink-muted)]">
          <Clock size={15} weight="bold" className="mt-0.5 shrink-0 text-[var(--ink-muted)]/70" />
          <span>{n}</span>
        </div>
      ))}
    </div>
  );
}

function DocumentAnalysisCard({ analysis }) {
  return (
    <div className="mt-1 space-y-2.5">
      <p className="text-sm text-[var(--ink)]/75">
        Analyzed <span className="font-medium text-[var(--ink)]">{analysis.filename}</span> — {analysis.n_clauses} clause
        {analysis.n_clauses === 1 ? "" : "s"} detected.
      </p>
      {analysis.detected_topics.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]/70 mb-1">Covered</p>
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
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]/70 mb-1">Not addressed</p>
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
        <summary className="cursor-pointer text-xs font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-colors duration-150">
          Clause-by-clause detail
        </summary>
        <ul className="mt-2 space-y-1.5">
          {analysis.clauses.map((c, i) => (
            <li key={i} className="rounded-xl border border-[var(--line)] bg-[var(--olive)]/[0.025] px-3 py-2 text-xs">
              <div className="font-medium text-[var(--ink)]/80">
                {c.heading || (c.number ? `Clause ${c.number}` : "Clause")}
              </div>
              <div className="mt-0.5 text-[var(--ink-muted)]/80 line-clamp-2">{c.text}</div>
              {c.detected_topics.length > 0 && (
                <div className="mt-1 text-[var(--ink-muted)]/70">{c.detected_topics.join(", ")}</div>
              )}
              {c.relevant_source_ids?.length > 0 && (
                <div className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] text-[var(--ink-muted)]">
                  <span className="font-semibold text-[var(--olive)]">Relevant provisions: </span>
                  {c.relevant_source_ids.slice(0, 3).map(formatSourceId).join(" · ")}
                </div>
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
        <div className="max-w-[88%] px-4 py-3 text-sm leading-relaxed bg-[var(--olive-dark)] text-[var(--ivory)] rounded-3xl rounded-br-lg sm:max-w-[72%]">
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
        <div className="w-7 h-7 rounded-full bg-[var(--olive)] flex items-center justify-center flex-shrink-0 mb-0.5">
          <Scales size={15} weight="bold" className="text-white" />
        </div>
        <div className="max-w-[80%] px-4 py-3 text-sm bg-red-50 border border-red-200 text-red-800 rounded-3xl rounded-bl-lg">
          <p>{msg.error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-100 transition-colors duration-150"
            >
              <ArrowCounterClockwise size={13} weight="bold" /> Retry
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
      <div className="w-7 h-7 rounded-full bg-[var(--olive)] flex items-center justify-center flex-shrink-0 mb-0.5">
        {msg.isDocumentAnalysis ? (
          <FileText size={15} weight="bold" className="text-white" />
        ) : (
          <Scales size={15} weight="bold" className="text-white" />
        )}
      </div>
      <div className="flex max-w-[calc(100%-2.4rem)] flex-col items-start sm:max-w-[85%]">
        {msg.mode && !msg.isDocumentAnalysis && (
          <span className="inline-flex items-center text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)] mb-1.5 px-2.5 py-0.5 border border-[var(--line)] rounded-full bg-[var(--paper)]">
            {msg.mode === "Research" ? "Research note" : "Advice reply"}
          </span>
        )}
        <div className="px-4 py-3 text-sm leading-relaxed bg-[var(--paper)] border border-[var(--line)] text-[var(--ink)] rounded-3xl rounded-bl-lg shadow-sm w-full">
          {msg.isDocumentAnalysis ? (
            <DocumentAnalysisCard analysis={msg.analysis} />
          ) : (
            <>
              <div>{renderContent(msg.text)}</div>
              <GenerationNotice mode={msg.generation_mode} />
              {msg.abstained && <AbstainNotice reason={msg.abstain_reason} />}
              <ConflictNotice conflicts={msg.conflicts} />
              <TemporalNotes notes={msg.temporal_notes} />
              {!msg.abstained && <MissingInformation items={msg.missing_information} />}
              <SourcePanel sources={msg.sources} mode={msg.mode} />
              {msg.legal_domain && (
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-[var(--ink-muted)]/80">
                  <span className="rounded-full border border-[var(--line)] px-2 py-0.5 capitalize">{msg.legal_domain}</span>
                  {msg.jurisdiction?.state && (
                    <span className="rounded-full border border-[var(--line)] px-2 py-0.5">{msg.jurisdiction.state}, India</span>
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
                <div className="w-7 h-7 rounded-full bg-[var(--olive)] flex items-center justify-center flex-shrink-0">
                  <Scales size={15} weight="bold" className="text-white" />
                </div>
                <div className="px-4 py-3.5 bg-[var(--paper)] border border-[var(--line)] rounded-3xl rounded-bl-lg shadow-sm">
                  <div className="flex gap-1 items-center">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-[var(--sage)] animate-bounce"
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
