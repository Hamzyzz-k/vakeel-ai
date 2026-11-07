import { useState, useRef, useEffect } from "react";
import { ArrowLeft, List, SidebarSimple } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import Sidebar from "./components/Sidebar.jsx";
import ModeToggle from "./components/ModeToggle.jsx";
import SearchBar from "./components/SearchBar.jsx";
import ChatArea from "./components/ChatArea.jsx";
import LandingPage from "./components/LandingPage.jsx";
import { useIsMobile } from "./hooks/useIsMobile.js";
import { fetchWithTimeout, RequestTimeoutError } from "./lib/api.js";

const STORAGE_KEY = "vakeel_conversations_v1";
const MODE_TO_API = { Advice: "advice", Research: "research" };
// Long enough for the backend's provider fallbacks (Groq, then Gemini) to
// finish; anything past this is a stalled request, not a slow answer.
const CHAT_TIMEOUT_MS = 120000;
const UPLOAD_TIMEOUT_MS = 90000;
const WAKING_AFTER_MS = 3000;

function failureText(err, action) {
  if (err instanceof RequestTimeoutError) {
    return `${action} timed out (${err.message.toLowerCase()}). The server may still be waking up. Try again.`;
  }
  return `${action} failed: ${err.message}`;
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return parsed.map((conversation) => ({
      ...conversation,
      messages: (conversation.messages || []).map((message) => ({
        ...message,
        mode: message.mode === "Adviser" ? "Advice" : message.mode === "Lawyer" ? "Research" : message.mode,
      })),
    }));
  } catch {
    return [];
  }
}

function groupFor(createdAt) {
  const now = new Date();
  const created = new Date(createdAt);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  if (created >= startOfToday) return "Today";
  if (created >= startOfYesterday) return "Yesterday";
  return "Earlier";
}

function titleFromMessage(text) {
  const trimmed = text.trim().replace(/\s+/g, " ");
  return trimmed.length > 48 ? trimmed.slice(0, 48) + "…" : trimmed;
}

function Workspace({ onHome, initialMode = "Advice" }) {
  const isMobile = useIsMobile();

  const [conversations, setConversations] = useState(loadConversations);
  const [activeId, setActiveId] = useState(null);
  const [mode, setMode] = useState(initialMode);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  // Not `useState(!isMobile)` -- useIsMobile() reports false on its very
  // first render (its real value only lands after its own useEffect runs),
  // so that would always initialize the sidebar open regardless of actual
  // device width. window.innerWidth is available synchronously at this
  // point, so read it directly for the one-time initial value instead.
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 768);
  const [serverWaking, setServerWaking] = useState(false);
  const [serverUnreachable, setServerUnreachable] = useState(false);

  const textareaRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

  // The free backend host sleeps when idle. Ping it as soon as the
  // workspace opens so the wake-up overlaps with the user typing, and say
  // so if it is slow instead of leaving a silent spinner.
  useEffect(() => {
    let active = true;
    const slow = setTimeout(() => active && setServerWaking(true), WAKING_AFTER_MS);
    fetchWithTimeout("/api/v1/health", {}, CHAT_TIMEOUT_MS)
      .then((res) => {
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        if (active) setServerUnreachable(false);
      })
      .catch(() => active && setServerUnreachable(true))
      .finally(() => {
        clearTimeout(slow);
        if (active) setServerWaking(false);
      });
    return () => {
      active = false;
      clearTimeout(slow);
    };
  }, []);

  const activeConversation = conversations.find((c) => c.id === activeId) || null;
  const messages = activeConversation?.messages ?? [];

  function updateConversation(id, updater) {
    setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
  }

  function newChat() {
    setActiveId(null);
    setInput("");
    if (isMobile) setSidebarOpen(false);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  function openConversation(id) {
    setActiveId(id);
    setInput("");
    if (isMobile) setSidebarOpen(false);
  }

  function deleteConversation(id) {
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;
    if (!window.confirm(`Delete “${conversation.title}”? This cannot be undone.`)) return;
    setConversations((prev) => prev.filter((item) => item.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setInput("");
    }
  }

  async function send(text) {
    const question = (text ?? input).trim();
    if (!question || isTyping) return;

    let convId = activeId;
    const userMsg = { id: Date.now().toString(), role: "user", text: question };

    if (convId === null) {
      convId = `c_${Date.now()}`;
      const newConv = {
        id: convId,
        title: titleFromMessage(question),
        preview: question,
        createdAt: Date.now(),
        messages: [userMsg],
      };
      setConversations((prev) => [newConv, ...prev]);
      setActiveId(convId);
    } else {
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, userMsg] }));
    }

    setInput("");
    setIsTyping(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    try {
      const res = await fetchWithTimeout("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, mode: MODE_TO_API[mode] }),
      }, CHAT_TIMEOUT_MS);
      if (!res.ok) {
        // Limit messages (429) carry a readable detail; show it, not the code.
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server responded ${res.status}`);
      }
      const data = await res.json();

      const aiMsg = {
        id: (Date.now() + 1).toString(),
        role: "ai",
        mode,
        text: data.answer,
        abstained: data.abstained,
        abstain_reason: data.abstain_reason,
        sources: data.sources,
        jurisdiction: data.jurisdiction,
        legal_domain: data.legal_domain,
        conflicts: data.conflicts,
        temporal_notes: data.temporal_notes,
        missing_information: data.missing_information,
        coverage: data.coverage,
        generation_mode: data.generation_mode,
        provider_error: data.provider_error,
      };
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, aiMsg] }));
    } catch (err) {
      const errMsg = {
        id: (Date.now() + 1).toString(),
        role: "ai",
        error: failureText(err, "The request"),
        retryQuestion: question,
      };
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, errMsg] }));
    } finally {
      setIsTyping(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  function retry(errorMsg) {
    // Drop the error bubble, then resend the same question -- keeps the
    // transcript clean instead of stacking repeated failure bubbles.
    updateConversation(activeId, (c) => ({
      ...c,
      messages: c.messages.filter((m) => m.id !== errorMsg.id),
    }));
    send(errorMsg.retryQuestion);
  }

  async function uploadDocument(file) {
    let convId = activeId;
    const userMsg = { id: Date.now().toString(), role: "user", text: `Uploaded ${file.name}` };

    if (convId === null) {
      convId = `c_${Date.now()}`;
      const newConv = {
        id: convId,
        title: `Document: ${file.name}`,
        preview: "Document analysis",
        createdAt: Date.now(),
        messages: [userMsg],
      };
      setConversations((prev) => [newConv, ...prev]);
      setActiveId(convId);
    } else {
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, userMsg] }));
    }

    setIsTyping(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetchWithTimeout("/api/v1/documents/upload", { method: "POST", body: formData }, UPLOAD_TIMEOUT_MS);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server responded ${res.status}`);
      }
      const analysis = await res.json();
      const aiMsg = { id: (Date.now() + 1).toString(), role: "ai", isDocumentAnalysis: true, analysis };
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, aiMsg] }));
    } catch (err) {
      const errMsg = { id: (Date.now() + 1).toString(), role: "ai", error: failureText(err, "Document analysis") };
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, errMsg] }));
    } finally {
      setIsTyping(false);
    }
  }

  function onQuickPrompt(prompt) {
    setInput(prompt);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }

  const sidebarConversations = conversations.map((c) => ({ ...c, group: groupFor(c.createdAt) }));
  const activeTitle = activeConversation?.title ?? null;

  return (
    <div className="workspace-shell-app flex h-[100dvh] min-h-[100dvh] w-full overflow-hidden bg-[var(--canvas)] text-[var(--ink)]">
      <Sidebar
        isOpen={sidebarOpen}
        isMobile={isMobile}
        activeId={activeId}
        conversations={sidebarConversations}
        onNewChat={newChat}
        onSelectConversation={openConversation}
        onDeleteConversation={deleteConversation}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="workspace-main-app flex min-w-0 flex-1 flex-col bg-[var(--canvas)]">
        <header className="workspace-topbar-app flex min-h-[72px] flex-shrink-0 items-center justify-between border-b border-[var(--line)] bg-[color:var(--canvas)]/90 px-4 backdrop-blur sm:px-8">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <button
              onClick={() => setSidebarOpen((p) => !p)}
              className="flex-shrink-0 p-2 text-[var(--ink-muted)] transition-colors hover:bg-[var(--sage-soft)] hover:text-[var(--ink)]"
              aria-label="Toggle sidebar"
            >
              {isMobile ? <List size={20} weight="bold" /> : <SidebarSimple size={17} weight={sidebarOpen ? "fill" : "regular"} />}
            </button>
            <button
              type="button"
              onClick={onHome}
              aria-label="Back to landing page"
              className="group inline-flex items-center gap-2 font-mono text-[10px] font-medium text-[var(--forest)] transition-all duration-200 hover:gap-3 active:scale-[0.98]"
            >
              <ArrowLeft size={14} weight="bold" className="transition-transform duration-300 group-hover:-translate-x-0.5" />
              <span>Back to landing page</span>
            </button>
            {activeTitle && <><span aria-hidden="true" className="h-5 w-px bg-[var(--line)]" /><h1 className="max-w-[110px] truncate text-xs font-medium text-[var(--ink-muted)] sm:max-w-xs">{activeTitle}</h1></>}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <ModeToggle mode={mode} onChange={setMode} isMobile={isMobile} />
          </div>
        </header>

        {serverWaking && (
          <div role="status" className="flex-shrink-0 border-b border-[var(--line)] bg-[var(--paper)] px-4 py-2 text-center text-[11px] text-[var(--ink-muted)] sm:px-8">
            Waking the server. The free host sleeps when idle, so the first answer can take up to a minute.
          </div>
        )}
        {serverUnreachable && !serverWaking && (
          <div role="status" className="flex-shrink-0 border-b border-[var(--line)] bg-[var(--paper)] px-4 py-2 text-center text-[11px] text-[var(--ink-muted)] sm:px-8">
            The server isn't responding right now. Questions will fail until it's back.
          </div>
        )}

        <ChatArea
          activeId={activeId}
          messages={messages}
          isTyping={isTyping}
          serverWaking={serverWaking}
          mode={mode}
          onQuickPrompt={onQuickPrompt}
          onRetry={retry}
        />

        <SearchBar
          input={input}
          setInput={setInput}
          mode={mode}
          isTyping={isTyping}
          onSend={() => send()}
          onUploadDocument={uploadDocument}
          textareaRef={textareaRef}
        />
      </div>
    </div>
  );
}

export default function App() {
  const [workspaceOpen, setWorkspaceOpen] = useState(() => window.location.hash === "#workspace");
  const [entryMode, setEntryMode] = useState("Advice");

  useEffect(() => {
    function syncRoute() {
      setWorkspaceOpen(window.location.hash === "#workspace");
    }
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);

  function openWorkspace(mode = "Advice") {
    setEntryMode(mode);
    window.history.pushState({}, "", "#workspace");
    setWorkspaceOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openLanding() {
    window.history.pushState({}, "", window.location.pathname);
    setWorkspaceOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <AnimatePresence mode="wait">
      {workspaceOpen ? (
        <motion.div key="workspace" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Workspace onHome={openLanding} initialMode={entryMode} />
        </motion.div>
      ) : (
        <motion.div key="landing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <LandingPage onEnter={openWorkspace} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
