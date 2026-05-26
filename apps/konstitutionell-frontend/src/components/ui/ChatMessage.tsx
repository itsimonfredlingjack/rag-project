import React from "react";
import { motion } from "framer-motion";
import { Shield, BookOpen, GitCompare, RefreshCw, AlertCircle, FileQuestion, Loader2 } from "lucide-react";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";
import { SourceChip } from "./SourceChip";
import { AnswerWithCitations } from "./AnswerWithCitations";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { useAppStore } from "../../stores/useAppStore";

const MODE_ICONS = {
    verify: Shield,
    summarize: BookOpen,
    compare: GitCompare,
} as const;

const MODE_LABELS = {
    verify: "Verifiera",
    summarize: "Sammanfatta",
    compare: "Jämför",
} as const;

interface ChatMessageProps {
    queryResult: QueryResult;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ queryResult }) => {
    const retryQuery = useAppStore((s) => s.retryQuery);
    const {
        id,
        query,
        mode,
        answer,
        sources,
        searchStage,
        thoughtChain,
        error,
    } = queryResult;

    const ModeIcon = MODE_ICONS[mode];
    const isSearching = searchStage === "searching";
    const isError = searchStage === "error";
    const hasAnswer = searchStage === "reading" || searchStage === "complete" || searchStage === "reasoning";

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="w-full max-w-2xl mx-auto space-y-4"
        >
            {/* User's question - elegant transparent container */}
            <div className="flex justify-end gap-3">
                <div
                    className={clsx(
                        "relative max-w-[85%] rounded px-4 py-2.5",
                        "bg-[#38bdf8]/5 backdrop-blur-md",
                        "border border-[#38bdf8]/15 shadow-sm"
                    )}
                >
                    <p className="text-slate-100 text-sm leading-relaxed">{query}</p>
                    <div className="flex items-center gap-1.5 mt-1.5">
                        <ModeIcon className="w-3 h-3 text-slate-500" strokeWidth={1.5} />
                        <span className="text-[9px] font-mono uppercase tracking-wider text-slate-500">
                            {MODE_LABELS[mode]}
                        </span>
                    </div>
                </div>
            </div>

            {/* AI Response - with floating confidence badge */}
            <div
                className={clsx(
                    "relative rounded px-5 sm:px-6 pt-5 pb-5",
                    "glass-panel border border-white/5"
                )}
                role="region"
                aria-label="AI-svar"
                aria-live="polite"
            >
                {/* Floating Confidence Badge */}
                <div className="absolute -top-3 left-4">
                    <ConfidenceBadge queryResult={queryResult} />
                </div>

                {/* Simplified narrative Swedish loader (No tech pipeline dots) */}
                {
                    isSearching && (
                        <div className="mt-3 py-1 flex flex-col gap-3">
                            <div className="flex items-center gap-2 text-slate-400">
                                <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-primary" />
                                <span className="text-xs font-mono tracking-wide">
                                    {queryResult.pipelineStage === "query_classification" && "Analyserar fråga..."}
                                    {queryResult.pipelineStage === "decontextualization" && "Klargör sammanhang..."}
                                    {queryResult.pipelineStage === "retrieval" && "Söker i myndighetsarkiven..."}
                                    {queryResult.pipelineStage === "grading" && "Värderar relevans..."}
                                    {queryResult.pipelineStage === "self_reflection" && "Strukturerar svar..."}
                                    {queryResult.pipelineStage === "generation" && "Sammanställer svar..."}
                                    {queryResult.pipelineStage === "guardrail_validation" && "Kontrollerar fakta..."}
                                    {(!queryResult.pipelineStage || queryResult.pipelineStage === "idle") && "Bearbetar..."}
                                </span>
                            </div>
                            {/* Simple text loading skeleton */}
                            <div className="space-y-2 animate-pulse opacity-40">
                                <div className="h-2 bg-white/10 rounded w-11/12" />
                                <div className="h-2 bg-white/10 rounded w-4/5" />
                                <div className="h-2 bg-white/10 rounded w-3/4" />
                            </div>
                        </div>
                    )
                }

                {/* Error state with recovery action */}
                {
                    isError && (
                        <div className="mt-3 p-4 rounded bg-red-950/20 border border-red-500/15">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" strokeWidth={1.5} />
                                <div className="flex-1">
                                    <p className="text-xs font-semibold text-red-200">Ett fel uppstod</p>
                                    <p className="text-xs text-red-300 mt-1">
                                        {error || "Det gick inte att slutföra sökningen just nu."}
                                    </p>
                                    <button
                                        onClick={() => retryQuery(id)}
                                        className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-medium text-red-300 bg-red-500/10 hover:bg-red-500/20 rounded border border-red-500/20 transition-all cursor-pointer"
                                    >
                                        <RefreshCw className="w-3 h-3" />
                                        Försök igen
                                    </button>
                                </div>
                            </div>
                        </div>
                    )
                }

                {/* Answer content */}
                {
                    hasAnswer && (
                        <div className="mt-3">
                            {/* Thought chain (if present) - styled as simple details box */}
                            {typeof thoughtChain === "string" && thoughtChain.trim() && (
                                <details className="mb-3 border border-white/5 bg-black/10 rounded overflow-hidden">
                                    <summary className="px-3 py-2 text-[10px] text-slate-500 hover:text-slate-300 uppercase tracking-widest cursor-pointer select-none font-mono">
                                        Visa AI-analys
                                    </summary>
                                    <div className="p-3 border-t border-white/5 text-[11px] text-slate-400 font-mono bg-black/5 whitespace-pre-wrap leading-relaxed">
                                        {thoughtChain}
                                    </div>
                                </details>
                            )}

                            {/* Main answer */}
                            {answer ? (
                                <div
                                    className="text-slate-200 text-[13.5px] leading-relaxed font-ui"
                                    style={{ lineHeight: "1.8" }}
                                >
                                    <AnswerWithCitations answer={answer} sources={sources} />
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 text-slate-500 text-xs italic">
                                    <Loader2 className="w-3 h-3 animate-spin text-accent-primary" />
                                    Genererar svar...
                                </div>
                            )}
                        </div>
                    )
                }

                {/* Source chips or empty state */}
                {
                    hasAnswer && (
                        <div className="mt-4 pt-3.5 border-t border-white/5">
                            {sources.length > 0 ? (
                                <>
                                    <div className="text-[9px] font-mono uppercase tracking-widest text-slate-500 mb-2">
                                        Referenser ({sources.length})
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {sources.map((source) => (
                                            <SourceChip key={source.id} source={source} />
                                        ))}
                                    </div>
                                </>
                            ) : (
                                <div className="flex items-start gap-2.5 p-3 rounded bg-white/[0.01] border border-white/5">
                                    <FileQuestion className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                                    <div>
                                        <p className="text-xs font-medium text-slate-400">Inga direkta källhänvisningar hittades</p>
                                        <p className="text-[10px] text-slate-500 mt-0.5">
                                            Svaret baseras på modellens allmänna rättskunskap. Pröva att specificera lag eller myndighet i frågan.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>
                    )
                }
            </div >
        </motion.div >
    );
};
