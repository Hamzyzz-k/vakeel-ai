import { Plus, Trash, User, X } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import BrandMark from "./BrandMark.jsx";

function SidebarContent({ isMobile, activeId, conversations, onNewChat, onSelectConversation, onDeleteConversation, onClose }) {
  return (
    <div className="flex flex-col h-full w-64 bg-[var(--olive-dark)] text-[var(--ivory)]">
      <div className="px-5 pt-6 pb-5 flex items-center justify-between flex-shrink-0">
        <BrandMark compact inverse className="text-white" />
        {isMobile && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Close sidebar"
          >
            <X size={16} weight="bold" />
          </button>
        )}
      </div>

      <div className="px-3 pb-4 flex-shrink-0">
        <button
          onClick={() => { onNewChat(); if (isMobile) onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-white/15 text-sm text-white/70 hover:bg-white/8 hover:text-white transition-all duration-150"
        >
          <Plus size={16} weight="bold" className="flex-shrink-0" />
          New conversation
        </button>
      </div>

      <div className="h-px bg-white/8 mx-4 mb-3 flex-shrink-0" />

      <div className="flex-1 overflow-y-auto px-2 space-y-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {conversations.length === 0 && (
          <p className="px-3 text-xs text-white/25 leading-relaxed">
            No conversations yet. Ask a question to start one.
          </p>
        )}
        {(["Today", "Yesterday", "Earlier"]).map((group) => {
          const items = conversations.filter((c) => c.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-white/25 px-3 pb-1">
                {group}
              </p>
              {items.map((conv) => (
                <div key={conv.id} className="group relative">
                  <button
                    onClick={() => { onSelectConversation(conv.id); if (isMobile) onClose(); }}
                    className={`w-full text-left pl-3 pr-10 py-2.5 rounded-xl transition-all duration-150 ${
                      activeId === conv.id ? "bg-white/12 text-white" : "text-white/55 hover:bg-white/6 hover:text-white/85"
                    }`}
                  >
                    <p className="text-sm font-medium truncate leading-snug">{conv.title}</p>
                    <p className="text-[11px] text-white/30 truncate mt-0.5">{conv.preview}</p>
                  </button>
                  <button
                    onClick={(event) => { event.stopPropagation(); onDeleteConversation(conv.id); }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-white/30 opacity-0 transition-all hover:bg-white/10 hover:text-white group-hover:opacity-100 focus:opacity-100"
                    aria-label={`Delete ${conv.title}`}
                    title="Delete conversation"
                  >
                    <Trash size={14} weight="bold" />
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="flex-shrink-0 border-t border-white/8 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-white/12 flex items-center justify-center flex-shrink-0">
            <User size={16} weight="bold" className="text-white/60" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">Local session</p>
            <p className="text-[11px] text-white/35 truncate">History stays on this device</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Sidebar(props) {
  const { isOpen, isMobile, onClose } = props;

  if (isMobile) {
    return (
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22 }}
              className="fixed inset-0 bg-[var(--olive-dark)]/55 z-40"
              onClick={onClose}
            />
            <motion.div
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="fixed top-0 left-0 h-full z-50 shadow-2xl"
            >
              <SidebarContent {...props} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    );
  }

  return (
    <aside
      className={`flex-shrink-0 transition-all duration-300 ease-in-out overflow-hidden ${isOpen ? "w-64" : "w-0"}`}
    >
      <SidebarContent {...props} />
    </aside>
  );
}
