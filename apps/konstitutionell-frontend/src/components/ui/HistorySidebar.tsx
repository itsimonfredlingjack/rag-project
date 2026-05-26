import { useAppStore } from "../../stores/useAppStore";
import { MessageSquare, Plus, PanelLeftClose, Home } from "lucide-react";

export function HistorySidebar() {
  const {
    queries,
    activeQueryId,
    setFocusedQuery,
    isSidebarOpen,
    toggleSidebar,
    resetToHome,
    isSearching,
  } = useAppStore();

  if (!isSidebarOpen) {
    return null; // Side panel is toggled from header, returning null keeps main view full-width
  }

  return (
    <aside className="w-64 border-r border-white/5 bg-[#090b0e]/95 backdrop-blur-md flex flex-col h-full shrink-0 font-ui text-slate-300 relative z-30 transition-all duration-300">
      {/* Sidebar Header */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between">
        <button
          onClick={resetToHome}
          className="flex items-center gap-2 text-xs font-semibold tracking-widest text-slate-200 hover:text-accent-primary transition-colors cursor-pointer"
        >
          <Home className="w-4 h-4" />
          <span>PORTAL HISTORIK</span>
        </button>
        <button
          onClick={toggleSidebar}
          className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-white/[0.02] rounded transition-colors cursor-pointer"
          title="Dölj historik"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* New Search Button */}
      <div className="p-3">
        <button
          onClick={resetToHome}
          disabled={isSearching}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-accent-primary/10 hover:bg-accent-primary/20 active:scale-98 text-accent-primary border border-accent-primary/20 hover:border-accent-primary/40 rounded text-xs font-medium tracking-wide transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Ny konversation</span>
        </button>
      </div>

      {/* Search History List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2 py-2 flex flex-col gap-1">
        <div className="text-[9px] uppercase font-mono tracking-widest text-slate-500 px-3 py-2">
          Tidigare sökningar ({queries.length})
        </div>
        {queries.length === 0 ? (
          <div className="text-xs text-slate-600 italic px-3 py-4">
            Inga tidigare sökningar
          </div>
        ) : (
          [...queries].reverse().map((q) => {
            const isActive = q.id === activeQueryId;
            return (
              <button
                key={q.id}
                onClick={() => setFocusedQuery(q.id)}
                className={`w-full text-left px-3 py-2.5 rounded flex items-start gap-2.5 transition-all text-xs cursor-pointer group border ${
                  isActive
                    ? "bg-slate-900/40 border-accent-primary/20 text-accent-primary font-medium"
                    : "bg-transparent border-transparent text-slate-400 hover:text-slate-200 hover:bg-white/[0.01]"
                }`}
              >
                <MessageSquare className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                  isActive ? "text-accent-primary" : "text-slate-500 group-hover:text-slate-400"
                }`} />
                <span className="truncate flex-1" title={q.query}>
                  {q.query}
                </span>
              </button>
            );
          })
        )}
      </div>

      {/* Sidebar Footer */}
      <div className="p-3 border-t border-white/5 text-[9px] font-mono text-slate-500 flex items-center justify-between">
        <span>Arkiv AI v3.0</span>
        <span className="flex h-1.5 w-1.5 relative">
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent-primary" />
        </span>
      </div>
    </aside>
  );
}
