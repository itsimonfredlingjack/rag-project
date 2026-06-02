import React, { useState } from "react";
import { Shield, ShieldAlert, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";

interface ConfidenceBadgeProps {
    queryResult: QueryResult;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
    queryResult,
}) => {
    const [showTooltip, setShowTooltip] = useState(false);
    const { evidenceLevel: backendLevel, sources, answer, searchStage } = queryResult;

    // Don't render if no answer yet or still searching
    if (!answer || searchStage === "searching") return null;

    const sourceCount = sources.length;
    // Calculate avg score if possible
    const avgScore =
        sourceCount > 0
            ? sources.reduce((acc, s) => acc + s.score, 0) / sourceCount
            : 0;

    // Compute fallback evidence level if backend doesn't provide one
    const computedLevel = (): "HIGH" | "MEDIUM" | "LOW" => {
        if (sourceCount >= 3 && avgScore >= 0.6) return "HIGH";
        if (sourceCount >= 1 && avgScore >= 0.4) return "MEDIUM";
        return "LOW";
    };

    const evidenceLevel = backendLevel || computedLevel();

    // Configuration based on level
    const config = {
        HIGH: {
            label: "Verifierad källa",
            icon: Shield,
            color: "text-[#38bdf8]",
            bg: "bg-[#38bdf8]/5",
            border: "border-[#38bdf8]/20",
        },
        MEDIUM: {
            label: "Indirekt källa",
            icon: Shield,
            color: "text-[#f59e0b]",
            bg: "bg-[#f59e0b]/5",
            border: "border-[#f59e0b]/20",
        },
        LOW: {
            label: "Obekräftad",
            icon: ShieldAlert,
            color: "text-red-400",
            bg: "bg-red-500/5",
            border: "border-red-500/20",
        },
    }[evidenceLevel || "LOW"];

    const activeConfig = config || {
        label: "Okänd status",
        icon: Info,
        color: "text-slate-500",
        bg: "bg-white/[0.01]",
        border: "border-white/5",
    };

    const Icon = activeConfig.icon;

    return (
        <div className="relative inline-block">
            <button
                type="button"
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                onClick={() => setShowTooltip(!showTooltip)}
                className={clsx(
                    "flex items-center gap-1 px-2 py-0.5 rounded-[3px] border cursor-help transition-colors shadow-sm",
                    activeConfig.bg,
                    activeConfig.border,
                    activeConfig.color
                )}
            >
                <Icon className="w-3 h-3" strokeWidth={2} />
                <span className="text-[9px] font-semibold uppercase tracking-wider">
                    {activeConfig.label.split(" ")[0]}
                </span>
            </button>

            <AnimatePresence>
                {showTooltip && (
                    <motion.div
                        initial={{ opacity: 0, y: 4, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 4, scale: 0.98 }}
                        transition={{ duration: 0.1 }}
                        className="absolute bottom-full left-0 mb-2 w-60 p-3 bg-[#0b0f13]/95 rounded border border-white/5 shadow-2xl z-50 text-left pointer-events-none backdrop-blur-md text-slate-300"
                    >
                        <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/5">
                            <Icon className={clsx("w-3.5 h-3.5", activeConfig.color)} />
                            <span className={clsx("text-xs font-semibold uppercase tracking-wide", activeConfig.color)}>
                                {activeConfig.label}
                            </span>
                        </div>

                        <div className="space-y-1.5 text-[11px]">
                            <div className="flex justify-between">
                                <span className="text-slate-500">Antal referenser:</span>
                                <span className="font-mono text-slate-300">{sourceCount}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-slate-500">Genomsnittlig relevans:</span>
                                <span className="font-mono text-slate-300">
                                    {(avgScore * 100).toFixed(0)}%
                                </span>
                            </div>
                            <div className="mt-2 text-[10px] text-slate-500 leading-normal">
                                Bedömning baseras på källornas kvalitet och träffsäkerhet för denna fråga.
                            </div>
                        </div>

                        {/* Arrow */}
                        <div className="absolute bottom-[-5px] left-4 w-2 h-2 bg-[#0b0f13] border-b border-r border-white/5 transform rotate-45" />
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
