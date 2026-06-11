/**
 * Build-time feature flags for the web app.
 *
 * Stage 1 has no runtime flag service on the frontend; user-visible rollouts are
 * gated by NEXT_PUBLIC_* env vars (statically inlined by Next at build time, so
 * each flag must be referenced as a literal `process.env.NEXT_PUBLIC_...` — a
 * dynamic key would not be replaced).
 *
 * `ui.followup.approval_queue` (ADR-0008 §H): gates the Sprint 8C follow-up
 * HITL surface (the "Needs review" tab, review dialog, approve/reject/edit, and
 * the awaiting-approval count badge).  Default OFF — set
 * NEXT_PUBLIC_FEATURE_FOLLOWUP_APPROVAL=1 to enable for a cohort/preview.
 */

export const FOLLOWUP_APPROVAL_ENABLED =
  process.env.NEXT_PUBLIC_FEATURE_FOLLOWUP_APPROVAL === "1" ||
  process.env.NEXT_PUBLIC_FEATURE_FOLLOWUP_APPROVAL === "true";
