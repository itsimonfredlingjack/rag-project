import { create } from 'zustand';

interface Source {
    id: string;
    title: string;
    type: 'pdf' | 'web' | 'text';
    date: string;
    snippet: string;
    relevance: number; // 0-1
}

interface AppState {
    query: string;
    isSearching: boolean;
    searchStage: 'idle' | 'searching' | 'reading' | 'reasoning' | 'complete';
    sources: Source[];
    activeSourceId: string | null;
    citationTarget: DOMRect | null;
    connectorCoords: { x: number; y: number } | null;

    setQuery: (q: string) => void;
    startSearch: () => void;
    setActiveSource: (id: string | null) => void;
    setSearchStage: (stage: AppState['searchStage']) => void;
    setCitationTarget: (rect: DOMRect | null) => void;
    setConnectorCoords: (coords: { x: number; y: number } | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
    query: '',
    isSearching: false,
    searchStage: 'idle',
    sources: [],
    activeSourceId: null,
    citationTarget: null,
    connectorCoords: null,

    setQuery: (query) => set({ query }),

    startSearch: () => {
        set({ isSearching: true, searchStage: 'searching', activeSourceId: null, citationTarget: null, connectorCoords: null });

        // Simulate RAG pipeline
        setTimeout(() => {
            set({
                sources: MOCK_SOURCES,
                searchStage: 'reading'
            });
        }, 1500);
    },

    setActiveSource: (id) => set({ activeSourceId: id }),
    setSearchStage: (stage) => set({ searchStage: stage }),
    setCitationTarget: (rect) => set({ citationTarget: rect }),
    setConnectorCoords: (coords) => set({ connectorCoords: coords }),
}));

const MOCK_SOURCES: Source[] = [
    { id: '1', title: 'Global Health Report 2024', type: 'pdf', date: '2024-01-15', snippet: 'Key findings indicate a 15% rise in...', relevance: 0.95 },
    { id: '2', title: 'WHO Policy Brief', type: 'web', date: '2023-11-20', snippet: 'The framework suggests implementing...', relevance: 0.88 },
    { id: '3', title: 'Academic Journal X', type: 'text', date: '2023-09-00', snippet: 'Methodology used in this study involved...', relevance: 0.82 },
    { id: '4', title: 'Dataset Z', type: 'text', date: '2024-02-01', snippet: 'Raw data compilation from region...', relevance: 0.75 },
];
