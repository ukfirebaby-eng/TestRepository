import anthropic

_ROUTER_SYSTEM = """\
You are a query routing assistant for a hybrid knowledge retrieval system.
Classify the user query into exactly one category and respond with ONLY that
single word, lowercase, no punctuation.

Categories:
- semantic: The query asks for a description, explanation, or factual detail
  that can be answered from a single passage of text.
  Example: "What products does Apple make?" or "Why did Facebook rename itself?"

- relational: The query requires traversing relationships between multiple
  entities — ownership chains, multi-hop connections, or comparing entities.
  Example: "Which companies did Microsoft acquire?" or "Who owns WhatsApp?"

- hybrid: The query needs BOTH relevant text passages AND entity relationship
  traversal to give a complete answer.
  Example: "How has Meta's acquisition strategy affected its product portfolio?"
"""


def route_query(client: anthropic.Anthropic, query: str) -> str:
    """Classify a query as 'semantic', 'relational', or 'hybrid'."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        system=_ROUTER_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    route = response.content[0].text.strip().lower()
    if route not in ("semantic", "relational", "hybrid"):
        route = "hybrid"
    return route
