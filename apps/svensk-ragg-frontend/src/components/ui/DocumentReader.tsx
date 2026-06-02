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
      <div className="flex items-center bg-[#090b0e] border-b border-white/5 overflow-x-auto custom-scrollbar pr-4">
        {openDocuments.map((doc) => {
          const isActive = doc.id === activeDocumentTabId;
          return (
            <div
              key={doc.id}
              className={`flex items-center gap-2 px-4 py-3 text-[11px] font-ui border-r border-white/5 cursor-pointer select-none transition-all group shrink-0 relative ${
                isActive
                  ? "bg-slate-900/40 text-accent-primary font-medium"
                  : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.01]"
              }`}
              onClick={() => setActiveDocumentTabId(doc.id)}
            >
              <FileText className={`w-3.5 h-3.5 ${isActive ? "text-accent-primary" : "text-slate-600"}`} />
              <span className="truncate max-w-[120px]">{doc.title}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  closeDocument(doc.id);
                }}
                className="p-0.5 rounded text-slate-600 hover:text-red-400 hover:bg-white/5 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity ml-1.5"
                title="Stäng flik"
              >
                <X className="w-3 h-3" />
              </button>
              {isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent-primary" />
              )}
            </div>
          );
        })}
      </div>

      {/* 2. Active Tab Content Area */}
      {activeDoc && (
        <div className="flex-1 flex flex-col min-h-0">
          
          {/* Metadata Sub-Header */}
          <div className="px-6 py-2.5 bg-slate-950/10 border-b border-white/5 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              {activeDoc.sfs_nummer && (
                <span className="text-accent-tertiary font-semibold bg-amber-500/5 px-2 py-0.5 rounded-[3px] border border-amber-500/10">
                  SFS {activeDoc.sfs_nummer}
                </span>
              )}
              {activeDoc.source && (
                <span className="capitalize text-slate-400 font-medium">
                  Källa: {activeDoc.source}
                </span>
              )}
            </div>
            
            {activeDoc.sfs_nummer && (
              <a
                href={`https://www.riksdagen.se/sv/dokument-lagar/dokument/svensk-forfattningssamling/sfs-${activeDoc.sfs_nummer.replace(":", "-")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-slate-500 hover:text-accent-primary transition-colors font-ui text-[10px]"
              >
                <span>Riksdagen</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>

          {/* Document Content Display */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-6 sm:p-8">
            {!activeDoc.isLoaded ? (
              /* Skeleton Loading State */
              <div className="flex flex-col gap-4 animate-pulse opacity-40">
                <div className="h-5 bg-white/10 rounded w-2/3" />
                <div className="h-3 bg-white/10 rounded w-1/2" />
                <div className="h-[1px] bg-white/5 my-4" />
                <div className="h-3 bg-white/5 rounded w-full" />
                <div className="h-3 bg-white/5 rounded w-full" />
                <div className="h-3 bg-white/5 rounded w-5/6" />
              </div>
            ) : activeDoc.error ? (
              /* Error Display */
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2.5 text-accent-tertiary bg-amber-500/5 border border-amber-500/10 p-4 rounded font-ui text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <div>
                    <span className="font-semibold block mb-0.5">Kunde inte hämta fulltext</span>
                    <span>{activeDoc.error}. Visar sökavsnitt:</span>
                  </div>
                </div>
                <div className="h-[1px] bg-white/5 my-4" />
                <div className="font-doc text-slate-300 text-sm leading-relaxed bg-black/10 border border-white/5 p-5 rounded">
                  {activeDoc.snippet}
                </div>
              </div>
            ) : (
              /* Document Fulltext (Lora font) */
              <article className="prose-doc max-w-2xl mx-auto">
                {activeDoc.law_name && (
                  <h1 className="text-lg sm:text-xl font-semibold mb-1 text-slate-100 font-ui leading-normal">
                    {activeDoc.law_name}
                  </h1>
                )}
                {activeDoc.kapitel_rubrik && (
                  <h2 className="text-[10px] text-accent-primary font-mono tracking-wider font-semibold uppercase mb-6">
                    {activeDoc.kapitel_rubrik}
                  </h2>
                )}
                
                <div
                  className="font-doc text-slate-300 text-sm leading-relaxed whitespace-pre-wrap selection:bg-accent-primary/20 selection:text-white"
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
