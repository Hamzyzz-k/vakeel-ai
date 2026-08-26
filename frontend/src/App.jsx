import { useState, useRef, useEffect } from "react";
import { List, SidebarSimple } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import Sidebar from "./components/Sidebar.jsx";
import ModeToggle from "./components/ModeToggle.jsx";
import SearchBar from "./components/SearchBar.jsx";
import ChatArea from "./components/ChatArea.jsx";
import BrandMark from "./components/BrandMark.jsx";
import LandingPage from "./components/LandingPage.jsx";
import { useIsMobile } from "./hooks/useIsMobile.js";
import { apiUrl } from "./lib/api.js";

const STORAGE_KEY = "vakeel_conversations_v1";
const MODE_TO_API = { Advice: "advice", Research: "research" };

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

  const textareaRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

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
      const res = await fetch(apiUrl("/api/v1/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, mode: MODE_TO_API[mode] }),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
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
        error: `Could not reach the backend: ${err.message}`,
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
      const res = await fetch(apiUrl("/api/v1/documents/upload"), { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server responded ${res.status}`);
      }
      const analysis = await res.json();
      const aiMsg = { id: (Date.now() + 1).toString(), role: "ai", isDocumentAnalysis: true, analysis };
      updateConversation(convId, (c) => ({ ...c, messages: [...c.messages, aiMsg] }));
    } catch (err) {
      const errMsg = { id: (Date.now() + 1).toString(), role: "ai", error: `Could not analyze document: ${err.message}` };
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
    <div className="flex h-[100dvh] min-h-[100dvh] w-full overflow-hidden font-sans bg-[var(--canvas)] text-[var(--ink)]">
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

      <div className="flex-1 flex flex-col min-w-0 bg-[var(--canvas)]">
        <header className="flex items-center justify-between px-4 sm:px-6 py-3.5 border-b border-[var(--line)] bg-[color:var(--sage-soft)]/90 backdrop-blur flex-shrink-0">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <button
              onClick={() => setSidebarOpen((p) => !p)}
              className="p-2 rounded-lg hover:bg-[var(--sage-soft)] transition-colors text-[var(--ink-muted)] hover:text-[var(--ink)] flex-shrink-0"
              aria-label="Toggle sidebar"
            >
              {isMobile ? <List size={20} weight="bold" /> : <SidebarSimple size={17} weight={sidebarOpen ? "fill" : "regular"} />}
            </button>
            {activeTitle ? (
              <h1 className="text-sm font-medium text-[var(--ink-muted)] truncate max-w-[120px] sm:max-w-xs">{activeTitle}</h1>
            ) : (
              <button type="button" onClick={onHome} aria-label="Back to Vakeel AI home" className="rounded-xl text-[var(--ink)]">
                <BrandMark compact />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <ModeToggle mode={mode} onChange={setMode} isMobile={isMobile} />
          </div>
        </header>

        <ChatArea
          activeId={activeId}
          messages={messages}
          isTyping={isTyping}
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
