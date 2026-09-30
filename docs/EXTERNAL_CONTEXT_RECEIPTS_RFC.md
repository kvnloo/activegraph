# Downstream RFC sketch: external-context receipts

Status: fork-only design note backed by `examples/external_context_receipts.py`.
This is not an ActiveGraph contract amendment.

## User problem

A behavior can make a decision using information that does not live in the
ActiveGraph projection: a memory database, search index, file service, another
agent harness, or a remote retrieval API.

ActiveGraph can already show the mutation that followed and, with
`trace_context_reads=True`, which in-graph objects the behavior read. The
external evidence can remain invisible in the trace even when it materially
shaped the decision.

The goal is auditability of that dependency without turning ActiveGraph into a
memory system or copying sensitive retrieved content into the event log.

## Ownership hypothesis

**External host/integration first, not runtime law.**

The runtime already permits arbitrary custom events and BehaviorGraph stamps
those events with the behavior actor, triggering event, and frame. The
downstream experiment therefore emits an app-level `external_context.read`
event before work derived from the retrieval.

Core should absorb a new primitive only if the host-level pattern cannot meet
replay/audit requirements consistently across multiple integrations.

## Invariant at risk

The event log should be able to answer enough of "what caused this result?" to
support audit and comparison.

For external context, the minimum useful evidence is:

- which integration/provider was consulted;
- an opaque identity for the external resource/index;
- a deterministic fingerprint of the request;
- a deterministic fingerprint of the returned result set;
- result count;
- causal linkage to the behavior execution that consumed it.

The event log does **not** need to own the retrieved documents themselves.

## Current proof

The fork experiment uses only existing public behavior/event primitives.

Within one behavior execution it:

1. constructs a deterministic request;
2. simulates retrieval from an external memory index;
3. emits `external_context.read`;
4. creates a graph object derived from that context.

Tests check that:

- canonical request/result hashing is deterministic;
- the receipt is emitted before the derived mutation;
- receipt and mutation share actor + triggering-event causality;
- request text and retrieved fixture content are absent from the receipt.

This is evidence that the first slice may need no core API at all.

## Candidate receipt shape

Illustrative application-level payload:

```json
{
  "provider": "memory-service",
  "resource": "memory-index:v7",
  "request_sha256": "...",
  "results_sha256": "...",
  "count": 12
}
```

Provider adapters may need extra non-sensitive metadata, but a generic core
schema should not be assumed from one integration.

## Replay semantics

The proposed receipt is historical evidence, not an instruction to re-run the
retrieval.

Normal replay should reproduce the accepted event stream without contacting the
external provider. Strict execution replay is a separate question: if a
behavior actively re-runs retrieval, a host could compare the new fingerprint
to the recorded receipt and decide whether drift is acceptable.

That comparison policy belongs outside core until concrete use cases establish
otherwise.

## Privacy boundary

A digest is not encryption.

- raw queries/results should stay out of the event payload by default;
- resource names should be opaque when names themselves are sensitive;
- low-entropy secrets remain guessable from ordinary hashes;
- keyed fingerprints or an external evidence vault may be appropriate in a
  privacy-sensitive host.

ActiveGraph should not imply that a SHA-256 field makes private data safe.

## Failure model

First slice:

- successful retrieval emits `external_context.read`;
- provider failure remains the integration's existing failure path;
- no runtime exception taxonomy changes;
- no behavior is automatically subscribed to receipt events.

A later experiment can test whether an application-level
`external_context.failed` event is useful. That should not be standardized
without real failure-routing evidence.

## Alternatives

### Extend framework `context.read`

Pros: one query surface for all reads.

Cons: today's contract intentionally scopes `context.read` to concrete
in-graph object reads. Folding remote retrieval into it would widen a locked
runtime meaning and force provider semantics into core.

### EventSink-only receipt

Pros: zero new events in the authoritative log.

Cons: the dependency would no longer be part of the canonical replay/fork
history, which defeats the strongest audit use case.

### Copy retrieved content into graph objects

Pros: native provenance from then on.

Cons: conflates memory ownership with runtime state, duplicates potentially
sensitive data, and makes retrieval storage policy a framework concern.

## Promotion gates

Before proposing anything upstream beyond an issue/discussion:

1. demonstrate the pattern with at least two unlike sources (for example FTS
   memory + file/search retrieval);
2. prove receipt visibility through trace export and an EventSink;
3. prove fork/replay preserves historical receipts without re-querying;
4. inject provider failure and stale-result cases;
5. measure event-volume overhead;
6. identify one concrete requirement that custom app events cannot satisfy.

If gate 6 never appears, the correct upstream result may simply be
documentation showing the existing extension point.

## What would disprove this ownership hypothesis

Move the boundary toward runtime law only if multiple integrations require the
same semantics and those semantics cannot be expressed reliably through custom
events while preserving ActiveGraph's replay, causal ordering, and failure
contracts.
