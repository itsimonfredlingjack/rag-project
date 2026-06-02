/**
 * One question + full RAG result. Used in the chat-like flow (queries array).
 */
export interface QueryResultSource {
  id: string;
  document_id?: string;
  title: string;
  snippet: string;
  score: number;
  doc_type: string;
  source: string;
  source_scope?: string;
  date?: string;
  url?: string;
  retriever?: string;
  retriever_source?: string;
}

export interface QueryResultCitation {
  claim: string;
  source_id: string;
  source_title: string;
  source_collection: string;
  tier: string;
}

export interface QueryResultRetrievalMetadata {
  mode?: string;
  chunks_used?: number;
  deduplicated_documents?: number;
  raw_results?: number;
  max_chunks?: number;
  max_context_tokens?: number;
  max_chunk_tokens?: number;
  max_answer_tokens?: number;
  [key: string]: unknown;
}

export interface QueryResultPipelineLogEntry {
  ts: number;
  stage: string;
  message: string;
}

export type QueryResultMode = "verify" | "summarize" | "compare";

export interface QueryResult {
  id: string;
  query: string;
  mode: QueryResultMode;
  answer: string;
  sources: QueryResultSource[];
  pipelineLog: QueryResultPipelineLogEntry[];
  searchStage: string;
  pipelineStage: string;
  selectedPipelineStage: string | null;
  isPipelineDrawerOpen: boolean;
  evidenceLevel: string | null;
  retrievalStrategy: string | null;
  thoughtChain: unknown | null;
  error: string | null;
  timestamp: number;
  lastStageChangeTimestamp: number;
  searchTimeMs: number | null;
  totalTimeMs: number | null;
  latencyMs?: number | null;
  dataSourceAttribution?: string | null;
  refusalReason?: string | null;
  citations?: QueryResultCitation[];
  retrieval?: QueryResultRetrievalMetadata | null;
  rewrittenQuery?: string;
  retrievalLatencyMs?: number;
  gradingMetrics?: {
    total: number;
    relevant: number;
    ambiguous: number;
  };
}
