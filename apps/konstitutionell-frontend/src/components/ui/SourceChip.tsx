import React, { useState } from "react";
import clsx from "clsx";
import { ChevronDown, FileText } from "lucide-react";
import type { QueryResultSource } from "../../types/queryResult";
import { useAppStore } from "../../stores/useAppStore";

interface SourceChipProps {
    source: QueryResultSource;
}

export const SourceChip: React.FC<SourceChipProps> = ({ source }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    // Color logic
    const score = source.score;
    let colorClass = "";
    let borderClass = "";
    let textClass = "";
    let bgHoverClass = "";
    const bgExpandedClass = "bg-[#13181E]/95";

    if (score >= 0.7) {
        // High relevance (Green)
        colorClass = "bg-emerald-500/5";
        borderClass = "border-emerald-500/20";
        textClass = "text-emerald-400";
        bgHoverClass = "hover:bg-emerald-500/10";
    } else if (score >= 0.4) {
        // Medium relevance (Orange)
        colorClass = "bg-amber-500/5";
        borderClass = "border-amber-500/20";
        textClass = "text-amber-400";
        bgHoverClass = "hover:bg-amber-500/10";
    } else {
        // Low relevance (Red)
        colorClass = "bg-red-500/5";
        borderClass = "border-red-500/20";
        textClass = "text-red-400";
        bgHoverClass = "hover:bg-red-500/10";
    }

    // Format title: shorten if too long
    const shortTitle = source.title.length > 25
        ? source.title.slice(0, 22) + "…"
        : source.title;

    return (
        <div className="inline-block align-top">
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={clsx(
                    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono",
                    "border transition-all duration-200",
                    "hover:scale-[1.02] active:scale-[0.98]",
                    colorClass,
                    borderClass,
                    textClass,
                    bgHoverClass
                )}
            >
                <span>{shortTitle}</span>
                <span className="opacity-70">{source.score.toFixed(2)}</span>
                <ChevronDown
                    className={clsx(
                        "w-3 h-3 transition-transform",
                        isExpanded && "rotate-180"
                    )}
                    strokeWidth={1.5}
                />
            </button>

            {isExpanded && (
                <div
                    className={clsx(
                        "mt-1.5 ml-1 p-3 rounded-xl border text-xs max-w-md shadow-lg backdrop-blur-md relative z-30",
                        "text-slate-300",
                        bgExpandedClass,
                        borderClass
                    )}
                >
                    <div className="flex justify-between items-start mb-2 gap-2">
                        <div className="font-semibold text-slate-200">{source.title}</div>
                        <div className={clsx("text-[9px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded border bg-white/[0.02]", borderClass, "text-slate-400 border-white/10")}>
                            {source.doc_type || "DOC"}
                        </div>
                    </div>

                    {/* Inline Preview */}
                    <div className="bg-black/20 p-2.5 rounded-lg border border-white/5 font-serif text-slate-300 leading-relaxed italic mb-2">
                        "{source.snippet || "Ingen förhandsgranskning tillgänglig."}"
                    </div>

                    <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-white/5 text-[10px] text-slate-500 font-mono">
                        <div className="flex items-center gap-2.5">
                            <span>Källa: {source.source || "—"}</span>
                            <span>Relevans: {(source.score * 100).toFixed(0)}%</span>
                        </div>
                        <button
                            type="button"
                            onClick={() => {
                                useAppStore.getState().openDocument(source.id, source.title, source.snippet, source.source);
                            }}
                            className="flex items-center gap-1 px-2.5 py-1 rounded bg-teal-500/10 hover:bg-teal-500/20 text-teal-400 border border-teal-500/20 hover:border-teal-500/30 transition-all cursor-pointer font-ui text-[10px] font-medium"
                        >
                            <FileText className="w-3 h-3" />
                            <span>Öppna i läsare</span>
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
