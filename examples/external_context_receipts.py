"""Prototype external-context receipts using ActiveGraph's existing event surface.

This intentionally adds no runtime API and reserves no framework namespace.
It demonstrates the smallest useful pattern for recording that a behavior
consulted context which lives outside the ActiveGraph projection (memory DB,
search index, file service, another harness, etc.).

The receipt stores stable digests and counts, not retrieved content. That is
useful for audit/replay comparison, but SHA-256 is not an encryption boundary:
use opaque resource identifiers and do not treat a digest as protection for
low-entropy secrets.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from activegraph import Graph


EVENT_TYPE = "external_context.read"


def canonical_sha256(value: Any) -> str:
    """Return a deterministic SHA-256 for JSON-compatible data."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def emit_external_context_receipt(
    graph: Graph,
    *,
    provider: str,
    resource: str,
    request: Any,
    results: list[Any],
):
    """Emit one content-free receipt before work derived from external context."""
    return graph.emit(
        EVENT_TYPE,
        {
            "provider": provider,
            "resource": resource,
            "request_sha256": canonical_sha256(request),
            "results_sha256": canonical_sha256(results),
            "count": len(results),
        },
    )


def demo() -> Graph:
    graph = Graph()

    request = {"query": "what did we decide about replay integrity?", "limit": 2}
    retrieved = [
        {
            "id": "memory:decision-17",
            "text": "private fixture text that must not enter the event payload",
            "score": 0.93,
        },
        {
            "id": "memory:decision-23",
            "text": "another private fixture",
            "score": 0.88,
        },
    ]

    emit_external_context_receipt(
        graph,
        provider="example-memory",
        resource="memory-index:v1",
        request=request,
        results=retrieved,
    )

    # A later event may be derived from that context. The receipt preceding it
    # makes the dependency visible without copying the retrieved content into
    # the ActiveGraph log.
    graph.add_object(
        "claim",
        {
            "text": "Replay integrity was an explicit prior decision.",
            "evidence": ["external-context-receipt"],
        },
    )
    return graph


if __name__ == "__main__":
    graph = demo()
    for event in graph.events:
        print(json.dumps(event.to_dict(), sort_keys=True))
