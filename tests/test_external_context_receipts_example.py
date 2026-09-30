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


def test_receipt_is_causally_tied_to_behavior_and_precedes_derived_mutation():
    graph = demo()
    events = graph.events

    goal = next(event for event in events if event.type == "goal.created")
    receipt = next(event for event in events if event.type == "external_context.read")
    created = next(event for event in events if event.type == "object.created")

    assert events.index(receipt) < events.index(created)
    assert receipt.actor == "external-context-example"
    assert receipt.caused_by == goal.id
    assert created.actor == receipt.actor
    assert created.caused_by == receipt.caused_by

    payload = receipt.payload
    assert payload["provider"] == "example-memory"
    assert payload["resource"] == "memory-index:v1"
    assert payload["count"] == 2
    assert len(payload["request_sha256"]) == 64
    assert len(payload["results_sha256"]) == 64

    serialized = json.dumps(payload, sort_keys=True)
    assert "private fixture text" not in serialized
    assert "another private fixture" not in serialized
    assert "what did we decide" not in serialized


def test_same_external_read_produces_same_receipt_digest():
    first = next(
        event for event in demo().events if event.type == "external_context.read"
    ).payload
    second = next(
        event for event in demo().events if event.type == "external_context.read"
    ).payload
    assert first["request_sha256"] == second["request_sha256"]
    assert first["results_sha256"] == second["results_sha256"]
