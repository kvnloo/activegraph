"""Lifecycle evidence for the downstream external-context receipt experiment."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

from click.testing import CliRunner

from activegraph import Graph, Runtime
from activegraph.behaviors.base import Behavior
from activegraph.cli.main import cli
from activegraph.sinks.testing import RecordingSink


EXAMPLE = Path(__file__).parent.parent / "examples" / "external_context_receipts.py"
MODULE = runpy.run_path(str(EXAMPLE))
emit_external_context_receipt = MODULE["emit_external_context_receipt"]


def _behavior(provider_calls: list[str]) -> Behavior:
    def researcher(event, graph, ctx):
        provider_calls.append(event.id)
        emit_external_context_receipt(
            graph,
            provider="fixture-memory",
            resource="memory-index:test",
            request={"query": "replay integrity", "limit": 2},
            results=[
                {"id": "memory:1", "text": "private one"},
                {"id": "memory:2", "text": "private two"},
            ],
        )
        graph.add_object("claim", {"text": "derived from external context"})

    return Behavior(
        name="receipt-researcher",
        fn=researcher,
        on=["goal.created"],
    )


def _receipt(events):
    return next(event for event in events if event.type == "external_context.read")


def test_receipt_survives_save_load_without_requerying_provider(tmp_path):
    db = str(tmp_path / "receipt.db")
    provider_calls: list[str] = []

    runtime = Runtime(
        Graph(),
        behaviors=[_behavior(provider_calls)],
        persist_to=db,
    )
    runtime.run_goal("use external memory")
    runtime.save_state()

    original = _receipt(runtime.graph.events)
    assert provider_calls == [original.caused_by]

    # Loading materializes accepted history; it must not contact the external
    # provider just to reconstruct that history.
    loaded = Runtime.load(db, run_id=runtime.run_id, behaviors=[])
    replayed = _receipt(loaded.graph.events)

    assert provider_calls == [original.caused_by]
    assert replayed.to_dict() == original.to_dict()
    assert replayed.id in loaded.graph.replayed_ids


def test_receipt_is_shared_history_across_fork_and_structural_diff(tmp_path):
    db = str(tmp_path / "fork.db")
    runtime = Runtime(
        Graph(),
        behaviors=[_behavior([])],
        persist_to=db,
    )
    runtime.run_goal("use external memory")
    runtime.save_state()

    events = runtime.graph.events
    receipt = _receipt(events)
    claim_event = next(event for event in events if event.type == "object.created")

    fork = runtime.fork(at_event=claim_event.id, label="receipt-fork")
    fork.graph.add_object("note", {"text": "fork-only"})
    fork.save_state()

    diff = runtime.diff(fork)
    assert any(
        event.id == receipt.id and event.type == receipt.type
        for event in diff.shared_events
    )
    assert not any(
        event.type == "external_context.read"
        for event in diff.fork_only_events
    )
    assert any(
        obj.in_parent is None and obj.in_fork is not None
        for obj in diff.divergent_objects
    )


def test_receipt_exports_to_jsonl_without_raw_external_content(tmp_path):
    db = str(tmp_path / "export.db")
    runtime = Runtime(
        Graph(),
        behaviors=[_behavior([])],
        persist_to=db,
    )
    runtime.run_goal("use external memory")
    runtime.save_state()

    out = tmp_path / "trace.jsonl"
    url = f"sqlite:///{db}"
    result = CliRunner().invoke(
        cli,
        [
            "export-trace",
            url,
            "--run-id",
            runtime.run_id,
            "--format",
            "jsonl",
            "--output",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    receipt = next(row for row in rows if row["type"] == "external_context.read")
    serialized = json.dumps(receipt, sort_keys=True)
    assert receipt["payload"]["count"] == 2
    assert "private one" not in serialized
    assert "private two" not in serialized
    assert "replay integrity" not in serialized


def test_receipt_is_visible_to_event_sink_in_log_order():
    sink = RecordingSink()
    runtime = Runtime(
        Graph(),
        behaviors=[_behavior([])],
        sinks=[sink],
    )
    try:
        runtime.run_goal("use external memory")
        assert runtime.flush_sinks(timeout=2.0)

        delivered = list(sink.events)
        receipt_index = next(
            i for i, event in enumerate(delivered)
            if event.type == "external_context.read"
        )
        claim_index = next(
            i for i, event in enumerate(delivered)
            if event.type == "object.created"
        )
        assert receipt_index < claim_index
        assert delivered[receipt_index].actor == "receipt-researcher"
    finally:
        runtime.close_sinks(timeout=2.0)


def test_same_request_with_changed_external_results_has_different_fingerprint():
    def run(results):
        graph = Graph()

        def researcher(event, behavior_graph, ctx):
            emit_external_context_receipt(
                behavior_graph,
                provider="fixture-memory",
                resource="memory-index:test",
                request={"query": "same query", "limit": 2},
                results=results,
            )

        Runtime(
            graph,
            behaviors=[
                Behavior(
                    name="drift-check",
                    fn=researcher,
                    on=["goal.created"],
                )
            ],
        ).run_goal("check external drift")
        return _receipt(graph.events).payload

    first = run([{"id": "memory:1", "version": 1}])
    changed = run([{"id": "memory:1", "version": 2}])

    assert first["request_sha256"] == changed["request_sha256"]
    assert first["results_sha256"] != changed["results_sha256"]


def test_provider_failure_emits_behavior_failure_without_false_success_receipt():
    graph = Graph()

    def researcher(event, behavior_graph, ctx):
        raise RuntimeError("fixture provider unavailable")

    Runtime(
        graph,
        behaviors=[
            Behavior(
                name="failing-provider",
                fn=researcher,
                on=["goal.created"],
            )
        ],
    ).run_goal("exercise provider failure")

    types = [event.type for event in graph.events]
    assert "behavior.failed" in types
    assert "external_context.read" not in types
    assert "object.created" not in types

    failure = next(event for event in graph.events if event.type == "behavior.failed")
    assert failure.payload["behavior"] == "failing-provider"
    assert failure.payload["exception_type"] == "RuntimeError"
