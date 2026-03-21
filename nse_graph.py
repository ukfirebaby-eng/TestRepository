"""
nse_graph.py — Novel Genesis System: Narrative State Engine (NSE) graph.

Provides the graph node dataclasses and two public functions consumed by
both the pipeline and the Phase J.2 ML layer:

  reconstruct_nse_at_scene(initial_path, log_path, target_scene) -> NSEGraph
  deserialise_nse(graph_path) -> NSEGraph

Graph node types
----------------
  CharacterNode     — a character present in the story world
  InformationNode   — a piece of diegetic information (secret, fact, rumour)
  RelationshipNode  — a directed relationship between two characters
  EventNode         — a plot event (occurred or pending)
  NSEGraph          — the complete graph (four typed dicts)

Mutation log format (nse/mutation_log.jsonl)
--------------------------------------------
Each line is a JSON object:
  {
    "scene_num":     <int>,
    "mutation_type": <str>,   # see MUTATION_* constants below
    "payload":       <dict>   # type-specific data
  }

Supported mutation_type values:
  ADD_NODE            — add a character, information, relationship, or event node
  UPDATE_NODE         — update fields on an existing node
  REVEAL_INFORMATION  — mark an InformationNode as revealed (set revealed_at_scene)
  CONCEAL_INFORMATION — re-hide an InformationNode (set revealed_at_scene to None)
  SHIFT_RELATIONSHIP  — update tension_level / trust_level on a RelationshipNode
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Mutation type constants
# ---------------------------------------------------------------------------

MUTATION_ADD_NODE = "ADD_NODE"
MUTATION_UPDATE_NODE = "UPDATE_NODE"
MUTATION_REVEAL_INFORMATION = "REVEAL_INFORMATION"
MUTATION_CONCEAL_INFORMATION = "CONCEAL_INFORMATION"
MUTATION_SHIFT_RELATIONSHIP = "SHIFT_RELATIONSHIP"


# ---------------------------------------------------------------------------
# Node dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CharacterNode:
    """A character present in the story world."""
    id: str
    name: str
    role: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class InformationNode:
    """A piece of diegetic information.

    ``revealed_at_scene`` is ``None`` while the information is a secret and
    set to the scene number when it becomes known to the reader / characters.
    """
    id: str
    description: str
    holder_id: Optional[str] = None          # character who holds this info
    revealed_at_scene: Optional[int] = None  # None = still concealed


@dataclass
class RelationshipNode:
    """A directed relationship between two characters.

    Both ``tension_level`` and ``trust_level`` are normalised floats in
    the range [0.0, 1.0].
    """
    id: str
    source_id: str
    target_id: str
    tension_level: float = 0.0
    trust_level: float = 1.0
    relationship_type: str = "neutral"


@dataclass
class EventNode:
    """A plot event — either already occurred or pending."""
    id: str
    description: str
    occurred: bool = False
    occurred_at_scene: Optional[int] = None


@dataclass
class NSEGraph:
    """The complete Narrative State Engine graph.

    All four dicts are keyed by node ``id``.
    """
    characters: dict[str, CharacterNode] = field(default_factory=dict)
    information: dict[str, InformationNode] = field(default_factory=dict)
    relationships: dict[str, RelationshipNode] = field(default_factory=dict)
    events: dict[str, EventNode] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _nse_from_dict(data: dict[str, Any]) -> NSEGraph:
    """Deserialise an NSEGraph from a plain Python dict (parsed from JSON)."""
    graph = NSEGraph()

    for cid, cdata in data.get("characters", {}).items():
        graph.characters[cid] = CharacterNode(
            id=cid,
            name=cdata.get("name", cid),
            role=cdata.get("role", ""),
            attributes=cdata.get("attributes", {}),
        )

    for iid, idata in data.get("information", {}).items():
        graph.information[iid] = InformationNode(
            id=iid,
            description=idata.get("description", ""),
            holder_id=idata.get("holder_id"),
            revealed_at_scene=idata.get("revealed_at_scene"),
        )

    for rid, rdata in data.get("relationships", {}).items():
        graph.relationships[rid] = RelationshipNode(
            id=rid,
            source_id=rdata.get("source_id", ""),
            target_id=rdata.get("target_id", ""),
            tension_level=float(rdata.get("tension_level", 0.0)),
            trust_level=float(rdata.get("trust_level", 1.0)),
            relationship_type=rdata.get("relationship_type", "neutral"),
        )

    for eid, edata in data.get("events", {}).items():
        graph.events[eid] = EventNode(
            id=eid,
            description=edata.get("description", ""),
            occurred=bool(edata.get("occurred", False)),
            occurred_at_scene=edata.get("occurred_at_scene"),
        )

    return graph


def deserialise_nse(graph_path: Path) -> NSEGraph:
    """Load the live NSE graph snapshot from *graph_path* (nse_graph.json).

    Returns an empty ``NSEGraph`` if the file does not exist or is malformed.
    """
    graph_path = Path(graph_path)
    if not graph_path.exists():
        return NSEGraph()
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return _nse_from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return NSEGraph()


# ---------------------------------------------------------------------------
# Mutation application
# ---------------------------------------------------------------------------

def _apply_mutation(graph: NSEGraph, mutation: dict[str, Any]) -> None:
    """Apply a single mutation record to *graph* in-place."""
    mtype = mutation.get("mutation_type", "")
    payload: dict[str, Any] = mutation.get("payload", {})

    if mtype == MUTATION_ADD_NODE:
        node_type = payload.get("node_type", "")
        nid = payload.get("id", "")
        if not nid:
            return
        if node_type == "character":
            graph.characters[nid] = CharacterNode(
                id=nid,
                name=payload.get("name", nid),
                role=payload.get("role", ""),
                attributes=payload.get("attributes", {}),
            )
        elif node_type == "information":
            graph.information[nid] = InformationNode(
                id=nid,
                description=payload.get("description", ""),
                holder_id=payload.get("holder_id"),
                revealed_at_scene=payload.get("revealed_at_scene"),
            )
        elif node_type == "relationship":
            graph.relationships[nid] = RelationshipNode(
                id=nid,
                source_id=payload.get("source_id", ""),
                target_id=payload.get("target_id", ""),
                tension_level=float(payload.get("tension_level", 0.0)),
                trust_level=float(payload.get("trust_level", 1.0)),
                relationship_type=payload.get("relationship_type", "neutral"),
            )
        elif node_type == "event":
            graph.events[nid] = EventNode(
                id=nid,
                description=payload.get("description", ""),
                occurred=bool(payload.get("occurred", False)),
                occurred_at_scene=payload.get("occurred_at_scene"),
            )

    elif mtype == MUTATION_UPDATE_NODE:
        node_type = payload.get("node_type", "")
        nid = payload.get("id", "")
        updates: dict[str, Any] = payload.get("updates", {})
        if node_type == "character" and nid in graph.characters:
            node = graph.characters[nid]
            for k, v in updates.items():
                if hasattr(node, k):
                    setattr(node, k, v)
        elif node_type == "information" and nid in graph.information:
            node = graph.information[nid]
            for k, v in updates.items():
                if hasattr(node, k):
                    setattr(node, k, v)
        elif node_type == "relationship" and nid in graph.relationships:
            node = graph.relationships[nid]
            for k, v in updates.items():
                if hasattr(node, k):
                    setattr(node, k, v)
        elif node_type == "event" and nid in graph.events:
            node = graph.events[nid]
            for k, v in updates.items():
                if hasattr(node, k):
                    setattr(node, k, v)

    elif mtype == MUTATION_REVEAL_INFORMATION:
        nid = payload.get("id", "")
        scene = payload.get("scene_num")
        if nid in graph.information:
            graph.information[nid].revealed_at_scene = scene

    elif mtype == MUTATION_CONCEAL_INFORMATION:
        nid = payload.get("id", "")
        if nid in graph.information:
            graph.information[nid].revealed_at_scene = None

    elif mtype == MUTATION_SHIFT_RELATIONSHIP:
        nid = payload.get("id", "")
        if nid in graph.relationships:
            rel = graph.relationships[nid]
            if "tension_level" in payload:
                rel.tension_level = float(payload["tension_level"])
            if "trust_level" in payload:
                rel.trust_level = float(payload["trust_level"])


# ---------------------------------------------------------------------------
# Public reconstruction function
# ---------------------------------------------------------------------------

def reconstruct_nse_at_scene(
    initial_path: Path,
    log_path: Path,
    target_scene: int,
) -> NSEGraph:
    """Reconstruct the NSE graph state *after* scene ``target_scene`` ends.

    This means the returned graph is the state that exists **when prose
    generation for scene ``target_scene + 1`` begins** — i.e. the complexity
    visible to the LLM at that point.

    Parameters
    ----------
    initial_path:
        Path to the initial ``nse_graph.json`` snapshot (scene 0 / foundation
        state, before any prose has been generated).
    log_path:
        Path to ``nse/mutation_log.jsonl`` — one JSON mutation per line.
    target_scene:
        Replay mutations up to and including this scene number.
        Pass ``0`` to obtain the foundation graph (no mutations applied).

    Returns
    -------
    NSEGraph
        The reconstructed graph.  Returns an empty graph if both paths are
        missing (safe for scene 1 when the pipeline has just started).
    """
    initial_path = Path(initial_path)
    log_path = Path(log_path)

    # Load the initial (foundation) graph
    graph = deserialise_nse(initial_path)

    if target_scene == 0 or not log_path.exists():
        return graph

    # Replay mutations in order, up to target_scene (inclusive)
    try:
        with log_path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    mutation = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                scene_num = mutation.get("scene_num", 0)
                if scene_num <= target_scene:
                    _apply_mutation(graph, mutation)
    except OSError:
        pass

    return graph
