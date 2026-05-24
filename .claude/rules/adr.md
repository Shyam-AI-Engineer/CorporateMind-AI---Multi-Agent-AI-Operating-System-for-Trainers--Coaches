# Architecture Decision Records (ADR)

Architecture drift without traceability is how systems become unmaintainable. ADRs are how we lock in *why* a decision was made so future engineers (and Claude) can revisit with full context.

## When an ADR is required
A new ADR is needed for any change to:
- Database strategy (RLS vs schema-per-tenant, sharding, partitioning rule)
- AI gateway / provider mix / routing matrix
- Queue architecture (Celery vs alternatives, queue topology)
- Tenancy model
- Observability stack
- Deployment topology (Vercel/Railway → K8s, multi-region)
- Agent topology (adding/removing an agent in the LangGraph runtime)
- Channel-adapter contracts (the `ChannelAdapter` ABC surface)
- Billing model / pricing tier semantics
- New external dependency that becomes load-bearing

In short: anything where six months from now a reader would ask "why on earth did we do it this way?"

## Where they live
```
docs/adr/
├── 0001-modular-monolith.md
├── 0002-euri-as-sole-llm-egress.md
├── 0003-postgres-rls-as-tenant-isolation-default.md
└── ...
```

Filename pattern: `NNNN-kebab-case-title.md` where `NNNN` is the next zero-padded sequence number.

## Structure (required sections)
```markdown
# ADR-NNNN: Short Decision Title

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX | Deprecated
- **Date:** YYYY-MM-DD
- **Deciders:** names / roles

## Context
What's the problem? What constraints / forces are in play? Why are we deciding this now?

## Decision
What did we decide? Be specific. Name files, services, tools where relevant.

## Alternatives considered
At least 2. For each: short description + why we didn't pick it.

## Consequences
- Positive: what this unlocks.
- Negative: what this costs us / what we give up.
- Neutral: what becomes different but isn't strictly better/worse.

## References
Links to RFCs, vendor docs, prior ADRs, related issues.
```

## Immutability
- ADRs are immutable after the `Status` reaches `Accepted`.
- Change of direction is captured by writing a NEW ADR that **supersedes** the old one. Both reference each other (`Status: Superseded by ADR-0017` on the old; `Supersedes ADR-0003` on the new).
- Typo fixes are the only post-acceptance edit allowed.

## Review
- ADRs go through normal code review on a PR. At least one approval from a senior engineer.
- The ADR is merged together with the implementing code change (or in a closely-paired PR).

## Architecture drift without an ADR = review blocker
If a PR makes a change in any of the listed areas without a referenced ADR, the review comment is: "ADR required."
