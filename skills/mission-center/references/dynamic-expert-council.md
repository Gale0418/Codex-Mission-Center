# Dynamic Expert Council Gate

## Purpose and Timing

This gate is separate from the Creative Cross-Domain Council. The creative council is an early North Star and architecture divergence tool. Re-enter this gate later when research, implementation, optimization, a material trade-off, or a local optimum reveals a question whose answer may change the plan.

Do not run a council as ceremony. First classify the decision's complexity from the number of coupled systems, reversibility, uncertainty, safety or compliance exposure, cost of being wrong, and amount of new evidence required.

| Complexity | Route | Use when |
| --- | --- | --- |
| low | `skip` | The change is reversible, has one established solution, and does not materially change risk, scope, or a prior decision. Record the rationale and continue. |
| medium | `council_lite` | A bounded decision has meaningful trade-offs or uncertainty, but can be explored from local context without current external research. |
| high | `council_full` | The decision has coupled constraints, durable consequences, a high cost of error, safety, legal, security, financial, or time-sensitive claims, or could redirect the mission. |

When the route is unclear, choose the safer route and state why. A council must alter a question, option, experiment, guardrail, or task design; otherwise stop and retain the current plan.

## `council_lite`

Choose at least three dynamically selected professional perspectives from the mechanism, constraints, and decision at hand. Do not draw from a fixed role catalogue. Each perspective must contribute a distinct assumption, failure mode, or evaluation criterion.

Include one **improbable but feasible** perspective: it deliberately proposes an apparently absurd solution that still obeys known constraints, then identifies its smallest safe test. It is a source of structured imagination, not permission to ignore safety, user intent, budget, or evidence.

Use the provided context and clearly label assumptions. External web research is not required for Lite. Converge on a recommendation, rejected alternatives, decisive trade-offs, and the next low-cost validation.

## Dynamic Perspective Contract

For every selected perspective, define a compact charter from the decision rather than a reusable roster:

- **receives:** the decision, available evidence, constraints, and unresolved question;
- **responsibility:** one distinct mechanism or evaluation duty;
- **not responsible for:** adjacent decisions or claims assigned elsewhere, so views do not duplicate each other;
- **produces:** a decision-relevant deliverable with explicit success criteria;
- **low-confidence behavior:** identify the missing evidence, avoid a false conclusion, and hand off a bounded verification question.

Each perspective outputs: (1) observation and supporting evidence or a labelled assumption, (2) risk or blind spot, (3) recommendation, and (4) confidence plus unknowns. Keep generators of options separate from validators of evidence or safety when one perspective cannot credibly do both.

## Chair and Handoffs

The chair requires evidence for factual claims, makes each handoff explicit, and uses only bounded retries before escalating an unresolved conflict or evidence gap. The chair does not average opinions: it publishes the decision, material dissent, and the next verification that could change the decision.

## `council_full`

Before deliberating, confirm and state the current date. For each time-sensitive or high-risk claim, search for the latest relevant **primary source** and record its publication or update date. Prefer official documentation, standards bodies, regulators, original research, or the system owner over summaries and search snippets.

If a site is blocked, use Jina Reader or Jina Search as a retrieval fallback, then preserve the original source URL and distinguish the retrieved text from the primary source. Do not invent metrics, source access, dates, consensus, experiment outcomes, or citations. If reliable evidence cannot be obtained, mark the claim unknown, narrow the recommendation, or ask the user before proceeding.

Select perspectives dynamically and independently challenge the evidence, constraints, downside, and reversibility. Include the improbable-but-feasible perspective from Lite, but promote it only when evidence and a bounded experiment justify doing so. Finish with a traceable recommendation: evidence, remaining uncertainty, decision owner, guardrails, and a reversible next step.

## Evidence Discipline and Exploration Variance

Keep evidence discipline proportional to the route: separate observed facts, sourced facts, assumptions, and proposals; attach decision-relevant sources for Full; and say when evidence is missing. Increase exploration variance by testing more distinct mechanisms, constraints, and counterarguments—not by claiming different model settings or temperature values.

Simulated perspectives are reasoning aids and do not consume additional runtime-agent quota. Running real subagents or Shadow experiments requires the user's explicit approval and an agreed budget before execution. Never imply that a simulated view was independently executed or externally verified.
