import { create } from 'zustand';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const API_ENDPOINT = `${BACKEND_URL}/api/constitutional/agent/query/stream`;

// Prevent overlapping streams when user iterates quickly.
let activeAbortController: AbortController | null = null;

// Matches backend Source response
export interface Source {
    id: string;
    title: string;
    snippet: string;
    score: number;         // Backend uses "score", not "relevance"
    doc_type: string;      // "prop", "mot", "sou", "bet", "sfs"
    source: string;        // "riksdagen", etc.
}

// Pipeline stages matching backend flow + CRAG
export type PipelineStage =
    | 'idle'
    | 'query_classification'
    | 'decontextualization'
    | 'retrieval'
    | 'grading'            // NY: CRAG Grading
    | 'self_reflection'    // NY: CRAG Reflection
    | 'generation'
    | 'guardrail_validation';

export type EvidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | null;

export interface PipelineLogEntry {
    ts: number;
    stage: PipelineStage;
    message: string;
}

interface AppState {
    query: string;
    submittedQuery: string;
    queryHistory: string[];
    isSearching: boolean;
    searchStage: 'idle' | 'searching' | 'reading' | 'reasoning' | 'complete' | 'error';
    pipelineStage: PipelineStage;
    selectedPipelineStage: PipelineStage;
    isPipelineDrawerOpen: boolean;
    pipelineLog: PipelineLogEntry[];
    evidenceLevel: EvidenceLevel;
    retrievalStrategy: string | null;
    sources: Source[];
    activeSourceId: string | null;
    hoveredSourceId: string | null;
    lockedSourceId: string | null;
    citationTarget: DOMRect | null;
    connectorCoords: { x: number; y: number } | null;
    answer: string;
    thoughtChain: string | null; // NY: För att visa tankekedjan
    error: string | null;
    currentSearchId: string | null;
    lastStageChangeTimestamp: number;

    setQuery: (q: string) => void;
    startSearch: (mode?: 'auto' | 'chat' | 'assist' | 'evidence') => Promise<void>;
    addQueryToHistory: (q: string) => void;
    setHoveredSource: (id: string | null) => void;
    toggleLockedSource: (id: string) => void;
    setActiveSource: (id: string | null) => void;
    getEffectiveActiveSourceId: () => string | null;
    setSelectedPipelineStage: (stage: PipelineStage) => void;
    togglePipelineDrawer: (force?: boolean) => void;
    setSearchStage: (stage: AppState['searchStage']) => void;
    setCitationTarget: (rect: DOMRect | null) => void;
    setConnectorCoords: (coords: { x: number; y: number } | null) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
    query: '',
    submittedQuery: '',
    queryHistory: [],
    isSearching: false,
    searchStage: 'idle',
    pipelineStage: 'idle',
    selectedPipelineStage: 'query_classification',
    isPipelineDrawerOpen: false,
    pipelineLog: [],
    evidenceLevel: null,
    retrievalStrategy: null,
    sources: [],
    activeSourceId: null,
    hoveredSourceId: null,
    lockedSourceId: null,
    citationTarget: null,
    connectorCoords: null,
    answer: '',
    thoughtChain: null,
    error: null,
    currentSearchId: null,
    lastStageChangeTimestamp: 0,

    setQuery: (query) => set({ query }),

    addQueryToHistory: (q) =>
        set((state) => {
            const trimmed = q.trim();
            if (!trimmed) return state;
            const next = [trimmed, ...state.queryHistory.filter((x) => x !== trimmed)].slice(0, 12);
            return { queryHistory: next };
        }),

    startSearch: async (mode = 'auto') => {
        const { query } = get();
        if (!query.trim()) return;

        if (activeAbortController) {
            activeAbortController.abort();
        }
        activeAbortController = new AbortController();
        const searchId = crypto.randomUUID();

        let generationLogged = false;

        get().addQueryToHistory(query);

        set({
            isSearching: true,
            searchStage: 'searching',
            pipelineStage: 'query_classification',
            submittedQuery: query,
            selectedPipelineStage: 'query_classification',
            isPipelineDrawerOpen: false,
            pipelineLog: [
                {
                    ts: Date.now(),
                    stage: 'query_classification',
                    message: 'Classify: starting pipeline…',
                },
            ],
            activeSourceId: null,
            hoveredSourceId: null,
            lockedSourceId: null,
            citationTarget: null,
            connectorCoords: null,
            sources: [],
            answer: '',
            thoughtChain: null,
            error: null,
            evidenceLevel: null,
            currentSearchId: searchId,
            lastStageChangeTimestamp: Date.now(),
        });

        // Helper to enforce minimum visual duration for stages
        const updateStageWithDelay = (
            updateFn: () => void,
            minDurationMs: number = 500
        ) => {
            const { lastStageChangeTimestamp, currentSearchId } = get();
            if (currentSearchId !== searchId) return;

            const now = Date.now();
            const elapsed = now - lastStageChangeTimestamp;
            const remaining = Math.max(0, minDurationMs - elapsed);

            if (remaining > 0) {
                setTimeout(() => {
                    if (get().currentSearchId !== searchId) return;
                    updateFn();
                    set({ lastStageChangeTimestamp: Date.now() });
                }, remaining);
            } else {
                updateFn();
                set({ lastStageChangeTimestamp: Date.now() });
            }
        };

        try {
            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: activeAbortController.signal,
                body: JSON.stringify({
                    question: query,
                    mode: mode,
                    history: []
                }),
            });

            if (!response.ok) throw new Error(`Backend request failed: ${response.status}`);
            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (get().currentSearchId !== searchId) break;
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;
                const events = buffer.split('\n\n');
                buffer = events.pop() || '';

                for (const eventBlock of events) {
                    if (!eventBlock.trim()) continue;
                    const dataMatch = eventBlock.match(/^data:\s*(.+)$/m);
                    if (!dataMatch) continue;

                    try {
                        const data = JSON.parse(dataMatch[1]);

                        switch (data.type) {
                            case 'metadata':
                                if (data.sources) set({ sources: data.sources });
                                if (data.evidence_level) set({ evidenceLevel: data.evidence_level });

                                updateStageWithDelay(() => {
                                    set((state) => ({
                                        pipelineLog: [...state.pipelineLog, {
                                            ts: Date.now(),
                                            stage: 'retrieval',
                                            message: `Retrieval: fetched ${data.sources?.length ?? 0} sources`,
                                        }].slice(-50),
                                        // Gå till 'grading' istället för 'generation' direkt
                                        pipelineStage: 'grading',
                                        searchStage: 'reading',
                                    }));
                                }, 600);
                                break;

                            case 'grading':
                                // NYTT: Visar att vi bedömer dokument
                                updateStageWithDelay(() => {
                                    set((state) => ({
                                        pipelineLog: [...state.pipelineLog, {
                                            ts: Date.now(),
                                            stage: 'grading',
                                            message: `Grading: ${data.relevant_count}/${data.total_count} documents relevant`,
                                        }].slice(-50),
                                        pipelineStage: 'self_reflection',
                                    }));
                                }, 400);
                                break;

                            case 'thought_chain':
                                // NYTT: Tar emot tankekedjan
                                set({ thoughtChain: data.content });
                                updateStageWithDelay(() => {
                                    set((state) => ({
                                        pipelineLog: [...state.pipelineLog, {
                                            ts: Date.now(),
                                            stage: 'self_reflection',
                                            message: 'Reflection: analyzing evidence sufficiency...',
                                        }].slice(-50),
                                        pipelineStage: 'generation',
                                        searchStage: 'reasoning'
                                    }));
                                }, 400);
                                break;

                            case 'token':
                                if (data.content) {
                                    if (!generationLogged) {
                                        generationLogged = true;
                                        set((state) => ({
                                            pipelineLog: [...state.pipelineLog, {
                                                ts: Date.now(),
                                                stage: 'generation',
                                                message: 'Generate: composing answer…'
                                            }].slice(-50),
                                        }));
                                    }
                                    set((state) => ({
                                        answer: state.answer + data.content,
                                        pipelineStage: 'generation',
                                        searchStage: 'reasoning',
                                    }));
                                }
                                break;

                            case 'corrections':
                                set((state) => ({
                                    pipelineStage: 'guardrail_validation',
                                    pipelineLog: [...state.pipelineLog, {
                                        ts: Date.now(),
                                        stage: 'guardrail_validation',
                                        message: `Validate: ${data.corrections?.length || 0} corrections applied`,
                                    }].slice(-50),
                                }));
                                if (data.corrected_text) set({ answer: data.corrected_text });
                                break;

                            case 'done':
                                set((state) => ({
                                    searchStage: 'complete',
                                    pipelineStage: 'idle',
                                    isSearching: false,
                                    pipelineLog: [...state.pipelineLog, {
                                        ts: Date.now(),
                                        stage: 'guardrail_validation',
                                        message: `Complete: ${data.total_time_ms ? `${data.total_time_ms.toFixed(0)}ms` : 'done'}`,
                                    }].slice(-50),
                                }));
                                break;

                            case 'error':
                                set((state) => ({
                                    error: data.message || 'Unknown error',
                                    searchStage: 'error',
                                    pipelineStage: 'idle',
                                    isSearching: false,
                                    pipelineLog: [...state.pipelineLog, {
                                        ts: Date.now(),
                                        stage: 'idle',
                                        message: `Error: ${data.message}`,
                                    }].slice(-50),
                                }));
                                break;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE data:', e);
                    }
                }
            }

            // Cleanup check
            const currentState = get();
            if (currentState.isSearching && currentState.currentSearchId === searchId) {
                set({ isSearching: false, searchStage: 'complete' });
            }

        } catch (error) {
            if (error instanceof DOMException && error.name === 'AbortError') return;
            if (get().currentSearchId !== searchId) return;
            set({
                isSearching: false,
                searchStage: 'error',
                pipelineStage: 'idle',
                error: error instanceof Error ? error.message : 'Search failed'
            });
        } finally {
            if (activeAbortController?.signal.aborted) activeAbortController = null;
        }
    },

    setHoveredSource: (id) => set((state) => ({ hoveredSourceId: id, activeSourceId: state.lockedSourceId ? state.lockedSourceId : id })),
    toggleLockedSource: (id) => set((state) => {
        const isUnlock = state.lockedSourceId === id;
        const nextLocked = isUnlock ? null : id;
        return { lockedSourceId: nextLocked, activeSourceId: nextLocked ?? state.hoveredSourceId };
    }),
    setActiveSource: (id) => get().setHoveredSource(id),
    getEffectiveActiveSourceId: () => { const s = get(); return s.lockedSourceId ?? s.hoveredSourceId; },
    setSelectedPipelineStage: (stage) => set({ selectedPipelineStage: stage }),
    togglePipelineDrawer: (force) => set((state) => ({ isPipelineDrawerOpen: typeof force === 'boolean' ? force : !state.isPipelineDrawerOpen })),
    setSearchStage: (stage) => set({ searchStage: stage }),
    setCitationTarget: (rect) => set({ citationTarget: rect }),
    setConnectorCoords: (coords) => set({ connectorCoords: coords }),
}));
