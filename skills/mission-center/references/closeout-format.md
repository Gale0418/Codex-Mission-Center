# Closeout Format

## Required Sections

- `Summary`
- `Completed`
- `Unfinished`
- `Risks`
- `Smoke tests`
- `Retro`

## Conditional Section

- `Completion critic council`: required when the route was `critic_lite` or `critic_full`; optional for an eligible recorded `skip`. The existing closeout generator remains valid for work where this section is not routed. When routed, augment its output with the validated derived record link and disposition summary.

## Guidance

- Keep it brief but concrete.
- Mention what changed, what shipped, and what remains.
- Note anything that should be done differently next time.
- Keep smoke-test evidence distinct from critic evidence. For the Completion Critic Council, record `skip` reason or route, immutable snapshot, authorization/budgets, lanes/seats and capability limits, finding dispositions/dissent, repairs, rerun verification, and residual risk. An unresolved `Critical` cannot be accepted or waived: it prevents `Done`, a shipped release, and clean Closeout; record only a blocked/not-shipped checkpoint.
- For a named release cycle, pass `--cycle <safe-id>` to the closeout generator. It writes the current `closeout.md` and an immutable `closeouts/<safe-id>.md`; a later attempt to reuse that cycle ID with different content fails closed.
