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


def _reachable(graph: dict, node: str, reverse: bool = False) -> set:
    """Return the non-empty transitive closure from *node*.

    With ``reverse=True`` this follows edges towards upstream fields.  The
    result is a set, so converging paths and repeated propagation never produce
    duplicate fields.
    """
    adjacency = _adjacency(graph, reverse=reverse)
    reached: set = set()
    pending = list(adjacency.get(node, ()))

    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(adjacency.get(current, ()))

    return reached


def add_edge(graph: dict, src: str, dst: str) -> dict:
    """Add a field-level edge from *src* to *dst* and return the graph.

    Re-adding an existing edge is a no-op.  Direct self-dependencies are
    rejected by leaving the edge out rather than appending it.
    """
    graph = _ensure_graph(graph)
    if src == dst:
        return graph

    edge = (src, dst)
    if edge not in graph["edges"]:
        graph["edges"].append(edge)
    graph["nodes"].add(src)
    graph["nodes"].add(dst)
    return graph


def upstream_of(graph: dict, node: str) -> set:
    """Return every field that reaches *node* through one or more edges."""
    return _reachable(graph, node, reverse=True)


def downstream_of(graph: dict, node: str) -> set:
    """Return every field reachable from *node* through one or more edges."""
    return _reachable(graph, node, reverse=False)


def detect_cycle(graph: dict) -> list:
    """Return one cycle as a closed path, or an empty list when acyclic.

    The returned path repeats its first field as its last element.  The graph
    is not modified.
    """
    adjacency = _adjacency(graph)
    nodes = sorted(_all_nodes(graph))
    unseen = 0
    on_stack = 1
    finished = 2
    state = {node: unseen for node in nodes}

    for start in nodes:
        if state[start] != unseen:
            continue

        state[start] = on_stack
        path = [start]
        positions = {start: 0}
        # Each entry is [node, next neighbour index].
        stack: list[list[Any]] = [[start, 0]]

        while stack:
            current, neighbour_index = stack[-1]
            neighbours = adjacency.get(current, [])

            if neighbour_index >= len(neighbours):
                state[current] = finished
                stack.pop()
                positions.pop(current, None)
                if path and path[-1] == current:
                    path.pop()
                continue

            neighbour = neighbours[neighbour_index]
            stack[-1][1] = neighbour_index + 1
            neighbour_state = state.get(neighbour, unseen)

            if neighbour_state == on_stack:
                cycle_start = positions[neighbour]
                return path[cycle_start:] + [neighbour]

            if neighbour_state == unseen:
                state[neighbour] = on_stack
                positions[neighbour] = len(path)
                path.append(neighbour)
                stack.append([neighbour, 0])

    return []


def propagate_delete(graph: dict, node: str) -> set:
    """Return all downstream fields affected by deleting *node*."""
    return downstream_of(graph, node)


def merge_graphs(a: dict, b: dict) -> dict:
    """Merge two lineage graphs into a new graph.

    Nodes and edges are unioned.  Edges from *a* precede edges from *b*, and
    duplicate edges are included only once.
    """
    merged = {
        "nodes": set(a.get("nodes", set())) | set(b.get("nodes", set())),
        "edges": [],
    }
    seen_edges: set = set()
    for graph in (a, b):
        for edge in graph.get("edges", []):
            if edge not in seen_edges:
                seen_edges.add(edge)
                merged["edges"].append(edge)
    return merged


def validate_graph(graph: dict) -> list:
    """Return human-readable problems found in *graph*.

    An empty list means that the graph has no duplicate edges, no self loops,
    and no edge endpoint missing from the declared node set.
    """
    issues: list = []
    edges = graph.get("edges", [])
    nodes = graph.get("nodes", set())

    seen: set = set()
    for source, target in edges:
        edge = (source, target)
        if edge in seen:
            issues.append(f"duplicate edge: {source}->{target}")
        seen.add(edge)

    for source, target in edges:
        if source == target:
            issues.append(f"self loop: {source}->{target}")

    dangling_nodes: set = set()
    for source, target in edges:
        if source not in nodes:
            dangling_nodes.add(source)
        if target not in nodes:
            dangling_nodes.add(target)
    for node in sorted(dangling_nodes):
        issues.append(f"dangling node: {node}")

    return issues


def lineage_batch(graphs: dict) -> dict:
    """Build one lineage graph for each named input graph.

    *graphs* maps a name to a graph description.  The result maps the same
    names to freshly built graphs that can be queried independently.
    """
    built: dict = {}
    for name, graph in graphs.items():
        built[name] = {
            "nodes": _all_nodes(graph),
            "edges": list(graph.get("edges", [])),
        }
    return built
