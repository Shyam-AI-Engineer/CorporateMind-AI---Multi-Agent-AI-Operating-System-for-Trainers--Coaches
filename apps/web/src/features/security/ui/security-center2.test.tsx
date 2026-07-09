/**
 * Frontend unit tests — Sprint 58: Security Center (part 2).
 * Covers: securityKeys, SecurityAlertsPanel, SecurityCenter (loading/error/happy path).
 * NO jest-dom matchers.
 */

import React from "react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type {
  ApiKeyHealth,
  AuditSummary,
  PermissionOverview,
  RoleDistribution,
  SecurityAlert,
  SecurityAlerts,
  SecuritySummary,
} from "@/features/security/types";
import { SecurityAlertsPanel } from "@/features/security/ui/SecurityAlertsPanel";
import { SecurityCenter } from "@/features/security/ui/SecurityCenter";
import { securityKeys } from "@/features/security/api/use-security";

// ── Module-level mock variables ────────────────────────────────────────────────
const mockUseSecuritySummary = vi.fn();
const mockUseRoleDistribution = vi.fn();
const mockUseApiKeyHealth = vi.fn();
const mockUseAuditSummary = vi.fn();
const mockUsePermissionOverview = vi.fn();
const mockUseSecurityAlerts = vi.fn();

vi.mock("@/features/security/api/use-security", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return {
    ...original,
    useSecuritySummary: (...args: unknown[]) => mockUseSecuritySummary(...args),
    useRoleDistribution: (...args: unknown[]) => mockUseRoleDistribution(...args),
    useApiKeyHealth: (...args: unknown[]) => mockUseApiKeyHealth(...args),
    useAuditSummary: (...args: unknown[]) => mockUseAuditSummary(...args),
    usePermissionOverview: (...args: unknown[]) => mockUsePermissionOverview(...args),
    useSecurityAlerts: (...args: unknown[]) => mockUseSecurityAlerts(...args),
  };
});

afterEach(() => vi.clearAllMocks());

const NOW = "2026-07-09T10:00:00Z";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeSummary(overrides: Partial<SecuritySummary> = {}): SecuritySummary {
  return {
    overall_security_score: 1.0,
    active_api_keys: 5,
    expired_api_keys: 0,
    active_workspace_members: 10,
    organization_admins: 2,
    audit_events_today: 20,
    critical_audit_events: 0,
    checked_at: NOW,
    ...overrides,
  };
}

function makeRoles(): RoleDistribution {
  return {
    roles: [{ role: "admin", count: 2 }, { role: "member", count: 8 }],
    total_members: 10,
    checked_at: NOW,
  };
}

function makeApiKeys(): ApiKeyHealth {
  return {
    total_keys: 5,
    active: 5,
    expired: 0,
    never_used: 0,
    used_last_30_days: 4,
    checked_at: NOW,
  };
}

function makeAudit(): AuditSummary {
  return {
    events_today: 10,
    critical_events: 0,
    warning_events: 1,
    top_modules: [{ module: "billing", event_count: 5 }],
    checked_at: NOW,
  };
}

function makePermissions(): PermissionOverview {
  return {
    workspaces: [
      { workspace_id: "ws-1122334455667788", owners: 1, admins: 2, members: 5, viewers: 0 },
    ],
    total_workspaces: 1,
    checked_at: NOW,
  };
}

function makeAlerts(alerts: SecurityAlert[] = []): SecurityAlerts {
  return { alerts, total: alerts.length, checked_at: NOW };
}

function makeAlert(overrides: Partial<SecurityAlert> = {}): SecurityAlert {
  return {
    alert_type: "expired_api_keys",
    severity: "high",
    message: "1 API key has expired.",
    count: 1,
    ...overrides,
  };
}

function setupAllHooks(opts: { loading?: boolean; error?: boolean } = {}) {
  const loading = opts.loading ?? false;
  const error = opts.error ?? false;
  const base = { isLoading: loading, isError: error, data: undefined };

  if (loading || error) {
    mockUseSecuritySummary.mockReturnValue(base);
    mockUseRoleDistribution.mockReturnValue(base);
    mockUseApiKeyHealth.mockReturnValue(base);
    mockUseAuditSummary.mockReturnValue(base);
    mockUsePermissionOverview.mockReturnValue(base);
    mockUseSecurityAlerts.mockReturnValue(base);
  } else {
    mockUseSecuritySummary.mockReturnValue({ isLoading: false, isError: false, data: makeSummary() });
    mockUseRoleDistribution.mockReturnValue({ isLoading: false, isError: false, data: makeRoles() });
    mockUseApiKeyHealth.mockReturnValue({ isLoading: false, isError: false, data: makeApiKeys() });
    mockUseAuditSummary.mockReturnValue({ isLoading: false, isError: false, data: makeAudit() });
    mockUsePermissionOverview.mockReturnValue({ isLoading: false, isError: false, data: makePermissions() });
    mockUseSecurityAlerts.mockReturnValue({ isLoading: false, isError: false, data: makeAlerts() });
  }
}

// ── securityKeys ───────────────────────────────────────────────────────────────

describe("securityKeys", () => {
  it("summary() returns array with security and summary", () => {
    const key = securityKeys.summary();
    expect(key).toContain("security");
    expect(key).toContain("summary");
  });

  it("roles() includes roles", () => {
    expect(securityKeys.roles()).toContain("roles");
  });

  it("apiKeys() includes api-keys", () => {
    expect(securityKeys.apiKeys()).toContain("api-keys");
  });

  it("audit() includes audit", () => {
    expect(securityKeys.audit()).toContain("audit");
  });

  it("permissions() includes permissions", () => {
    expect(securityKeys.permissions()).toContain("permissions");
  });

  it("alerts() includes alerts", () => {
    expect(securityKeys.alerts()).toContain("alerts");
  });

  it("all keys start with security", () => {
    expect(securityKeys.summary()[0]).toBe("security");
    expect(securityKeys.roles()[0]).toBe("security");
    expect(securityKeys.alerts()[0]).toBe("security");
  });

  it("keys are distinct", () => {
    const keys = [
      JSON.stringify(securityKeys.summary()),
      JSON.stringify(securityKeys.roles()),
      JSON.stringify(securityKeys.apiKeys()),
      JSON.stringify(securityKeys.audit()),
      JSON.stringify(securityKeys.permissions()),
      JSON.stringify(securityKeys.alerts()),
    ];
    const unique = new Set(keys);
    expect(unique.size).toBe(6);
  });
});

// ── SecurityAlertsPanel ────────────────────────────────────────────────────────

describe("SecurityAlertsPanel", () => {
  it("renders the panel container", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts()} />);
    expect(screen.getByTestId("security-alerts-panel")).not.toBeNull();
  });

  it("shows no-alerts message when total = 0", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts()} />);
    expect(screen.getByTestId("no-alerts")).not.toBeNull();
  });

  it("no-alerts text is positive", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts()} />);
    expect(screen.getByTestId("no-alerts").textContent).toContain("No security alerts");
  });

  it("shows alert count badge when alerts exist", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert()])} />);
    expect(screen.getByTestId("alert-count-badge")).not.toBeNull();
  });

  it("alert count badge shows correct count", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert(), makeAlert({ alert_type: "unused_api_keys" })])} />);
    expect(screen.getByTestId("alert-count-badge").textContent).toContain("2");
  });

  it("singular 'alert' in badge when total = 1", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert()])} />);
    expect(screen.getByTestId("alert-count-badge").textContent).toContain("1 alert");
  });

  it("plural 'alerts' in badge when total > 1", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert(), makeAlert({ alert_type: "unused_api_keys" })])} />);
    expect(screen.getByTestId("alert-count-badge").textContent).toContain("alerts");
  });

  it("renders alert item for each alert", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert()])} />);
    expect(screen.getByTestId("alert-item-expired_api_keys")).not.toBeNull();
  });

  it("severity badge shows correct severity label", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert({ severity: "high" })])} />);
    const badge = screen.getByTestId("alert-severity-high");
    expect(badge.textContent).toBe("High");
  });

  it("critical severity badge renders", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert({ severity: "critical" })])} />);
    expect(screen.getByTestId("alert-severity-critical")).not.toBeNull();
  });

  it("medium severity badge renders", () => {
    render(
      <SecurityAlertsPanel
        alerts={makeAlerts([makeAlert({ alert_type: "excessive_admins", severity: "medium" })])}
      />
    );
    expect(screen.getByTestId("alert-severity-medium")).not.toBeNull();
  });

  it("low severity badge renders", () => {
    render(
      <SecurityAlertsPanel
        alerts={makeAlerts([makeAlert({ alert_type: "unused_api_keys", severity: "low" })])}
      />
    );
    expect(screen.getByTestId("alert-severity-low")).not.toBeNull();
  });

  it("shows alert type label (not raw key)", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert()])} />);
    const item = screen.getByTestId("alert-item-expired_api_keys");
    expect(item.textContent).toContain("Expired API Keys");
  });

  it("shows alert message text", () => {
    render(
      <SecurityAlertsPanel
        alerts={makeAlerts([makeAlert({ message: "3 keys expired." })])}
      />
    );
    const item = screen.getByTestId("alert-item-expired_api_keys");
    expect(item.textContent).toContain("3 keys expired.");
  });

  it("renders multiple alert items", () => {
    const alerts = makeAlerts([
      makeAlert({ alert_type: "expired_api_keys" }),
      makeAlert({ alert_type: "unused_api_keys", severity: "low", message: "2 never used." }),
    ]);
    render(<SecurityAlertsPanel alerts={alerts} />);
    expect(screen.getByTestId("alert-item-expired_api_keys")).not.toBeNull();
    expect(screen.getByTestId("alert-item-unused_api_keys")).not.toBeNull();
  });

  it("does not render no-alerts when total > 0", () => {
    render(<SecurityAlertsPanel alerts={makeAlerts([makeAlert()])} />);
    expect(screen.queryByTestId("no-alerts")).toBeNull();
  });
});

// ── SecurityCenter ─────────────────────────────────────────────────────────────

describe("SecurityCenter", () => {
  it("shows loading state when any hook is loading", () => {
    setupAllHooks({ loading: true });
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-loading")).not.toBeNull();
  });

  it("loading text is descriptive", () => {
    setupAllHooks({ loading: true });
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-loading").textContent?.length).toBeGreaterThan(0);
  });

  it("shows error state when any hook errors", () => {
    setupAllHooks({ error: true });
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-error")).not.toBeNull();
  });

  it("error message is descriptive", () => {
    setupAllHooks({ error: true });
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-error").textContent?.length).toBeGreaterThan(0);
  });

  it("renders security center when data is loaded", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-center")).not.toBeNull();
  });

  it("does not show loading when data is ready", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.queryByTestId("security-loading")).toBeNull();
  });

  it("does not show error when data is ready", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.queryByTestId("security-error")).toBeNull();
  });

  it("renders security score card", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-score-card")).not.toBeNull();
  });

  it("renders security alerts panel", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("security-alerts-panel")).not.toBeNull();
  });

  it("renders role distribution chart", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("role-distribution-chart")).not.toBeNull();
  });

  it("renders api key health panel", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("api-key-health-panel")).not.toBeNull();
  });

  it("renders audit summary section", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("audit-summary-section")).not.toBeNull();
  });

  it("renders permission matrix", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("permission-matrix")).not.toBeNull();
  });

  it("shows Security Posture section heading", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByRole("heading", { name: /^Security Posture$/i })).not.toBeNull();
  });

  it("shows Access Control section heading", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByRole("heading", { name: /^Access Control$/i })).not.toBeNull();
  });

  it("shows Audit Summary section heading", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByRole("heading", { name: /^Audit Summary$/i })).not.toBeNull();
  });

  it("shows Permission Overview section heading", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByRole("heading", { name: /^Permission Overview$/i })).not.toBeNull();
  });

  it("audit events today shown in summary section", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("audit-today").textContent).toContain("10");
  });

  it("audit critical events shown", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("audit-critical").textContent).toContain("0");
  });

  it("audit warning events shown", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("audit-warning").textContent).toContain("1");
  });

  it("top audit module shown", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("audit-module-billing")).not.toBeNull();
  });

  it("shows no-alerts when alerts array is empty", () => {
    mockUseSecuritySummary.mockReturnValue({ isLoading: false, isError: false, data: makeSummary() });
    mockUseRoleDistribution.mockReturnValue({ isLoading: false, isError: false, data: makeRoles() });
    mockUseApiKeyHealth.mockReturnValue({ isLoading: false, isError: false, data: makeApiKeys() });
    mockUseAuditSummary.mockReturnValue({ isLoading: false, isError: false, data: makeAudit() });
    mockUsePermissionOverview.mockReturnValue({ isLoading: false, isError: false, data: makePermissions() });
    mockUseSecurityAlerts.mockReturnValue({ isLoading: false, isError: false, data: makeAlerts([]) });
    render(<SecurityCenter />);
    expect(screen.getByTestId("no-alerts")).not.toBeNull();
  });

  it("shows active alerts when present", () => {
    mockUseSecuritySummary.mockReturnValue({ isLoading: false, isError: false, data: makeSummary() });
    mockUseRoleDistribution.mockReturnValue({ isLoading: false, isError: false, data: makeRoles() });
    mockUseApiKeyHealth.mockReturnValue({ isLoading: false, isError: false, data: makeApiKeys() });
    mockUseAuditSummary.mockReturnValue({ isLoading: false, isError: false, data: makeAudit() });
    mockUsePermissionOverview.mockReturnValue({ isLoading: false, isError: false, data: makePermissions() });
    mockUseSecurityAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeAlerts([makeAlert()]),
    });
    render(<SecurityCenter />);
    expect(screen.getByTestId("alert-count-badge")).not.toBeNull();
  });

  it("shows security score as percentage", () => {
    setupAllHooks();
    render(<SecurityCenter />);
    expect(screen.getByTestId("score-ring").textContent).toContain("100%");
  });

  it("degraded score shown correctly", () => {
    mockUseSecuritySummary.mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeSummary({ overall_security_score: 0.6 }),
    });
    mockUseRoleDistribution.mockReturnValue({ isLoading: false, isError: false, data: makeRoles() });
    mockUseApiKeyHealth.mockReturnValue({ isLoading: false, isError: false, data: makeApiKeys() });
    mockUseAuditSummary.mockReturnValue({ isLoading: false, isError: false, data: makeAudit() });
    mockUsePermissionOverview.mockReturnValue({ isLoading: false, isError: false, data: makePermissions() });
    mockUseSecurityAlerts.mockReturnValue({ isLoading: false, isError: false, data: makeAlerts() });
    render(<SecurityCenter />);
    expect(screen.getByTestId("score-ring").textContent).toContain("60%");
  });
});
