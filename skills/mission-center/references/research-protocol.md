# Research Protocol

## Prior Art Gate

Before creating a custom solution:

1. Record the pre-search idea and the problem it intends to solve.
2. Inspect local files, docs, Git history, and existing dependencies.
3. Search standards, official examples, maintained libraries, papers, and comparable open-source projects when current or external facts matter.
4. Compare four paths: adopt, adapt, learn, or build independently.
5. Explain why the selected path best fits the mission.

For comparable open-source projects, record maintenance state, scope fit, contract ideas, dependency cost, and license. Classify each result as `Adopt`, `Adapt`, `Learn`, or `Reject`. Prefer learning from stable interfaces and evidence gates over importing large role or prompt libraries.

Prefer primary and official sources. Treat search snippets as leads, not evidence.

## Network Fallback

Use normal search, purpose-built connectors, or official documentation first. If a public page is blocked by rendering or anti-bot behavior, use Jina Reader as a reading fallback. Use Jina Search only when a valid credential is already configured.

Do not use Jina or another proxy to bypass authentication, authorization, paywalls, robots restrictions, or private access controls. If evidence remains unavailable, mark the claim uncertain instead of inventing an answer.

## Representative GitHub Screening

For software, AI-tooling, developer-tool, framework, runtime, agent, OCR, translation, or game-system missions with meaningful prior art, search broadly and then deeply screen roughly three to seven representative candidates. Adjust the count to the decision; never add weak candidates merely to fill a quota.

Choose candidates that expose genuinely different routes where available: a direct competitor, the same use case, the same subsystem, a different architecture, a formerly popular abandoned approach, or another representative technical alternative. Do not count forks as independent architectures.

GitHub Stars and Forks are only weak popularity signals. Never rank candidates by Stars alone. Evaluate only decision-relevant evidence, including:

- problem, actual user workflow, and scope fit;
- relevant module boundaries, data flow, client/server or local/cloud split, IPC, state, storage, caching, plugin/provider boundaries, and extension model;
- language, runtime, major libraries, build, packaging, deployment, dependency health, operational cost, and exit difficulty;
- recent commits and releases, issue and pull-request activity, maintainer response, contributors, roadmap, and archived status;
- tests, CI, documentation, error handling, migrations, release process, dependency management, security posture, license, and known limitations.

Do not label a project maintained from one recent commit. When weaknesses may affect the decision, inspect primary issue, discussion, pull-request, changelog, or release-note evidence for recurring bugs, performance complaints, maintenance pain, platform limits, and breaking dependencies. Mark unavailable evidence unknown.

Use a compact comparison matrix containing only dimensions that change the decision, then classify each candidate as `Adopt`, `Adapt`, `Learn`, or `Reject`. State what to reuse, what architecture to learn from, what not to copy, and which dependencies are not worth introducing.

## Concise Research Log

Keep only decision-relevant entries in `notes.md`:

```text
Pre-search idea | Source | Adopted insight | License status
```

Temporary detailed screening may remain under `output/` or the working session. Do not paste full search results, raw Markdown, long summaries, or source-code dumps into persistent MissionCenter memory.

## Clean-room Reference

- Extract requirements, concepts, principles, public interfaces, and comparison criteria.
- Do not copy source code, prose, artwork, or highly distinctive implementation structure without permission.
- After research, implement from the approved requirements and record which external ideas affected the decision.
- If concrete content must be copied or modified, stop Clean-room handling and perform license review first.

## License Gate

Record source URL, author, version, SPDX identifier, attribution duties, maintenance state, security posture, compatibility, cost, and exit difficulty.

- Prefer permissive licenses such as MIT, BSD-2-Clause, BSD-3-Clause, ISC, and Apache-2.0 when they fit.
- Treat AGPL, SSPL, non-commercial, and unknown licenses as blocked by default.
- Send GPL and custom licenses to explicit human review.
- Treat a public repository without a license as all rights reserved for concrete content.
- Get user approval before adding an external dependency, service, or material license obligation.

Record adopted and rejected candidates in `decisions.md` with a brief reason.
