import { Plus, Scale, User, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

function SidebarContent({ isMobile, activeId, conversations, onNewChat, onSelectConversation, onClose }) {
  return (
    <div className="flex flex-col h-full w-64 bg-[#0a0a0a] text-white">
      <div className="px-5 pt-6 pb-5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-white flex items-center justify-center flex-shrink-0">
            <Scale className="w-4 h-4 text-black" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-white font-serif">Vakeel AI</span>
        </div>
        {isMobile && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Close sidebar"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="px-3 pb-4 flex-shrink-0">
        <button
          onClick={() => { onNewChat(); if (isMobile) onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-white/15 text-sm text-white/70 hover:bg-white/8 hover:text-white transition-all duration-150"
        >
          <Plus className="w-4 h-4 flex-shrink-0" />
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
                <button
                  key={conv.id}
                  onClick={() => { onSelectConversation(conv.id); if (isMobile) onClose(); }}
                  className={`w-full text-left px-3 py-2.5 rounded-xl transition-all duration-150 ${
                    activeId === conv.id ? "bg-white/12 text-white" : "text-white/55 hover:bg-white/6 hover:text-white/85"
                  }`}
                >
                  <p className="text-sm font-medium truncate leading-snug">{conv.title}</p>
                  <p className="text-[11px] text-white/30 truncate mt-0.5">{conv.preview}</p>
                </button>
              ))}
            </div>
          );
        })}
      </div>

      <div className="flex-shrink-0 border-t border-white/8 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-white/12 flex items-center justify-center flex-shrink-0">
            <User className="w-4 h-4 text-white/60" />
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
              className="fixed inset-0 bg-black/50 z-40"
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
