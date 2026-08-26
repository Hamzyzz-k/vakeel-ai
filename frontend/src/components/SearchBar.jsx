import { useRef, useEffect, useState } from "react";
import { FileText, PaperPlaneTilt, Plus } from "@phosphor-icons/react";

export default function SearchBar({ input, setInput, mode, isTyping, onSend, onUploadDocument, textareaRef }) {
  const [showPlus, setShowPlus] = useState(false);
  const plusRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (plusRef.current && !plusRef.current.contains(e.target)) {
        setShowPlus(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  function autoResize(e) {
    const el = e.currentTarget;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 128) + "px";
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    setShowPlus(false);
    if (file) onUploadDocument(file);
    e.target.value = "";
  }

  const hasInput = !!input.trim();

  return (
    <div className="flex-shrink-0 border-t border-[var(--line)] bg-[var(--taupe)]/25 px-4 pb-5 pt-3">
      <div className="max-w-2xl mx-auto relative">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={handleFileChange}
        />

        {showPlus && (
          <div
            ref={plusRef}
            className="absolute bottom-full left-0 mb-2.5 bg-[var(--paper)] border border-[var(--line)] rounded-2xl shadow-2xl overflow-hidden z-20 w-48"
            style={{ boxShadow: "0 12px 36px rgba(53,67,46,0.14)" }}
          >
            <div className="px-4 py-2.5 border-b border-[var(--line)]">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--ink-muted)]/70">Attach</p>
            </div>
            <button
              className="flex items-center gap-3 px-4 py-3 w-full text-left hover:bg-[var(--olive)]/[0.04] transition-colors group"
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="w-7 h-7 rounded-lg bg-[var(--olive)]/[0.06] flex items-center justify-center group-hover:bg-[var(--olive)]/[0.10] transition-colors">
                <FileText size={15} weight="bold" className="text-[var(--ink)]/65" />
              </div>
              <div className="min-w-0">
                <span className="text-sm font-medium text-[var(--ink)]/80 block">Document</span>
                <span className="text-[10px] text-[var(--ink-muted)]/70">PDF or TXT, for clause analysis</span>
              </div>
            </button>
          </div>
        )}

        <div
          className="flex items-end gap-3 bg-[var(--ivory)] border border-[var(--line-strong)] rounded-3xl px-4 py-3 transition-all duration-200 focus-within:border-[var(--olive)]"
          style={{ boxShadow: "0 5px 22px rgba(53,67,46,0.09), 0 1px 3px rgba(53,67,46,0.08)" }}
        >
          <button
            onClick={() => setShowPlus((p) => !p)}
            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 ${
              showPlus ? "bg-[var(--olive-dark)] text-[var(--ivory)] rotate-45" : "bg-[var(--sage-soft)] text-[var(--ink-muted)] hover:bg-[var(--taupe)] hover:text-[var(--ink)]"
            }`}
            aria-label="Add attachment"
          >
            <Plus size={16} weight="bold" />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onInput={autoResize}
            placeholder={`Ask in ${mode} mode...`}
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-[var(--ink)] placeholder:text-[var(--ink-muted)]/60 outline-none leading-relaxed overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden py-1"
            style={{ minHeight: "24px", maxHeight: "128px" }}
          />

          <button
            onClick={onSend}
            disabled={isTyping || !hasInput}
            className={`relative flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 ${
              hasInput ? "bg-[var(--olive)] hover:bg-[var(--olive-dark)] active:scale-[0.96]" : "bg-[var(--sage-soft)] text-[var(--ink-muted)]/40 cursor-not-allowed"
            }`}
            aria-label="Send message"
          >
            <PaperPlaneTilt size={15} weight="fill" className={hasInput ? "text-white" : "text-[var(--ink-muted)]/50"} />
          </button>
        </div>

        <p className="text-center text-[10px] text-[var(--ink-muted)]/65 mt-2 leading-relaxed">
          Vakeel AI provides general legal information, not legal advice. Consult a licensed attorney for your situation.
        </p>
      </div>
    </div>
  );
}
