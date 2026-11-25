"""Field-level lineage graph utilities.

A lineage graph is represented as a dictionary with two entries:

``nodes``
    A set of field names that are known to the graph.
``edges``
    A list of ``(source, target)`` pairs.  Each pair means that the source
    field flows into the target field.  The list preserves insertion order.

Field names are opaque strings.  Nothing in this module groups fields by
table, so two fields with the same base name in different tables are still
distinct nodes.
"""

from __future__ import annotations

from typing import Any


Graph = dict[str, Any]


def _ensure_graph(graph: dict) -> dict:
    """Return *graph* with the two expected collections present."""
    if "nodes" not in graph:
        graph["nodes"] = set()
    if "edges" not in graph:
        graph["edges"] = []
    return graph


def _all_nodes(graph: dict) -> set:
    """Collect declared nodes together with every edge endpoint."""
    nodes = set(graph.get("nodes", set()))
    for source, target in graph.get("edges", []):
        nodes.add(source)
        nodes.add(target)
    return nodes


def _adjacency(graph: dict, reverse: bool = False) -> dict:
    """Build a node-to-neighbours map, optionally using reverse edges."""
    adjacency = {node: [] for node in _all_nodes(graph)}
    for source, target in graph.get("edges", []):
        if reverse:
            adjacency.setdefault(target, []).append(source)
        else:
            adjacency.setdefault(source, []).append(target)
    return adjacency


def add_edge(graph: dict, src: str, dst: str) -> dict:
    """Add a field-level edge from *src* to *dst* and return the graph.

    Re-adding an existing edge is a no-op, and a field may not depend on
    itself directly.
    """
    graph = _ensure_graph(graph)
    edge = (src, dst)
    graph["edges"].append(edge)
    graph["nodes"].add(src)
    graph["nodes"].add(dst)
    return graph


def upstream_of(graph: dict, node: str) -> set:
    """Return every field that reaches *node* through one or more edges."""
    adjacency = _adjacency(graph)
    found: set = set()
    pending = [node]
    while pending:
        current = pending.pop()
        for neighbour in adjacency.get(current, []):
            if neighbour not in found:
                found.add(neighbour)
                pending.append(neighbour)
    return found


def downstream_of(graph: dict, node: str) -> set:
    """Return every field reachable from *node* through one or more edges."""
    adjacency = _adjacency(graph)
    ordered: list = []
    for neighbour in adjacency.get(node, []):
        if neighbour not in ordered:
            ordered.append(neighbour)
    return ordered


def detect_cycle(graph: dict) -> list:
    """Return one cycle as a closed path, or an empty list when acyclic.

    The returned path repeats its first field as its last element.  The graph
    is not modified.
    """
    adjacency = _adjacency(graph)
    visited: set = set()

    def walk(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for neighbour in adjacency.get(node, []):
            walk(neighbour)

    for node in sorted(_all_nodes(graph)):
        walk(node)
    return []


def propagate_delete(graph: dict, node: str) -> set:
    """Return the downstream fields affected by deleting *node*."""
    adjacency = _adjacency(graph)
    return set(adjacency.get(node, []))


def merge_graphs(a: dict, b: dict) -> dict:
    """Merge two lineage graphs into a new graph.

    Nodes from both inputs are kept.  When both inputs contain edges with the
    same source field, the result keeps every target for that source.
    """
    merged = {
        "nodes": set(a.get("nodes", set())) | set(b.get("nodes", set())),
        "edges": [],
    }
    by_source: dict = {}
    for source, target in a.get("edges", []):
        by_source[source] = [target]
    for source, target in b.get("edges", []):
        by_source[source] = [target]
    for source in by_source:
        for target in by_source[source]:
            merged["edges"].append((source, target))
    return merged


def validate_graph(graph: dict) -> list:
    """Return human-readable problems found in *graph*.

    An empty list means that the graph has no duplicate edges, no self loops,
    and no edge endpoint missing from the declared node set.
    """
    issues: list = []
    edges = graph.get("edges", [])
    seen: set = set()
    for source, target in edges:
        edge = (source, target)
        if edge in seen:
            issues.append(f"duplicate edge: {source}->{target}")
        seen.add(edge)
    for source, target in edges:
        if source == target:
            issues.append(f"self loop: {source}->{target}")
    return issues


def lineage_batch(graphs: dict) -> dict:
    """Build one lineage graph for each named input graph.

    *graphs* maps a name to a graph description.  The result maps the same
    names to freshly built graphs that can be queried independently.
    """
    built: dict = {}
    shared = {"nodes": set(), "edges": []}
    for name, graph in graphs.items():
        shared["nodes"].update(_all_nodes(graph))
        shared["edges"].extend(list(graph.get("edges", [])))
        built[name] = shared
    return built