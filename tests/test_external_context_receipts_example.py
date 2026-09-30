"""Proof tests for the external-context receipt example.

This is deliberately an example-level experiment, not a new ActiveGraph
contract. It checks whether the existing custom-event surface is sufficient
before proposing any runtime change.
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path


EXAMPLE = Path(__file__).parent.parent / "examples" / "external_context_receipts.py"
MODULE = runpy.run_path(str(EXAMPLE))

canonical_sha256 = MODULE["canonical_sha256"]
demo = MODULE["demo"]


def test_canonical_digest_is_key_order_independent():
    left = {"query": "alpha", "filters": {"b": 2, "a": 1}}
    right = {"filters": {"a": 1, "b": 2}, "query": "alpha"}
    assert canonical_sha256(left) == canonical_sha256(right)


def test_receipt_precedes_derived_mutation_and_contains_no_retrieved_content():
    graph = demo()
    events = graph.events

    assert [event.type for event in events] == [
        "external_context.read",
        "object.created",
    ]

    receipt = events[0].payload
    assert receipt["provider"] == "example-memory"
    assert receipt["resource"] == "memory-index:v1"
    assert receipt["count"] == 2
    assert len(receipt["request_sha256"]) == 64
    assert len(receipt["results_sha256"]) == 64

    serialized = json.dumps(receipt, sort_keys=True)
    assert "private fixture text" not in serialized
    assert "another private fixture" not in serialized
    assert "what did we decide" not in serialized


def test_same_external_read_produces_same_receipt_digest():
    first = demo().events[0].payload
    second = demo().events[0].payload
    assert first["request_sha256"] == second["request_sha256"]
    assert first["results_sha256"] == second["results_sha256"]
