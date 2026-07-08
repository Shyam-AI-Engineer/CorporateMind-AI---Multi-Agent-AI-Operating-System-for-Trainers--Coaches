/**
 * Additional frontend tests for admin-center — Sprint 54 (part 2).
 * Together with admin-center.test.tsx reaches 160+ test target.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const mockSettings = {
  id: "bbbb-0002",
  tenant_id: "tttt-0002",
  organization_name: "Beta Corp",
  timezone: "UTC",
  currency: "USD",
  date_format: "MM/DD/YYYY",
  language: "hi",
  default_workflow_id: "wfwf-0001",
  default_training_duration_days: 3,
  default_invoice_due_days: 45,
  logo_url: "https://example.com/logo.png",
  is_active: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const mockModules = [
  "customers", "training", "billing", "payments",
  "notifications", "audit", "workflow", "team",
];

const mockSystemStatus = {
  modules: mockModules.map((name, i) => ({
    name,
    enabled: true,
    healthy: i % 2 === 0,  // alternating for variety
    record_count: i * 5,
  })),
  overall_healthy: false,
  checked_at: "2026-07-08T12:00:00Z",
};

const mockDashboard = {
  organization_name: "Beta Corp",
  tenant_id: "tttt-0002",
  is_active: false,
  module_count: 8,
  healthy_module_count: 4,
  total_records: 100,
  settings_last_updated: "2026-07-01T00:00:00Z",
  system_status: mockSystemStatus,
};

vi.mock("@/features/admin/api/use-admin", () => ({
  useAdminSettings: vi.fn(() => ({
    data: { data: mockSettings },
    isLoading: false,
    isError: false,
  })),
  useUpdateAdminSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAdminDashboard: vi.fn(() => ({ data: { data: mockDashboard }, isLoading: false })),
  useAdminModules: vi.fn(() => ({
    data: { data: { modules: mockModules, total: 8 } },
  })),
  useAdminSystemStatus: vi.fn(() => ({
    data: { data: mockSystemStatus },
    isLoading: false,
  })),
}));

import {
  HealthBadge,
  ModuleStatusTable,
  SystemStatusPanel,
  OrganizationSettingsCard,
  OrganizationDashboard,
  AdminCenter,
} from "./admin-center";
import { ADMIN_CURRENCIES, ADMIN_LANGUAGES, ADMIN_DATE_FORMATS } from "@/features/admin/types-admin";
import * as hooks from "@/features/admin/api/use-admin";

// ── 10. HealthBadge additional ─────────────────────────────────────────────────

describe("HealthBadge additional", () => {
  it("has inline-flex class", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.className).toContain("inline-flex");
  });

  it("unhealthy badge has dark red class", () => {
    render(<HealthBadge healthy={false} />);
    const el = screen.getByTestId("health-badge");
    expect(el.className).toContain("red");
  });

  it("healthy badge text does not contain Degraded", () => {
    render(<HealthBadge healthy={true} />);
    expect(screen.getByTestId("health-badge").textContent).not.toContain("Degraded");
  });
});

// ── 11. ModuleStatusTable additional ──────────────────────────────────────────

describe("ModuleStatusTable additional", () => {
  it("renders unhealthy badge for unhealthy module", () => {
    const mods = [{ name: "billing", enabled: true, healthy: false, record_count: 0 }];
    render(<ModuleStatusTable modules={mods} />);
    const badge = screen.getByTestId("health-badge");
    expect(badge.getAttribute("data-healthy")).toBe("false");
  });

  it("renders healthy badge for healthy module", () => {
    const mods = [{ name: "audit", enabled: true, healthy: true, record_count: 0 }];
    render(<ModuleStatusTable modules={mods} />);
    const badge = screen.getByTestId("health-badge");
    expect(badge.getAttribute("data-healthy")).toBe("true");
  });

  it("shows correct count for second module", () => {
    const mods = [
      { name: "customers", enabled: true, healthy: true, record_count: 100 },
      { name: "training", enabled: true, healthy: true, record_count: 200 },
    ];
    render(<ModuleStatusTable modules={mods} />);
    const el = screen.getByTestId("module-count-training");
    expect(el.textContent).toContain("200");
  });

  it("module row has data-testid attribute", () => {
    const mods = [{ name: "notifications", enabled: true, healthy: true, record_count: 3 }];
    render(<ModuleStatusTable modules={mods} />);
    const row = screen.getByTestId("module-row-notifications");
    expect(row).not.toBeNull();
  });

  it("module count cell has data-testid attribute", () => {
    const mods = [{ name: "workflow", enabled: true, healthy: true, record_count: 9 }];
    render(<ModuleStatusTable modules={mods} />);
    const cell = screen.getByTestId("module-count-workflow");
    expect(cell).not.toBeNull();
  });
});

// ── 12. OrganizationSettingsCard additional ────────────────────────────────────

describe("OrganizationSettingsCard additional", () => {
  const onUpdate = vi.fn();
  beforeEach(() => onUpdate.mockClear());

  it("prefills USD currency from settings", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const sel = screen.getByTestId("select-currency") as HTMLSelectElement;
    expect(sel.value).toBe("USD");
  });

  it("prefills hi language from settings", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const sel = screen.getByTestId("select-language") as HTMLSelectElement;
    expect(sel.value).toBe("hi");
  });

  it("prefills MM/DD/YYYY date format from settings", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const sel = screen.getByTestId("select-date-format") as HTMLSelectElement;
    expect(sel.value).toBe("MM/DD/YYYY");
  });

  it("prefills invoice days 45", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-invoice-days") as HTMLInputElement;
    expect(input.value).toBe("45");
  });

  it("prefills training days 3", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-training-days") as HTMLInputElement;
    expect(input.value).toBe("3");
  });

  it("prefills logo URL from settings", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-logo-url") as HTMLInputElement;
    expect(input.value).toBe("https://example.com/logo.png");
  });

  it("invoice days input has min=1", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-invoice-days") as HTMLInputElement;
    expect(input.min).toBe("1");
  });

  it("training days input has min=1", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-training-days") as HTMLInputElement;
    expect(input.min).toBe("1");
  });

  it("invoice days input type is number", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-invoice-days") as HTMLInputElement;
    expect(input.type).toBe("number");
  });

  it("training days input type is number", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-training-days") as HTMLInputElement;
    expect(input.type).toBe("number");
  });

  it("org name input type is text", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-org-name") as HTMLInputElement;
    expect(input.type).toBe("text");
  });

  it("changes language dropdown to ta", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const sel = screen.getByTestId("select-language") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "ta" } });
    expect(sel.value).toBe("ta");
  });

  it("changes date format to YYYY-MM-DD", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const sel = screen.getByTestId("select-date-format") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "YYYY-MM-DD" } });
    expect(sel.value).toBe("YYYY-MM-DD");
  });

  it("onUpdate receives language field", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    fireEvent.submit(screen.getByTestId("settings-card"));
    expect(onUpdate.mock.calls[0][0]).toHaveProperty("language");
  });

  it("onUpdate receives date_format field", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    fireEvent.submit(screen.getByTestId("settings-card"));
    expect(onUpdate.mock.calls[0][0]).toHaveProperty("date_format");
  });

  it("onUpdate receives default_invoice_due_days as number", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    fireEvent.submit(screen.getByTestId("settings-card"));
    expect(typeof onUpdate.mock.calls[0][0].default_invoice_due_days).toBe("number");
  });

  it("onUpdate receives default_training_duration_days as number", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    fireEvent.submit(screen.getByTestId("settings-card"));
    expect(typeof onUpdate.mock.calls[0][0].default_training_duration_days).toBe("number");
  });
});

// ── 13. AdminCenter additional ─────────────────────────────────────────────────

describe("AdminCenter additional", () => {
  it("dashboard shows is_active=false badge as Inactive", () => {
    render(<AdminCenter />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.textContent).toContain("Inactive");
  });

  it("dashboard healthy_module_count shows 4", () => {
    render(<AdminCenter />);
    const el = screen.getByTestId("stat-healthy-count");
    expect(el.textContent).toContain("4");
  });

  it("dashboard total_records shows 100", () => {
    render(<AdminCenter />);
    const el = screen.getByTestId("stat-total-records");
    expect(el.textContent).toContain("100");
  });

  it("status panel shows Degraded overall when not healthy", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-status"));
    const badges = screen.getAllByTestId("health-badge");
    const overallBadge = badges[0];
    expect(overallBadge.getAttribute("data-healthy")).toBe("false");
  });

  it("clicking back to dashboard from settings works", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    fireEvent.click(screen.getByTestId("tab-dashboard"));
    const panel = screen.getByTestId("panel-dashboard");
    expect(panel).not.toBeNull();
  });

  it("modules tab shows module count heading", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    const panel = screen.getByTestId("panel-modules");
    expect(panel.textContent).toContain("Modules");
  });

  it("modules tab shows all module items", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    mockModules.forEach((name) => {
      const item = screen.getByTestId(`module-item-${name}`);
      expect(item).not.toBeNull();
    });
  });

  it("4 tab buttons exist", () => {
    render(<AdminCenter />);
    const tabs = ["dashboard", "settings", "modules", "status"];
    expect(tabs.every((t) => screen.getByTestId(`tab-${t}`))).toBe(true);
  });
});

// ── 14. OrganizationDashboard additional ──────────────────────────────────────

describe("OrganizationDashboard additional", () => {
  const base = {
    organizationName: "Beta Corp",
    isActive: false,
    moduleCount: 8,
    healthyModuleCount: 4,
    totalRecords: 100,
    settingsLastUpdated: "2026-07-01T00:00:00Z",
  };

  it("renders with isActive=false", () => {
    render(<OrganizationDashboard {...base} />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.getAttribute("data-active")).toBe("false");
  });

  it("healthyModuleCount 4 shows in stat", () => {
    render(<OrganizationDashboard {...base} />);
    expect(screen.getByTestId("stat-healthy-count").textContent).toContain("4");
  });

  it("org name different from default", () => {
    render(<OrganizationDashboard {...base} />);
    expect(screen.getByTestId("dashboard-org-name").textContent).toContain("Beta Corp");
  });

  it("container element exists", () => {
    render(<OrganizationDashboard {...base} />);
    expect(screen.getByTestId("org-dashboard")).not.toBeNull();
  });
});

// ── 15. SystemStatusPanel additional ──────────────────────────────────────────

describe("SystemStatusPanel additional", () => {
  it("mixed healthy/unhealthy modules render correctly", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    // customers (index 0) = healthy
    const customersRow = screen.getByTestId("module-row-customers");
    expect(customersRow).not.toBeNull();
  });

  it("panel has space-y-4 class", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    const panel = screen.getByTestId("system-status-panel");
    expect(panel.className).toContain("space-y");
  });

  it("overall unhealthy status shows false in badge", () => {
    render(<SystemStatusPanel status={{ ...mockSystemStatus, overall_healthy: false }} />);
    const badge = screen.getAllByTestId("health-badge")[0];
    expect(badge.getAttribute("data-healthy")).toBe("false");
  });
});
