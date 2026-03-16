#!/usr/bin/env python3
"""
Hybrid RAG Demo
===============
Demonstrates how routing queries to the right retrieval path
(semantic vector search, relational graph traversal, or both)
produces better answers than a single-strategy approach.

Requirements:
    pip install -r requirements.txt

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python demo.py
"""
import os
import sys
import anthropic

from hybrid_rag.corpus import DOCUMENTS
from hybrid_rag.ingest import build_indexes
from hybrid_rag.router import route_query
from hybrid_rag.retrieval import vector_search, graph_search
from hybrid_rag.synthesizer import synthesize_answer

DEMO_QUERIES = [
    # Semantic: single-chunk factual lookup, graph traversal adds nothing
    ("semantic",   "What products does Apple make?"),
    ("semantic",   "Why did Facebook change its name to Meta?"),
    # Relational: multi-hop entity traversal, a single text chunk won't suffice
    ("relational", "Which companies has Microsoft acquired?"),
    ("relational", "Who is the CEO of the company that Elon Musk acquired?"),
    # Hybrid: needs both factual context AND relationship traversal
    ("hybrid",     "How has Meta grown its user base through acquisitions?"),
    ("hybrid",     "What AI and developer tools does the company that acquired GitHub offer?"),
]

SEP = "=" * 62


def run_demo() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)

    print(SEP)
    print("HYBRID RAG DEMO  —  Building indexes")
    print(SEP)
    vectorizer, matrix, chunk_ids, graph, chunks = build_indexes(client, DOCUMENTS)
    print(
        f"\nReady: {len(chunks)} chunks | "
        f"{graph.number_of_nodes()} graph nodes | "
        f"{graph.number_of_edges()} graph edges\n"
    )

    for expected_route, query in DEMO_QUERIES:
        print(SEP)
        print(f"QUERY  [{expected_route.upper()} expected]")
        print(f"  {query}")
        print("-" * 62)

        route = route_query(client, query)
        match = "✓" if route == expected_route else "✗"
        print(f"Router decision: {route.upper()}  {match}")

        vec_results, graph_results = [], []

        if route in ("semantic", "hybrid"):
            vec_results = vector_search(query, vectorizer, matrix, chunk_ids, chunks)
            top_score = vec_results[0]["score"] if vec_results else 0.0
            print(f"Vector retrieved: {len(vec_results)} chunks  (top score: {top_score:.3f})")
        else:
            print("Vector retrieved: — (skipped by router)")

        if route in ("relational", "hybrid"):
            graph_results = graph_search(query, graph, chunks, client)
            print(f"Graph  retrieved: {len(graph_results)} triples")
        else:
            print("Graph  retrieved: — (skipped by router)")

        answer = synthesize_answer(client, query, route, vec_results, graph_results)
        print(f"\nANSWER:\n{answer}\n")

    print(SEP)
    print("Demo complete.")
    print(SEP)


if __name__ == "__main__":
    run_demo()
