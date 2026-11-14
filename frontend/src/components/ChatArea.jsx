import { useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  ArrowRight,
  BookOpen,
  Check,
  Clock,
  FileText,
  Question,
  Scales,
  SealCheck,
  Warning,
} from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import SourcePanel from "./SourcePanel.jsx";

const QUICK_PROMPTS = [
  "A supplier breached a contract to deliver goods on time. What compensation can I claim?",
  "What are my rights if a seller ships goods that don't match the description?",
  "A product I bought is defective and the seller refuses a refund. What does the law provide?",
  "What is the punishment for murder under Section 302 IPC?",
  "My motorcycle was stopped for no helmet. What does the Motor Vehicles Act require?",
  "What does CMVR Rule 62 say about a transport vehicle's fitness certificate?",
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
  motor_vehicles_act_1988: "Motor Vehicles Act, 1988",
  central_motor_vehicles_rules_1989: "Central Motor Vehicles Rules, 1989",
  karnataka_motor_vehicles_rules_1989: "Karnataka Motor Vehicles Rules, 1989",
};

function formatSourceId(sourceId) {
  const match = sourceId.match(/^indiacode:([^:]+):([sra])(.+)$/);
  if (!match) return sourceId;
  const labels = { s: "Section", r: "Rule", a: "Article" };
  return `${ACT_NAMES[match[1]] || match[1].replaceAll("_", " ")}, ${labels[match[2]]} ${match[3]}`;
}

const CITATION = /\[(S\d+(?:\s*,\s*S\d+)*)\]/g;

// "[S1]" in the verified answer becomes a button that opens that exact
// section under "Cited law", instead of an opaque bracketed code.
function CitationMark({ label, source, onCite }) {
  if (!source || !onCite) {
    return <span className="mx-0.5 font-mono text-[10px] text-[var(--ink-muted)]">{label}</span>;
  }
  return (
    <button
      type="button"
      onClick={() => onCite(label)}
      title={source.title}
      aria-label={`Show cited law ${label}: ${source.title}`}
      className="mx-0.5 inline-flex -translate-y-px items-center rounded-[2px] border border-[var(--line-strong)] bg-[var(--canvas)] px-1 align-baseline font-mono text-[10px] font-medium leading-[1.4] text-[var(--ink)] transition-colors duration-150 hover:border-[var(--ink)] hover:bg-[var(--ink)] hover:text-[var(--paper)]"
    >
      {label}
    </button>
  );
}

function withCitations(line, sources, onCite) {
  const parts = [];
  let last = 0;
  for (const match of line.matchAll(CITATION)) {
    if (match.index > last) parts.push(line.slice(last, match.index));
    match[1].split(/\s*,\s*/).forEach((label) => {
      parts.push(
        <CitationMark
          key={`${match.index}-${label}`}
          label={label}
          source={sources?.find((s) => s.label === label)}
          onCite={onCite}
        />,
      );
    });
    last = match.index + match[0].length;
  }
  parts.push(line.slice(last));
  return parts;
}

function renderContent(text, sources, onCite) {
  return text.split("\n").map((line, i) => {
    if (IRAC_HEADERS.has(line.trim())) {
      return (
        <div key={i} className="mt-4 first:mt-0 text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]">
          {line.trim()}
        </div>
      );
    }
    return line ? <p key={i}>{withCitations(line, sources, onCite)}</p> : <div key={i} className="h-2" />;
  });
}

function sentenceCase(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

// Intake returns snake_case keys ("criminal_procedure").
function areaLabel(domain) {
  return sentenceCase(domain.replaceAll("_", " "));
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
      className="workspace-content-app mx-auto flex h-full w-full max-w-3xl select-none flex-col justify-center px-5 sm:px-8"
    >
      <div className={`mb-6 flex h-12 w-12 items-center justify-center shadow-[6px_6px_0_rgba(0,0,0,0.12)] ${isResearch ? "bg-[var(--olive-dark)] text-[var(--ivory)]" : "bg-[var(--taupe)] text-[var(--olive-dark)]"}`}>
        {isResearch ? <BookOpen size={26} weight="duotone" /> : <Scales size={27} weight="bold" />}
      </div>
      <p className="mb-5 inline-block w-fit border-b border-[var(--forest)] pb-1 font-mono text-[9px] uppercase tracking-[0.1em] text-[var(--forest)]">Citation-verified legal information</p>
      <h2 className="mb-3 font-serif text-5xl font-semibold leading-[0.86] tracking-[-0.055em] text-[var(--ink)] sm:text-7xl">
        {isResearch ? "Build a sourced legal research note" : "Tell me what happened"}
      </h2>
      <p className="text-[var(--ink-muted)] text-sm sm:text-base max-w-xl mb-6 leading-relaxed">
        {isResearch
          ? "Get a structured issue, rule, authorities, application, alternative view, and conclusion—with the exact source text open beside the note."
          : "Get a direct explanation of what the loaded law means for your facts, what you can do next, and which missing detail could change the answer."}
      </p>
      <div className="flex items-start gap-2.5 border-l-2 border-[var(--sage)] pl-3 mb-8 max-w-xl text-xs leading-relaxed text-[var(--ink-muted)]">
        <BookOpen className="w-4 h-4 mt-0.5 shrink-0 text-[var(--olive)]" />
        <span>Current coverage: 22 verified central and Karnataka statutes. Unsupported areas are refused instead of matched to unrelated law.</span>
      </div>
      <div className="w-full max-w-2xl border-t border-[var(--line)]">
        {QUICK_PROMPTS.map((prompt, index) => (
          <button
            key={prompt}
            onClick={() => onQuickPrompt(prompt)}
            className="group grid w-full grid-cols-[30px_1fr_18px] items-center gap-3 border-b border-[var(--line)] bg-transparent px-2 py-4 text-left text-sm text-[var(--ink-muted)] transition-all duration-200 hover:px-4 hover:text-[var(--forest)] active:scale-[0.99]"
          >
            <span className="font-mono text-[9px] text-[var(--stone)]">{String(index + 1).padStart(2, "0")}</span>
            <span>{prompt}</span>
            <ArrowRight size={14} weight="bold" className="opacity-35 transition-all group-hover:translate-x-1 group-hover:opacity-70" />
          </button>
        ))}
      </div>
    </motion.div>
  );
}

// Real pipeline stages from the streaming route, in order. Each is shown
// only once the backend reports that it has started.
const LIVE_STAGES = {
  reading: "Reading your question",
  searching: "Searching the loaded laws",
  writing: "Writing the answer",
  checking: "Checking every citation",
};
const STAGE_ORDER = Object.keys(LIVE_STAGES);

const CARD_SHADOW = "0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.05)";

function WorkingStatus({ mode, stage }) {
  if (mode === "chat") {
    // Before the first event arrives the question is, truthfully, being read.
    const current = stage && LIVE_STAGES[stage.stage] ? stage.stage : "reading";
    return <StageList current={current} found={stage?.sources || []} />;
  }
  return <RotatingStatus mode={mode} />;
}

function StatusShell({ children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-end gap-2.5 justify-start"
      role="status"
      aria-live="polite"
    >
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[2px] bg-[var(--ink)]">
        <Scales size={15} weight="bold" className="text-[var(--canvas)]" />
      </div>
      <div className="rounded-[2px] border border-[var(--line)] bg-[var(--paper)] px-4 py-3" style={{ boxShadow: CARD_SHADOW }}>
        {children}
      </div>
    </motion.div>
  );
}

// All four real steps at once: finished ones ticked, the current one
// marked, the rest waiting -- so progress reads as progress.
function StageList({ current, found }) {
  const index = STAGE_ORDER.indexOf(current);
  return (
    <StatusShell>
      <ol className="space-y-1.5">
        {STAGE_ORDER.map((key, i) => {
          const state = i < index ? "done" : i === index ? "current" : "pending";
          return (
            <li
              key={key}
              aria-current={state === "current" ? "step" : undefined}
              className={`flex items-center gap-2 text-xs ${
                state === "current" ? "font-semibold text-[var(--ink)]" : "text-[var(--ink-muted)]"
              }`}
            >
              <span className="flex h-3 w-3 items-center justify-center" aria-hidden="true">
                {state === "done" && <Check size={12} weight="bold" className="text-[var(--ink)]" />}
                {state === "current" && <span className="h-1.5 w-1.5 rounded-full bg-[var(--ink)] animate-pulse" />}
                {state === "pending" && <span className="h-1.5 w-1.5 rounded-full border border-[var(--stone)]" />}
              </span>
              {LIVE_STAGES[key]}
              <span className="sr-only">{state === "done" ? "(done)" : state === "pending" ? "(waiting)" : "(in progress)"}</span>
            </li>
          );
        })}
      </ol>
      {found.length > 0 && (
        <p className="mt-2.5 max-w-sm border-t border-[var(--line)] pt-2 text-[11px] leading-relaxed text-[var(--ink-muted)]">
          Found: {found.slice(0, 3).join("; ")}
        </p>
      )}
    </StatusShell>
  );
}

function StatusBubble({ label, detail }) {
  return (
    <StatusShell>
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--ink)] animate-pulse" />
        <span className="text-xs font-semibold text-[var(--ink)]">{label}</span>
      </div>
      <p className="mt-1 text-[11px] text-[var(--ink-muted)]">{detail}</p>
    </StatusShell>
  );
}

// Used while waking the server, for document uploads, and before the first
// real stage arrives (or against a backend without the streaming route).
function RotatingStatus({ mode }) {
  const [step, setStep] = useState(0);
  const stages = mode === "waking"
    ? [["Waking the server", "The free host sleeps when idle, so this first answer can take up to a minute"]]
    : mode === "document"
    ? [
        ["Reading the uploaded document", "Extracting clauses and headings"],
        ["Checking clause structure", "Separating sections without changing the text"],
        ["Mapping legal topics", "Matching only against loaded sources"],
      ]
    : [
        ["Reading your question", "Identifying the legal issue and jurisdiction"],
        ["Searching the loaded laws", "Retrieving the strongest sections and rules"],
        ["Checking source text", "Testing that each citation supports the claim"],
        ["Preparing the answer", "Writing a clear response with the limits made visible"],
      ];

  useEffect(() => {
    setStep(0);
    const timer = window.setInterval(() => setStep((current) => (current + 1) % stages.length), 2800);
    return () => window.clearInterval(timer);
  }, [mode, stages.length]);

  const [label, detail] = stages[step];
  return <StatusBubble label={label} detail={detail} />;
}

// Sentences the model wrote that no supplied section backs (often practical
// steps). Kept out of the answer and collapsed, so they read as unchecked
// suggestions, never as verified law.
function UnverifiedNotes({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <details className="group mt-3 border-t border-[var(--line)] pt-3">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)] hover:text-[var(--ink-muted)]">
        <Warning size={15} weight="bold" />
        Not verified against the loaded law ({items.length})
      </summary>
      <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--ink-muted)]">
        The model also wrote these, but none of the cited sections states them. Treat them as unchecked suggestions.
      </p>
      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-[var(--ink-muted)]">
        {items.map((item, index) => <li key={index}>— {item}</li>)}
      </ul>
    </details>
  );
}

function AbstainNotice({ reason }) {
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-[2px] border border-[var(--line-strong)] bg-[var(--canvas)] px-3 py-2 text-xs text-[var(--ink-muted)]">
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
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
        <Question size={15} weight="bold" />
        To make this answer specific
      </div>
      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-[var(--ink-muted)]">
        {items.slice(0, 4).map((item, index) => <li key={index}>— {sentenceCase(item)}</li>)}
      </ul>
    </div>
  );
}

function GenerationNotice({ mode }) {
  if (mode !== "extractive_fallback") return null;
  return (
    <div className="mt-2.5 flex items-start gap-2 rounded-[2px] border border-[var(--line-strong)] bg-[var(--canvas)] px-3 py-2 text-xs leading-relaxed text-[var(--ink-muted)]">
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
        <div key={i} className="flex items-start gap-2 rounded-[2px] border border-[var(--line-strong)] bg-[var(--canvas)] px-3 py-2 text-xs text-[var(--ink-muted)]">
          <Warning size={15} weight="fill" className="mt-0.5 shrink-0" />
          <div>
            <span className="font-medium">Conflicting authority: </span>
            {c.reason}
            {c.stronger && <span> — {c.stronger} is the stronger authority.</span>}
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
        <div key={i} className="flex items-start gap-2 rounded-[2px] border border-[var(--line)] bg-[var(--olive)]/[0.025] px-3 py-2 text-xs text-[var(--ink-muted)]">
          <Clock size={15} weight="bold" className="mt-0.5 shrink-0 text-[var(--ink-muted)]" />
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
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)] mb-1">Covered</p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.detected_topics.map((t) => (
              <span key={t} className="rounded-full border border-[var(--line-strong)] bg-[var(--canvas)] px-2 py-0.5 text-[11px] text-[var(--ink-muted)]">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {analysis.missing_topics.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)] mb-1">Not addressed</p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.missing_topics.map((t) => (
              <span key={t} className="rounded-full border border-[var(--line-strong)] bg-[var(--canvas)] px-2 py-0.5 text-[11px] text-[var(--ink-muted)]">
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
            <li key={i} className="rounded-[2px] border border-[var(--line)] bg-[var(--olive)]/[0.025] px-3 py-2 text-xs">
              <div className="font-medium text-[var(--ink)]/80">
                {c.heading || (c.number ? `Clause ${c.number}` : "Clause")}
              </div>
              <div className="mt-0.5 text-[var(--ink-muted)] line-clamp-2">{c.text}</div>
              {c.detected_topics.length > 0 && (
                <div className="mt-1 text-[var(--ink-muted)]">{c.detected_topics.join(", ")}</div>
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
        <div className="max-w-[88%] rounded-[2px] bg-[var(--olive-dark)] px-4 py-3 text-sm leading-relaxed text-[var(--ivory)] sm:max-w-[72%]">
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
        <div className="mb-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[2px] bg-[var(--olive)]">
          <Scales size={15} weight="bold" className="text-white" />
        </div>
        <div className="max-w-[80%] rounded-[2px] border border-[var(--line-strong)] bg-[var(--canvas)] px-4 py-3 text-sm text-[var(--ink)]">
          <p>{msg.error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 flex items-center gap-1.5 rounded-[2px] border border-[var(--line-strong)] px-2.5 py-1 text-xs font-medium text-[var(--ink)] hover:bg-[var(--taupe)] transition-colors duration-150"
            >
              <ArrowCounterClockwise size={13} weight="bold" /> Retry
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  return <AnswerCard msg={msg} />;
}

// The answer's own status line: only claimed when it's true -- the shown
// text is built solely from sentences that passed the citation check.
function CheckedLine({ msg }) {
  if (msg.abstained || msg.generation_mode === "extractive_fallback" || !msg.sources?.length) return null;
  const sections = msg.sources.length;
  return (
    <span className="inline-flex items-center gap-1">
      <SealCheck size={13} weight="fill" className="text-[var(--ink)]" aria-hidden="true" />
      Each citation checked against the law it cites ({sections} section{sections === 1 ? "" : "s"})
    </span>
  );
}

function AnswerCard({ msg }) {
  const [focus, setFocus] = useState(null);
  const isDocument = msg.isDocumentAnalysis;
  // A fresh object each click, so citing the same section twice re-opens it.
  const onCite = (label) => setFocus({ label });

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="flex justify-start items-start gap-2.5"
    >
      <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[2px] bg-[var(--olive)]">
        {isDocument ? (
          <FileText size={15} weight="bold" className="text-white" />
        ) : (
          <Scales size={15} weight="bold" className="text-white" />
        )}
      </div>
      <article
        className="w-full max-w-[calc(100%-2.4rem)] rounded-[2px] border border-[var(--line)] bg-[var(--paper)] px-4 py-3.5 text-sm leading-relaxed text-[var(--ink)] sm:max-w-[85%] sm:px-5"
        style={{ boxShadow: CARD_SHADOW }}
      >
        {isDocument ? (
          <DocumentAnalysisCard analysis={msg.analysis} />
        ) : (
          <>
            {msg.mode && (
              <header className="mb-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--ink-muted)]">
                <span className="font-semibold text-[var(--ink)]">{msg.mode === "Research" ? "Research note" : "Advice"}</span>
                {!msg.abstained && msg.sources?.length > 0 && <span aria-hidden="true">·</span>}
                <CheckedLine msg={msg} />
              </header>
            )}
            <div className="space-y-1 text-[14.5px] leading-[1.65]">{renderContent(msg.text, msg.sources, onCite)}</div>
            <GenerationNotice mode={msg.generation_mode} />
            {msg.abstained && <AbstainNotice reason={msg.abstain_reason} />}
            <ConflictNotice conflicts={msg.conflicts} />
            <TemporalNotes notes={msg.temporal_notes} />
            <SourcePanel sources={msg.sources} focus={focus} />
            {!msg.abstained && <UnverifiedNotes items={msg.unverified} />}
            {!msg.abstained && <MissingInformation items={msg.missing_information} />}
            {msg.legal_domain && (
              <footer className="mt-3 flex flex-wrap gap-1.5 text-[11px] text-[var(--ink-muted)]">
                <span className="rounded-[2px] border border-[var(--line)] px-2 py-0.5">{areaLabel(msg.legal_domain)}</span>
                {msg.jurisdiction?.state && (
                  <span className="rounded-[2px] border border-[var(--line)] px-2 py-0.5">{msg.jurisdiction.state}, India</span>
                )}
              </footer>
            )}
          </>
        )}
      </article>
    </motion.div>
  );
}

export default function ChatArea({ activeId, messages, isTyping, serverWaking, stage, mode, onQuickPrompt, onRetry }) {
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

            {isTyping && <WorkingStatus mode={serverWaking ? "waking" : "chat"} stage={stage} />}

            <div ref={bottomRef} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
