import { useEffect } from "react";
import { useAppStore } from "./stores/useAppStore";
import { HistorySidebar } from "./components/ui/HistorySidebar";
import { FacetFilters } from "./components/ui/FacetFilters";
import { DocumentReader } from "./components/ui/DocumentReader";
import { HeroSection } from "./components/ui/HeroSection";
import { ChatView } from "./components/ui/ChatView";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { PanelLeft, Shield } from "lucide-react";

function App() {
  const {
    viewMode,
    isSidebarOpen,
    toggleSidebar,
    fetchFacets,
  } = useAppStore();

  const isHeroMode = viewMode === "hero";

  // Fetch filters/facets on load
  useEffect(() => {
    fetchFacets();
  }, [fetchFacets]);

  return (
    <div className="w-screen h-screen overflow-hidden flex bg-app-bg text-[#E2E8F0] font-ui select-none relative">
      {/* Background Ambient Mesh */}
      <div className="ambient-mesh" />

      <ErrorBoundary>
        {/* Collapsible Left Sidebar */}
        <HistorySidebar />

        {/* Main Work Area */}
        <div className="flex-1 flex flex-col min-w-0 h-full relative z-10 bg-transparent">
          
          {/* Header Bar */}
          <header className="h-14 border-b border-white/[0.05] bg-slate-950/20 backdrop-blur-md px-6 flex items-center justify-between shrink-0 z-30">
            <div className="flex items-center gap-4">
              {!isSidebarOpen && (
                <button
                  onClick={toggleSidebar}
                  className="p-1.5 text-slate-500 hover:text-accent-primary hover:bg-white/[0.02] rounded transition-colors cursor-pointer"
                  title="Visa historik"
                >
                  <PanelLeft className="w-4 h-4" />
                </button>
              )}
              
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-accent-primary" />
                <span className="text-xs font-semibold tracking-widest uppercase text-slate-200">
                  Konstitutionell AI
                </span>
                <span className="text-[9px] text-accent-primary/80 font-mono bg-accent-primary/5 px-2 py-0.5 rounded border border-accent-primary/15">
                  Riksarkiv RAG
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Clean, Non-Technical Connection Dot */}
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-white/[0.02] border border-white/[0.05] text-[10px] font-medium text-slate-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent-primary" />
                </span>
                <span>Ansluten</span>
              </div>
            </div>
          </header>

          {/* View Container */}
          <div className="flex-1 flex min-h-0 min-w-0 relative">
            {isHeroMode ? (
              /* 1. Hero Search Panel (Home view) */
              <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col justify-start py-8 relative">
                <HeroSection />
                <div className="max-w-3xl w-full mx-auto px-6 sm:px-8 mt-6">
                  <FacetFilters />
                </div>
              </div>
            ) : (
              /* 2. Search Results view (Split layout) */
              <div className="flex-1 flex min-h-0 min-w-0 border-t border-white/[0.05]">
                {/* Left Panel: Chat view */}
                <div className="flex-1 md:w-1/2 flex flex-col min-w-0 h-full bg-slate-950/10">
                  <ChatView />
                </div>

                {/* Right Panel: Split Document Reader */}
                <div className="hidden md:flex md:w-1/2 h-full border-l border-white/[0.05] bg-slate-950/20 backdrop-blur-sm">
                  <DocumentReader />
                </div>
              </div>
            )}
          </div>
        </div>
      </ErrorBoundary>
    </div>
  );
}

export default App;
