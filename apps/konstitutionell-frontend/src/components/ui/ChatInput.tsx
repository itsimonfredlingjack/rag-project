import React, { useState, useEffect, useRef } from "react";
import { useAppStore } from "../../stores/useAppStore";
import clsx from "clsx";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, BookOpen, GitCompare, ArrowUp, RotateCcw } from "lucide-react";
import type { QueryResultMode } from "../../types/queryResult";
import type { BackendMode } from "../../stores/useAppStore";

const MODE_CONFIG: {
    id: QueryResultMode;
    icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
    label: string;
    backendMode: BackendMode;
}[] = [
        { id: "verify", icon: Shield, label: "Verifiera", backendMode: "evidence" },
        { id: "summarize", icon: BookOpen, label: "Sammanfatta", backendMode: "chat" },
        { id: "compare", icon: GitCompare, label: "Jämför", backendMode: "assist" },
    ];

export const ChatInput: React.FC = () => {
    const [input, setInput] = useState("");
    const [shake, setShake] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const activeMode = useAppStore((s) => s.activeMode);
    const setActiveMode = useAppStore((s) => s.setActiveMode);
    const setQuery = useAppStore((s) => s.setQuery);
    const startSearch = useAppStore((s) => s.startSearch);
    const isSearching = useAppStore((s) => s.isSearching);
    const queries = useAppStore((s) => s.queries);
    const resetToHome = useAppStore((s) => s.resetToHome);

    // Auto-resize textarea
    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + "px";
        }
    }, [input]);

    const handleSubmit = () => {
        if (isSearching) return;

        if (!input.trim()) {
            setShake(true);
            setTimeout(() => setShake(false), 500);
            return;
        }

        const modeConfig = MODE_CONFIG.find((m) => m.id === activeMode);
        const backendMode = modeConfig?.backendMode ?? "evidence";

        setQuery(input.trim());
        startSearch(backendMode, activeMode);
        setInput("");

        // Reset textarea height
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
        }
    };

    const handleNewConversation = () => {
        resetToHome();
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div
            className={clsx(
                "border-t border-white/[0.035]",
                "bg-panel-bg/40 backdrop-blur-xl",
                "px-4 py-3 relative z-20"
            )}
        >
            <div className="max-w-3xl mx-auto flex items-end gap-3 font-ui">
                {/* Mode selector buttons */}
                <div className="flex gap-1 flex-shrink-0 bg-black/20 p-1 rounded-2xl border border-white/5">
                    {MODE_CONFIG.map((mode) => {
                        const Icon = mode.icon;
                        const isActive = activeMode === mode.id;

                        return (
                            <button
                                key={mode.id}
                                type="button"
                                onClick={() => setActiveMode(mode.id)}
                                aria-label={mode.label}
                                aria-pressed={isActive}
                                className={clsx(
                                    "w-10 h-10 rounded-xl flex items-center justify-center cursor-pointer",
                                    "transition-all duration-200 focus:outline-none",
                                    isActive
                                        ? "bg-accent-primary/10 border border-accent-primary/25 text-accent-primary shadow-[0_0_12px_rgba(0,240,244,0.15)]"
                                        : "bg-transparent border border-transparent text-slate-400 hover:text-slate-200"
                                )}
                                title={mode.label}
                            >
                                <Icon className="w-4 h-4" strokeWidth={1.5} />
                            </button>
                        );
                    })}
                </div>

                {/* Input textarea */}
                <div className="flex-1 relative">
                    <motion.div
                        animate={shake ? { x: [-4, 4, -4, 4, 0] } : { x: 0 }}
                        transition={{ duration: 0.4 }}
                    >
                        <textarea
                            ref={textareaRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ställ en fråga..."
                            rows={1}
                            disabled={isSearching}
                            className={clsx(
                                "w-full resize-none rounded-2xl px-4 py-3 pr-12",
                                "bg-black/30 border",
                                shake
                                    ? "border-red-500 ring-2 ring-red-500/20"
                                    : "border-white/5",
                                "text-slate-200 text-[14px] placeholder:text-slate-500",
                                "focus:outline-none focus:ring-1 focus:ring-accent-primary/10 focus:border-accent-primary/30 focus:shadow-[0_0_15px_rgba(0,240,244,0.06)]",
                                "transition-all duration-200",
                                "disabled:opacity-60 disabled:cursor-not-allowed"
                            )}
                            style={{
                                minHeight: "48px",
                                maxHeight: "150px",
                            }}
                        />
                    </motion.div>
                </div>

                {/* Send button */}
                <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={isSearching}
                    aria-label="Skicka"
                    className={clsx(
                        "w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0",
                        "transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-accent-primary/20",
                        !isSearching
                            ? "bg-accent-primary text-slate-950 hover:bg-accent-primary/95 shadow-[0_0_12px_rgba(0,240,244,0.25)] hover:shadow-[0_0_18px_rgba(0,240,244,0.45)] cursor-pointer"
                            : "bg-white/[0.02] border border-white/5 text-slate-600 cursor-not-allowed"
                    )}
                >
                    <ArrowUp className="w-5 h-5" strokeWidth={2} />
                </button>

                {/* New conversation button */}
                <AnimatePresence>
                    {queries.length > 0 && (
                        <motion.button
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.8 }}
                            type="button"
                            onClick={handleNewConversation}
                            aria-label="Ny konversation"
                            className={clsx(
                                "w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0 cursor-pointer",
                                "border border-white/5 bg-white/[0.02] focus:outline-none focus:ring-2 focus:ring-white/10",
                                "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]",
                                "transition-all duration-200"
                            )}
                            title="Ny konversation"
                        >
                            <RotateCcw className="w-4 h-4" strokeWidth={1.5} />
                        </motion.button>
                    )}
                </AnimatePresence>
            </div>

            {/* Hint text */}
            <div className="max-w-3xl mx-auto mt-2 px-1">
                <span className="text-[10px] text-slate-500 font-mono">
                    Enter = skicka ↵ | Shift+Enter = ny rad
                </span>
            </div>
        </div>
    );
};
