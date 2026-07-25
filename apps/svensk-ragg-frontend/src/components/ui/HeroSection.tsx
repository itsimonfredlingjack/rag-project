import { motion } from "framer-motion";
import {
  Search,
  ChevronRight,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useAppStore } from "../../stores/useAppStore";
import { useState, useRef, useEffect } from "react";

const PLACEHOLDER_BY_MODE: Record<"verify" | "summarize" | "compare", string> =
{
  verify: "Sök och verifiera mot Riksdagens öppna data...",
  summarize: "Be om en sammanfattning utifrån Riksdagen-källor...",
  compare: "Jämför teman eller dokument i Riksdagens öppna data...",
};

const GOLDEN_CARDS = [
  {
    id: "verify",
    title: "Verifiera i riksdagsmaterial",
    text: "Kontrollera påståenden mot hämtade källor från Riksdagens öppna data.",
    example: "Är det grundlagsskyddat att demonstrera utan tillstånd?",
  },
  {
    id: "summarize",
    title: "Sammanfatta källor",
    text: "Få en kort sammanställning och granska de hämtade riksdagsdokumenten direkt.",
    example: "Vad krävs för att ändra en svensk grundlag?",
  },
  {
    id: "compare",
    title: "Jämför dokument",
    text: "Identifiera skillnader och återkommande teman i Riksdagens öppna data.",
    example: "Jämför yttrandefriheten i RF med Europakonventionen.",
  },
];

const EXAMPLE_QUESTIONS = [
  "Vad säger regeringsformen om mötesfrihet?",
  "Vilka riksdagsdokument nämner proportionalitetsprincipen?",
  "Vilka dokument nämner Justitiekanslern?"
];

export function HeroSection() {
  const { query, setQuery, startSearch, isSearching } = useAppStore();
  const [activeMode, setActiveMode] = useState<
    "verify" | "summarize" | "compare"
  >("verify");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const BACKEND_MODE_MAP: Record<
    typeof activeMode,
    "auto" | "chat" | "assist" | "evidence"
  > = {
    verify: "evidence",
    summarize: "chat",
    compare: "auto",
  };

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

  const handleCardClick = (card: typeof GOLDEN_CARDS[number]) => {
    if (isSearching) return;
    const mode = card.id as "verify" | "summarize" | "compare";
    setActiveMode(mode);
    setQuery(card.example);
    if (textareaRef.current) {
      textareaRef.current.value = card.example;
    }
    const backendMode = BACKEND_MODE_MAP[mode];
    startSearch(backendMode, mode);
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
      className="flex flex-col items-center justify-start w-full max-w-2xl mx-auto pt-[min(10vh,4rem)] px-4 font-ui"
      animate={{
        opacity: isSearching ? 0.3 : 1,
        scale: isSearching ? 0.99 : 1,
      }}
      transition={{ duration: 0.15 }}
    >
      {/* 1. Brand header */}
      <div className="w-full relative z-20 group text-center mb-8">
        <h1 className="text-2xl font-light tracking-[0.2em] text-slate-100 uppercase">
          Svensk{" "}
          <span className="text-accent-primary font-semibold">RAG</span>
        </h1>
        <p className="text-xs text-slate-500 tracking-widest mt-2 uppercase font-mono">
          Demo över Riksdagens öppna data med spårbara källor
        </p>
      </div>

      {/* 2. Main Search Console */}
      <div className="w-full relative z-20 mb-8">
        {/* Mode Selector */}
        <div className="flex justify-center gap-1.5 mb-4">
          {(["verify", "summarize", "compare"] as const).map((mode) => {
            const labels: Record<typeof mode, string> = {
              verify: "Verifiera sanning",
              summarize: "Sammanfatta källor",
              compare: "Jämför dokument",
            };
            return (
              <button
                key={mode}
                onClick={() => setActiveMode(mode)}
                className={`px-3 py-1.5 text-[11px] uppercase tracking-wider font-medium rounded transition-all cursor-pointer border ${
                  activeMode === mode
                    ? "bg-slate-900 border-accent-primary/20 text-accent-primary"
                    : "bg-transparent border-transparent text-slate-500 hover:text-slate-300"
                }`}
              >
                {labels[mode]}
              </button>
            );
          })}
        </div>

        {/* Input Area */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="relative bg-slate-950/40 border border-white/5 backdrop-blur-xl rounded-lg p-2.5 flex items-center transition-all focus-within:border-accent-primary/30 focus-within:bg-slate-950/60 shadow-lg">
            <Search
              className="w-5 h-5 text-slate-500 ml-3 self-start mt-3.5"
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
              className="flex-1 bg-transparent border-none text-base text-slate-100 placeholder-slate-500 p-3 focus:ring-0 focus:outline-none tracking-wide resize-none overflow-hidden"
              style={{ minHeight: "44px" }}
            />
            <div className="mr-2 flex items-center gap-2 self-start mt-1.5">
              <button
                type="submit"
                disabled={isSearching}
                onMouseDown={handleSubmitButtonMouseDown}
                aria-label="Skicka sökning"
                className="w-9 h-9 flex items-center justify-center bg-accent-primary/10 hover:bg-accent-primary/25 rounded text-accent-primary border border-accent-primary/20 hover:border-accent-primary/30 cursor-pointer transition-all active:scale-95 disabled:opacity-50"
              >
                {isSearching ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ChevronRight className="w-4 h-4" strokeWidth={2} />
                )}
              </button>
            </div>
          </div>
        </form>

        {/* Example Questions */}
        {!query && (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {EXAMPLE_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleExampleClick(q)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#0f141c]/40 hover:bg-[#0f141c]/80 border border-white/5 hover:border-accent-primary/20 text-[11px] text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
              >
                <Sparkles className="w-3 h-3 text-accent-primary/70" />
                <span>{q}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 3. Simplified topic list (No system panel buttons) */}
      {!query && (
        <div className="w-full grid grid-cols-1 gap-3 mt-4">
          {GOLDEN_CARDS.map((card) => (
            <button
              key={card.id}
              onClick={() => handleCardClick(card)}
              className="group w-full text-left p-4 rounded bg-[#0f141c]/30 hover:bg-[#0f141c]/70 border border-white/5 hover:border-accent-primary/15 transition-all duration-200 cursor-pointer"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-200 group-hover:text-accent-primary transition-colors">
                  {card.title}
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-accent-primary transition-colors" />
              </div>
              <p className="text-[11px] text-slate-500 leading-normal font-light">
                {card.text}
              </p>
            </button>
          ))}
        </div>
      )}
    </motion.div>
  );
}
