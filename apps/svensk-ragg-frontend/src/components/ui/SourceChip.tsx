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

    // Color logic - clean obsidian/blue
    const score = source.score;
    const isHigh = score >= 0.6;

    const colorClass = isHigh ? "bg-accent-primary/5" : "bg-white/[0.01]";
    const borderClass = isHigh ? "border-accent-primary/15" : "border-white/5";
    const textClass = isHigh ? "text-accent-primary" : "text-slate-400";
    const bgHoverClass = isHigh ? "hover:bg-accent-primary/10" : "hover:bg-white/[0.03]";
    const bgExpandedClass = "bg-[#0b0f13]/95";

    // Format title: shorten if too long
    const shortTitle = source.title.length > 28
        ? source.title.slice(0, 25) + "…"
        : source.title;

    return (
        <div className="inline-block align-top">
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={clsx(
                    "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[3px] text-[10px] font-mono",
                    "border transition-all duration-200",
                    "active:scale-[0.98]",
                    colorClass,
                    borderClass,
                    textClass,
                    bgHoverClass
                )}
            >
                <span>{shortTitle}</span>
                <span className="opacity-60">{source.score.toFixed(2)}</span>
                <ChevronDown
                    className={clsx(
                        "w-3 h-3 transition-transform opacity-60",
                        isExpanded && "rotate-180"
                    )}
                    strokeWidth={1.5}
                />
            </button>

            {isExpanded && (
                <div
                    className={clsx(
                        "mt-1.5 p-3.5 rounded border text-xs max-w-sm shadow-xl backdrop-blur-md relative z-30",
                        "text-slate-300",
                        bgExpandedClass,
                        "border-white/5"
                    )}
                >
                    <div className="flex justify-between items-start mb-2 gap-2">
                        <div className="font-semibold text-slate-200 text-xs">{source.title}</div>
                        <div className="text-[8px] uppercase tracking-widest font-mono px-1.5 py-0.5 rounded border bg-white/[0.02] text-slate-400 border-white/5">
                            {source.doc_type || "DOC"}
                        </div>
                    </div>

                    {/* Inline Preview */}
                    <div className="bg-black/30 p-2.5 rounded border border-white/5 font-serif text-slate-300 text-[11px] leading-relaxed italic mb-2">
                        "{source.snippet || "Ingen förhandsgranskning tillgänglig."}"
                    </div>

                    <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-white/5 text-[9px] text-slate-500 font-mono">
                        <div className="flex items-center gap-2">
                            <span>Källa: {source.source || "—"}</span>
                            <span>Score: {(source.score * 100).toFixed(0)}%</span>
                        </div>
                        <button
                            type="button"
                            onClick={() => {
                                useAppStore.getState().openDocument(source.id, source.title, source.snippet, source.source);
                            }}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-accent-primary/10 hover:bg-accent-primary/20 text-accent-primary border border-accent-primary/20 hover:border-accent-primary/30 transition-all cursor-pointer font-ui text-[9px] font-medium"
                        >
                            <FileText className="w-2.5 h-2.5" />
                            <span>Öppna</span>
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
