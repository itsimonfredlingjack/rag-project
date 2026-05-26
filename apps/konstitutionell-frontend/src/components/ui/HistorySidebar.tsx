import { useAppStore } from "../../stores/useAppStore";
import { MessageSquare, Plus, PanelLeftClose, PanelLeft, Home } from "lucide-react";

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
    return (
      <button
        onClick={toggleSidebar}
        className="fixed top-4 left-4 z-40 p-2 bg-[#11161B]/95 border border-white/5 hover:border-teal-500/30 text-stone-400 hover:text-teal-400 rounded-lg shadow-lg backdrop-blur-md transition-all cursor-pointer"
        title="Visa sidopanel"
      >
        <PanelLeft className="w-5 h-5" />
      </button>
    );
  }

  return (
    <aside className="w-64 border-r border-white/5 bg-[#11161B] flex flex-col h-full shrink-0 font-ui text-slate-300 relative z-30 transition-all duration-300">
      {/* Sidebar Header */}
      <div className="p-4 border-bottom border-white/5 flex items-center justify-between">
        <button
          onClick={resetToHome}
          className="flex items-center gap-2 text-sm font-semibold tracking-wider bg-gradient-to-r from-teal-400 to-teal-200 bg-clip-text text-transparent hover:opacity-80 transition-opacity cursor-pointer"
        >
          <Home className="w-4 h-4 text-teal-400" />
          <span>K-AI PORTAL</span>
        </button>
        <button
          onClick={toggleSidebar}
          className="p-1.5 text-stone-500 hover:text-teal-400 hover:bg-white/[0.02] rounded-md transition-colors cursor-pointer"
          title="Dölj sidopanel"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* New Search Button */}
      <div className="p-3">
        <button
          onClick={resetToHome}
          disabled={isSearching}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-teal-600/10 hover:bg-teal-600/20 active:scale-98 text-teal-400 border border-teal-500/20 hover:border-teal-500/40 rounded-xl text-sm font-medium transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" />
          <span>Ny sökning</span>
        </button>
      </div>

      {/* Search History List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2 py-2 flex flex-col gap-1">
        <div className="text-[10px] uppercase font-mono tracking-widest text-slate-500 px-3 py-2">
          Historik ({queries.length})
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
                className={`w-full text-left px-3 py-2.5 rounded-lg flex items-start gap-2.5 transition-all text-xs cursor-pointer group ${
                  isActive
                    ? "bg-teal-950/20 border border-teal-500/20 text-teal-400 font-medium"
                    : "hover:bg-white/[0.02] border border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <MessageSquare className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                  isActive ? "text-teal-400" : "text-slate-500 group-hover:text-slate-400"
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
      <div className="p-3 border-t border-white/5 text-[10px] font-mono text-slate-500 flex items-center justify-between">
        <span>V3.0 (Nordic Dark)</span>
        <span className="flex h-2 w-2 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-teal-500" />
        </span>
      </div>
    </aside>
  );
}
