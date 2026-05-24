---
name: create-compliance-rule
description: Add a new rule to ComplianceGuardAgent (e.g., a channel-specific block, a new frequency-cap variant, a content-policy classifier)
---

# Create Compliance Rule Skill

## Goal
Add a new rule that ComplianceGuardAgent enforces on every outbound message. Compliance rules are non-bypassable and must be testable in isolation.

## Steps
1. **Ask for:**
   - Rule name + one-line description.
   - What it checks (recipient state, frequency, content, time-of-day, channel state).
   - Block / warn / require-HITL semantics.
   - Channel scope (all / specific channel).
   - Configurability (per-tenant override allowed?).
2. **Add the rule implementation** in `apps/api/src/corpmind/agents/compliance_guard/rules/<name>.py`:
   ```python
   class <Name>Rule(ComplianceRule):
       name = "<rule_name>"
       channels = ("email", "whatsapp", ...)  # or ALL
       configurable = True | False

       async def check(self, msg: OutboundMessage, ctx: TenantContext) -> RuleResult:
           # returns RuleResult.pass_() | block(reason) | hitl(reason)
   ```
3. **Register** the rule in `apps/api/src/corpmind/agents/compliance_guard/registry.py` with explicit ordering (earlier rules short-circuit later ones).
4. **Add configuration** (if per-tenant configurable) — schema in `tenants.compliance_config` JSONB, default in `apps/api/src/corpmind/modules/compliance/defaults.py`.
5. **Add audit logging:**
   - Pass → no audit (avoid noise).
   - Block → `audit_events` row with `event_type=compliance.blocked`, reason, recipient hash, channel, tenant_id.
   - HITL → emit `campaign.approval_requested` event with the rule name + reason.
6. **Add metrics:**
   - `compliance_check_total{rule,outcome}`.
   - `compliance_block_total{rule,channel,tenant}`.
7. **Add a kill-switch feature flag** — `compliance.<rule_name>.enabled` — for emergency disable. Default ON.
8. **Tests:**
   - Unit: rule check for each outcome (pass / block / hitl) with fixtures.
   - Integration: end-to-end send pipeline with this rule enabled — verify the right outcome.
   - Configuration: per-tenant override changes behavior.
   - Kill-switch: rule disabled → all messages pass this rule.

## Quality rules
- Rules are SIDE-EFFECT-FREE on the `check()` path (no DB writes other than audit on block/hitl).
- `check()` is fast (target < 10ms) — heavy work happens before in earlier rules or async pre-warm.
- Per-rule kill-switch flag exists.
- Default configuration is documented.
- A new rule that could increase block rate > 1% needs a shadow period before full enablement (use feature-flag % rollout).
- Block reasons are user-meaningful strings shown in the trainer's notification ("Recipient hasn't opted in via verified source", not "rule_42_failed").

## References
- `.claude/rules/compliance-guard.md`
- `.claude/rules/langgraph-agents.md`
- `.claude/rules/feature-flags.md`
