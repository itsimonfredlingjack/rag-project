import { motion, AnimatePresence } from 'framer-motion';
import { Search, Shield, Zap } from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';

export function TrustHull() {
    const { query, setQuery, startSearch, searchStage, sources, activeSourceId, setActiveSource } = useAppStore();
    const activeSource = sources.find(s => s.id === activeSourceId);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (query.trim()) startSearch();
    };

    return (
        <div className="w-full h-full flex flex-col p-6 pointer-events-none">
            {/* ===== HEADER ===== */}
            <header className="flex items-center justify-between text-white/60 mb-6 pointer-events-auto">
                <div className="flex items-center gap-3">
                    <Shield className="w-5 h-5 text-cyan-400" />
                    <span className="text-sm font-medium tracking-wider">CONSTITUTIONAL AI</span>
                    <span className="text-xs text-cyan-400 font-mono">V3.0</span>
                </div>
                <div className="flex items-center gap-6 text-xs font-mono">
                    <span>MEM: 24GB</span>
                    <span>LATENCY: 12ms</span>
                </div>
            </header>

            {/* ===== MAIN CONTENT ===== */}
            <main className="flex-1 flex gap-6 overflow-hidden">

                {/* LEFT PANEL: Search + Synthesis */}
                <div className="flex-1 flex flex-col max-w-3xl pointer-events-auto">
                    {/* Search Input */}
                    <form onSubmit={handleSubmit} className="mb-6">
                        <div className="relative group">
                            <input
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Enter query to verify..."
                                className="w-full bg-black/60 border border-white/10 p-4 pl-12 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400/50 transition-all backdrop-blur-sm"
                            />
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 group-focus-within:text-cyan-400 transition-colors" />
                        </div>
                    </form>

                    {/* Synthesis Panel */}
                    <AnimatePresence>
                        {searchStage !== 'idle' && (
                            <motion.div
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -20 }}
                                className="flex-1 bg-black/70 border border-white/10 rounded-lg p-6 backdrop-blur-md overflow-auto"
                            >
                                {searchStage === 'searching' && (
                                    <div className="flex items-center gap-3 text-cyan-400 font-mono text-sm">
                                        <Zap className="w-4 h-4 animate-pulse" />
                                        <span>Retrieving Sources...</span>
                                    </div>
                                )}

                                {searchStage === 'reading' && (
                                    <div className="text-white/90">
                                        <h3 className="text-lg font-medium text-cyan-400 mb-4 tracking-wide">Synthesis</h3>
                                        <p className="mb-4 leading-relaxed">
                                            Based on the analysis of <span className="text-cyan-400 font-mono font-bold">{sources.length} sources</span>, the data indicates a significant shift in regional health outcomes. Specifically, rapid intervention protocols have reduced mortality by 15%
                                            <button
                                                onMouseEnter={(e) => {
                                                    console.log('Hover [1]');
                                                    setActiveSource('1');
                                                    const rect = e.currentTarget.getBoundingClientRect();
                                                    console.log('Target Rect:', rect);
                                                    useAppStore.getState().setCitationTarget(rect);
                                                }}
                                                onMouseLeave={() => {
                                                    console.log('Leave [1]');
                                                    setActiveSource(null);
                                                    useAppStore.getState().setCitationTarget(null);
                                                }}
                                                className="ml-1 inline-flex items-center justify-center text-xs bg-cyan-400/10 text-cyan-400 px-2 py-0.5 rounded border border-cyan-400/30 hover:bg-cyan-400/20 transition-all cursor-pointer"
                                            >
                                                [1]
                                            </button>.
                                        </p>
                                        <p className="leading-relaxed">
                                            However, discrepancies remain regarding the long-term sustainability of these measures as highlighted in recent policy briefs
                                            <button
                                                onMouseEnter={(e) => {
                                                    setActiveSource('2');
                                                    useAppStore.getState().setCitationTarget(e.currentTarget.getBoundingClientRect());
                                                }}
                                                onMouseLeave={() => {
                                                    setActiveSource(null);
                                                    useAppStore.getState().setCitationTarget(null);
                                                }}
                                                className="ml-1 inline-flex items-center justify-center text-xs bg-cyan-400/10 text-cyan-400 px-2 py-0.5 rounded border border-cyan-400/30 hover:bg-cyan-400/20 transition-all cursor-pointer"
                                            >
                                                [2]
                                            </button>.
                                        </p>
                                    </div>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* RIGHT PANEL: Source Cards (DOM) */}
                <AnimatePresence>
                    {sources.length > 0 && (
                        <motion.aside
                            initial={{ opacity: 0, x: 50 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 50 }}
                            className="w-80 flex flex-col gap-3 overflow-y-auto pointer-events-auto"
                        >
                            <h4 className="text-xs font-mono text-white/50 uppercase tracking-wider mb-2">Sources</h4>
                            {sources.map((source) => (
                                <motion.div
                                    key={source.id}
                                    data-source-id={source.id}
                                    onMouseEnter={() => setActiveSource(source.id)}
                                    onMouseLeave={() => setActiveSource(null)}
                                    className={`
                    p-4 rounded-lg border transition-all cursor-pointer
                    ${activeSourceId === source.id
                                            ? 'bg-cyan-400/10 border-cyan-400/50 shadow-lg shadow-cyan-400/10'
                                            : 'bg-black/50 border-white/10 hover:border-white/20'
                                        }
                  `}
                                >
                                    <div className="flex items-start justify-between mb-2">
                                        <h5 className="text-sm font-medium text-white/90 leading-tight">{source.title}</h5>
                                        <span className="text-xs font-mono text-cyan-400 uppercase">{source.type}</span>
                                    </div>
                                    <p className="text-xs text-white/50 mb-2">{source.date}</p>
                                    <p className="text-xs text-white/60 line-clamp-2">{source.snippet}</p>
                                </motion.div>
                            ))}
                        </motion.aside>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
