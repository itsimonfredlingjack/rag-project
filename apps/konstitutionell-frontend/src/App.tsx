import { useEffect } from "react";
import { useAppStore } from "./stores/useAppStore";
import { HistorySidebar } from "./components/ui/HistorySidebar";
import { FacetFilters } from "./components/ui/FacetFilters";
import { SearchInspector } from "./components/ui/SearchInspector";
import { DocumentReader } from "./components/ui/DocumentReader";
import { HeroSection } from "./components/ui/HeroSection";
import { ChatView } from "./components/ui/ChatView";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PanelLeft, Terminal, Shield } from "lucide-react";

function App() {
  const {
    viewMode,
    isSidebarOpen,
    toggleSidebar,
    toggleSearchInspector,
    isSearchInspectorOpen,
    activeQueryId,
    queries,
    fetchFacets,
  } = useAppStore();

  const isHeroMode = viewMode === "hero";
  const activeQuery = queries.find((q) => q.id === activeQueryId);

  // Fetch filters/facets on load
  useEffect(() => {
    fetchFacets();
  }, [fetchFacets]);

  return (
    <div className="w-screen h-screen overflow-hidden flex bg-app-bg text-[#E2E8F0] font-ui select-none relative">
      {/* Background Ambient Glows */}
      <div className="ambient-glow-cyan top-[-100px] left-[-100px] opacity-25 pointer-events-none z-0" />
      <div className="ambient-glow-amber bottom-[-100px] right-[-100px] opacity-15 pointer-events-none z-0" />

      <ErrorBoundary>
        {/* Collapsible Left Sidebar */}
        <HistorySidebar />

        {/* Main Work Area */}
        <div className="flex-1 flex flex-col min-w-0 h-full relative z-10">
          
          {/* Header Bar */}
          <header className="h-14 border-b border-white/[0.035] bg-panel-bg/60 backdrop-blur-md px-6 flex items-center justify-between shrink-0 z-30 shadow-[0_4px_24px_rgba(0,0,0,0.4)]">
            <div className="flex items-center gap-4">
              {!isSidebarOpen && (
                <button
                  onClick={toggleSidebar}
                  className="p-1.5 text-stone-500 hover:text-accent-primary hover:bg-white/[0.02] rounded-md transition-colors cursor-pointer"
                  title="Visa sidopanel"
                >
                  <PanelLeft className="w-4 h-4" />
                </button>
              )}
              
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-accent-primary filter drop-shadow-[0_0_8px_rgba(0,240,244,0.4)]" />
                <span className="text-xs font-semibold tracking-wider uppercase text-slate-300">
                  Konstitutionell AI
                </span>
                <span className="text-[10px] text-accent-primary/80 font-mono bg-accent-primary/5 px-1.5 py-0.5 rounded border border-accent-primary/10">
                  Myndighetsdata RAG
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Local Dev Indicator */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/5 border border-emerald-500/15 text-[10px] font-medium text-emerald-400 font-mono">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                </span>
                <span>Local</span>
              </div>

              {/* Technical Search Inspector Toggle */}
              {!isHeroMode && activeQuery && (
                <button
                  onClick={() => toggleSearchInspector()}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs transition-all cursor-pointer ${
                    isSearchInspectorOpen
                      ? "bg-accent-primary/10 border-accent-primary/30 text-accent-primary font-medium shadow-[0_0_12px_rgba(0,240,244,0.15)]"
                      : "bg-white/[0.02] border-white/5 hover:border-accent-primary/20 text-slate-400 hover:text-slate-200"
                  }`}
                  title="Visa teknisk analys"
                >
                  <Terminal className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Inspector</span>
                </button>
              )}
            </div>
          </header>

          {/* View Container */}
          <div className="flex-1 flex min-h-0 min-w-0 relative">
            {isHeroMode ? (
              /* 1. Hero Search Panel (Home view) */
              <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col justify-start py-8 relative">
                <HeroSection />
                <div className="max-w-4xl w-full mx-auto px-6 sm:px-8 mt-6">
                  <FacetFilters />
                </div>
              </div>
            ) : (
              /* 2. Search Results view (Split layout) */
              <div className="flex-1 flex min-h-0 min-w-0 border-t border-white/[0.02]">
                {/* Left Panel: Query and Streaming Answer */}
                <div className="flex-1 md:w-1/2 flex flex-col min-w-0 h-full bg-app-bg/50">
                  <ChatView />
                </div>

                {/* Right Panel: Split Document Reader */}
                <div className="hidden md:flex md:w-1/2 h-full border-l border-white/[0.035] bg-panel-bg/25">
                  <DocumentReader />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Floating Inspector Drawer */}
        <SearchInspector />
      </ErrorBoundary>
    </div>
  );
}

export default App;
