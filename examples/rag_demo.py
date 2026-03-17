"""End-to-end RAG system demo.

Demonstrates the full pipeline:
1. Ingest 5 documents about RAG and retrieval
2. Run 6 queries covering different query types
3. Print answers with citations
4. Run offline evaluation

Works entirely in memory — no external services required.

Usage:
    python examples/rag_demo.py
"""

from __future__ import annotations

import logging
import sys
import os

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

# ------------------------------------------------------------------
# 1. Build the RAG stack (all in-memory, no external services)
# ------------------------------------------------------------------

from rag_system.retrieval.hybrid import HybridRetriever
from rag_system.ingestion.embedder import MockEmbedder
from rag_system.ingestion.pipeline import IngestionPipeline
from rag_system.reranking.base import MockReranker
from rag_system.storage.document_store import InMemoryDocumentStore
from rag_system.storage.index_store import InMemoryIndexStore
from rag_system.agent.graph import build_graph
from rag_system.agent.state import initial_state
from rag_system.models import IngestRequest
from rag_system.eval.harness import EvalHarness
from rag_system.eval.datasets import load_dataset
from rag_system.models import EvalRequest

retriever = HybridRetriever()
embedder = MockEmbedder()
reranker = MockReranker()
doc_store = InMemoryDocumentStore()
idx_store = InMemoryIndexStore()

pipeline = IngestionPipeline(
    retriever=retriever,
    document_store=doc_store,
    index_store=idx_store,
    embedder=embedder,
)

graph = build_graph(
    retriever=retriever,
    reranker=reranker,
    embedder=embedder,
    llm_client=None,  # extractive mode (no API key needed)
    document_store=doc_store,
)

# ------------------------------------------------------------------
# 2. Ingest documents
# ------------------------------------------------------------------

DOCUMENTS = [
    {
        "doc_id": "doc_rrf",
        "title": "Reciprocal Rank Fusion",
        "text": """
Reciprocal Rank Fusion (RRF) is a rank aggregation method used in hybrid search systems.
The RRF formula is: score(d) = sum_i( 1 / (k + rank_i(d)) )
where k is typically set to 60 (the default in Elasticsearch and OpenSearch).

RRF is robust because it does not depend on the raw score values of individual
retrieval systems — only their rank order. This makes it safe to combine lexical
(BM25) and semantic (dense vector) retrieval results without score normalization.

Elastic explicitly recommends RRF as the default hybrid fusion method.
Unlike linear score combination, RRF does not require tuning normalization parameters.
""",
    },
    {
        "doc_id": "doc_bm25",
        "title": "BM25 Lexical Retrieval",
        "text": """
BM25 (Best Match 25) is a probabilistic ranking function used for lexical (keyword) search.
It is an extension of the TF-IDF model with two saturation parameters: k1 and b.

BM25 scores documents based on:
- Term frequency (TF): how often the query term appears in the document
- Inverse document frequency (IDF): how rare the term is across all documents
- Document length normalization: penalizes very long documents

BM25 works best for keyword-heavy queries, exact term matches, and ID lookups.
It struggles with semantic paraphrase queries where the user does not use the exact words.

The standard formula: BM25(D, Q) = sum_i IDF(q_i) * (f(q_i, D) * (k1+1)) / (f(q_i, D) + k1*(1-b+b*|D|/avgdl))
""",
    },
    {
        "doc_id": "doc_dense",
        "title": "Dense Vector Retrieval",
        "text": """
Dense vector retrieval (semantic search) uses neural embedding models to convert text
into high-dimensional float vectors, then finds similar documents using approximate
nearest neighbor (ANN) search.

Key properties:
- Embeddings capture semantic meaning, not just token overlap
- Works well for paraphrase queries and conceptual questions
- Requires an embedding model (e.g., text-embedding-3-small from OpenAI)
- Uses cosine similarity or dot product for scoring

Dense retrieval is complementary to BM25: semantic search finds relevant documents
even when they do not share keywords with the query, while BM25 excels at exact matches.

Common embedding dimensions: 768 (BERT), 1536 (OpenAI ada-002), 3072 (text-embedding-3-large).
""",
    },
    {
        "doc_id": "doc_hybrid",
        "title": "Hybrid Search Architecture",
        "text": """
Hybrid search combines multiple retrieval signals to improve recall and precision.
The standard architecture uses:
1. BM25 (lexical): retrieve top-K by keyword matching
2. Dense vector (semantic): retrieve top-K by embedding similarity
3. Fusion: combine both ranked lists into a single ranking

Hybrid search outperforms either method alone because they solve complementary failure modes:
- BM25 fails on paraphrase queries (different words, same meaning)
- Dense retrieval fails on rare terms, IDs, and exact keyword queries

The recommended fusion method in production is Reciprocal Rank Fusion (RRF),
which is robust to score scale differences between retrieval systems.

After hybrid retrieval, apply a cross-encoder reranker to re-score the top N candidates
based on full query-document interaction. This improves precision significantly.
""",
    },
    {
        "doc_id": "doc_langgraph",
        "title": "LangGraph for Agent Orchestration",
        "text": """
LangGraph is a framework for building stateful, multi-step agent workflows using a
directed graph of nodes and edges.

Key concepts:
- State: a typed dictionary passed between all nodes
- Nodes: Python functions that receive state and return state updates
- Edges: connections between nodes (can be conditional)
- Conditional edges: dynamic routing based on state values

LangGraph supports:
- Persistence: save and resume workflow state
- Streaming: stream node outputs in real time
- Human-in-the-loop: pause workflow for human input
- Debugging: inspect state at each node via LangSmith

For RAG systems, LangGraph enables:
- Bounded retrieval loops with retry budgets
- Evidence sufficiency checks before answer generation
- Query rewriting on retry
- Full tracing of every retrieval and generation step
""",
    },
]

print("=" * 60)
print("AGENTIC RAG SYSTEM DEMO")
print("=" * 60)
print(f"\nIngesting {len(DOCUMENTS)} documents...")

for doc in DOCUMENTS:
    resp = pipeline.ingest(IngestRequest(
        text=doc["text"].strip(),
        doc_id=doc["doc_id"],
        tenant_id="demo",
        title=doc["title"],
    ))
    print(f"  ✓ {doc['title']} → {resp.chunks_created} chunks")

# ------------------------------------------------------------------
# 3. Run queries
# ------------------------------------------------------------------

QUERIES = [
    ("semantic", "How does Reciprocal Rank Fusion work?"),
    ("semantic", "What are the advantages of hybrid search over BM25 alone?"),
    ("semantic", "Explain dense vector retrieval and when to use it"),
    ("keyword", "What is the BM25 formula?"),
    ("temporal", "What are the latest recommendations for hybrid fusion?"),
    ("multi_hop", "Compare BM25 versus dense retrieval and explain which is better"),
]

print(f"\n{'=' * 60}")
print("RUNNING QUERIES")
print("=" * 60)

for query_type, query in QUERIES:
    print(f"\n[{query_type.upper()}] {query}")
    print("-" * 50)

    state = initial_state(
        query=query,
        tenant_id="demo",
        max_steps=2,
    )
    result = graph.invoke(state)

    print(f"Answer: {result['validated_answer'][:300]}...")
    print(f"Citations: {len(result.get('citations', []))} chunks")
    print(f"Evidence sufficient: {result.get('evidence_sufficient', False)}")
    print(f"Retry loop used: {result.get('used_retry_loop', False)}")
    latency = result.get("latency_counters", {}).get("total_ms", 0)
    print(f"Latency: {latency:.1f}ms")

    if result.get("citations"):
        print("Sources:")
        for c in result["citations"][:3]:
            print(f"  - [{c.chunk_id[:8]}...] {c.section_title or c.doc_id}")

# ------------------------------------------------------------------
# 4. Offline evaluation
# ------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("OFFLINE EVALUATION")
print("=" * 60)

# Need to also ingest eval docs
for doc in DOCUMENTS:
    pipeline.ingest(IngestRequest(
        text=doc["text"].strip(),
        doc_id=f"eval_{doc['doc_id']}",
        tenant_id="eval",
        title=doc["title"],
    ))

harness = EvalHarness(graph=graph)
eval_result = harness.run(EvalRequest(
    dataset_name="default",
    tenant_id="eval",
))

print(f"Dataset: {eval_result.dataset_name} ({eval_result.num_queries} queries)")
print(f"nDCG@10:            {eval_result.ndcg_at_10:.3f}")
print(f"Citation Precision: {eval_result.citation_precision:.3f}")
print(f"Faithfulness:       {eval_result.faithfulness:.3f}")
print(f"Avg Latency:        {eval_result.avg_latency_ms:.1f}ms")
print(f"Retry Loop Rate:    {eval_result.loop_rate:.1%}")

print("\n" + "=" * 60)
print("DEMO COMPLETE")
print("=" * 60)
print("\nTo start the API server:")
print("  pip install -r requirements_rag.txt")
print("  uvicorn rag_system.api.main:app --reload")
print("\nTo run tests:")
print("  pytest tests/rag_system/ -v")
