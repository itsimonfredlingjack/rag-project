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
                "border-t border-white/5",
                "bg-slate-950/20 backdrop-blur-xl",
                "px-4 py-3 relative z-20"
            )}
        >
            <div className="max-w-2xl mx-auto flex items-end gap-2.5 font-ui">
                {/* Mode selector buttons */}
                <div className="flex gap-1 flex-shrink-0 bg-slate-950/40 p-1 rounded border border-white/5">
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
                                    "w-9 h-9 rounded flex items-center justify-center cursor-pointer",
                                    "transition-all duration-200 focus:outline-none border",
                                    isActive
                                        ? "bg-accent-primary/10 border-accent-primary/20 text-accent-primary shadow-sm"
                                        : "bg-transparent border-transparent text-slate-500 hover:text-slate-300"
                                )}
                                title={mode.label}
                            >
                                <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
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
                                "w-full resize-none rounded px-4 py-2.5 pr-10 border",
                                shake
                                    ? "border-red-500 ring-1 ring-red-500/20"
                                    : "border-white/5",
                                "bg-slate-950/30",
                                "text-slate-200 text-sm placeholder:text-slate-500",
                                "focus:outline-none focus:border-accent-primary/30 focus:bg-slate-950/50",
                                "transition-all duration-200",
                                "disabled:opacity-60 disabled:cursor-not-allowed"
                            )}
                            style={{
                                minHeight: "40px",
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
                        "w-10 h-10 rounded flex items-center justify-center flex-shrink-0 border",
                        "transition-all duration-200 focus:outline-none",
                        !isSearching
                            ? "bg-accent-primary/15 border-accent-primary/25 text-accent-primary hover:bg-accent-primary/25 cursor-pointer"
                            : "bg-transparent border-white/5 text-slate-600 cursor-not-allowed"
                    )}
                >
                    <ArrowUp className="w-4 h-4" strokeWidth={2} />
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
                                "w-10 h-10 rounded flex items-center justify-center flex-shrink-0 cursor-pointer border",
                                "border-white/5 bg-white/[0.01] focus:outline-none",
                                "text-slate-400 hover:text-slate-200 hover:bg-white/[0.02]",
                                "transition-all duration-200"
                            )}
                            title="Ny konversation"
                        >
                            <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />
                        </motion.button>
                    )}
                </AnimatePresence>
            </div>

            {/* Hint text */}
            <div className="max-w-2xl mx-auto mt-1.5 px-1 flex justify-between text-[9px] text-slate-600 font-mono">
                <span>Enter = skicka | Shift+Enter = ny rad</span>
                <span>Riksdagens öppna data</span>
            </div>
        </div>
    );
};
