# Experiment Design

## Versioned Contracts

Every `ExperimentManifest` declares schema version, experiment kind, candidates, cases, separate metrics, hard constraints, trial/token/wall-clock budgets, retry limit, stopping conditions, validation plan, and promotion state. Every `ExperimentResult` reports baseline deltas, Pareto candidates, confidence, sample count, unknowns, and a promotion recommendation.

Metrics with different units remain separate. Compute composite loss only when the manifest explicitly supplies normalization and weights. Missing observations stay unknown and never receive an invented score.

## Shadow Defaults

- read-only sandbox and network disabled
- maximum concurrency `2`
- at most one retry per trial
- positive trial, token, and wall-clock limits are mandatory
- early stop on budget exhaustion, hard-constraint failure, or declared stopping rule
- winning candidates enter `Review`; they are never adopted automatically

## Core Fixtures

1. Rule, structured-LLM, and hybrid expert routing.
2. Technical instruction, role mission, artifact contract, and full-persona prompt ablation.
3. Self-evaluation, independent evaluator, and deterministic-plus-evaluator agreement.
4. Full log, free summary, and structured handoff packet.
5. Timeout, invalid schema, contradiction, context overflow, and runtime disconnect fault injection.

Shadow execution must use fixtures or explicitly authorized read-only trial commands. Formal adoption still passes Mission Center verification.
