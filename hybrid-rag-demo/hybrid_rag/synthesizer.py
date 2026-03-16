import anthropic

_SYNTHESIS_SYSTEM = (
    "You are an expert analyst answering questions from retrieved knowledge. "
    "Use ONLY the provided context. Be concise (3-5 sentences). "
    "If graph facts and text passages conflict, trust the graph facts."
)


def synthesize_answer(
    client: anthropic.Anthropic,
    query: str,
    route: str,
    vector_results: list[dict],
    graph_results: list[dict],
) -> str:
    sections = [f"Question: {query}\nRoute used: {route.upper()}\n"]

    if graph_results:
        lines = [f"  {t['triple'][0].title()} --[{t['triple'][1]}]--> {t['triple'][2].title()}"
                 for t in graph_results]
        sections.append("--- Knowledge Graph Facts ---\n" + "\n".join(lines))

    if vector_results:
        passages = [f"[{i+1}] {r['text']}" for i, r in enumerate(vector_results)]
        sections.append("--- Relevant Text Passages ---\n" + "\n\n".join(passages))

    prompt = "\n\n".join(sections)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=_SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
