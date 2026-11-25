"""Public contract tests for the field-level lineage package."""

from lineage import (
    add_edge,
    detect_cycle,
    downstream_of,
    lineage_batch,
    propagate_delete,
    upstream_of,
)


def test_downstream_lookup_after_add_edge():
    graph = {}
    add_edge(graph, "raw.orders", "clean.orders")
    add_edge(graph, "clean.orders", "mart.orders")

    assert downstream_of(graph, "raw.orders") == {
        "clean.orders",
        "mart.orders",
    }


def test_upstream_lookup_after_add_edge():
    graph = {}
    add_edge(graph, "raw.orders", "clean.orders")

    assert upstream_of(graph, "clean.orders") == {"raw.orders"}


def test_delete_propagation_reaches_mart():
    graph = {}
    add_edge(graph, "raw.orders", "clean.orders")
    add_edge(graph, "clean.orders", "mart.orders")

    assert propagate_delete(graph, "raw.orders") == {
        "clean.orders",
        "mart.orders",
    }


def test_cycle_is_detected():
    graph = {}
    add_edge(graph, "orders.a", "orders.b")
    add_edge(graph, "orders.b", "orders.c")
    add_edge(graph, "orders.c", "orders.a")

    cycle = detect_cycle(graph)

    assert cycle
    assert cycle[0] == cycle[-1]


def test_batch_graphs_are_independent():
    first = {}
    add_edge(first, "first.raw", "first.clean")
    second = {}
    add_edge(second, "second.raw", "second.clean")

    built = lineage_batch({"first": first, "second": second})

    assert built["first"]["edges"] == [("first.raw", "first.clean")]
    assert built["second"]["edges"] == [("second.raw", "second.clean")]