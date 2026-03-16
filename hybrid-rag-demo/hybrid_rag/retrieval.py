import json
import anthropic
import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_ENTITY_SYSTEM = (
    "You are a named entity extractor. "
    "Return ONLY a JSON array of entity names mentioned in the query. "
    "No explanation, no markdown."
)


def extract_query_entities(client: anthropic.Anthropic, query: str) -> list[str]:
    """Return entity names found in the query."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=128,
        system=_ENTITY_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    raw = response.content[0].text.strip()
    try:
        entities = json.loads(raw)
        if isinstance(entities, list):
            return [str(e).lower().strip() for e in entities]
    except json.JSONDecodeError:
        pass
    return []


def vector_search(
    query: str,
    vectorizer: TfidfVectorizer,
    matrix: np.ndarray,
    chunk_ids: list[str],
    chunks: list[dict],
    top_k: int = 3,
) -> list[dict]:
    """Return top_k chunks by TF-IDF cosine similarity."""
    query_vec = vectorizer.transform([query])
    scores = cosine_similarity(query_vec, matrix).flatten()
    top_indices = scores.argsort()[::-1][:top_k]
    chunk_map = {c["chunk_id"]: c["text"] for c in chunks}
    return [
        {"chunk_id": chunk_ids[i], "text": chunk_map[chunk_ids[i]], "score": float(scores[i])}
        for i in top_indices
        if scores[i] > 0
    ]


def graph_search(
    query: str,
    graph: nx.DiGraph,
    chunks: list[dict],
    client: anthropic.Anthropic,
    top_k: int = 8,
) -> list[dict]:
    """BFS from seed entities (depth=2, bidirectional) to retrieve graph triples."""
    seed_entities = extract_query_entities(client, query)

    # Find matching nodes (substring match, case-insensitive)
    seed_nodes = set()
    graph_nodes = list(graph.nodes())
    for seed in seed_entities:
        for node in graph_nodes:
            if seed in node or node in seed:
                seed_nodes.add(node)

    if not seed_nodes:
        return []

    triples = []
    seen = set()

    for seed in seed_nodes:
        # Outgoing edges (what did this entity do)
        for u, v in nx.bfs_edges(graph, seed, depth_limit=2):
            edge_data = graph.get_edge_data(u, v, {})
            triple = (u, edge_data.get("predicate", "related_to"), v)
            if triple not in seen:
                seen.add(triple)
                triples.append({"triple": triple, "chunk_id": edge_data.get("chunk_id", "")})

        # Incoming edges (what was done to this entity)
        reversed_graph = graph.reverse(copy=False)
        for u, v in nx.bfs_edges(reversed_graph, seed, depth_limit=2):
            # In reversed graph u->v means original v->u
            edge_data = graph.get_edge_data(v, u, {})
            triple = (v, edge_data.get("predicate", "related_to"), u)
            if triple not in seen:
                seen.add(triple)
                triples.append({"triple": triple, "chunk_id": edge_data.get("chunk_id", "")})

    return triples[:top_k]
