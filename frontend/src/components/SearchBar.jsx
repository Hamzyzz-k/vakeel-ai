import { useRef, useEffect, useState } from "react";
import { Plus, FileText, Send, Mic } from "lucide-react";

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
    <div className="px-4 pb-5 pt-3 flex-shrink-0">
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
            className="absolute bottom-full left-0 mb-2.5 bg-white border border-black/12 rounded-2xl shadow-2xl overflow-hidden z-20 w-48"
            style={{ boxShadow: "0 8px 40px rgba(0,0,0,0.12)" }}
          >
            <div className="px-4 py-2.5 border-b border-black/6">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-black/35">Attach</p>
            </div>
            <button
              className="flex items-center gap-3 px-4 py-3 w-full text-left hover:bg-black/4 transition-colors group"
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="w-7 h-7 rounded-lg bg-black/6 flex items-center justify-center group-hover:bg-black/10 transition-colors">
                <FileText className="w-3.5 h-3.5 text-black/60" />
              </div>
              <div className="min-w-0">
                <span className="text-sm font-medium text-black/75 block">Document</span>
                <span className="text-[10px] text-black/35">PDF or TXT, for clause analysis</span>
              </div>
            </button>
          </div>
        )}

        <div
          className="flex items-end gap-3 bg-white border border-black/14 rounded-3xl px-4 py-3 transition-all duration-200 focus-within:border-black/35"
          style={{ boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.05)" }}
        >
          <button
            onClick={() => setShowPlus((p) => !p)}
            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 ${
              showPlus ? "bg-black text-white rotate-45" : "bg-black/7 text-black/45 hover:bg-black/14 hover:text-black/70"
            }`}
            aria-label="Add attachment"
          >
            <Plus className="w-4 h-4" />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            onInput={autoResize}
            placeholder={`Ask your ${mode} anything...`}
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-black placeholder:text-black/32 outline-none leading-relaxed overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden py-1"
            style={{ minHeight: "24px", maxHeight: "128px" }}
          />

          <button
            onClick={hasInput ? onSend : undefined}
            disabled={isTyping}
            className={`relative flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-200 ${
              hasInput ? "bg-black hover:opacity-75" : "bg-transparent text-black/45 hover:bg-black/8 hover:text-black/70"
            }`}
            aria-label={hasInput ? "Send message" : "Voice input"}
          >
            <Send
              className={`w-3.5 h-3.5 text-white absolute transition-all duration-200 ${
                hasInput ? "opacity-100 scale-100" : "opacity-0 scale-75"
              }`}
            />
            <Mic
              className={`w-4 h-4 absolute transition-all duration-200 ${
                hasInput ? "opacity-0 scale-75" : "opacity-100 scale-100"
              }`}
            />
          </button>
        </div>

        <p className="text-center text-[10px] text-black/22 mt-2 leading-relaxed">
          Vakeel AI provides general legal information, not legal advice. Consult a licensed attorney for your situation.
        </p>
      </div>
    </div>
  );
}
