import { useAppStore } from "../../stores/useAppStore";
import { X, FileText, ExternalLink, AlertCircle } from "lucide-react";

// Safe HTML highlighting function
function highlightText(text: string, snippet: string | undefined, query: string): string {
  if (!text) return "";
  
  // Escape HTML to prevent XSS before wrapping with highlights
  const escapedText = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  if (snippet) {
    // Escape HTML in snippet to match escapedText
    const escapedSnippet = snippet
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;")
      .trim()
      .replace(/\s+/g, " ");

    try {
      // Split snippet into long clauses (min 15 chars) to handle line break discrepancies
      const clauses = escapedSnippet
        .split(/[.,;]/)
        .map(c => c.trim())
        .filter(c => c.length > 15);
        
      let highlighted = escapedText;
      let replacedAny = false;
      
      for (const clause of clauses) {
        const escapedClause = clause.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const regex = new RegExp(`(${escapedClause})`, "gi");
        if (regex.test(highlighted)) {
          highlighted = highlighted.replace(regex, '<mark class="rag-highlight">$1</mark>');
          replacedAny = true;
        }
      }
      
      if (replacedAny) {
        return highlighted;
      }
    } catch (e) {
      console.warn("Highlight helper error:", e);
    }
  }
  
  // Fallback: highlight query keywords
  const terms = query
    .split(/\s+/)
    .map(t => t.trim().replace(/[.,/#!$%^&*;:{}=_`~()-]/g, ""))
    .filter(t => t.length > 3 && !["eller", "inte", "från", "till", "genom", "under", "efter", "också", "eller", "eller"].includes(t.toLowerCase()));
    
  if (terms.length === 0) return escapedText;
  
  let highlighted = escapedText;
  try {
    for (const term of terms) {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      // Match words
      const regex = new RegExp(`\\b(${escaped})\\b`, "gi");
      highlighted = highlighted.replace(regex, '<mark class="rag-highlight">$1</mark>');
    }
  } catch {
    // ignore
  }
  return highlighted;
}

export function DocumentReader() {
  const {
    openDocuments,
    activeDocumentTabId,
    closeDocument,
    setActiveDocumentTabId,
    query,
  } = useAppStore();

  if (openDocuments.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-slate-500 bg-[#0F1318] border-l border-white/5 font-ui">
        <FileText className="w-10 h-10 mb-3 opacity-30 text-teal-400" />
        <span className="text-sm font-medium">Inga dokument öppnade</span>
        <span className="text-xs text-slate-600 mt-1 max-w-[240px] text-center leading-relaxed">
          Klicka på en källhänvisning i sökresultaten för att öppna dess fulltext här.
        </span>
      </div>
    );
  }

  const activeDoc = openDocuments.find((d) => d.id === activeDocumentTabId);

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#0F1318] border-l border-white/5 h-full relative z-20">
      
      {/* 1. Tabs List Header */}
      <div className="flex items-center bg-[#11161B] border-b border-white/5 overflow-x-auto custom-scrollbar pr-4">
        {openDocuments.map((doc) => {
          const isActive = doc.id === activeDocumentTabId;
          return (
            <div
              key={doc.id}
              className={`flex items-center gap-1.5 px-4 py-3 text-xs font-ui border-r border-white/5 cursor-pointer select-none transition-all group shrink-0 ${
                isActive
                  ? "bg-[#0F1318] text-teal-400 font-medium"
                  : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.01]"
              }`}
              onClick={() => setActiveDocumentTabId(doc.id)}
            >
              <FileText className={`w-3.5 h-3.5 ${isActive ? "text-teal-400" : "text-slate-600"}`} />
              <span className="truncate max-w-[120px]">{doc.title}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  closeDocument(doc.id);
                }}
                className="p-0.5 rounded text-stone-600 hover:text-red-400 hover:bg-white/5 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity ml-1.5"
                title="Stäng flik"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>

      {/* 2. Active Tab Content Area */}
      {activeDoc && (
        <div className="flex-1 flex flex-col min-h-0">
          
          {/* Metadata Sub-Header */}
          <div className="px-6 py-3 bg-[#11161B]/40 border-b border-white/5 flex items-center justify-between text-xs font-ui text-slate-400">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {activeDoc.sfs_nummer && (
                <span className="font-mono text-teal-400 font-semibold bg-teal-500/5 px-2 py-0.5 rounded border border-teal-500/10">
                  {activeDoc.sfs_nummer}
                </span>
              )}
              {activeDoc.source && (
                <span className="capitalize text-slate-300 font-medium">
                  Källa: {activeDoc.source}
                </span>
              )}
            </div>
            
            {activeDoc.sfs_nummer && (
              <a
                href={`https://www.riksdagen.se/sv/dokument-lagar/dokument/svensk-forfattningssamling/sfs-${activeDoc.sfs_nummer.replace(":", "-")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-stone-500 hover:text-teal-400 transition-colors"
              >
                <span>Visa på Riksdagen</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>

          {/* Document Content Display */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
            {!activeDoc.isLoaded ? (
              /* Skeleton Loading State */
              <div className="flex flex-col gap-4 animate-pulse">
                <div className="h-6 bg-white/[0.03] rounded-lg w-2/3" />
                <div className="h-4 bg-white/[0.03] rounded-lg w-1/2" />
                <div className="h-[1px] bg-white/5 my-4" />
                <div className="h-4 bg-white/[0.02] rounded w-full" />
                <div className="h-4 bg-white/[0.02] rounded w-full" />
                <div className="h-4 bg-white/[0.02] rounded w-5/6" />
                <div className="h-4 bg-white/[0.02] rounded w-full" />
                <div className="h-4 bg-white/[0.02] rounded w-4/5" />
              </div>
            ) : activeDoc.error ? (
              /* Error Display */
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2.5 text-amber-500 bg-amber-500/5 border border-amber-500/15 p-4 rounded-2xl font-ui text-xs">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <div>
                    <span className="font-semibold block mb-0.5">Kunde inte hämta fulltext</span>
                    <span>{activeDoc.error}. Visar sökavsnitt som fallback:</span>
                  </div>
                </div>
                <div className="h-[1px] bg-white/5 my-4" />
                <div className="font-doc text-slate-300 text-base leading-relaxed bg-black/10 border border-white/5 p-5 rounded-2xl">
                  {activeDoc.snippet}
                </div>
              </div>
            ) : (
              /* Document Fulltext (Lora font) */
              <article className="prose-doc max-w-3xl mx-auto">
                {activeDoc.law_name && (
                  <h1 className="text-xl sm:text-2xl font-semibold mb-2 text-slate-100 font-ui leading-normal">
                    {activeDoc.law_name}
                  </h1>
                )}
                {activeDoc.kapitel_rubrik && (
                  <h2 className="text-base text-teal-400 font-mono tracking-wider font-semibold mb-6">
                    {activeDoc.kapitel_rubrik}
                  </h2>
                )}
                
                <div
                  className="font-doc text-slate-300 text-base leading-relaxed whitespace-pre-wrap selection:bg-teal-500/30 selection:text-white"
                  dangerouslySetInnerHTML={{
                    __html: highlightText(
                      activeDoc.content || "",
                      activeDoc.snippet,
                      query
                    ),
                  }}
                />
              </article>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
