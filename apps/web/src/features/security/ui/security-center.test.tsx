/**
 * Frontend unit tests — Sprint 58: Security Center (part 1).
 * Covers: types/constants, SecurityScoreCard, RoleDistributionChart,
 *         ApiKeyHealthPanel, PermissionMatrix.
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
  SecurityAlerts,
  SecuritySummary,
} from "@/features/security/types";
import {
  ALERT_SEVERITY_LABELS,
  ALERT_TYPE_LABELS,
  ROLE_LABELS,
} from "@/features/security/types";
import { SecurityScoreCard } from "@/features/security/ui/SecurityScoreCard";
import { RoleDistributionChart } from "@/features/security/ui/RoleDistributionChart";
import { ApiKeyHealthPanel } from "@/features/security/ui/ApiKeyHealthPanel";
import { PermissionMatrix } from "@/features/security/ui/PermissionMatrix";

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

function makeRoleDistribution(overrides: Partial<RoleDistribution> = {}): RoleDistribution {
  return {
    roles: [
      { role: "owner", count: 1 },
      { role: "admin", count: 2 },
      { role: "member", count: 7 },
    ],
    total_members: 10,
    checked_at: NOW,
    ...overrides,
  };
}

function makeApiKeyHealth(overrides: Partial<ApiKeyHealth> = {}): ApiKeyHealth {
  return {
    total_keys: 10,
    active: 8,
    expired: 0,
    never_used: 1,
    used_last_30_days: 7,
    checked_at: NOW,
    ...overrides,
  };
}

function makePermissionOverview(overrides: Partial<PermissionOverview> = {}): PermissionOverview {
  return {
    workspaces: [
      { workspace_id: "ws-aabbccdd-1111-2222-3333-aabbccddeeff", owners: 1, admins: 2, members: 5, viewers: 0 },
      { workspace_id: "ws-11223344-5566-7788-9900-aabbccddeeff", owners: 0, admins: 1, members: 3, viewers: 2 },
    ],
    total_workspaces: 2,
    checked_at: NOW,
    ...overrides,
  };
}

// ── Types and constants ────────────────────────────────────────────────────────

describe("ROLE_LABELS", () => {
  it("has owner label", () => {
    expect(ROLE_LABELS.owner).toBe("Owner");
  });

  it("has admin label", () => {
    expect(ROLE_LABELS.admin).toBe("Admin");
  });

  it("has member label", () => {
    expect(ROLE_LABELS.member).toBe("Member");
  });

  it("has viewer label", () => {
    expect(ROLE_LABELS.viewer).toBe("Viewer");
  });

  it("has exactly 4 roles", () => {
    expect(Object.keys(ROLE_LABELS).length).toBe(4);
  });
});

describe("ALERT_SEVERITY_LABELS", () => {
  it("has low label", () => {
    expect(ALERT_SEVERITY_LABELS.low).toBe("Low");
  });

  it("has medium label", () => {
    expect(ALERT_SEVERITY_LABELS.medium).toBe("Medium");
  });

  it("has high label", () => {
    expect(ALERT_SEVERITY_LABELS.high).toBe("High");
  });

  it("has critical label", () => {
    expect(ALERT_SEVERITY_LABELS.critical).toBe("Critical");
  });

  it("has exactly 4 severities", () => {
    expect(Object.keys(ALERT_SEVERITY_LABELS).length).toBe(4);
  });
});

describe("ALERT_TYPE_LABELS", () => {
  const requiredTypes = [
    "expired_api_keys",
    "unused_api_keys",
    "critical_audit_events",
    "no_admin_user",
    "excessive_admins",
    "pending_invitations",
  ];

  it.each(requiredTypes)("has label for %s", (type) => {
    expect(ALERT_TYPE_LABELS[type]).not.toBeUndefined();
    expect(ALERT_TYPE_LABELS[type].length).toBeGreaterThan(0);
  });
});

// ── SecurityScoreCard ──────────────────────────────────────────────────────────

describe("SecurityScoreCard", () => {
  it("renders the container", () => {
    render(<SecurityScoreCard summary={makeSummary()} />);
    expect(screen.getByTestId("security-score-card")).not.toBeNull();
  });

  it("shows 100% score when score is 1.0", () => {
    render(<SecurityScoreCard summary={makeSummary({ overall_security_score: 1.0 })} />);
    expect(screen.getByTestId("score-ring").textContent).toContain("100%");
  });

  it("shows 70% score when score is 0.7", () => {
    render(<SecurityScoreCard summary={makeSummary({ overall_security_score: 0.7 })} />);
    expect(screen.getByTestId("score-ring").textContent).toContain("70%");
  });

  it("shows 0% score when score is 0", () => {
    render(<SecurityScoreCard summary={makeSummary({ overall_security_score: 0.0 })} />);
    expect(screen.getByTestId("score-ring").textContent).toContain("0%");
  });

  it("shows score ring with 'Security Score' label", () => {
    render(<SecurityScoreCard summary={makeSummary()} />);
    expect(screen.getByTestId("score-ring").textContent).toContain("Security Score");
  });

  it("shows active api key count", () => {
    render(<SecurityScoreCard summary={makeSummary({ active_api_keys: 7 })} />);
    expect(screen.getByTestId("metric-active-keys").textContent).toContain("7");
  });

  it("shows expired api key count", () => {
    render(<SecurityScoreCard summary={makeSummary({ expired_api_keys: 3 })} />);
    expect(screen.getByTestId("metric-expired-keys").textContent).toContain("3");
  });

  it("shows active members count", () => {
    render(<SecurityScoreCard summary={makeSummary({ active_workspace_members: 15 })} />);
    expect(screen.getByTestId("metric-members").textContent).toContain("15");
  });

  it("shows org admins count", () => {
    render(<SecurityScoreCard summary={makeSummary({ organization_admins: 4 })} />);
    expect(screen.getByTestId("metric-admins").textContent).toContain("4");
  });

  it("shows audit events today", () => {
    render(<SecurityScoreCard summary={makeSummary({ audit_events_today: 30 })} />);
    expect(screen.getByTestId("metric-audit-today").textContent).toContain("30");
  });

  it("shows critical audit events", () => {
    render(<SecurityScoreCard summary={makeSummary({ critical_audit_events: 2 })} />);
    expect(screen.getByTestId("metric-critical").textContent).toContain("2");
  });

  it("renders 6 metric tiles", () => {
    render(<SecurityScoreCard summary={makeSummary()} />);
    const tiles = [
      "metric-active-keys", "metric-expired-keys", "metric-members",
      "metric-admins", "metric-audit-today", "metric-critical",
    ];
    for (const tid of tiles) {
      expect(screen.getByTestId(tid)).not.toBeNull();
    }
  });
});

// ── RoleDistributionChart ──────────────────────────────────────────────────────

describe("RoleDistributionChart", () => {
  it("renders the container", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("role-distribution-chart")).not.toBeNull();
  });

  it("shows total members count", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution({ total_members: 10 })} />);
    expect(screen.getByTestId("total-members").textContent).toContain("10");
  });

  it("shows singular 'member' when total is 1", () => {
    const dist: RoleDistribution = {
      roles: [{ role: "owner", count: 1 }],
      total_members: 1,
      checked_at: NOW,
    };
    render(<RoleDistributionChart distribution={dist} />);
    expect(screen.getByTestId("total-members").textContent).toContain("1 member");
  });

  it("shows 'members' when total > 1", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution({ total_members: 5 })} />);
    expect(screen.getByTestId("total-members").textContent).toContain("members");
  });

  it("shows no-members message when empty", () => {
    const empty: RoleDistribution = { roles: [], total_members: 0, checked_at: NOW };
    render(<RoleDistributionChart distribution={empty} />);
    expect(screen.getByTestId("no-members")).not.toBeNull();
  });

  it("does not render role bar when empty", () => {
    const empty: RoleDistribution = { roles: [], total_members: 0, checked_at: NOW };
    render(<RoleDistributionChart distribution={empty} />);
    expect(screen.queryByTestId("role-bar")).toBeNull();
  });

  it("renders role bar when members exist", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("role-bar")).not.toBeNull();
  });

  it("renders a segment per role", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("bar-segment-owner")).not.toBeNull();
    expect(screen.getByTestId("bar-segment-admin")).not.toBeNull();
    expect(screen.getByTestId("bar-segment-member")).not.toBeNull();
  });

  it("renders a row per role in legend", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("role-row-owner")).not.toBeNull();
    expect(screen.getByTestId("role-row-admin")).not.toBeNull();
    expect(screen.getByTestId("role-row-member")).not.toBeNull();
  });

  it("shows count for owner role", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("role-count-owner").textContent).toBe("1");
  });

  it("shows count for member role", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    expect(screen.getByTestId("role-count-member").textContent).toBe("7");
  });

  it("bar segment has proportional width for owner", () => {
    render(<RoleDistributionChart distribution={makeRoleDistribution()} />);
    const seg = screen.getByTestId("bar-segment-owner");
    expect(seg.getAttribute("style")).toContain("10%");
  });

  it("viewer role renders if present", () => {
    const dist: RoleDistribution = {
      roles: [{ role: "viewer", count: 3 }],
      total_members: 3,
      checked_at: NOW,
    };
    render(<RoleDistributionChart distribution={dist} />);
    expect(screen.getByTestId("role-row-viewer")).not.toBeNull();
    expect(screen.getByTestId("role-count-viewer").textContent).toBe("3");
  });
});

// ── ApiKeyHealthPanel ──────────────────────────────────────────────────────────

describe("ApiKeyHealthPanel", () => {
  it("renders the panel", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth()} />);
    expect(screen.getByTestId("api-key-health-panel")).not.toBeNull();
  });

  it("shows total keys", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ total_keys: 10 })} />);
    expect(screen.getByTestId("key-total").textContent).toBe("10");
  });

  it("shows active keys", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ active: 8 })} />);
    expect(screen.getByTestId("key-active").textContent).toBe("8");
  });

  it("shows expired keys", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ expired: 2 })} />);
    expect(screen.getByTestId("key-expired").textContent).toBe("2");
  });

  it("shows never-used keys", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ never_used: 3 })} />);
    expect(screen.getByTestId("key-never-used").textContent).toBe("3");
  });

  it("shows used-last-30d keys", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ used_last_30_days: 6 })} />);
    expect(screen.getByTestId("key-used-30d").textContent).toBe("6");
  });

  it("shows expired warning when expired > 0", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ expired: 2 })} />);
    expect(screen.getByTestId("expired-warning")).not.toBeNull();
  });

  it("does not show expired warning when expired = 0", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ expired: 0 })} />);
    expect(screen.queryByTestId("expired-warning")).toBeNull();
  });

  it("warning message mentions count", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ expired: 3 })} />);
    expect(screen.getByTestId("expired-warning").textContent).toContain("3");
  });

  it("singular 'key' in warning when expired = 1", () => {
    render(<ApiKeyHealthPanel health={makeApiKeyHealth({ expired: 1 })} />);
    expect(screen.getByTestId("expired-warning").textContent).toContain("1 key");
  });

  it("shows zero values correctly", () => {
    const health: ApiKeyHealth = {
      total_keys: 0, active: 0, expired: 0, never_used: 0, used_last_30_days: 0, checked_at: NOW
    };
    render(<ApiKeyHealthPanel health={health} />);
    expect(screen.getByTestId("key-total").textContent).toBe("0");
  });
});

// ── PermissionMatrix ───────────────────────────────────────────────────────────

describe("PermissionMatrix", () => {
  it("renders the matrix container", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    expect(screen.getByTestId("permission-matrix")).not.toBeNull();
  });

  it("shows no-workspaces message when empty", () => {
    const empty: PermissionOverview = { workspaces: [], total_workspaces: 0, checked_at: NOW };
    render(<PermissionMatrix overview={empty} />);
    expect(screen.getByTestId("no-workspaces")).not.toBeNull();
  });

  it("shows workspace count badge", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    expect(screen.getByTestId("workspace-count").textContent).toContain("2");
  });

  it("shows singular 'workspace' when count is 1", () => {
    const single: PermissionOverview = {
      workspaces: [{ workspace_id: "ws-1", owners: 1, admins: 0, members: 2, viewers: 0 }],
      total_workspaces: 1,
      checked_at: NOW,
    };
    render(<PermissionMatrix overview={single} />);
    expect(screen.getByTestId("workspace-count").textContent).toContain("1 workspace");
  });

  it("renders a row per workspace", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const ws1 = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    const ws2 = "ws-11223344-5566-7788-9900-aabbccddeeff";
    expect(screen.getByTestId(`workspace-row-${ws1}`)).not.toBeNull();
    expect(screen.getByTestId(`workspace-row-${ws2}`)).not.toBeNull();
  });

  it("shows owners count for workspace", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    expect(screen.getByTestId(`ws-owners-${wsId}`).textContent).toBe("1");
  });

  it("shows admins count for workspace", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    expect(screen.getByTestId(`ws-admins-${wsId}`).textContent).toBe("2");
  });

  it("shows members count for workspace", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    expect(screen.getByTestId(`ws-members-${wsId}`).textContent).toBe("5");
  });

  it("shows viewers count for workspace", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    expect(screen.getByTestId(`ws-viewers-${wsId}`).textContent).toBe("0");
  });

  it("shows zero viewers for workspace with none", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    expect(screen.getByTestId(`ws-viewers-${wsId}`).textContent).toBe("0");
  });

  it("workspace ID is truncated in display", () => {
    render(<PermissionMatrix overview={makePermissionOverview()} />);
    const wsId = "ws-aabbccdd-1111-2222-3333-aabbccddeeff";
    const cell = screen.getByTestId(`ws-id-${wsId}`);
    expect(cell.textContent?.length).toBeLessThan(wsId.length);
  });

  it("does not render table when no workspaces", () => {
    const empty: PermissionOverview = { workspaces: [], total_workspaces: 0, checked_at: NOW };
    render(<PermissionMatrix overview={empty} />);
    expect(screen.queryByTestId("workspace-count")).toBeNull();
  });
});
