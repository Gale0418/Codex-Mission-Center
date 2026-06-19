# Research Protocol

## Prior Art Gate

Before creating a custom solution:

1. Record the pre-search idea and the problem it intends to solve.
2. Inspect local files, docs, Git history, and existing dependencies.
3. Search standards, official examples, maintained libraries, papers, and comparable open-source projects when current or external facts matter.
4. Compare four paths: adopt, adapt, learn, or build independently.
5. Explain why the selected path best fits the mission.

Prefer primary and official sources. Treat search snippets as leads, not evidence.

## Network Fallback

Use normal search, purpose-built connectors, or official documentation first. If a public page is blocked by rendering or anti-bot behavior, use Jina Reader as a reading fallback. Use Jina Search only when a valid credential is already configured.

Do not use Jina or another proxy to bypass authentication, authorization, paywalls, robots restrictions, or private access controls. If evidence remains unavailable, mark the claim uncertain instead of inventing an answer.

## Concise Research Log

Keep only decision-relevant entries in `notes.md`:

```text
Pre-search idea | Source | Adopted insight | License status
```

Do not paste full search results or long article summaries into the workspace.

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
