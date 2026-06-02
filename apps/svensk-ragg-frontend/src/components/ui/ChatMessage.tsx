import React from "react";
import { motion } from "framer-motion";
import {
    Shield,
    BookOpen,
    GitCompare,
    RefreshCw,
    AlertCircle,
    FileQuestion,
    Loader2,
    Database,
    Clock,
    FileText,
    ExternalLink,
} from "lucide-react";
import clsx from "clsx";
import type { QueryResult, QueryResultSource } from "../../types/queryResult";
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

const PUBLIC_SCOPE = "riksdagen_open_data_only";

const formatLatency = (value?: number | null): string | null => {
    if (value == null || Number.isNaN(value)) return null;
    if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
    return `${Math.round(value)} ms`;
};

const sourceDocumentId = (source: QueryResultSource): string =>
    source.document_id || source.id || "—";

const fieldValue = (value?: string | null): string => {
    if (!value || !value.trim()) return "—";
    return value;
};

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
        dataSourceAttribution,
        refusalReason,
        latencyMs,
        retrievalLatencyMs,
        totalTimeMs,
        retrievalStrategy,
        citations,
    } = queryResult;

    const ModeIcon = MODE_ICONS[mode];
    const isSearching = searchStage === "searching";
    const isRefusal = Boolean(refusalReason);
    const isError = searchStage === "error" && !isRefusal;
    const hasAnswer = searchStage === "reading" || searchStage === "complete" || searchStage === "reasoning" || Boolean(answer) || isRefusal;
    const sourceIds = Array.from(
        new Set(sources.map(sourceDocumentId).filter((sourceId) => sourceId !== "—"))
    );
    const renderedLatency = formatLatency(latencyMs ?? totalTimeMs ?? retrievalLatencyMs);
    const isPublicResponse = Boolean(
        dataSourceAttribution ||
        refusalReason ||
        retrievalStrategy === "public_bm25_only" ||
        citations?.length ||
        sources.some((source) => source.source_scope === PUBLIC_SCOPE || source.source === "riksdagen")
    );

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
                                    {queryResult.pipelineStage === "retrieval" && "Söker i Riksdagens öppna data..."}
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
                                    className={clsx(
                                        "text-[13.5px] leading-relaxed font-ui",
                                        isRefusal ? "text-amber-100" : "text-slate-200"
                                    )}
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

                            {isPublicResponse && (
                                <div
                                    className={clsx(
                                        "mt-4 rounded border p-3 text-[11px] leading-relaxed",
                                        isRefusal
                                            ? "bg-amber-950/15 border-amber-400/15 text-amber-100"
                                            : "bg-sky-950/10 border-sky-300/10 text-slate-300"
                                    )}
                                >
                                    <div className="grid gap-2">
                                        {dataSourceAttribution && (
                                            <div className="flex items-start gap-2">
                                                <Database className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-primary" strokeWidth={1.5} />
                                                <span>{dataSourceAttribution}</span>
                                            </div>
                                        )}
                                        {sourceIds.length > 0 && (
                                            <div className="flex items-start gap-2">
                                                <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" strokeWidth={1.5} />
                                                <span>
                                                    Käll-ID: <span className="font-mono">{sourceIds.join(", ")}</span>
                                                </span>
                                            </div>
                                        )}
                                        {renderedLatency && (
                                            <div className="flex items-start gap-2">
                                                <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" strokeWidth={1.5} />
                                                <span>Svarstid: {renderedLatency}</span>
                                            </div>
                                        )}
                                        {refusalReason && (
                                            <div className="flex items-start gap-2">
                                                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" strokeWidth={1.5} />
                                                <span>
                                                    refusal_reason: <span className="font-mono">{refusalReason}</span>
                                                </span>
                                            </div>
                                        )}
                                    </div>
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
                                    {isPublicResponse && (
                                        <details className="mt-3 rounded border border-white/5 bg-black/10 overflow-hidden">
                                            <summary className="px-3 py-2 text-[10px] text-slate-400 hover:text-slate-200 uppercase tracking-widest cursor-pointer select-none font-mono">
                                                Visa hämtade källor
                                            </summary>
                                            <div className="border-t border-white/5 divide-y divide-white/5">
                                                {sources.map((source) => (
                                                    <div key={`${source.id}-inspector`} className="p-3 text-[11px] text-slate-300">
                                                        <div className="font-medium text-slate-200 leading-snug">
                                                            {source.title || sourceDocumentId(source)}
                                                        </div>
                                                        <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[10px]">
                                                            <div>
                                                                <dt className="text-slate-500">document_id</dt>
                                                                <dd className="break-all text-slate-300">{sourceDocumentId(source)}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="text-slate-500">date</dt>
                                                                <dd>{fieldValue(source.date)}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="text-slate-500">source_scope</dt>
                                                                <dd className="break-all">{fieldValue(source.source_scope)}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="text-slate-500">retriever_source</dt>
                                                                <dd>{fieldValue(source.retriever_source || source.retriever)}</dd>
                                                            </div>
                                                            <div className="sm:col-span-2">
                                                                <dt className="text-slate-500">url</dt>
                                                                <dd className="break-all">
                                                                    {source.url ? (
                                                                        <a
                                                                            href={source.url}
                                                                            target="_blank"
                                                                            rel="noreferrer"
                                                                            className="inline-flex items-center gap-1 text-accent-primary hover:text-sky-200"
                                                                        >
                                                                            {source.url}
                                                                            <ExternalLink className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                                                                        </a>
                                                                    ) : (
                                                                        "—"
                                                                    )}
                                                                </dd>
                                                            </div>
                                                        </dl>
                                                    </div>
                                                ))}
                                            </div>
                                        </details>
                                    )}
                                </>
                            ) : (
                                <div className={clsx(
                                    "flex items-start gap-2.5 p-3 rounded border",
                                    isRefusal
                                        ? "bg-amber-950/10 border-amber-400/10"
                                        : "bg-white/[0.01] border-white/5"
                                )}>
                                    <FileQuestion className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                                    <div>
                                        <p className="text-xs font-medium text-slate-400">
                                            {isRefusal ? "Strukturerad vägran" : "Inga direkta källhänvisningar hittades"}
                                        </p>
                                        <p className="text-[10px] text-slate-500 mt-0.5">
                                            {isPublicResponse
                                                ? "Inga Riksdagen-källor kunde visas för detta svar."
                                                : "Inga källor kunde visas för denna körning."}
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
