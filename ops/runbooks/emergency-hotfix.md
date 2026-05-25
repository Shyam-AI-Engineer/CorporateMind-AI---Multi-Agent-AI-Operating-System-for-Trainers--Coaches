# Runbook: Emergency Hotfix

## Incident Summary

A critical bug in production requires a fix that cannot wait for the standard PR review and canary deploy cycle. This runbook defines the abbreviated path to patch production safely and quickly.

**This path requires explicit sign-off from the Incident Commander (IC) + Tech Lead.**

## When to Use This Runbook

- SEV1 or SEV2 incident requiring an immediate code fix.
- A cross-tenant data leak (see `cross-tenant-data-suspected.md`) with a confirmed code root cause.
- A compliance enforcement failure (e.g., ComplianceGuardAgent is not blocking correctly).
- A security vulnerability with active exploitation risk.

**Do NOT use this path for:** performance improvements, UX fixes, or anything that can wait for a normal release cycle.

## Prerequisites

1. IC and Tech Lead have agreed this qualifies for emergency path.
2. The root cause is identified and the fix is understood.
3. A rollback plan exists (what to do if the hotfix makes things worse).

## Hotfix Process

### Step 1: Create a Hotfix Branch

```bash
git checkout main
git pull origin main
git checkout -b hotfix/<incident-id>-<short-description>
```

### Step 2: Write the Minimal Fix

- Fix **only** the root cause. No cleanup, no refactors, no opportunistic improvements.
- If the fix is a config change or feature flag flip, prefer that over a code change.
- Write a regression test that reproduces the bug (can be merged in the follow-up PR if time is critical).

### Step 3: Abbreviated Review

- Minimum: 1 Tech Lead approval (not self-approval).
- CI must pass (lint + unit tests). Skip integration tests only with explicit IC approval.
- If CI is too slow: Tech Lead can manually verify the critical path locally.

### Step 4: Merge and Deploy

```bash
git checkout main
git merge --no-ff hotfix/<incident-id>-<short-description>
git tag v<version>-hotfix.<n>
git push origin main --tags
```

- Deploy to staging first if possible (even a 2-minute soak helps).
- If staging is unavailable or too slow: deploy directly to canary (10%), monitor for 5 minutes, then 100%.

### Step 5: Verify Fix

- Confirm the triggering condition no longer reproduces.
- Check Grafana and Sentry for stabilization (no new errors from the fixed path).
- Update the incident channel with the fix status.

### Step 6: Post-Hotfix Cleanup

Within 24 hours:
- [ ] Add regression test if not included in the hotfix.
- [ ] Create a follow-up PR for any cleanup the hotfix skipped.
- [ ] Update `CHANGELOG.md` if it exists.
- [ ] Begin postmortem (due within 5 business days).

## Escalation Path

- **IC:** Approves the use of this runbook. Owns customer comms.
- **Tech Lead:** Owns the fix. Signs off on the code.
- **On-call engineer:** Executes the deploy if Tech Lead is unavailable.

## Rollback Plan

If the hotfix makes things worse:
```bash
git revert HEAD  # or git reset --hard HEAD~1
# Deploy the revert immediately
```
Or flip the relevant feature flag to `false` if the fix was feature-flag-gated.

## Important Notes

- **Never skip `--no-verify` on commits** — the pre-commit hooks are safety guards, not obstacles.
- **Document everything** — every decision made during the hotfix (why we skipped X, why we chose Y) belongs in the incident channel, not just in your head.
- **One fix per hotfix PR** — if there are two bugs, two PRs. Don't combine.
