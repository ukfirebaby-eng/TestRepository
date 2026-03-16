import json
import anthropic
import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

_EXTRACTION_SYSTEM = (
    "You are an information extraction assistant. "
    "Return ONLY valid JSON with no explanation or markdown."
)

_EXTRACTION_USER = """\
Extract all named entities and relationships from the text below.

Return JSON in this exact format:
{{
  "entities": ["Entity1", "Entity2"],
  "relations": [
    ["subject", "predicate", "object"]
  ]
}}

Use short, consistent predicates: acquired, ceo_of, founded, subsidiary_of,
renamed_to, product_of, departed_from.

Text:
{text}"""


def chunk_documents(docs: list[str]) -> list[dict]:
    """Each document is a single chunk for this demo corpus."""
    return [{"chunk_id": f"doc_{i}", "doc_id": i, "text": doc.strip()} for i, doc in enumerate(docs)]


def extract_entities_and_relations(
    client: anthropic.Anthropic, chunks: list[dict]
) -> list[dict]:
    results = []
    for chunk in chunks:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": _EXTRACTION_USER.format(text=chunk["text"])}],
        )
        raw = response.content[0].text.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"entities": [], "relations": []}
        results.append({
            "chunk_id": chunk["chunk_id"],
            "entities": data.get("entities", []),
            "relations": data.get("relations", []),
        })
    return results


def build_tfidf_index(
    chunks: list[dict],
) -> tuple[TfidfVectorizer, np.ndarray, list[str]]:
    texts = [c["text"] for c in chunks]
    chunk_ids = [c["chunk_id"] for c in chunks]
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix, chunk_ids


def build_knowledge_graph(extractions: list[dict]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for ext in extractions:
        chunk_id = ext["chunk_id"]
        for entity in ext["entities"]:
            node = entity.lower().strip()
            if not graph.has_node(node):
                graph.add_node(node, label=entity)
        for relation in ext["relations"]:
            if len(relation) != 3:
                continue
            subj, pred, obj = relation
            s = subj.lower().strip()
            o = obj.lower().strip()
            if not graph.has_node(s):
                graph.add_node(s, label=subj)
            if not graph.has_node(o):
                graph.add_node(o, label=obj)
            graph.add_edge(s, o, predicate=pred.lower().strip(), chunk_id=chunk_id)
    return graph


def build_indexes(
    client: anthropic.Anthropic,
    docs: list[str],
) -> tuple[TfidfVectorizer, np.ndarray, list[str], nx.DiGraph, list[dict]]:
    print("  Chunking documents...")
    chunks = chunk_documents(docs)

    print(f"  Extracting entities from {len(chunks)} chunks via Claude...")
    extractions = extract_entities_and_relations(client, chunks)

    print("  Building TF-IDF index...")
    vectorizer, matrix, chunk_ids = build_tfidf_index(chunks)

    print("  Building knowledge graph...")
    graph = build_knowledge_graph(extractions)

    return vectorizer, matrix, chunk_ids, graph, chunks
