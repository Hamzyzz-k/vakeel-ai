import { useEffect, useRef, useState } from "react";
import ChatMessage from "./components/ChatMessage.jsx";
import { IconScale, IconSend } from "./components/icons.jsx";

const EXAMPLE_QUESTIONS = [
  "A supplier breached a contract to deliver goods on time and I suffered financial loss. What compensation can I claim?",
  "What are my rights if a seller ships goods that don't match the description?",
  "My landlord in Bangalore won't return my security deposit. What can I do?",
];

const MODES = [
  { id: "consultant", label: "Consultant", hint: "Plain-language answers" },
  { id: "research", label: "Research", hint: "IRAC-structured notes" },
];

export default function App() {
  const [mode, setMode] = useState("consultant");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-grow the textarea with content instead of a fixed 1-row box that
  // scrolls internally for anything longer than a few words -- a real
  // usability fix, not just a visual one: legal questions run long.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  async function send(text) {
    const question = (text ?? input).trim();
    if (!question || sending) return;

    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", pending: true },
    ]);

    try {
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, mode }),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      const data = await res.json();

      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          text: data.answer,
          abstained: data.abstained,
          abstain_reason: data.abstain_reason,
          sources: data.sources,
          evidence_score: data.evidence_score,
          jurisdiction: data.jurisdiction,
          legal_domain: data.legal_domain,
          conflicts: data.conflicts,
          temporal_notes: data.temporal_notes,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", error: `Could not reach the backend: ${err.message}`, retryQuestion: question },
      ]);
    } finally {
      setSending(false);
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
        inputRef.current?.focus();
      });
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex h-screen flex-col bg-ink-950 text-ink-100">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-ink-800 bg-ink-950/90 px-4 py-3 backdrop-blur">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-b from-brass-500 to-brass-700 text-ink-950 shadow-panel">
            <IconScale width="18" height="18" strokeWidth="2" />
          </span>
          <div className="min-w-0">
            <h1 className="font-serif text-[17px] font-semibold leading-tight tracking-tight text-ink-100">
              Vakeel AI
            </h1>
            {/* Hidden below sm: at mobile width this line left zero gap
                before the mode toggle (measured: 0px, touching) -- the
                page <title>/meta description already carry this text, so
                dropping it here at narrow widths loses nothing. */}
            <p className="hidden truncate text-[11px] leading-tight text-ink-500 sm:block">
              AI legal research &middot; not advice from a licensed lawyer
            </p>
          </div>
        </div>

        <div className="flex shrink-0 rounded-lg border border-ink-800 bg-ink-900 p-0.5 text-xs" role="tablist" aria-label="Response mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="tab"
              aria-selected={mode === m.id}
              title={m.hint}
              onClick={() => setMode(m.id)}
              className={`rounded-md px-3 py-1.5 font-medium transition-colors duration-150 ${
                mode === m.id ? "bg-brass-500 text-ink-950" : "text-ink-400 hover:text-ink-200"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </header>

      <main ref={listRef} className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.length === 0 && (
            <div className="mt-10 space-y-4 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-ink-900 text-brass-400 shadow-panel">
                <IconScale width="22" height="22" />
              </div>
              <p className="text-sm text-ink-400">Ask a question about Indian law, or try one of these:</p>
              <div className="flex flex-col gap-2 text-left">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="rounded-lg border border-ink-800 bg-ink-900/60 px-3.5 py-2.5 text-left text-[13px] leading-snug text-ink-300 transition-colors duration-150 hover:border-ink-700 hover:bg-ink-900"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <ChatMessage key={i} message={m} onRetry={m.retryQuestion ? () => send(m.retryQuestion) : null} />
          ))}
        </div>
      </main>

      <footer className="shrink-0 border-t border-ink-800 bg-ink-950 px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <textarea
            ref={(el) => {
              textareaRef.current = el;
              inputRef.current = el;
            }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your legal question..."
            rows={1}
            autoFocus
            className="max-h-40 flex-1 resize-none rounded-xl border border-ink-800 bg-ink-900 px-3.5 py-2.5 text-sm text-ink-100 placeholder-ink-500 outline-none transition-colors duration-150 focus:border-brass-500"
          />
          <button
            onClick={() => send()}
            disabled={sending || !input.trim()}
            aria-label="Send question"
            className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl bg-brass-500 text-ink-950 transition-opacity duration-150 hover:bg-brass-400 disabled:opacity-30"
          >
            <IconSend />
          </button>
        </div>
      </footer>
    </div>
  );
}
