import { motion } from "framer-motion";
import {
  Search,
  Map,
  Shield,
  Zap,
  ChevronRight,
  CornerDownLeft,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useAppStore } from "../../stores/useAppStore";
import { useState, useRef, useEffect } from "react";

// Color mapping for Tailwind classes (must be explicit for build-time)
const COLOR_CLASSES = {
  cyan: {
    bg: "bg-teal-500/10 border border-teal-500/20",
    text: "text-teal-400",
  },
  emerald: {
    bg: "bg-emerald-500/10 border border-emerald-500/20",
    text: "text-emerald-400",
  },
  orange: {
    bg: "bg-amber-500/10 border border-amber-500/20",
    text: "text-amber-400",
  },
} as const;

const PLACEHOLDER_BY_MODE: Record<"verify" | "summarize" | "compare", string> =
{
  verify: "Ställ en fråga mot lokala offentliga dokument...",
  summarize: "Be om en kort sammanfattning av hittade källor...",
  compare: "Jämför två dokument eller regelverk...",
};

const GLASS_CARDS = [
  {
    id: "verify",
    title: "Fråga med källor",
    text: "Testa hur retrieval, svar och källpanel hänger ihop.",
    icon: Shield,
    color: "cyan" as const,
    mode: "verify" as const,
    example: "Är det grundlagsskyddat att demonstrera utan tillstånd?",
  },
  {
    id: "summarize",
    title: "Källspårning",
    text: "Inspektera vilka dokument som valdes ut som underlag.",
    icon: Map,
    color: "emerald" as const,
    mode: "summarize" as const,
    example: "Sammanfatta SOU 2023:25 om AI-förordningen.",
  },
  {
    id: "compare",
    title: "Jämförelse",
    text: "Jämför material och se hur pipeline väger källor.",
    icon: Zap,
    color: "orange" as const,
    mode: "compare" as const,
    example: "Jämför RF 2 kap. med EKMR artikel 10.",
  },
];

const EXAMPLE_QUESTIONS = [
  "Vad säger regeringsformen om demonstrationsfrihet?",
  "Vad krävs för att ändra en grundlag?",
  "Jämför yttrandefriheten i RF med USA:s First Amendment."
];

export function HeroSection() {
  const { query, setQuery, startSearch, isSearching } = useAppStore();
  const [activeMode, setActiveMode] = useState<
    "verify" | "summarize" | "compare"
  >("verify");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Map UI modes to backend modes
  const BACKEND_MODE_MAP: Record<
    typeof activeMode,
    "auto" | "chat" | "assist" | "evidence"
  > = {
    verify: "evidence",
    summarize: "chat",
    compare: "auto",
  };

  // Use DOM value as source of truth so click-submit always sees latest (fixes IME/stale state)
  const getValueToSubmit = (): string => {
    const fromDom = textareaRef.current?.value;
    const value = (
      fromDom !== undefined && fromDom !== null ? fromDom : query
    ).trim();
    return value;
  };

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isSearching) return;

    const value = getValueToSubmit();
    if (!value) return;

    // Apply back to store
    setQuery(value);
    
    const backendMode = BACKEND_MODE_MAP[activeMode];
    startSearch(backendMode, activeMode);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleExampleClick = (q: string) => {
    if (isSearching) return;
    setQuery(q);
    if (textareaRef.current) {
      textareaRef.current.value = q;
    }
    const backendMode = BACKEND_MODE_MAP[activeMode];
    startSearch(backendMode, activeMode);
  };

  const handleCardClick = (card: typeof GLASS_CARDS[number]) => {
    if (isSearching) return;
    setActiveMode(card.mode);
    setQuery(card.example);
    if (textareaRef.current) {
      textareaRef.current.value = card.example;
    }
    const backendMode = BACKEND_MODE_MAP[card.mode];
    startSearch(backendMode, card.mode);
  };

  const handleSubmitButtonMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    handleSubmit();
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        textareaRef.current.scrollHeight + "px";
    }
  }, [query]);

  return (
    <motion.div
      className="flex flex-col items-center justify-start w-full max-w-4xl mx-auto pt-[min(8vh,3rem)] px-4 sm:px-6 font-ui"
      animate={{
        opacity: isSearching ? 0.4 : 1,
        scale: isSearching ? 0.98 : 1,
        filter: isSearching ? "blur(2px)" : "blur(0px)"
      }}
      transition={{ duration: 0.15 }}
    >
      {/* 1. Hero Search */}
      <div className="w-full relative z-20 group">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-3 px-1">
          {/* Brand with subtle gradient accent */}
          <h1 className="text-xl sm:text-2xl font-light tracking-widest text-slate-100">
            <span className="bg-gradient-to-r from-slate-100 via-teal-400 to-slate-200 bg-clip-text text-transparent animate-gradient">
              KONSTITUTIONELL AI
            </span>{" "}
            <span className="text-teal-400 font-mono text-[10px] sm:text-xs ml-1 sm:ml-2">v3.0</span>
          </h1>

          {/* Mode Selector */}
          <div className="flex items-center gap-1 bg-[#11161B]/60 rounded-xl p-1 border border-white/5 shadow-sm backdrop-blur-sm self-start sm:self-auto">
            {(["verify", "summarize", "compare"] as const).map((mode) => {
              const labels: Record<typeof mode, string> = {
                verify: "Verifiera",
                summarize: "Sammanfatta",
                compare: "Jämför",
              };
              return (
                <button
                  key={mode}
                  onClick={() => setActiveMode(mode)}
                  className={`min-h-[36px] px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer focus-ring ${activeMode === mode
                    ? "bg-teal-500/10 border border-teal-500/20 text-teal-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                    }`}
                >
                  {labels[mode]}
                </button>
              );
            })}
          </div>
        </div>

        {/* Input Area */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="absolute inset-0 bg-teal-500/5 blur-xl rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

          <div className="relative bg-[#11161B]/80 border border-white/5 backdrop-blur-xl rounded-2xl p-2 flex items-center transition-all focus-within:bg-[#11161B] focus-within:border-teal-500/40 focus-within:ring-2 focus-within:ring-teal-500/10 shadow-lg">
            <Search
              className="w-6 h-6 text-slate-500 ml-4 self-start mt-4"
              strokeWidth={1.5}
            />
            <textarea
              ref={textareaRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSearching}
              aria-label="Sökfråga"
              placeholder={PLACEHOLDER_BY_MODE[activeMode]}
              rows={1}
              className="flex-1 bg-transparent border-none text-base sm:text-lg text-slate-100 placeholder-slate-500 p-4 focus:ring-0 focus:outline-none tracking-wide resize-none overflow-hidden"
              style={{ minHeight: "56px" }}
            />
            <div className="mr-2 sm:mr-4 flex items-center gap-2 sm:gap-3 self-start mt-2 sm:mt-3">
              <span className="text-[10px] font-mono text-slate-500 bg-white/5 px-2 py-1 rounded border border-white/5 hidden md:block">
                Enter{" "}
                <CornerDownLeft
                  className="w-3 h-3 inline ml-1 text-slate-400 opacity-50"
                  strokeWidth={1.5}
                />
              </span>
              <button
                type="submit"
                disabled={isSearching}
                onMouseDown={handleSubmitButtonMouseDown}
                aria-label="Skicka fråga"
                className="min-w-[44px] min-h-[44px] p-2.5 bg-teal-500/10 hover:bg-teal-500/20 rounded-xl text-teal-400 border border-teal-500/20 hover:border-teal-500/40 cursor-pointer transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed focus-ring"
              >
                {isSearching ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <ChevronRight className="w-5 h-5" strokeWidth={1.5} />
                )}
              </button>
            </div>
          </div>
        </form>

        {/* Example Questions */}
        {!query && (
          <>
            <h2 className="sr-only">Exempelfrågor</h2>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleExampleClick(q)}
                  className="flex items-center gap-1.5 px-3.5 py-2 min-h-[36px] rounded-full bg-white/[0.02] hover:bg-white/[0.04] border border-white/5 hover:border-teal-500/30 text-xs text-slate-400 hover:text-teal-400 transition-colors cursor-pointer focus-ring"
                >
                  <Sparkles className="w-3 h-3 opacity-60 text-teal-400" />
                  <span className="hidden sm:inline">{q}</span>
                  <span className="sm:hidden">{q.length > 35 ? q.slice(0, 35) + "..." : q}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* 2. Quick Actions / Interactive Cards */}
      <h2 className="sr-only">Kom igång</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 w-full mt-8 sm:mt-12">
        {GLASS_CARDS.map((card, i) => (
          <motion.button
            key={card.id}
            type="button"
            onClick={() => handleCardClick(card)}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 + i * 0.05, duration: 0.2 }}
            className="group relative bg-[#11161B]/80 hover:bg-[#151C23] border border-white/5 hover:border-teal-500/20 p-6 rounded-2xl backdrop-blur-md transition-all cursor-pointer hover:-translate-y-1 shadow-sm hover:shadow-lg text-left w-full"
          >
            {/* Top Shine */}
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            <div className="flex items-start justify-between mb-4">
              <div
                className={`w-10 h-10 rounded-xl ${COLOR_CLASSES[card.color].bg} flex items-center justify-center group-hover:scale-110 transition-transform duration-300 border border-white/5`}
              >
                <card.icon className="w-5 h-5 text-slate-200" strokeWidth={1.5} />
              </div>
              <div className="opacity-0 group-hover:opacity-100 transition-opacity transform translate-x-2 group-hover:translate-x-0">
                <ChevronRight
                  className="w-4 h-4 text-stone-500"
                  strokeWidth={1.5}
                />
              </div>
            </div>

            <h3 className="text-slate-100 font-medium mb-2 group-hover:text-teal-400 transition-colors">
              {card.title}
            </h3>
            <p className="text-sm text-slate-400 leading-relaxed font-light mb-3">
              {card.text}
            </p>
            <div className="text-[10px] font-mono text-slate-500 bg-black/10 inline-block px-2.5 py-1 rounded border border-white/5">
              Ex: {card.example.slice(0, 30)}...
            </div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
