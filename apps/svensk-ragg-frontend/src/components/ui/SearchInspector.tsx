import { useAppStore } from "../../stores/useAppStore";
import { X, Terminal, Cpu, Clock, Award, ShieldCheck, HelpCircle } from "lucide-react";

export function SearchInspector() {
  const {
    isSearchInspectorOpen,
    toggleSearchInspector,
    activeQueryId,
    queries,
  } = useAppStore();

  if (!isSearchInspectorOpen) return null;

  const activeQuery = queries.find((q) => q.id === activeQueryId);
  if (!activeQuery) return null;

  // Formatting helpers
  const formatMs = (ms: number | null | undefined) => {
    if (ms == null) return "N/A";
    return `${ms.toFixed(0)} ms`;
  };

  return (
    <div className="fixed inset-y-0 right-0 w-96 border-l border-white/5 bg-[#11161B]/95 backdrop-blur-xl z-50 flex flex-col font-ui shadow-2xl animate-in slide-in-from-right duration-200">
      {/* Drawer Header */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-2 text-teal-400">
          <Terminal className="w-4 h-4" />
          <span className="font-semibold text-sm text-slate-200 uppercase tracking-wider">Search Inspector</span>
        </div>
        <button
          onClick={() => toggleSearchInspector(false)}
          className="p-1 text-slate-500 hover:text-slate-200 hover:bg-white/[0.02] rounded-md transition-colors cursor-pointer"
          title="Stäng panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Drawer Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-5 flex flex-col gap-6 font-ui text-slate-300">
        
        {/* Section 1: Query Expansion */}
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-teal-500 flex items-center gap-1.5 font-mono">
            <Cpu className="w-3.5 h-3.5" />
            Query Decontextualization
          </h3>
          <div className="bg-black/20 border border-white/5 p-3 rounded-xl flex flex-col gap-2.5 text-xs font-mono">
            <div>
              <span className="text-slate-500 block text-[9px] uppercase tracking-wider mb-0.5">Original</span>
              <span className="text-slate-300">{activeQuery.query}</span>
            </div>
            <div className="h-[1px] bg-white/5" />
            <div>
              <span className="text-slate-500 block text-[9px] uppercase tracking-wider mb-0.5">Expanded / Rewritten</span>
              <span className="text-teal-400">{activeQuery.rewrittenQuery || "Ingen omformulering krävdes"}</span>
            </div>
          </div>
        </div>

        {/* Section 2: Pipeline Latencies */}
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-teal-500 flex items-center gap-1.5 font-mono">
            <Clock className="w-3.5 h-3.5" />
            Pipeline Latency
          </h3>
          <div className="bg-black/20 border border-white/5 p-3 rounded-xl flex flex-col gap-2 text-xs font-mono">
            <div className="flex items-center justify-between py-1">
              <span className="text-slate-400">Dense & Sparse Search:</span>
              <span className="text-slate-200 font-bold">{formatMs(activeQuery.retrievalLatencyMs || activeQuery.searchTimeMs)}</span>
            </div>
            <div className="flex items-center justify-between py-1 border-t border-white/5">
              <span className="text-slate-400">Total stream till done:</span>
              <span className="text-teal-400 font-bold">{formatMs(activeQuery.totalTimeMs)}</span>
            </div>
          </div>
        </div>

        {/* Section 3: CRAG Grading */}
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-teal-500 flex items-center gap-1.5 font-mono">
            <ShieldCheck className="w-3.5 h-3.5" />
            Corrective RAG (CRAG)
          </h3>
          <div className="bg-black/20 border border-white/5 p-3 rounded-xl flex flex-col gap-2.5 text-xs font-mono">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Evidence Level:</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                activeQuery.evidenceLevel === "HIGH" 
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                  : activeQuery.evidenceLevel === "MEDIUM"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/25"
                  : "bg-red-500/10 text-red-400 border border-red-500/25"
              }`}>
                {activeQuery.evidenceLevel || "NONE"}
              </span>
            </div>
            
            {activeQuery.gradingMetrics && (
              <>
                <div className="h-[1px] bg-white/5" />
                <div className="flex flex-col gap-1.5">
                  <span className="text-slate-500 text-[9px] uppercase tracking-wider block">Document Grader</span>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-white/[0.01] border border-white/5 p-1.5 rounded-lg">
                      <span className="text-[10px] text-slate-500 block">Totalt</span>
                      <span className="text-slate-300 font-bold">{activeQuery.gradingMetrics.total}</span>
                    </div>
                    <div className="bg-emerald-500/5 border border-emerald-500/10 p-1.5 rounded-lg">
                      <span className="text-[10px] text-emerald-500/70 block">Relevant</span>
                      <span className="text-emerald-400 font-bold">{activeQuery.gradingMetrics.relevant}</span>
                    </div>
                    <div className="bg-amber-500/5 border border-amber-500/10 p-1.5 rounded-lg">
                      <span className="text-[10px] text-amber-500/70 block">Osäker</span>
                      <span className="text-amber-400 font-bold">{activeQuery.gradingMetrics.ambiguous}</span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Section 4: Search Quality & Reranker scores */}
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-teal-500 flex items-center gap-1.5 font-mono">
            <Award className="w-3.5 h-3.5" />
            Jina Reranker Scores
          </h3>
          <div className="bg-black/20 border border-white/5 p-3 rounded-xl flex flex-col gap-2 text-xs font-mono max-h-72 overflow-y-auto custom-scrollbar">
            {activeQuery.sources.length === 0 ? (
              <span className="text-slate-500 italic">Inga källor tillgängliga</span>
            ) : (
              activeQuery.sources.map((s, idx) => (
                <div key={s.id} className="flex flex-col gap-1 py-1.5 border-b border-white/5 last:border-0">
                  <div className="flex items-center justify-between font-bold">
                    <span className="text-teal-400 truncate max-w-[200px]" title={s.title}>
                      {idx + 1}. {s.title}
                    </span>
                    <span className="text-slate-300">
                      {(s.score).toFixed(4)}
                    </span>
                  </div>
                  <div className="text-[9px] text-slate-500 truncate">
                    ID: {s.id} | Typ: {s.doc_type}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Info Box */}
        <div className="bg-teal-500/5 border border-teal-500/10 p-3 rounded-xl flex gap-2.5 text-xs text-teal-400/80 leading-relaxed font-ui">
          <HelpCircle className="w-4 h-4 shrink-0 mt-0.5 text-teal-400" />
          <span>
            Jina Reranker v2 (Cross-Encoder) poängsätter dokumenten efter semantisk relevans till frågan. Poäng nära 1 indikerar extremt hög matchning.
          </span>
        </div>

      </div>
    </div>
  );
}
