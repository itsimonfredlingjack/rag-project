import { create } from "zustand";
import {
  GRADING_WATCHDOG_MS,
  MIN_STAGE_DURATION_MS,
  METADATA_STAGE_DELAY_MS,
  MAX_PIPELINE_LOG_ENTRIES,
} from "../constants";
import type {
  QueryResult,
  QueryResultMode,
  QueryResultSource,
} from "../types/queryResult";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8900";
const API_ENDPOINT = `${BACKEND_URL}/api/constitutional/agent/query/stream`;

// Prevent overlapping streams when user iterates quickly.
let activeAbortController: AbortController | null = null;
const createSearchId = () => {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `search-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};
const scheduleMicrotask =
  typeof queueMicrotask === "function"
    ? queueMicrotask
    : (cb: () => void) => setTimeout(cb, 0);

// Token batching for performance - accumulate tokens and flush with RAF
let tokenBuffer: string[] = [];
let rafId: number | null = null;
let flushCallback: (() => void) | null = null;

const flushTokenBuffer = () => {
  rafId = null;
  if (tokenBuffer.length === 0 || !flushCallback) return;
  flushCallback();
  flushCallback = null;
};

const scheduleTokenFlush = (callback: () => void) => {
  flushCallback = callback;
  if (rafId === null) {
    rafId = requestAnimationFrame(flushTokenBuffer);
  }
};

// Matches backend Source response
export interface Source {
  id: string;
  title: string;
  snippet: string;
  score: number;
  doc_type: string;
  source: string;
}

// Pipeline stages matching backend flow + CRAG
export type PipelineStage =
  | "idle"
  | "query_classification"
  | "decontextualization"
  | "retrieval"
  | "grading"
  | "self_reflection"
  | "generation"
  | "guardrail_validation";

export type EvidenceLevel = "HIGH" | "MEDIUM" | "LOW" | null;

export interface PipelineLogEntry {
  ts: number;
  stage: PipelineStage;
  message: string;
}

export type BackendMode = "auto" | "chat" | "assist" | "evidence";

function createQueryResultId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `qr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function backendModeToUiMode(mode: BackendMode): QueryResultMode {
  if (mode === "evidence") return "verify";
  if (mode === "chat") return "summarize";
  return "compare";
}

function normalizeSources(data: unknown): QueryResultSource[] {
  if (!Array.isArray(data)) return [];
  return data.map((s: Record<string, unknown>) => ({
    id: String(s?.id ?? ""),
    title: String(s?.title ?? ""),
    snippet: String(s?.snippet ?? ""),
    score: Number(s?.score ?? 0),
    doc_type: String(s?.doc_type ?? ""),
    source: String(s?.source ?? ""),
  }));
}

export interface OpenDocumentTab {
  id: string;
  title: string;
  snippet?: string;
  source?: string;
  content?: string;
  sfs_nummer?: string;
  law_name?: string;
  kapitel_rubrik?: string;
  isLoaded: boolean;
  error?: string;
}

interface AppState {
  viewMode: "hero" | "results";
  query: string;
  activeMode: "verify" | "summarize" | "compare";
  queries: QueryResult[];
  activeQueryId: string | null;
  focusedQueryId: string | null;
  isSearching: boolean;
  currentSearchId: string | null;
  activeSourceId: string | null;
  hoveredSourceId: string | null;
  lockedSourceId: string | null;
  citationTarget: DOMRect | null;
  connectorCoords: { x: number; y: number } | null;

  // New Workspace state variables
  isSidebarOpen: boolean;
  selectedAgencies: string[];
  selectedDocTypes: string[];
  yearStart: number;
  yearEnd: number;
  availableFacets: {
    agencies: { id: string; name: string }[];
    doc_types: { id: string; name: string }[];
    years: { min: number; max: number };
  } | null;
  openDocuments: OpenDocumentTab[];
  activeDocumentTabId: string | null;
  isSearchInspectorOpen: boolean;

  setQuery: (q: string) => void;
  setActiveMode: (mode: "verify" | "summarize" | "compare") => void;
  startSearch: (mode?: BackendMode, uiMode?: QueryResultMode) => Promise<void>;
  retryQuery: (queryResultId: string) => void;
  setFocusedQuery: (id: string | null) => void;
  setHoveredSource: (id: string | null) => void;
  toggleLockedSource: (id: string) => void;
  setActiveSource: (id: string | null) => void;
  getEffectiveActiveSourceId: () => string | null;
  setSelectedPipelineStage: (stage: PipelineStage) => void;
  togglePipelineDrawer: (force?: boolean) => void;
  setCitationTarget: (rect: DOMRect | null) => void;
  setConnectorCoords: (coords: { x: number; y: number } | null) => void;
  updateQueryResult: (id: string, patch: Partial<QueryResult>) => void;
  resetToHome: () => void;

  // New Workspace actions
  toggleSidebar: () => void;
  toggleAgencyFilter: (agencyId: string) => void;
  toggleDocTypeFilter: (docTypeId: string) => void;
  setYearRange: (start: number, end: number) => void;
  clearFilters: () => void;
  fetchFacets: () => Promise<void>;
  openDocument: (docId: string, title: string, snippet?: string, source?: string) => Promise<void>;
  closeDocument: (docId: string) => void;
  setActiveDocumentTabId: (docId: string) => void;
  toggleSearchInspector: (force?: boolean) => void;
}

const MAX = MAX_PIPELINE_LOG_ENTRIES;

export const useAppStore = create<AppState>((set, get) => ({
  viewMode: "hero",
  query: "",
  activeMode: "verify",
  queries: [],
  activeQueryId: null,
  focusedQueryId: null,
  isSearching: false,
  currentSearchId: null,
  activeSourceId: null,
  hoveredSourceId: null,
  lockedSourceId: null,
  citationTarget: null,
  connectorCoords: null,

  // New Workspace defaults
  isSidebarOpen: true,
  selectedAgencies: [],
  selectedDocTypes: [],
  yearStart: 1900,
  yearEnd: 2026,
  availableFacets: null,
  openDocuments: [],
  activeDocumentTabId: null,
  isSearchInspectorOpen: false,

  setQuery: (query) => set({ query }),

  setActiveMode: (mode) => set({ activeMode: mode }),

  setFocusedQuery: (id) => set({ focusedQueryId: id }),

  updateQueryResult: (id, patch) =>
    set((state) => ({
      queries: state.queries.map((q) => (q.id === id ? { ...q, ...patch } : q)),
    })),

  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),

  toggleAgencyFilter: (agencyId) =>
    set((state) => {
      const agencies = state.selectedAgencies.includes(agencyId)
        ? state.selectedAgencies.filter((id) => id !== agencyId)
        : [...state.selectedAgencies, agencyId];
      return { selectedAgencies: agencies };
    }),

  toggleDocTypeFilter: (docTypeId) =>
    set((state) => {
      const docTypes = state.selectedDocTypes.includes(docTypeId)
        ? state.selectedDocTypes.filter((id) => id !== docTypeId)
        : [...state.selectedDocTypes, docTypeId];
      return { selectedDocTypes: docTypes };
    }),

  setYearRange: (start, end) => set({ yearStart: start, yearEnd: end }),

  clearFilters: () => set({ selectedAgencies: [], selectedDocTypes: [], yearStart: 1900, yearEnd: 2026 }),

  toggleSearchInspector: (force) =>
    set((state) => ({
      isSearchInspectorOpen: typeof force === "boolean" ? force : !state.isSearchInspectorOpen,
    })),

  fetchFacets: async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/documents/facets`);
      if (res.ok) {
        const facets = await res.json();
        set({ availableFacets: facets });
      } else {
        throw new Error("Failed to fetch facets");
      }
    } catch (e) {
      console.warn("Could not fetch facets from backend, using default static facets:", e);
      // Failover static facets matching system scraper types
      set({
        availableFacets: {
          agencies: [
            { id: "sfs", name: "Svensk författningssamling (SFS)" },
            { id: "socialstyrelsen", name: "Socialstyrelsen" },
            { id: "naturvardsverket", name: "Naturvårdsverket" },
            { id: "lakemedelsverket", name: "Läkemedelsverket" },
            { id: "upphandlingsmyndigheten", name: "Upphandlingsmyndigheten" },
            { id: "sgu", name: "Sveriges geologiska undersökning (SGU)" },
            { id: "arn", name: "Allmänna reklamationsnämnden (ARN)" },
            { id: "jk", name: "Justitiekanslern (JK)" },
            { id: "diva", name: "DiVA Forskningsdatabas" }
          ],
          doc_types: [
            { id: "lag", name: "Lag" },
            { id: "förordning", name: "Förordning" },
            { id: "föreskrift", name: "Föreskrift" },
            { id: "allmänna_råd", name: "Allmänna Råd" },
            { id: "beslut", name: "Beslut / Dom" },
            { id: "rapport", name: "Rapport / Utredning" },
            { id: "thesis", name: "Avhandling / Thesis" },
            { id: "article", name: "Forskningsartikel" }
          ],
          years: { min: 1900, max: 2026 }
        }
      });
    }
  },

  openDocument: async (docId, title, snippet, source) => {
    const { openDocuments } = get();
    const existing = openDocuments.find((d) => d.id === docId);

    if (existing) {
      set({ activeDocumentTabId: docId });
      return;
    }

    const newTab: OpenDocumentTab = {
      id: docId,
      title: title || "Dokument",
      snippet: snippet,
      source: source,
      isLoaded: false,
    };

    set((state) => ({
      openDocuments: [...state.openDocuments, newTab],
      activeDocumentTabId: docId,
    }));

    try {
      const isSFS = docId.startsWith("sfs_") || source === "sfs";
      const fetchUrl = isSFS 
        ? `${BACKEND_URL}/api/documents/parents/${docId}`
        : `${BACKEND_URL}/api/documents/${docId}`;

      const res = await fetch(fetchUrl);
      if (!res.ok) throw new Error(`Fetch failed: ${res.statusText}`);
      
      const docData = await res.json();
      
      set((state) => ({
        openDocuments: state.openDocuments.map((d) => {
          if (d.id === docId) {
            return {
              ...d,
              isLoaded: true,
              content: docData.content || docData.full_text || "",
              sfs_nummer: docData.sfs_nummer || "",
              law_name: docData.law_name || "",
              kapitel_rubrik: docData.kapitel_rubrik || "",
            };
          }
          return d;
        }),
      }));
    } catch (e) {
      console.error("Error opening document:", e);
      set((state) => ({
        openDocuments: state.openDocuments.map((d) => {
          if (d.id === docId) {
            return {
              ...d,
              isLoaded: true,
              content: snippet || "Innehållet kunde inte hämtas från databasen.",
              error: e instanceof Error ? e.message : "Det gick inte att ladda dokumentets fulltext.",
            };
          }
          return d;
        }),
      }));
    }
  },

  closeDocument: (docId) =>
    set((state) => {
      const filtered = state.openDocuments.filter((d) => d.id !== docId);
      let nextActive = state.activeDocumentTabId;
      if (state.activeDocumentTabId === docId) {
        nextActive = filtered.length > 0 ? filtered[filtered.length - 1].id : null;
      }
      return {
        openDocuments: filtered,
        activeDocumentTabId: nextActive,
      };
    }),

  setActiveDocumentTabId: (docId) => set({ activeDocumentTabId: docId }),

  startSearch: async (mode = "auto", uiMode) => {
    const { query } = get();
    if (!query.trim()) return;

    const backendMode = mode;
    const resolvedUiMode = uiMode ?? backendModeToUiMode(backendMode);

    const previousAbortController = activeAbortController;
    let currentAbortController: AbortController | null = null;
    try {
      currentAbortController = new AbortController();
    } catch (abortCreateError) {
      console.warn(
        "[startSearch] AbortController unavailable, continuing without signal",
        abortCreateError,
      );
    }
    activeAbortController = currentAbortController;

    if (previousAbortController) {
      scheduleMicrotask(() => {
        try {
          if (!previousAbortController.signal.aborted) {
            previousAbortController.abort();
          }
        } catch (abortError) {
          console.warn("[startSearch] Abort threw, continuing", abortError);
        }
      });
    }

    const searchId = createSearchId();
    const queryResultId = createQueryResultId();
    const now = Date.now();

    const newResult: QueryResult = {
      id: queryResultId,
      query: query.trim(),
      mode: resolvedUiMode,
      answer: "",
      sources: [],
      pipelineLog: [
        {
          ts: now,
          stage: "query_classification",
          message: "Klassificera: startar pipeline…",
        },
      ],
      searchStage: "searching",
      pipelineStage: "query_classification",
      selectedPipelineStage: "query_classification",
      isPipelineDrawerOpen: false,
      evidenceLevel: null,
      retrievalStrategy: null,
      thoughtChain: null,
      error: null,
      timestamp: now,
      lastStageChangeTimestamp: now,
      searchTimeMs: null,
      totalTimeMs: null,
    };

    set((state) => ({
      viewMode: "results",
      isSearching: true,
      currentSearchId: searchId,
      activeQueryId: queryResultId,
      focusedQueryId: queryResultId,
      activeSourceId: null,
      hoveredSourceId: null,
      lockedSourceId: null,
      citationTarget: null,
      connectorCoords: null,
      queries: [...state.queries, newResult],
    }));

    let generationLogged = false;
    let gradingWatchdog: ReturnType<typeof setTimeout> | null = null;

    const clearGradingWatchdog = () => {
      if (gradingWatchdog) {
        clearTimeout(gradingWatchdog);
        gradingWatchdog = null;
      }
    };

    const armGradingWatchdog = () => {
      clearGradingWatchdog();
      gradingWatchdog = setTimeout(() => {
        if (get().currentSearchId !== searchId) return;
        const active = get().queries.find((q) => q.id === queryResultId);
        if (active?.pipelineStage !== "grading") return;
        get().updateQueryResult(queryResultId, {
          pipelineStage: "generation",
          searchStage: "reasoning",
          pipelineLog: [
            ...(active.pipelineLog || []),
            {
              ts: Date.now(),
              stage: "grading",
              message: "Grading: timeout, proceeding to generation",
            },
          ].slice(-MAX),
        });
      }, GRADING_WATCHDOG_MS);
    };

    const updateStageWithDelay = (
      updateFn: () => void,
      minDurationMs: number = MIN_STAGE_DURATION_MS,
    ) => {
      if (get().currentSearchId !== searchId) return;
      const active = get().queries.find((q) => q.id === queryResultId);
      if (!active) return;
      const now = Date.now();
      const elapsed = now - active.lastStageChangeTimestamp;
      const remaining = Math.max(0, minDurationMs - elapsed);

      if (remaining > 0) {
        setTimeout(() => {
          if (get().currentSearchId !== searchId) return;
          updateFn();
          get().updateQueryResult(queryResultId, {
            lastStageChangeTimestamp: Date.now(),
          });
        }, remaining);
      } else {
        updateFn();
        get().updateQueryResult(queryResultId, {
          lastStageChangeTimestamp: Date.now(),
        });
      }
    };

    // Retry config: exponential backoff for network errors only
    const MAX_RETRIES = 3;
    const RETRY_DELAYS = [1000, 2000, 4000];
    let lastNetworkError: Error | null = null;

    // Filter payload construction
    const buildFilterPayload = () => {
      const agencies = get().selectedAgencies;
      const docTypes = get().selectedDocTypes;
      const start = get().yearStart;
      const end = get().yearEnd;
      
      const payload: Record<string, string[] | number> = {};
      if (agencies.length > 0) payload.agencies = agencies;
      if (docTypes.length > 0) payload.doc_types = docTypes;
      if (start !== 1900) payload.year_start = start;
      if (end !== 2026) payload.year_end = end;
      
      return Object.keys(payload).length > 0 ? payload : null;
    };

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      // Wait before retry (skip delay on first attempt)
      if (attempt > 0 && lastNetworkError) {
        const delay = RETRY_DELAYS[attempt - 1] ?? 4000;
        console.warn(
          `[startSearch] Retry ${attempt}/${MAX_RETRIES} after ${delay}ms`,
          lastNetworkError.message,
        );
        await new Promise((r) => setTimeout(r, delay));
        if (get().currentSearchId !== searchId) break;
        if (currentAbortController?.signal.aborted) break;
        lastNetworkError = null;
      }

      try {
        const response = await fetch(API_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          ...(currentAbortController
            ? { signal: currentAbortController.signal }
            : {}),
          body: JSON.stringify({
            question: query,
            mode: mode,
            history: [],
            filters: buildFilterPayload(),
          }),
        });

        // Server errors (4xx/5xx) are not retried
        if (!response.ok)
          throw new Error(`Backend request failed: ${response.status}`);
        if (!response.body) throw new Error("No response body");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (get().currentSearchId !== searchId) break;
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          buffer += chunk;
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";

          for (const eventBlock of events) {
            if (!eventBlock.trim()) continue;
            const dataMatch = eventBlock.match(/^data:\s*(.+)$/m);
            if (!dataMatch) continue;

            try {
              const data = JSON.parse(dataMatch[1]);

              switch (data.type) {
                case "decontextualized": {
                  get().updateQueryResult(queryResultId, {
                    rewrittenQuery: data.rewritten,
                  });
                  break;
                }

                case "phase": {
                  if (data.phase === "retrieval_complete") {
                    get().updateQueryResult(queryResultId, {
                      retrievalLatencyMs: data.latency_ms,
                    });
                  }
                  break;
                }

                case "grading": {
                  get().updateQueryResult(queryResultId, {
                    gradingMetrics: {
                      total: data.total,
                      relevant: data.relevant,
                      ambiguous: data.ambiguous,
                    },
                  });
                  break;
                }

                case "thought_chain": {
                  get().updateQueryResult(queryResultId, {
                    thoughtChain: data.content,
                  });
                  break;
                }

                case "metadata": {
                  if (data.sources)
                    get().updateQueryResult(queryResultId, {
                      sources: normalizeSources(data.sources),
                    });
                  if (data.evidence_level)
                    get().updateQueryResult(queryResultId, {
                      evidenceLevel: data.evidence_level,
                    });
                  if (data.search_time_ms != null)
                    get().updateQueryResult(queryResultId, {
                      searchTimeMs: data.search_time_ms,
                    });
                  updateStageWithDelay(() => {
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (!active) return;
                    get().updateQueryResult(queryResultId, {
                      pipelineLog: [
                        ...active.pipelineLog,
                        {
                          ts: Date.now(),
                          stage: "retrieval",
                          message: `Retrieval: fetched ${data.sources?.length ?? 0} sources`,
                        },
                      ].slice(-MAX),
                      pipelineStage: "grading",
                      searchStage: "reading",
                    });
                    armGradingWatchdog();
                  }, METADATA_STAGE_DELAY_MS);
                  break;
                }

                case "token": {
                  if (!generationLogged) {
                    generationLogged = true;
                    updateStageWithDelay(() => {
                      const active = get().queries.find(
                        (q) => q.id === queryResultId,
                      );
                      if (!active) return;
                      get().updateQueryResult(queryResultId, {
                        pipelineLog: [
                          ...active.pipelineLog,
                          {
                            ts: Date.now(),
                            stage: "generation",
                            message: "Generation: streaming svar...",
                          },
                        ].slice(-MAX),
                        pipelineStage: "generation",
                        searchStage: "reasoning",
                      });
                    });
                  }
                  const token = data.content || "";
                  tokenBuffer.push(token);
                  scheduleTokenFlush(() => {
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (active) {
                      const added = tokenBuffer.join("");
                      tokenBuffer = [];
                      get().updateQueryResult(queryResultId, {
                        answer: active.answer + added,
                      });
                    }
                  });
                  break;
                }

                case "corrections": {
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (active)
                    get().updateQueryResult(queryResultId, {
                      pipelineLog: [
                        ...active.pipelineLog,
                        {
                          ts: Date.now(),
                          stage: "guardrail_validation",
                          message: `Validate: ${data.corrections?.length || 0} corrections applied`,
                        },
                      ].slice(-MAX),
                    });
                  if (data.corrected_text) {
                    const corrCur = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (corrCur)
                      get().updateQueryResult(queryResultId, {
                        answer: data.corrected_text,
                      });
                  }
                  break;
                }

                case "done":
                  clearGradingWatchdog();
                  if (tokenBuffer.length > 0) {
                    const remaining = tokenBuffer.join("");
                    tokenBuffer = [];
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (active)
                      get().updateQueryResult(queryResultId, {
                        answer: active.answer + remaining,
                      });
                  }
                  if (rafId !== null) {
                    cancelAnimationFrame(rafId);
                    rafId = null;
                  }
                  flushCallback = null;
                  {
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (active)
                      get().updateQueryResult(queryResultId, {
                        searchStage: "complete",
                        pipelineStage: "idle",
                        totalTimeMs: data.total_time_ms ?? null,
                        pipelineLog: [
                          ...active.pipelineLog,
                          {
                            ts: Date.now(),
                            stage: "guardrail_validation",
                            message: `Complete: ${data.total_time_ms ? `${data.total_time_ms.toFixed(0)}ms` : "done"}`,
                          },
                        ].slice(-MAX),
                      });
                  }
                  set({ isSearching: false, currentSearchId: null });
                  break;

                case "error":
                  clearGradingWatchdog();
                  tokenBuffer = [];
                  if (rafId !== null) {
                    cancelAnimationFrame(rafId);
                    rafId = null;
                  }
                  flushCallback = null;
                  {
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (active)
                      get().updateQueryResult(queryResultId, {
                        error: data.message || "Unknown error",
                        searchStage: "error",
                        pipelineStage: "idle",
                        pipelineLog: [
                          ...active.pipelineLog,
                          {
                            ts: Date.now(),
                            stage: "idle",
                            message: `Error: ${data.message}`,
                          },
                        ].slice(-MAX),
                      });
                  }
                  set({ isSearching: false, currentSearchId: null });
                  break;
              }
            } catch (e) {
              console.error("Error parsing SSE data:", e);
            }
          }
        }

        const currentState = get();
        if (
          currentState.isSearching &&
          currentState.currentSearchId === searchId
        ) {
          clearGradingWatchdog();
          const active = get().queries.find((q) => q.id === queryResultId);
          if (active)
            get().updateQueryResult(queryResultId, {
              searchStage: "complete",
              pipelineStage: "idle",
            });
          set({ isSearching: false, currentSearchId: null });
        }
        break; // Success – exit retry loop
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (get().currentSearchId !== searchId) return;

        // Retry on network errors (TypeError from fetch), not server errors
        const isNetworkError =
          error instanceof TypeError && !currentAbortController?.signal.aborted;
        if (isNetworkError && attempt < MAX_RETRIES) {
          lastNetworkError = error;
          continue;
        }

        clearGradingWatchdog();
        const active = get().queries.find((q) => q.id === queryResultId);
        if (active)
          get().updateQueryResult(queryResultId, {
            searchStage: "error",
            pipelineStage: "idle",
            error: error instanceof Error ? error.message : "Search failed",
          });
        set({ isSearching: false, currentSearchId: null });
        break; // Non-retryable error – exit retry loop
      } finally {
        clearGradingWatchdog();
        if (
          activeAbortController === currentAbortController &&
          currentAbortController?.signal.aborted
        ) {
          activeAbortController = null;
        }
      }
    } // end retry loop
  },

  retryQuery: (queryResultId) => {
    const queryResult = get().queries.find((q) => q.id === queryResultId);
    if (!queryResult) return;
    set((state) => ({
      queries: state.queries.filter((q) => q.id !== queryResultId),
      query: queryResult.query,
    }));
    const modeMap: Record<QueryResultMode, BackendMode> = {
      verify: "evidence",
      summarize: "chat",
      compare: "auto",
    };
    get().startSearch(modeMap[queryResult.mode], queryResult.mode);
  },

  setHoveredSource: (id) =>
    set((state) => ({
      hoveredSourceId: id,
      activeSourceId: state.lockedSourceId ? state.lockedSourceId : id,
    })),
  toggleLockedSource: (id) =>
    set((state) => {
      const isUnlock = state.lockedSourceId === id;
      const nextLocked = isUnlock ? null : id;
      return {
        lockedSourceId: nextLocked,
        activeSourceId: nextLocked ?? state.hoveredSourceId,
      };
    }),
  setActiveSource: (id) => get().setHoveredSource(id),
  getEffectiveActiveSourceId: () => {
    const s = get();
    return s.lockedSourceId ?? s.hoveredSourceId;
  },
  setSelectedPipelineStage: (stage) => {
    const aid = get().activeQueryId;
    if (aid) get().updateQueryResult(aid, { selectedPipelineStage: stage });
  },
  togglePipelineDrawer: (force) => {
    const aid = get().activeQueryId;
    if (!aid) return;
    const active = get().queries.find((q) => q.id === aid);
    if (active)
      get().updateQueryResult(aid, {
        isPipelineDrawerOpen:
          typeof force === "boolean" ? force : !active.isPipelineDrawerOpen,
      });
  },
  setCitationTarget: (rect) => set({ citationTarget: rect }),
  setConnectorCoords: (coords) => set({ connectorCoords: coords }),

  resetToHome: () => {
    if (activeAbortController) {
      try {
        activeAbortController.abort();
      } catch {
        // ignore
      }
      activeAbortController = null;
    }
    tokenBuffer = [];
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    flushCallback = null;
    set({
      viewMode: "hero",
      query: "",
      queries: [],
      activeQueryId: null,
      focusedQueryId: null,
      isSearching: false,
      currentSearchId: null,
      activeSourceId: null,
      hoveredSourceId: null,
      lockedSourceId: null,
      citationTarget: null,
      connectorCoords: null,
      openDocuments: [],
      activeDocumentTabId: null,
      isSearchInspectorOpen: false,
    });
  },
}));
