"""
Constitutional AI Dashboard API Routes
Provides access to ChromaDB document collections and statistics
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, AsyncGenerator
import chromadb
from chromadb.api.types import EmbeddingFunction, Embeddings, Documents
from sentence_transformers import SentenceTransformer
import os
import httpx
import tempfile
import base64
import re
import sys
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path

# Phase 1 & 2: Parallel retrieval orchestrator + Query rewriting
# NOTE: These components are not yet implemented. The /search-parallel endpoint
# will return an error if used. To implement, create:
# - app/services/retrieval_orchestrator.py
# - app/services/query_rewriter.py
# See docs/MODEL_OPTIMIZATION.md for details.
try:
    from app.services.retrieval_orchestrator import (
        RetrievalOrchestrator,
        RetrievalStrategy,
        RetrievalResult,
        RetrievalMetrics,
    )
    from app.services.query_rewriter import QueryRewriter
    RETRIEVAL_COMPONENTS_AVAILABLE = True
except ImportError:
    RETRIEVAL_COMPONENTS_AVAILABLE = False
    # Stub classes to prevent import errors
    class RetrievalStrategy:
        PARALLEL_V1 = "parallel_v1"
        REWRITE_V1 = "rewrite_v1"
        RAG_FUSION = "rag_fusion"
        ADAPTIVE = "adaptive"
    class RetrievalOrchestrator:
        pass
    class QueryRewriter:
        pass
    class RetrievalResult:
        pass
    class RetrievalMetrics:
        pass

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING SETUP - Unbuffered for systemd
# ═══════════════════════════════════════════════════════════════════════════
logger = logging.getLogger("constitutional")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[Constitutional] %(message)s'))
    logger.addHandler(handler)

router = APIRouter(prefix="/api/constitutional", tags=["constitutional"])

# ChromaDB path configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
PDF_CACHE_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache"

# ═══════════════════════════════════════════════════════════════════════════
# EMBEDDING MODEL - KBLab Swedish BERT (768-dim)
# Collections were indexed with this model - MUST use same for queries
# ═══════════════════════════════════════════════════════════════════════════
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"
EXPECTED_EMBEDDING_DIM = 768

# Global model cache
_sentence_transformer_model = None


class KBLabEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Custom embedding function using KBLab Swedish BERT.
    Verifies 768-dim output to ensure consistency with indexed embeddings.
    """
    
    def __init__(self):
        global _sentence_transformer_model
        if _sentence_transformer_model is None:
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            _sentence_transformer_model = SentenceTransformer(EMBEDDING_MODEL)
            
            # Verify dimension at load time
            test_emb = _sentence_transformer_model.encode("test")
            actual_dim = len(test_emb)
            if actual_dim != EXPECTED_EMBEDDING_DIM:
                raise RuntimeError(
                    f"FATAL: Embedding dimension mismatch! "
                    f"Expected {EXPECTED_EMBEDDING_DIM}, got {actual_dim}"
                )
            logger.info(f"Embedding model loaded: {actual_dim}-dim ✓")
        
        self.model = _sentence_transformer_model
    
    def __call__(self, input: Documents) -> Embeddings:
        """Generate embeddings for input documents."""
        embeddings = self.model.encode(list(input))
        return [emb.tolist() for emb in embeddings]


# Lazy-loaded embedding function
_embedding_function = None


def get_embedding_function() -> KBLabEmbeddingFunction:
    """Get or initialize the Swedish BERT embedding function (768-dim)"""
    global _embedding_function
    if _embedding_function is None:
        _embedding_function = KBLabEmbeddingFunction()
    return _embedding_function


# ═══════════════════════════════════════════════════════════════════════════
# KEYWORD EXTRACTION FOR TEXT SEARCH FALLBACK
# ═══════════════════════════════════════════════════════════════════════════

# Swedish stopwords to filter out
SWEDISH_STOPWORDS = {
    'och', 'i', 'att', 'en', 'ett', 'det', 'som', 'av', 'för', 'med', 'till',
    'på', 'är', 'om', 'har', 'de', 'den', 'vara', 'vad', 'var', 'hur', 'när',
    'kan', 'ska', 'inte', 'eller', 'men', 'så', 'från', 'vid', 'även', 'efter',
    'nu', 'där', 'mot', 'ut', 'upp', 'få', 'ta', 'ge', 'göra', 'finns', 'alla',
    'än', 'dessa', 'detta', 'vilka', 'vilket', 'sin', 'sina', 'sig', 'oss',
    'vi', 'ni', 'dom', 'dem', 'deras', 'vår', 'vårt', 'våra', 'han', 'hon',
    'henne', 'hans', 'hennes', 'ja', 'nej', 'bara', 'mycket', 'mer', 'mest',
    'enligt', 'säger', 'gäller', 'berätta', 'förklara', 'beskriv'
}


def extract_search_keywords(query: str) -> list[str]:
    """
    Extract meaningful keywords from a question for text search.
    Removes stopwords and question phrases, returns terms sorted by length (longest first).
    
    Swedish compound words are typically longer and more informative,
    so we prioritize them for $contains text search.
    """
    # Remove common question phrases first
    clean_query = query.lower()
    question_phrases = [
        r'^vad är\s+', r'^vad säger\s+', r'^vad innebär\s+',
        r'^hur fungerar\s+', r'^hur funkar\s+',
        r'^berätta om\s+', r'^förklara\s+', r'^beskriv\s+',
        r'^vilka\s+', r'^vilket\s+', r'^vilken\s+',
    ]
    for phrase in question_phrases:
        clean_query = re.sub(phrase, '', clean_query)
    
    # Remove punctuation
    clean_query = re.sub(r'[?!.,;:"\']', '', clean_query)
    
    # Split into words
    words = clean_query.split()
    
    # Filter out stopwords and short words
    keywords = [w for w in words if w not in SWEDISH_STOPWORDS and len(w) >= 3]
    
    # Remove duplicates while preserving first occurrence
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    # Sort by length (longest first) - Swedish compound words are most informative
    unique_keywords.sort(key=len, reverse=True)
    
    return unique_keywords


# ═══════════════════════════════════════════════════════════════════════════
# SNIPPET CLEANING - Bättre signal/brus-ratio
# ═══════════════════════════════════════════════════════════════════════════

def clean_snippet(text: str) -> str:
    """
    Rensa snippet från återkommande brus för bättre retrieval.
    
    Tar bort:
    - HTML entities (&nbsp;, &amp;, etc.)
    - XML/metadata-taggar
    - SFS-ramar och sidhuvud/sidfötter
    - Dubbla whitespace och brutna radbrytningar
    - Tomrader
    
    Mål: Bättre Context Precision genom mindre brus i top-k chunks.
    """
    import html
    
    # 1. Decode HTML entities
    text = html.unescape(text)
    
    # 2. Ta bort XML-taggar
    text = re.sub(r'<[^>]+>', '', text)
    
    # 3. Ta bort SFS-metadata (vanliga prefix)
    metadata_patterns = [
        r'^SFS nr:.*$',
        r'^Departement/myndighet:.*$',
        r'^Utfärdad:.*$',
        r'^Ändrad:.*$',
        r'^Omtryck:.*$',
        r'^Källa:.*$',
        r'^Senast hämtad:.*$',
    ]
    for pattern in metadata_patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)
    
    # 4. Ta bort sidhuvud/sidfötter (vanliga mönster)
    # Exempel: "Sida 1 av 10", "© Riksdagen", etc.
    footer_patterns = [
        r'Sida \d+ av \d+',
        r'© \w+',
        r'www\.\w+\.se',
        r'Utskriven från.*',
    ]
    for pattern in footer_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # 5. Normalisera whitespace
    # Ta bort dubbla mellanslag
    text = re.sub(r' {2,}', ' ', text)
    
    # Ta bort tomrader (mer än 2 radbrytningar i rad)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Fixa brutna radbrytningar (ord som delats mitt i)
    # Exempel: "yttran-\ndefrihet" → "yttrandefrihet"
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    
    # 6. Trim
    text = text.strip()
    
    return text


# Pydantic Models
class HealthResponse(BaseModel):
    status: str
    chromadb_connected: bool
    collections: Dict[str, int]
    timestamp: str


class OverviewStats(BaseModel):
    total_documents: int
    collections: Dict[str, int]
    storage_size_mb: float
    last_updated: str


class DocumentTypeStats(BaseModel):
    doc_type: str
    count: int
    percentage: float


class TimelineDataPoint(BaseModel):
    date: str
    count: int


class CollectionInfo(BaseModel):
    name: str
    document_count: int
    metadata_fields: List[str]


class SearchFilters(BaseModel):
    doc_type: Optional[str] = None
    source: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    filters: Optional[SearchFilters] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)
    sort: str = Field(default="relevance")


class SearchResult(BaseModel):
    id: str
    title: str
    source: str
    doc_type: Optional[str] = None
    snippet: str
    score: float
    date: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    page: int
    limit: int
    query: str


# ═══════════════════════════════════════════════════════════════════════════
# BATCH SEARCH MODELS - For N+1 query optimization
# Generates embedding ONCE, searches all doc_types in single request
# ═══════════════════════════════════════════════════════════════════════════

class BatchSearchRequest(BaseModel):
    """Request for batched document search across multiple doc_types"""
    query: str
    doc_types: List[str] = Field(..., description="Document types to search: 'prop', 'sfs', 'sou', 'mot', 'bet'")
    limit_per_type: int = Field(default=3, ge=1, le=20, description="Results per doc_type")


class BatchSearchResponse(BaseModel):
    """Response with results grouped by doc_type"""
    results_by_type: Dict[str, List[SearchResult]]
    total: int
    query: str
    embedding_generated_once: bool = True  # Confirms optimization was applied


# ═══════════════════════════════════════════════════════════════════════════
# PARALLEL SEARCH MODELS - Phase 1: Smarter Retrieval
# Searches collections in parallel with graceful degradation
# ═══════════════════════════════════════════════════════════════════════════

class ParallelSearchRequest(BaseModel):
    """Request for parallel collection search"""
    query: str
    k: int = Field(default=10, ge=1, le=50, description="Number of results")
    collections: Optional[List[str]] = Field(
        default=None,
        description="Collections to search. Default: all indexed collections"
    )
    timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    history: Optional[List[str]] = Field(
        default=None,
        description="Conversation history for decontextualization (Phase 2)"
    )


class RetrievalMetricsResponse(BaseModel):
    """Metrics from parallel retrieval - instrumentation for Phase 4"""
    latency: Dict[str, float]  # total_ms, dense_ms, bm25_ms
    results: Dict[str, int]    # dense_count, bm25_count, overlap, unique_total
    scores: Dict[str, float]   # top, mean, std, entropy
    timeouts: Dict[str, bool]  # dense, bm25
    strategy: str
    rewrite: Optional[Dict[str, Any]] = None  # Phase 2: rewrite metrics
    fusion: Optional[Dict[str, Any]] = None   # Phase 3: RAG-Fusion metrics
    adaptive: Optional[Dict[str, Any]] = None  # Phase 4: adaptive retrieval metrics


class ParallelSearchResponse(BaseModel):
    """Response from parallel search with instrumentation"""
    results: List[SearchResult]
    total: int
    query: str
    metrics: RetrievalMetricsResponse
    strategy_used: str = "parallel_v1"


class AdminStatus(BaseModel):
    chromadb_status: str
    chromadb_path: str
    pdf_cache_size_mb: float
    pdf_cache_files: int
    last_harvest: Optional[Dict[str, Any]] = None
    collections: List[CollectionInfo]


# Helper functions
def get_chromadb_client():
    """Get ChromaDB client with error handling"""
    try:
        if not os.path.exists(CHROMADB_PATH):
            return None
        return chromadb.PersistentClient(path=CHROMADB_PATH)
    except Exception as e:
        print(f"ChromaDB connection error: {e}")
        return None


def get_directory_size(path: str) -> float:
    """Calculate directory size in MB"""
    if not os.path.exists(path):
        return 0.0

    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except (OSError, FileNotFoundError):
                continue

    return total_size / (1024 * 1024)  # Convert to MB


def count_files_in_directory(path: str) -> int:
    """Count total files in directory recursively"""
    if not os.path.exists(path):
        return 0

    count = 0
    for dirpath, dirnames, filenames in os.walk(path):
        count += len(filenames)
    return count


# Endpoints

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check for Constitutional services
    Returns ChromaDB connection status and collection counts
    """
    client = get_chromadb_client()

    if not client:
        return HealthResponse(
            status="degraded",
            chromadb_connected=False,
            collections={},
            timestamp=datetime.now().isoformat()
        )

    try:
        collections = client.list_collections()
        collection_counts = {}

        for collection in collections:
            try:
                collection_counts[collection.name] = collection.count()
            except Exception as e:
                collection_counts[collection.name] = 0

        return HealthResponse(
            status="healthy",
            chromadb_connected=True,
            collections=collection_counts,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/stats/overview", response_model=OverviewStats)
async def get_overview_stats():
    """
    Overview statistics for Constitutional AI Dashboard
    Returns total documents, collection counts, and storage size
    """
    client = get_chromadb_client()

    if not client:
        return OverviewStats(
            total_documents=0,
            collections={},
            storage_size_mb=0.0,
            last_updated=datetime.now().isoformat()
        )

    try:
        collections = client.list_collections()
        collection_counts = {}
        total_docs = 0

        for collection in collections:
            try:
                count = collection.count()
                collection_counts[collection.name] = count
                total_docs += count
            except Exception:
                collection_counts[collection.name] = 0

        storage_size = get_directory_size(CHROMADB_PATH)

        return OverviewStats(
            total_documents=total_docs,
            collections=collection_counts,
            storage_size_mb=round(storage_size, 2),
            last_updated=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get overview stats: {str(e)}")


@router.get("/stats/documents-by-type", response_model=List[DocumentTypeStats])
async def get_documents_by_type():
    """
    Documents grouped by doc_type
    Returns counts for: prop, mot, sou, bet, ds, other
    """
    client = get_chromadb_client()

    if not client:
        return []

    try:
        # Query both main collections
        doc_type_counts = defaultdict(int)

        for collection_name in ["riksdag_documents_p1", "swedish_gov_docs"]:
            try:
                collection = client.get_collection(name=collection_name)

                # Get all documents with metadata (in batches to avoid memory issues)
                total_count = collection.count()
                batch_size = 1000
                offset = 0

                while offset < total_count:
                    limit = min(batch_size, total_count - offset)
                    results = collection.get(
                        limit=limit,
                        offset=offset,
                        include=["metadatas"]
                    )

                    if results and results.get("metadatas"):
                        for metadata in results["metadatas"]:
                            if metadata and "doc_type" in metadata:
                                doc_type = metadata["doc_type"]
                            else:
                                doc_type = "other"
                            doc_type_counts[doc_type] += 1

                    offset += limit

            except Exception as e:
                print(f"Error querying collection {collection_name}: {e}")
                continue

        # Calculate total for percentages
        total = sum(doc_type_counts.values())

        if total == 0:
            # Return mock data if no documents found
            return [
                DocumentTypeStats(doc_type="prop", count=0, percentage=0.0),
                DocumentTypeStats(doc_type="mot", count=0, percentage=0.0),
                DocumentTypeStats(doc_type="sou", count=0, percentage=0.0),
                DocumentTypeStats(doc_type="bet", count=0, percentage=0.0),
                DocumentTypeStats(doc_type="ds", count=0, percentage=0.0),
                DocumentTypeStats(doc_type="other", count=0, percentage=0.0),
            ]

        # Convert to response format
        results = []
        for doc_type, count in sorted(doc_type_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total) * 100
            results.append(DocumentTypeStats(
                doc_type=doc_type,
                count=count,
                percentage=round(percentage, 2)
            ))

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document type stats: {str(e)}")


@router.get("/stats/timeline", response_model=List[TimelineDataPoint])
async def get_timeline_stats():
    """
    Documents over time - last 30 days
    Returns document additions by date
    """
    client = get_chromadb_client()

    if not client:
        # Return mock data
        mock_data = []
        for i in range(30, 0, -1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            # Generate mock count (higher recent activity)
            count = max(0, int(1000 - (i * 20) + (i % 7) * 50))
            mock_data.append(TimelineDataPoint(date=date, count=count))
        return mock_data

    try:
        # Try to get actual timeline data from metadata
        timeline_counts = defaultdict(int)

        for collection_name in ["riksdag_documents_p1", "swedish_gov_docs"]:
            try:
                collection = client.get_collection(name=collection_name)
                total_count = collection.count()
                batch_size = 1000
                offset = 0

                while offset < total_count:
                    limit = min(batch_size, total_count - offset)
                    results = collection.get(
                        limit=limit,
                        offset=offset,
                        include=["metadatas"]
                    )

                    if results and results.get("metadatas"):
                        for metadata in results["metadatas"]:
                            if metadata and "date" in metadata:
                                try:
                                    doc_date = metadata["date"][:10]  # YYYY-MM-DD
                                    timeline_counts[doc_date] += 1
                                except Exception:
                                    continue

                    offset += limit

            except Exception as e:
                print(f"Error querying timeline for {collection_name}: {e}")
                continue

        if not timeline_counts:
            # Return mock data if no date metadata
            mock_data = []
            for i in range(30, 0, -1):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                count = max(0, int(1000 - (i * 20) + (i % 7) * 50))
                mock_data.append(TimelineDataPoint(date=date, count=count))
            return mock_data

        # Get last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        results = []
        for i in range(30):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            count = timeline_counts.get(date, 0)
            results.append(TimelineDataPoint(date=date, count=count))

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get timeline stats: {str(e)}")


@router.get("/collections", response_model=List[CollectionInfo])
async def list_collections():
    """
    List all ChromaDB collections with stats
    Returns collection name, document count, and metadata fields
    """
    client = get_chromadb_client()

    if not client:
        return []

    try:
        collections = client.list_collections()
        results = []

        for collection in collections:
            try:
                count = collection.count()

                # Get sample document to extract metadata fields
                metadata_fields = []
                if count > 0:
                    sample = collection.get(limit=1, include=["metadatas"])
                    if sample and sample.get("metadatas") and sample["metadatas"][0]:
                        metadata_fields = list(sample["metadatas"][0].keys())

                results.append(CollectionInfo(
                    name=collection.name,
                    document_count=count,
                    metadata_fields=metadata_fields
                ))

            except Exception as e:
                print(f"Error getting collection info for {collection.name}: {e}")
                continue

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """
    Search documents in ChromaDB
    Supports filters, pagination, and sorting
    """
    client = get_chromadb_client()

    if not client:
        raise HTTPException(status_code=503, detail="ChromaDB not available")

    logger.info(f"Search Query: '{request.query}', limit: {request.limit}, page: {request.page}")

    try:
        # Search across all collections: SFS (primary sources) + riksdag (secondary)
        all_results = []
        
        # Get embedding function for semantic search (768-dim KBLab model)
        embed_fn = get_embedding_function()

        # Search SFS collection first (primary sources), then riksdag collections
        for collection_name in ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]:
            try:
                logger.info(f"Accessing collection: {collection_name}")
                # Get collection WITHOUT embedding function to avoid conflict
                # We'll manually generate embeddings and use query_embeddings
                collection = client.get_collection(name=collection_name)
                logger.info(f"Collection {collection_name} loaded, count: {collection.count()}")

                # Build where filter
                where_filter = {}
                if request.filters:
                    if request.filters.doc_type:
                        where_filter["doc_type"] = request.filters.doc_type
                    if request.filters.source:
                        where_filter["source"] = request.filters.source

                # Query ChromaDB - try semantic first, fallback to text search
                n_results = min(request.limit * request.page, 100)
                query_results = None
                use_text_search = False

                try:
                    logger.info(f"Starting semantic query for '{request.query}'...")
                    
                    # Generate query embedding manually using our KBLab model
                    query_embedding = embed_fn([request.query])[0]
                    logger.info(f"Generated query embedding: {len(query_embedding)}-dim")
                    
                    # Use query_embeddings instead of query_texts to avoid embedding function conflict
                    query_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=n_results,
                        where=where_filter if where_filter else None,
                        include=["metadatas", "documents", "distances"]
                    )
                    logger.info(f"Semantic query SUCCESS! Found {len(query_results.get('ids', [[]])[0])} results")
                except Exception as embed_error:
                    # Fallback to text search if semantic search fails (embedding mismatch)
                    logger.warning(f"Semantic search FAILED: {embed_error}")
                    logger.info("Falling back to keyword text search...")
                    use_text_search = True
                    
                    # Extract keywords from the query for better text search
                    keywords = extract_search_keywords(request.query)
                    logger.info(f"Extracted keywords: {keywords}")
                    
                    # Try each keyword until we get results (OR logic)
                    query_results = {"ids": [], "metadatas": [], "documents": []}
                    for keyword in keywords[:3]:  # Try up to 3 keywords
                        try:
                            kw_results = collection.get(
                                where_document={"$contains": keyword},
                                limit=n_results,
                                include=["metadatas", "documents"]
                            )
                            if kw_results and kw_results.get("ids"):
                                # Merge results
                                existing_ids = set(query_results["ids"])
                                for i, doc_id in enumerate(kw_results["ids"]):
                                    if doc_id not in existing_ids:
                                        query_results["ids"].append(doc_id)
                                        if kw_results.get("metadatas"):
                                            query_results["metadatas"].append(kw_results["metadatas"][i])
                                        if kw_results.get("documents"):
                                            query_results["documents"].append(kw_results["documents"][i])
                                        existing_ids.add(doc_id)
                                        
                                        # Stop if we have enough results
                                        if len(query_results["ids"]) >= n_results:
                                            break
                        except Exception as kw_error:
                            logger.warning(f"Keyword '{keyword}' search failed: {kw_error}")
                            continue
                        
                        if len(query_results["ids"]) >= n_results:
                            break
                    
                    logger.info(f"Text search returned {len(query_results.get('ids', []))} results")

                if use_text_search and query_results and query_results.get("ids"):
                    # Text search results (flat structure)
                    for i, doc_id in enumerate(query_results["ids"]):
                        metadata = query_results["metadatas"][i] if query_results.get("metadatas") else {}
                        document = query_results["documents"][i] if query_results.get("documents") else ""

                        # Calculate basic relevance score based on query term frequency
                        query_lower = request.query.lower()
                        doc_lower = document.lower()
                        term_count = doc_lower.count(query_lower)
                        score = min(0.99, 0.5 + (term_count * 0.1))

                        # Clean snippet before truncating
                        cleaned_doc = clean_snippet(document)
                        snippet = cleaned_doc[:200] + "..." if len(cleaned_doc) > 200 else cleaned_doc

                        all_results.append(SearchResult(
                            id=doc_id,
                            title=metadata.get("title", "Untitled"),
                            source=metadata.get("source", collection_name),
                            doc_type=metadata.get("doc_type"),
                            snippet=snippet,
                            score=round(score, 4),
                            date=metadata.get("date")
                        ))
                elif query_results and query_results.get("ids") and len(query_results["ids"]) > 0:
                    # Semantic search results (nested structure)
                    for i in range(len(query_results["ids"][0])):
                        doc_id = query_results["ids"][0][i]
                        metadata = query_results["metadatas"][0][i] if query_results.get("metadatas") else {}
                        document = query_results["documents"][0][i] if query_results.get("documents") else ""
                        distance = query_results["distances"][0][i] if query_results.get("distances") else 1.0

                        score = 1.0 / (1.0 + distance)
                        
                        # Clean snippet before truncating
                        cleaned_doc = clean_snippet(document)
                        snippet = cleaned_doc[:200] + "..." if len(cleaned_doc) > 200 else cleaned_doc

                        all_results.append(SearchResult(
                            id=doc_id,
                            title=metadata.get("title", "Untitled"),
                            source=metadata.get("source", collection_name),
                            doc_type=metadata.get("doc_type"),
                            snippet=snippet,
                            score=round(score, 4),
                            date=metadata.get("date")
                        ))

            except Exception as e:
                logger.error(f"Error searching collection {collection_name}: {e}")
                continue

        # Sort results with SFS prioritization
        # Ordning: SFS > myndighetskälla > övrigt, sedan efter score
        if request.sort == "relevance":
            all_results.sort(key=lambda x: (
                # Primary: SFS-källor först (0 = högst prioritet)
                0 if x.doc_type == "sfs" else 1,
                # Secondary: Score (negativ för descending)
                -x.score
            ))
        elif request.sort == "date":
            all_results.sort(key=lambda x: x.date or "", reverse=True)

        # Apply pagination
        start_idx = (request.page - 1) * request.limit
        end_idx = start_idx + request.limit
        paginated_results = all_results[start_idx:end_idx]

        return SearchResponse(
            results=paginated_results,
            total=len(all_results),
            page=request.page,
            limit=request.limit,
            query=request.query
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
# BATCH SEARCH ENDPOINT - N+1 Query Optimization
# Reduces 3 API calls to 1 by generating embedding once and reusing it
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/search-batch", response_model=BatchSearchResponse)
async def search_documents_batch(request: BatchSearchRequest):
    """
    Batch search across multiple doc_types with single embedding generation.

    Performance improvement:
    - Before: 3 separate requests × (200ms embedding + 150ms search) = ~1050ms
    - After: 1 request × (200ms embedding + 3×150ms searches) = ~650ms
    - Improvement: ~38% faster, 66% fewer API calls
    """
    client = get_chromadb_client()

    if not client:
        raise HTTPException(status_code=503, detail="ChromaDB not available")

    logger.info(f"Batch Search: '{request.query}', doc_types: {request.doc_types}, limit_per_type: {request.limit_per_type}")

    try:
        # Generate embedding ONCE (this is the optimization!)
        embed_fn = get_embedding_function()
        query_embedding = embed_fn([request.query])[0]
        logger.info(f"Generated single embedding: {len(query_embedding)}-dim (reused for {len(request.doc_types)} doc_types)")

        # Initialize results grouped by doc_type
        results_by_type: Dict[str, List[SearchResult]] = {dt: [] for dt in request.doc_types}
        total_results = 0

        # Search all collections for each doc_type
        for collection_name in ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]:
            try:
                collection = client.get_collection(name=collection_name)

                # Search once per doc_type using the SAME embedding
                for doc_type in request.doc_types:
                    try:
                        query_results = collection.query(
                            query_embeddings=[query_embedding],  # Reuse embedding!
                            n_results=request.limit_per_type,
                            where={"doc_type": doc_type},
                            include=["metadatas", "documents", "distances"]
                        )

                        if query_results and query_results.get("ids") and len(query_results["ids"][0]) > 0:
                            for i in range(len(query_results["ids"][0])):
                                doc_id = query_results["ids"][0][i]
                                metadata = query_results["metadatas"][0][i] if query_results.get("metadatas") else {}
                                document = query_results["documents"][0][i] if query_results.get("documents") else ""
                                distance = query_results["distances"][0][i] if query_results.get("distances") else 1.0

                                score = 1.0 / (1.0 + distance)
                                cleaned_doc = clean_snippet(document)
                                snippet = cleaned_doc[:200] + "..." if len(cleaned_doc) > 200 else cleaned_doc

                                # Check if we already have this result (dedup across collections)
                                existing_ids = [r.id for r in results_by_type[doc_type]]
                                if doc_id not in existing_ids and len(results_by_type[doc_type]) < request.limit_per_type:
                                    results_by_type[doc_type].append(SearchResult(
                                        id=doc_id,
                                        title=metadata.get("title", "Untitled"),
                                        source=metadata.get("source", collection_name),
                                        doc_type=metadata.get("doc_type", doc_type),
                                        snippet=snippet,
                                        score=round(score, 4),
                                        date=metadata.get("date")
                                    ))
                                    total_results += 1

                    except Exception as type_error:
                        logger.warning(f"Error searching {collection_name} for {doc_type}: {type_error}")
                        continue

            except Exception as coll_error:
                logger.warning(f"Error accessing collection {collection_name}: {coll_error}")
                continue

        # Sort each doc_type's results by score
        for doc_type in results_by_type:
            results_by_type[doc_type].sort(key=lambda x: -x.score)

        logger.info(f"Batch search complete: {total_results} total results across {len(request.doc_types)} doc_types")

        return BatchSearchResponse(
            results_by_type=results_by_type,
            total=total_results,
            query=request.query,
            embedding_generated_once=True
        )

    except Exception as e:
        logger.error(f"Batch search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch search failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
# PARALLEL SEARCH - Phase 1: Smarter Retrieval
# Searches collections in parallel with graceful degradation and instrumentation
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/search-parallel", response_model=ParallelSearchResponse)
async def parallel_search(
    request: ParallelSearchRequest,
    x_retrieval_strategy: Optional[str] = Header(default=None, alias="X-Retrieval-Strategy")
):
    """
    Parallel search across multiple collections with graceful degradation.

    Smarter Retrieval (Phases 1-3):
    - Phase 1: Parallel collection search using asyncio.gather()
    - Phase 2: Query rewriting with decontextualization
    - Phase 3: RAG-Fusion multi-query with RRF merge
    - Returns results even if some collections timeout
    - Provides instrumentation metrics for Phase 4 adaptive retrieval

    Headers:
    - X-Retrieval-Strategy: "legacy" | "parallel_v1" (default) | "rewrite_v1" | "rag_fusion"
    """
    start_time = time.perf_counter()

    # Feature flag: allow A/B testing via header
    if x_retrieval_strategy == "legacy":
        # Fall back to sequential search for comparison
        logger.info("Using legacy sequential search (X-Retrieval-Strategy: legacy)")
        # Delegate to existing search endpoint logic
        legacy_response = await search_documents(SearchRequest(
            query=request.query,
            limit=request.k
        ))

        # Wrap in ParallelSearchResponse format
        total_latency = (time.perf_counter() - start_time) * 1000
        return ParallelSearchResponse(
            results=legacy_response.results,
            total=legacy_response.total,
            query=request.query,
            metrics=RetrievalMetricsResponse(
                latency={"total_ms": total_latency, "dense_ms": total_latency, "bm25_ms": 0},
                results={"dense_count": len(legacy_response.results), "bm25_count": 0, "overlap": 0, "unique_total": len(legacy_response.results)},
                scores={"top": legacy_response.results[0].score if legacy_response.results else 0, "mean": 0, "std": 0, "entropy": 0},
                timeouts={"dense": False, "bm25": False},
                strategy="legacy"
            ),
            strategy_used="legacy"
        )

    # Check if required components are available (unless using legacy mode)
    if not RETRIEVAL_COMPONENTS_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Parallel search requires RetrievalOrchestrator and QueryRewriter components which are not yet implemented. Use /search endpoint instead or set X-Retrieval-Strategy: legacy."
        )
    
    # Determine strategy (Phase 1, 2, 3, or 4)
    use_adaptive = x_retrieval_strategy == "adaptive"
    use_rewrite = x_retrieval_strategy in ("rewrite_v1", "rag_fusion")
    use_fusion = x_retrieval_strategy == "rag_fusion"

    if use_adaptive:
        strategy = RetrievalStrategy.ADAPTIVE
    elif use_fusion:
        strategy = RetrievalStrategy.RAG_FUSION
    elif use_rewrite:
        strategy = RetrievalStrategy.REWRITE_V1
    else:
        strategy = RetrievalStrategy.PARALLEL_V1

    # New parallel search (with optional rewriting/fusion)
    try:
        client = get_chromadb_client()
        if not client:
            raise HTTPException(status_code=503, detail="ChromaDB not available")

        # Get embedding function
        embed_fn = get_embedding_function()

        # Create query rewriter (for Phase 2, 3, and 4)
        query_rewriter = QueryRewriter() if (use_rewrite or use_adaptive) else None

        # Create orchestrator (Phase 3+ adds expander automatically)
        orchestrator = RetrievalOrchestrator(
            chromadb_client=client,
            embedding_function=embed_fn,
            default_timeout=request.timeout_seconds,
            query_rewriter=query_rewriter
        )

        # Execute search (parallel or with rewriting)
        result = await orchestrator.search(
            query=request.query,
            k=request.k,
            strategy=strategy,
            collections=request.collections,
            history=request.history  # Phase 2: conversation history
        )

        if not result.success:
            logger.error(f"Search failed: {result.error}")
            raise HTTPException(status_code=500, detail=result.error)

        # Convert to response format
        search_results = [
            SearchResult(
                id=r.id,
                title=r.title,
                source=r.source,
                doc_type=r.doc_type,
                snippet=r.snippet,
                score=r.score,
                date=r.date
            )
            for r in result.results
        ]

        # Build metrics response
        metrics_dict = result.metrics.to_dict()
        metrics_response = RetrievalMetricsResponse(
            latency=metrics_dict["latency"],
            results=metrics_dict["results"],
            scores=metrics_dict["scores"],
            timeouts=metrics_dict["timeouts"],
            strategy=metrics_dict["strategy"],
            rewrite=metrics_dict.get("rewrite"),  # Phase 2: include rewrite metrics
            fusion=metrics_dict.get("fusion"),    # Phase 3: include fusion metrics
            adaptive=metrics_dict.get("adaptive") # Phase 4: include adaptive metrics
        )

        # Log with strategy-specific info
        if use_adaptive:
            adaptive_info = metrics_dict.get("adaptive", {})
            signals = adaptive_info.get("confidence_signals", {})
            logger.info(
                f"Adaptive search: {len(search_results)} results in {metrics_dict['latency']['total_ms']:.1f}ms "
                f"(step: {adaptive_info.get('final_step', '?')}, confidence: {signals.get('overall_confidence', 0):.2f}, "
                f"escalations: {adaptive_info.get('total_escalations', 0)})"
            )
        elif use_fusion:
            fusion_info = metrics_dict.get("fusion", {})
            logger.info(
                f"RAG-Fusion search: {len(search_results)} results in {metrics_dict['latency']['total_ms']:.1f}ms "
                f"(queries: {fusion_info.get('num_queries', 1)}, gain: {fusion_info.get('fusion_gain', 0):.1%})"
            )
        else:
            logger.info(
                f"Parallel search: {len(search_results)} results in {metrics_dict['latency']['total_ms']:.1f}ms "
                f"(dense: {metrics_dict['latency']['dense_ms']:.1f}ms, timeout: {metrics_dict['timeouts']['dense']})"
            )

        return ParallelSearchResponse(
            results=search_results,
            total=len(search_results),
            query=request.query,
            metrics=metrics_response,
            strategy_used=strategy.value
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parallel search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Parallel search failed: {str(e)}")


@router.get("/admin/status", response_model=AdminStatus)
async def get_admin_status():
    """
    Admin status overview
    Returns ChromaDB status, PDF cache info, and harvest status
    """
    client = get_chromadb_client()

    # Get PDF cache info
    pdf_cache_size = get_directory_size(PDF_CACHE_PATH)
    pdf_cache_files = count_files_in_directory(PDF_CACHE_PATH)

    # Get collections info
    collections_info = []
    if client:
        try:
            collections = client.list_collections()
            for collection in collections:
                try:
                    count = collection.count()
                    metadata_fields = []
                    if count > 0:
                        sample = collection.get(limit=1, include=["metadatas"])
                        if sample and sample.get("metadatas") and sample["metadatas"][0]:
                            metadata_fields = list(sample["metadatas"][0].keys())

                    collections_info.append(CollectionInfo(
                        name=collection.name,
                        document_count=count,
                        metadata_fields=metadata_fields
                    ))
                except Exception:
                    continue
        except Exception as e:
            print(f"Error getting collections: {e}")

    # Check for harvest state file
    last_harvest = None
    harvest_state_path = "/home/ai-server/.claude/skills/swedish-gov-scraper/HARVEST_STATE.md"
    if os.path.exists(harvest_state_path):
        try:
            with open(harvest_state_path, 'r', encoding='utf-8') as f:
                content = f.read()
                last_harvest = {
                    "status": "available",
                    "file_path": harvest_state_path,
                    "note": "See HARVEST_STATE.md for details"
                }
        except Exception:
            pass

    return AdminStatus(
        chromadb_status="connected" if client else "disconnected",
        chromadb_path=CHROMADB_PATH,
        pdf_cache_size_mb=round(pdf_cache_size, 2),
        pdf_cache_files=pdf_cache_files,
        last_harvest=last_harvest,
        collections=collections_info
    )


# ═══════════════════════════════════════════════════════════════════════════
# PDF-to-Image Endpoint for OCR
# ═══════════════════════════════════════════════════════════════════════════

class PDFToImageRequest(BaseModel):
    url: str = Field(..., description="URL to PDF document")
    page: int = Field(1, description="Page number to convert (1-indexed)")


class PDFToImageResponse(BaseModel):
    image_base64: str
    page: int
    mime_type: str


@router.post("/pdf-to-image", response_model=PDFToImageResponse)
async def pdf_to_image(request: PDFToImageRequest):
    """
    Download a PDF from URL and convert specified page to base64 image.
    Used by agentic RAG for OCR with DeepSeek vision model.
    """
    try:
        # Download the PDF
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(request.url, follow_redirects=True)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download PDF: {response.status_code}"
                )
            pdf_content = response.content

        # Save to temp file and convert
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_content)
            tmp_path = tmp.name

        try:
            from pdf2image import convert_from_path
            import io

            # Convert specified page (pdf2image uses 1-indexed pages)
            images = convert_from_path(
                tmp_path,
                dpi=150,
                first_page=request.page,
                last_page=request.page
            )

            if not images:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not convert page {request.page}"
                )

            # Convert to base64
            buffer = io.BytesIO()
            images[0].save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            return PDFToImageResponse(
                image_base64=image_base64,
                page=request.page,
                mime_type="image/png"
            )

        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="pdf2image not installed. Run: pip install pdf2image"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


async def harvest_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for live harvest progress
    Sends periodic updates matching HarvestProgress interface
    """
    import asyncio
    await websocket.accept()

    try:
        # Mock harvest progress data matching frontend HarvestProgress interface
        sources = [
            "Riksdagen",
            "Skatteverket",
            "Socialstyrelsen",
            "Naturvårdsverket",
            "Boverket",
            "Dataportal"
        ]

        total_documents = 250000
        documents_per_update = 2500
        current_doc = 0
        source_index = 0

        while True:
            # Increment progress
            current_doc += documents_per_update
            if current_doc > total_documents:
                current_doc = total_documents

            # Calculate progress percentage
            progress = (current_doc / total_documents) * 100

            # Calculate ETA (mock)
            remaining_docs = total_documents - current_doc
            docs_per_minute = documents_per_update * 2  # 2 updates per minute
            minutes_remaining = remaining_docs / docs_per_minute if docs_per_minute > 0 else 0

            eta = None
            if minutes_remaining > 0:
                if minutes_remaining > 60:
                    hours = int(minutes_remaining / 60)
                    mins = int(minutes_remaining % 60)
                    eta = f"{hours}h {mins}m"
                else:
                    eta = f"{int(minutes_remaining)}m"

            # Rotate through sources
            current_source = sources[source_index % len(sources)]

            # Send progress update
            progress_data = {
                "documentsProcessed": current_doc,
                "currentSource": current_source,
                "progress": round(progress, 1),
                "totalDocuments": total_documents,
                "eta": eta
            }

            await websocket.send_json(progress_data)

            # If we've completed, reset for demo purposes
            if current_doc >= total_documents:
                await asyncio.sleep(5)
                current_doc = 0
                source_index = 0
            else:
                source_index += 1
                await asyncio.sleep(30)  # Update every 30 seconds

    except WebSocketDisconnect:
        print("[Harvest WS] Client disconnected")
    except Exception as e:
        print(f"[Harvest WS] Error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-ENCODER RERANKER - BGE-reranker-v2-m3
# ═══════════════════════════════════════════════════════════════════════════

# Global reranker cache (lazy-loaded)
_reranker_model = None
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"


def get_reranker_model():
    """
    Lazy-load BGE reranker model (~1.2GB VRAM).
    Caches model globally to avoid repeated loading.
    """
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker model: {RERANKER_MODEL_NAME}")
            _reranker_model = CrossEncoder(RERANKER_MODEL_NAME, max_length=512)
            logger.info("Reranker model loaded ✓")
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
            raise
    return _reranker_model


class RerankDocument(BaseModel):
    id: str
    title: str
    content: str


class RerankRequest(BaseModel):
    query: str = Field(..., description="The search query")
    documents: List[RerankDocument] = Field(..., description="Documents to rerank")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class RerankResult(BaseModel):
    id: str
    title: str
    score: float
    rank: int


class RerankResponse(BaseModel):
    results: List[RerankResult]
    model: str
    query: str


@router.post("/rerank", response_model=RerankResponse)
async def rerank_documents(request: RerankRequest):
    """
    Rerank documents using BGE cross-encoder model.

    Takes a query and list of candidate documents, scores each (query, doc) pair
    using a cross-encoder, and returns top-k documents sorted by relevance.

    VRAM: ~1.2GB for BGE-reranker-v2-m3
    Latency: ~10-30ms per document batch
    """
    if not request.documents:
        return RerankResponse(
            results=[],
            model=RERANKER_MODEL_NAME,
            query=request.query
        )

    logger.info(f"Reranking {len(request.documents)} documents for query: '{request.query[:50]}...'")

    try:
        # Get or load the reranker model
        reranker = get_reranker_model()

        # Prepare (query, document) pairs for cross-encoder
        # Combine title and content for better scoring
        pairs = [
            (request.query, f"{doc.title}\n{doc.content[:1000]}")
            for doc in request.documents
        ]

        # Score all pairs in batch (efficient)
        scores = reranker.predict(pairs, show_progress_bar=False)

        # Create results with scores
        scored_docs = [
            {
                "id": doc.id,
                "title": doc.title,
                "score": float(score)
            }
            for doc, score in zip(request.documents, scores)
        ]

        # Sort by score (highest first)
        scored_docs.sort(key=lambda x: x["score"], reverse=True)

        # Take top-k and add ranks
        results = [
            RerankResult(
                id=doc["id"],
                title=doc["title"],
                score=round(doc["score"], 4),
                rank=i + 1
            )
            for i, doc in enumerate(scored_docs[:request.top_k])
        ]

        logger.info(f"Reranking complete. Top score: {results[0].score if results else 0:.4f}")

        return RerankResponse(
            results=results,
            model=RERANKER_MODEL_NAME,
            query=request.query
        )

    except ImportError as e:
        logger.error(f"sentence-transformers not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="Reranker model not available. Install: pip install sentence-transformers"
        )
    except Exception as e:
        logger.error(f"Reranking failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reranking failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
# AGENTIC RAG ENDPOINT - Full pipeline for RAG2 Web UI
# Query routing → ChromaDB search → Ollama LLM → Jail Warden v2
# ═══════════════════════════════════════════════════════════════════════════

# Jail Warden v2 - Swedish legal term corrections
JAIL_WARDEN_CORRECTIONS = {
    "datainspektionen": "Integritetsskyddsmyndigheten (IMY)",
    "personuppgiftslagen": "GDPR och Dataskyddslagen (2018:218)",
    "pul": "GDPR och Dataskyddslagen (2018:218)",
    "pressfrihetslagen": "Tryckfrihetsförordningen (TF)",
    "grundlagen": "Regeringsformen (RF)",
    "offentlighetslagen": "Offentlighets- och sekretesslagen (OSL)",
    "sekretesslagen": "Offentlighets- och sekretesslagen (OSL)",
    "barnkonventionen": "Barnkonventionen (SFS 2018:1197)",
    "diskrimineringsombudsmannen": "Diskrimineringsombudsmannen (DO)",
    "konsumentombudsmannen": "Konsumentverket",
    "jämställdhetsombudsmannen": "Diskrimineringsombudsmannen (DO)",
    "handikappombudsmannen": "Diskrimineringsombudsmannen (DO)",
}

# Query classification patterns
CHAT_PATTERNS = [
    r'^(hej|tjena|hallå|hejsan|god\s+(morgon|dag|kväll))[\s!?]*$',
    r'^(tack|tackar|bra jobbat|fint)[\s!?]*$',
    r'^(vem är du|vad kan du|hur funkar du)[\s!?]*',
    r'^(ja|nej|ok|okej|alright)[\s!?]*$',
]

EVIDENCE_PATTERNS = [
    r'vad säger (lagen|lagstiftningen|rf|gdpr|osl|tf)',
    r'enligt \d+\s*(kap|§|kapitel)',
    r'visa (paragrafen|lagtext|källa)',
    r'citera\s+',
    r'(sfs|prop|sou)\s*\d{4}:\d+',
]


class ResponseMode(str):
    CHAT = "CHAT"
    ASSIST = "ASSIST"
    EVIDENCE = "EVIDENCE"


class WardenStatus(str):
    UNCHANGED = "UNCHANGED"
    TERM_CORRECTED = "TERM_CORRECTED"
    QUESTION_REWRITTEN = "QUESTION_REWRITTEN"
    FACT_VERIFIED = "FACT_VERIFIED"
    FACT_UNVERIFIED = "FACT_UNVERIFIED"
    CITATIONS_STRIPPED = "CITATIONS_STRIPPED"
    ERROR = "ERROR"


class EvidenceLevel(str):
    HIGH = "HIGH"
    LOW = "LOW"
    NONE = "NONE"


class AgentSource(BaseModel):
    id: str
    title: str
    snippet: str
    score: float
    doc_type: Optional[str] = None
    source: str


class ConversationMessage(BaseModel):
    """A message in conversation history."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field(default="auto", description="Query mode: auto, chat, assist, evidence")
    history: Optional[List[ConversationMessage]] = Field(
        default=None,
        description="Conversation history for context (max 10 messages)"
    )


class AgentQueryResponse(BaseModel):
    answer: str
    sources: List[AgentSource]
    reasoning_steps: List[str]
    model_used: str
    total_time_ms: int
    mode: str
    warden_status: str
    evidence_level: str
    corrections_applied: List[str]


def decontextualize_query(question: str, history: Optional[List[ConversationMessage]]) -> str:
    """
    Rewrite a follow-up question to be standalone using conversation history.
    
    Examples:
    - "Vad sa den om straff?" + history about GDPR → "Vad säger GDPR om straff?"
    - "Och enligt OSL?" + history about sekretess → "Vad säger offentlighets- och sekretesslagen om sekretess?"
    
    Uses simple pattern matching for common Swedish follow-up patterns.
    """
    if not history or len(history) < 2:
        return question
    
    q_lower = question.lower().strip()
    
    # Patterns that indicate a follow-up question
    followup_patterns = [
        r'^och\s+',           # "Och vad gäller..."
        r'^men\s+',           # "Men om..."
        r'^vad\s+med\s+',     # "Vad med..."
        r'^hur\s+är\s+det\s+med', # "Hur är det med..."
        r'^den\s+',           # "Den lagen..." (referring back)
        r'^det\s+',           # "Det kapitlet..."
        r'^samma\s+',         # "Samma sak för..."
        r'^enligt\s+\w+\?$',  # Short "enligt X?" questions
    ]
    
    # Check if this looks like a follow-up
    is_followup = any(re.match(pattern, q_lower) for pattern in followup_patterns)
    
    if not is_followup and len(question) > 30:
        # Long questions are usually self-contained
        return question
    
    # Extract context from last user question and assistant response
    last_user_q = None
    last_assistant_response = None
    
    for msg in reversed(history[-6:]):  # Check last 6 messages
        if msg.role == "user" and not last_user_q:
            last_user_q = msg.content
        elif msg.role == "assistant" and not last_assistant_response:
            last_assistant_response = msg.content
        if last_user_q and last_assistant_response:
            break
    
    if not last_user_q:
        return question
    
    # Extract key terms from previous context
    context_terms = []
    
    # Look for legal document references in previous Q/A
    doc_patterns = [
        r'(GDPR|gdpr)',
        r'(OSL|osl|offentlighets-?\s*och\s*sekretesslagen)',
        r'(RF|rf|regeringsformen)',
        r'(TF|tf|tryckfrihetsförordningen)',
        r'(SFS\s*\d{4}:\d+)',
        r'(prop\.\s*\d{4}/\d{2,4}:\d+)',
        r'(SOU\s*\d{4}:\d+)',
        r'(personuppgift\w*)',
        r'(sekretess\w*)',
        r'(yttrandefrihet\w*)',
    ]
    
    for pattern in doc_patterns:
        if last_user_q:
            matches = re.findall(pattern, last_user_q, re.IGNORECASE)
            context_terms.extend(matches)
        if last_assistant_response:
            matches = re.findall(pattern, last_assistant_response[:500], re.IGNORECASE)
            context_terms.extend(matches)
    
    if not context_terms:
        return question
    
    # Decontextualize: add context to the question
    # Take unique terms, preserve first occurrence order
    seen = set()
    unique_terms = []
    for term in context_terms:
        term_lower = term.lower() if isinstance(term, str) else str(term).lower()
        if term_lower not in seen:
            seen.add(term_lower)
            unique_terms.append(term if isinstance(term, str) else str(term))
    
    context_str = ", ".join(unique_terms[:3])  # Max 3 terms
    
    # Construct decontextualized question
    if is_followup:
        # For clear follow-ups, prepend context
        decontextualized = f"Angående {context_str}: {question}"
    else:
        # For short questions, append context
        decontextualized = f"{question} (kontext: {context_str})"
    
    logger.info(f"Decontextualized: '{question}' → '{decontextualized}'")
    return decontextualized


def classify_query(question: str) -> str:
    """
    Classify query into CHAT, ASSIST, or EVIDENCE mode.

    - CHAT: Smalltalk, greetings, meta-questions (no RAG needed)
    - EVIDENCE: Explicit legal references, citations requested (strict tone)
    - ASSIST: Default - dual-pass with fact+style (conversational but accurate)
    """
    q_lower = question.lower().strip()

    # Check CHAT patterns first
    for pattern in CHAT_PATTERNS:
        if re.match(pattern, q_lower, re.IGNORECASE):
            return ResponseMode.CHAT

    # Check EVIDENCE patterns
    for pattern in EVIDENCE_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return ResponseMode.EVIDENCE

    # Default to ASSIST
    return ResponseMode.ASSIST


def apply_jail_warden(text: str) -> tuple[str, list[str]]:
    """
    Apply Jail Warden v2 corrections to text.
    Returns (corrected_text, list_of_corrections_applied).
    """
    corrections = []
    corrected = text

    for wrong_term, correct_term in JAIL_WARDEN_CORRECTIONS.items():
        # Case-insensitive replacement
        pattern = re.compile(re.escape(wrong_term), re.IGNORECASE)
        if pattern.search(corrected):
            corrected = pattern.sub(correct_term, corrected)
            corrections.append(f"{wrong_term} → {correct_term}")

    return corrected, corrections


def determine_evidence_level(sources: list, answer: str) -> str:
    """
    Determine evidence level based on source quality.

    HIGH: Multiple high-scoring SFS/prop sources
    LOW: Some relevant sources but lower scores
    NONE: No relevant sources found
    """
    if not sources:
        return EvidenceLevel.NONE

    # Count high-quality sources (score > 0.7, SFS or prop type)
    high_quality = sum(
        1 for s in sources
        if s.get("score", 0) > 0.7 and s.get("doc_type") in ["sfs", "prop"]
    )

    # Average score
    avg_score = sum(s.get("score", 0) for s in sources) / len(sources)

    if high_quality >= 2 or avg_score > 0.75:
        return EvidenceLevel.HIGH
    elif len(sources) > 0 and avg_score > 0.4:
        return EvidenceLevel.LOW
    else:
        return EvidenceLevel.NONE


@router.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(request: AgentQueryRequest):
    """
    Full agentic RAG pipeline for Constitutional AI.

    Pipeline:
    1. Query classification (CHAT/ASSIST/EVIDENCE)
    2. ChromaDB semantic search (for ASSIST/EVIDENCE)
    3. Ollama LLM generation (Ministral 3 14B)
    4. Jail Warden v2 corrections
    5. Evidence level assignment

    Response modes:
    - CHAT: Direct LLM response, no sources
    - ASSIST: Search + LLM with conversational tone
    - EVIDENCE: Search + LLM with formal tone and citations
    """
    import time
    start_time = time.time()
    reasoning_steps = []

    try:
        # 1. Classify query
        if request.mode == "auto":
            mode = classify_query(request.question)
            reasoning_steps.append(f"Query classified as {mode}")
        else:
            mode = request.mode.upper()
            reasoning_steps.append(f"Mode set to {mode} by user")

        sources = []
        context_text = ""

        # 2. Search ChromaDB (skip for CHAT mode)
        if mode != ResponseMode.CHAT:
            reasoning_steps.append("Searching ChromaDB for relevant documents...")

            client = get_chromadb_client()
            if client:
                embed_fn = get_embedding_function()
                query_embedding = embed_fn([request.question])[0]

                all_sources = []
                for collection_name in ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]:
                    try:
                        collection = client.get_collection(name=collection_name)
                        results = collection.query(
                            query_embeddings=[query_embedding],
                            n_results=5,
                            include=["metadatas", "documents", "distances"]
                        )

                        if results and results.get("ids") and len(results["ids"][0]) > 0:
                            for i in range(len(results["ids"][0])):
                                doc_id = results["ids"][0][i]
                                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                                document = results["documents"][0][i] if results.get("documents") else ""
                                distance = results["distances"][0][i] if results.get("distances") else 1.0

                                score = 1.0 / (1.0 + distance)
                                cleaned_doc = clean_snippet(document)
                                snippet = cleaned_doc[:300] + "..." if len(cleaned_doc) > 300 else cleaned_doc

                                all_sources.append({
                                    "id": doc_id,
                                    "title": metadata.get("title", "Untitled"),
                                    "snippet": snippet,
                                    "score": round(score, 4),
                                    "doc_type": metadata.get("doc_type"),
                                    "source": metadata.get("source", collection_name),
                                    "full_text": cleaned_doc[:1500]  # For context
                                })
                    except Exception as e:
                        logger.warning(f"Error searching {collection_name}: {e}")
                        continue

                # Sort by score and take top 5
                all_sources.sort(key=lambda x: -x["score"])
                sources = all_sources[:5]

                reasoning_steps.append(f"Found {len(sources)} relevant documents")

                # Build context from sources with metadata
                if sources:
                    context_parts = []
                    for i, src in enumerate(sources, 1):
                        doc_type = src.get('doc_type', 'okänt')
                        score = src.get('score', 0.0)
                        # Mark SFS sources as priority
                        priority_marker = "⭐ PRIORITET (SFS)" if doc_type == "sfs" else f"Typ: {doc_type.upper()}"
                        context_parts.append(
                            f"[Källa {i}: {src['title']}] {priority_marker} | Relevans: {score:.2f}\n"
                            f"{src['full_text']}"
                        )
                    context_text = "\n\n".join(context_parts)

        # 3. Generate response with Ollama
        reasoning_steps.append("Generating response with Ministral 3 14B...")

        # Build system prompt based on mode
        if mode == ResponseMode.CHAT:
            system_prompt = """Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat."""
            user_prompt = request.question
        elif mode == ResponseMode.EVIDENCE:
            system_prompt = """Du är en juridisk expert specialiserad på svensk lag och förvaltningsrätt.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling) - PRIORITERA DETTA
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT FÖR EVIDENCE-MODE:
1. Använd ENDAST källor från korpusen - hitta på ingenting
2. Citera ALLTID exakta SFS-nummer och paragrafer när de finns i källorna
3. PRIORITERA SFS-källor (lagtext) över prop/sou/bet när flera källor finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt: "Jag saknar specifik information i korpusen"
5. Var formell, exakt och saklig - MAX 200 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Citera källor med [Källa X] och inkludera SFS-nummer/paragraf när tillgängligt"""
            user_prompt = f"""Fråga: {request.question}

Källor från korpusen:
{context_text if context_text else "Inga relevanta källor hittades i korpusen."}

Instruktioner:
- Använd ENDAST källorna ovan för att svara
- Citera exakta SFS-nummer och paragrafer när de finns i källorna
- Prioritera SFS-källor (lagtext) om flera källor finns
- Om källor saknas, säg tydligt att du saknar specifik information
- Var formell och exakt

Svara i ren text, inga asterisker eller formatering."""
        else:  # ASSIST
            system_prompt = """Du är Constitutional AI, en expert på svensk lag och myndighetsförvaltning.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling)
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT:
1. Använd ALLTID källorna som tillhandahålls i kontexten när de finns
2. Citera källor i formatet [Källa X] när du refererar till dem
3. Prioritera SFS-källor (lagtext) över prop/sou när båda finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information
5. Var kortfattat men exakt - MAX 150 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Inga rubriker, inga punktlistor, inga asterisker
8. Gå rakt på sak och var hjälpsam"""
            user_prompt = f"""Fråga: {request.question}

Källor från korpusen:
{context_text if context_text else "Inga relevanta källor hittades i korpusen."}

Instruktioner:
- Använd källorna ovan för att svara på frågan
- Citera källor med [Källa X] när du refererar till dem
- Om källor saknas, säg tydligt att du saknar specifik information
- Prioritera SFS-källor (lagtext) om flera källor finns

Svara i ren text utan formatering."""

        # Call Ollama
        model_used = "ministral-3:14b"
        try:
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                ollama_response = await http_client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "ministral-3:14b",  # Ministral 3 14B
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.2 if mode == ResponseMode.EVIDENCE else (0.4 if mode == ResponseMode.ASSIST else 0.7),
                            "top_p": 0.9,
                            "repeat_penalty": 1.1,
                            "num_predict": 1024 if mode != ResponseMode.CHAT else 512  # Mer utrymme för detaljerade svar i ASSIST/EVIDENCE
                        }
                    }
                )

                if ollama_response.status_code == 200:
                    ollama_data = ollama_response.json()
                    answer = ollama_data.get("message", {}).get("content", "")
                    model_used = ollama_data.get("model", model_used)
                else:
                    logger.error(f"Ollama error: {ollama_response.status_code}")
                    answer = "Tyvärr kunde jag inte generera ett svar just nu. Ollama-modellen svarade inte."
        except Exception as ollama_error:
            logger.error(f"Ollama request failed: {ollama_error}")
            answer = "Tyvärr kunde jag inte ansluta till språkmodellen. Kontrollera att Ollama körs på port 11434."

        # 4. Apply Jail Warden v2 corrections
        reasoning_steps.append("Applying Jail Warden v2 corrections...")
        corrected_answer, corrections = apply_jail_warden(answer)

        warden_status = WardenStatus.TERM_CORRECTED if corrections else WardenStatus.UNCHANGED

        if corrections:
            reasoning_steps.append(f"Corrected {len(corrections)} terms: {', '.join(corrections)}")

        # 5. Determine evidence level
        evidence_level = determine_evidence_level(
            [{"score": s["score"], "doc_type": s["doc_type"]} for s in sources],
            corrected_answer
        )
        reasoning_steps.append(f"Evidence level: {evidence_level}")

        # Calculate total time
        total_time_ms = int((time.time() - start_time) * 1000)
        reasoning_steps.append(f"Total time: {total_time_ms}ms")

        # Build response
        return AgentQueryResponse(
            answer=corrected_answer,
            sources=[
                AgentSource(
                    id=s["id"],
                    title=s["title"],
                    snippet=s["snippet"],
                    score=s["score"],
                    doc_type=s["doc_type"],
                    source=s["source"]
                ) for s in sources
            ],
            reasoning_steps=reasoning_steps,
            model_used=model_used,
            total_time_ms=total_time_ms,
            mode=mode,
            warden_status=warden_status,
            evidence_level=evidence_level,
            corrections_applied=corrections
        )

    except Exception as e:
        logger.error(f"Agent query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Agent query failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
# STREAMING AGENT ENDPOINT - Server-Sent Events for real-time response
# ═══════════════════════════════════════════════════════════════════════════

# Model fallback configuration
PRIMARY_MODEL = "ministral-3:14b"
FALLBACK_MODEL = "gpt-sw3:6.7b"
MODEL_TIMEOUT = 60.0


async def stream_ollama_response(
    system_prompt: str,
    user_prompt: str,
    model: str = PRIMARY_MODEL,
    temperature: float = 0.5,
    num_predict: int = 512
) -> AsyncGenerator[str, None]:
    """
    Stream tokens from Ollama and yield SSE-formatted chunks.
    Falls back to secondary model on timeout.
    """
    async def try_stream(model_name: str) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=MODEL_TIMEOUT) as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/chat",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                        "top_p": 0.9,
                        "repeat_penalty": 1.1,
                        "num_predict": num_predict
                    }
                }
            ) as response:
                if response.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Ollama error: {response.status_code}",
                        request=response.request,
                        response=response
                    )
                
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                # SSE format: data: {json}\n\n
                                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                            
                            if data.get("done", False):
                                model_used = data.get("model", model_name)
                                yield f"data: {json.dumps({'type': 'done', 'model': model_used})}\n\n"
                                return
                        except json.JSONDecodeError:
                            continue
    
    # Try primary model first
    try:
        async for chunk in try_stream(model):
            yield chunk
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Emit fallback event
        yield f"data: {json.dumps({'type': 'fallback', 'from': model, 'to': FALLBACK_MODEL, 'reason': str(e)})}\n\n"
        
        # Try fallback model
        try:
            async for chunk in try_stream(FALLBACK_MODEL):
                yield chunk
        except Exception as fallback_error:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Both models failed: {fallback_error}'})}\n\n"


@router.post("/agent/query/stream")
async def agent_query_stream(request: AgentQueryRequest):
    """
    Streaming version of agent query using Server-Sent Events.
    
    Returns SSE stream with events:
    - {type: "metadata", mode: "ASSIST", sources: [...], evidence_level: "HIGH"}
    - {type: "token", content: "..."}  (repeated for each token)
    - {type: "fallback", from: "ministral-3:14b", to: "gpt-sw3:6.7b"}
    - {type: "done", model: "ministral-3:14b"}
    - {type: "error", message: "..."}
    
    Frontend should use EventSource or fetch with streaming body.
    """
    async def generate() -> AsyncGenerator[str, None]:
        start_time = time.time()
        
        try:
            # 1. Classify query
            if request.mode == "auto":
                mode = classify_query(request.question)
            else:
                mode = request.mode.upper()
            
            # 1b. Decontextualize if we have history
            search_query = request.question
            if request.history and mode != ResponseMode.CHAT:
                search_query = decontextualize_query(request.question, request.history)
                if search_query != request.question:
                    yield f"data: {json.dumps({'type': 'decontextualized', 'original': request.question, 'rewritten': search_query})}\n\n"
            
            sources = []
            context_text = ""
            
            # 2. Search ChromaDB (skip for CHAT mode)
            if mode != ResponseMode.CHAT:
                client = get_chromadb_client()
                if client:
                    embed_fn = get_embedding_function()
                    query_embedding = embed_fn([search_query])[0]  # Use decontextualized query
                    
                    all_sources = []
                    for collection_name in ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]:
                        try:
                            collection = client.get_collection(name=collection_name)
                            results = collection.query(
                                query_embeddings=[query_embedding],
                                n_results=5,
                                include=["metadatas", "documents", "distances"]
                            )
                            
                            if results and results.get("ids") and len(results["ids"][0]) > 0:
                                for i in range(len(results["ids"][0])):
                                    doc_id = results["ids"][0][i]
                                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                                    document = results["documents"][0][i] if results.get("documents") else ""
                                    distance = results["distances"][0][i] if results.get("distances") else 1.0
                                    
                                    score = 1.0 / (1.0 + distance)
                                    cleaned_doc = clean_snippet(document)
                                    snippet = cleaned_doc[:300] + "..." if len(cleaned_doc) > 300 else cleaned_doc
                                    
                                    all_sources.append({
                                        "id": doc_id,
                                        "title": metadata.get("title", "Untitled"),
                                        "snippet": snippet,
                                        "score": round(score, 4),
                                        "doc_type": metadata.get("doc_type"),
                                        "source": metadata.get("source", collection_name),
                                        "full_text": cleaned_doc[:1500]
                                    })
                        except Exception as e:
                            logger.warning(f"Error searching {collection_name}: {e}")
                            continue
                    
                    all_sources.sort(key=lambda x: -x["score"])
                    sources = all_sources[:5]
                    
                    if sources:
                        context_parts = []
                        for i, src in enumerate(sources, 1):
                            doc_type = src.get('doc_type', 'okänt')
                            score = src.get('score', 0.0)
                            # Mark SFS sources as priority
                            priority_marker = "⭐ PRIORITET (SFS)" if doc_type == "sfs" else f"Typ: {doc_type.upper()}"
                            context_parts.append(
                                f"[Källa {i}: {src['title']}] {priority_marker} | Relevans: {score:.2f}\n"
                                f"{src['full_text']}"
                            )
                        context_text = "\n\n".join(context_parts)
            
            # Determine evidence level early
            evidence_level = determine_evidence_level(
                [{"score": s["score"], "doc_type": s["doc_type"]} for s in sources],
                ""
            )
            
            # Check confidence threshold - if NONE, ask for clarification
            if evidence_level == EvidenceLevel.NONE and mode != ResponseMode.CHAT and len(request.question) < 20:
                yield f"data: {json.dumps({'type': 'low_confidence', 'message': 'Kunde inte hitta relevanta källor. Kan du förtydliga din fråga?'})}\n\n"
            
            # Send metadata event with sources BEFORE streaming starts
            search_time = int((time.time() - start_time) * 1000)
            metadata = {
                "type": "metadata",
                "mode": mode,
                "sources": [
                    {"id": s["id"], "title": s["title"], "score": s["score"], "doc_type": s["doc_type"]}
                    for s in sources
                ],
                "evidence_level": evidence_level,
                "search_time_ms": search_time
            }
            yield f"data: {json.dumps(metadata)}\n\n"
            
            # 3. Build prompts
            if mode == ResponseMode.CHAT:
                system_prompt = """Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat."""
                user_prompt = request.question
                temperature = 0.7
            elif mode == ResponseMode.EVIDENCE:
                system_prompt = """Du är en juridisk expert specialiserad på svensk lag och förvaltningsrätt.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling) - PRIORITERA DETTA
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT FÖR EVIDENCE-MODE:
1. Använd ENDAST källor från korpusen - hitta på ingenting
2. Citera ALLTID exakta SFS-nummer och paragrafer när de finns i källorna
3. PRIORITERA SFS-källor (lagtext) över prop/sou/bet när flera källor finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt: "Jag saknar specifik information i korpusen"
5. Var formell, exakt och saklig - MAX 200 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Citera källor med [Källa X] och inkludera SFS-nummer/paragraf när tillgängligt"""
                user_prompt = f"""Fråga: {request.question}

Källor från korpusen:
{context_text if context_text else "Inga relevanta källor hittades i korpusen."}

Instruktioner:
- Använd ENDAST källorna ovan för att svara
- Citera exakta SFS-nummer och paragrafer när de finns i källorna
- Prioritera SFS-källor (lagtext) om flera källor finns
- Om källor saknas, säg tydligt att du saknar specifik information
- Var formell och exakt

Svara i ren text, inga asterisker eller formatering."""
                temperature = 0.2
            else:  # ASSIST
                system_prompt = """Du är Constitutional AI, en expert på svensk lag och myndighetsförvaltning.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling)
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT:
1. Använd ALLTID källorna som tillhandahålls i kontexten när de finns
2. Citera källor i formatet [Källa X] när du refererar till dem
3. Prioritera SFS-källor (lagtext) över prop/sou när båda finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information
5. Var kortfattat men exakt - MAX 150 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Inga rubriker, inga punktlistor, inga asterisker
8. Gå rakt på sak och var hjälpsam"""
                user_prompt = f"""Fråga: {request.question}

Källor från korpusen:
{context_text if context_text else "Inga relevanta källor hittades i korpusen."}

Instruktioner:
- Använd källorna ovan för att svara på frågan
- Citera källor med [Källa X] när du refererar till dem
- Om källor saknas, säg tydligt att du saknar specifik information
- Prioritera SFS-källor (lagtext) om flera källor finns

Svara i ren text utan formatering."""
                temperature = 0.4
            
            # 4. Stream LLM response with fallback
            # Set num_predict based on mode: longer for ASSIST/EVIDENCE, shorter for CHAT
            num_predict = 1024 if mode != ResponseMode.CHAT else 512
            full_answer = ""
            async for chunk in stream_ollama_response(system_prompt, user_prompt, PRIMARY_MODEL, temperature, num_predict):
                yield chunk
                
                # Collect full answer for Jail Warden
                try:
                    chunk_data = json.loads(chunk.replace("data: ", "").strip())
                    if chunk_data.get("type") == "token":
                        full_answer += chunk_data.get("content", "")
                except:
                    pass
            
            # 5. Apply Jail Warden corrections (post-processing)
            corrected_answer, corrections = apply_jail_warden(full_answer)
            
            if corrections:
                # Send correction event
                yield f"data: {json.dumps({'type': 'corrections', 'corrections': corrections, 'corrected_text': corrected_answer})}\n\n"
            
            # Final stats
            total_time = int((time.time() - start_time) * 1000)
            yield f"data: {json.dumps({'type': 'complete', 'total_time_ms': total_time})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming agent query failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
