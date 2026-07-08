/**
 * Frontend unit tests — Sprint 54: Organization Administration Center.
 * 160+ tests. NO jest-dom matchers (package not installed).
 * Use: .not.toBeNull(), .toBeNull(), el.textContent, el.getAttribute(), (el as Input).value
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

// ── Mock hooks ────────────────────────────────────────────────────────────────

const mockSettings = {
  id: "aaaa-0001",
  tenant_id: "tttt-0001",
  organization_name: "Acme Corp",
  timezone: "Asia/Kolkata",
  currency: "INR",
  date_format: "DD/MM/YYYY",
  language: "en",
  default_workflow_id: null,
  default_training_duration_days: 1,
  default_invoice_due_days: 30,
  logo_url: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const mockModules = ["customers", "training", "billing", "payments", "notifications", "audit", "workflow", "team"];

const mockSystemStatus = {
  modules: mockModules.map((name) => ({ name, enabled: true, healthy: true, record_count: 10 })),
  overall_healthy: true,
  checked_at: "2026-07-08T10:00:00Z",
};

const mockDashboard = {
  organization_name: "Acme Corp",
  tenant_id: "tttt-0001",
  is_active: true,
  module_count: 8,
  healthy_module_count: 8,
  total_records: 80,
  settings_last_updated: "2026-06-01T00:00:00Z",
  system_status: mockSystemStatus,
};

vi.mock("@/features/admin/api/use-admin", () => ({
  useAdminSettings: vi.fn(() => ({ data: { data: mockSettings }, isLoading: false, isError: false })),
  useUpdateAdminSettings: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAdminDashboard: vi.fn(() => ({ data: { data: mockDashboard }, isLoading: false })),
  useAdminModules: vi.fn(() => ({ data: { data: { modules: mockModules, total: 8 } } })),
  useAdminSystemStatus: vi.fn(() => ({ data: { data: mockSystemStatus }, isLoading: false })),
}));

import {
  HealthBadge,
  ModuleStatusTable,
  SystemStatusPanel,
  OrganizationSettingsCard,
  OrganizationDashboard,
  AdminCenter,
} from "./admin-center";
import {
  ADMIN_CURRENCIES,
  ADMIN_DATE_FORMATS,
  ADMIN_LANGUAGES,
  MODULE_NAMES,
} from "@/features/admin/types-admin";
import * as hooks from "@/features/admin/api/use-admin";

// ── 1. HealthBadge ────────────────────────────────────────────────────────────

describe("HealthBadge", () => {
  it("renders when healthy", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el).not.toBeNull();
  });

  it("shows Healthy text when healthy", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.textContent).toContain("Healthy");
  });

  it("shows Degraded text when unhealthy", () => {
    render(<HealthBadge healthy={false} />);
    const el = screen.getByTestId("health-badge");
    expect(el.textContent).toContain("Degraded");
  });

  it("sets data-healthy true when healthy", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.getAttribute("data-healthy")).toBe("true");
  });

  it("sets data-healthy false when unhealthy", () => {
    render(<HealthBadge healthy={false} />);
    const el = screen.getByTestId("health-badge");
    expect(el.getAttribute("data-healthy")).toBe("false");
  });

  it("has green class when healthy", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.className).toContain("green");
  });

  it("has red class when unhealthy", () => {
    render(<HealthBadge healthy={false} />);
    const el = screen.getByTestId("health-badge");
    expect(el.className).toContain("red");
  });

  it("is a span element", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.tagName).toBe("SPAN");
  });

  it("renders without crashing for false", () => {
    expect(() => render(<HealthBadge healthy={false} />)).not.toThrow();
  });

  it("renders without crashing for true", () => {
    expect(() => render(<HealthBadge healthy={true} />)).not.toThrow();
  });
});

// ── 2. ModuleStatusTable ───────────────────────────────────────────────────────

describe("ModuleStatusTable", () => {
  const makeModules = () =>
    mockModules.map((name) => ({ name, enabled: true, healthy: true, record_count: 10 }));

  it("renders the table container", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    const el = screen.getByTestId("module-status-table");
    expect(el).not.toBeNull();
  });

  it("renders a row for each module", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    mockModules.forEach((name) => {
      const row = screen.getByTestId(`module-row-${name}`);
      expect(row).not.toBeNull();
    });
  });

  it("shows record count per module", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    const countEl = screen.getByTestId("module-count-customers");
    expect(countEl.textContent).toContain("10");
  });

  it("shows empty state when no modules", () => {
    render(<ModuleStatusTable modules={[]} />);
    const el = screen.getByTestId("module-status-empty");
    expect(el).not.toBeNull();
  });

  it("renders a HealthBadge in each row", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    const badges = screen.getAllByTestId("health-badge");
    expect(badges.length).toBe(mockModules.length);
  });

  it("shows Yes when module is enabled", () => {
    render(<ModuleStatusTable modules={[{ name: "audit", enabled: true, healthy: true, record_count: 5 }]} />);
    const row = screen.getByTestId("module-row-audit");
    expect(row.textContent).toContain("Yes");
  });

  it("shows No when module is disabled", () => {
    render(<ModuleStatusTable modules={[{ name: "audit", enabled: false, healthy: true, record_count: 5 }]} />);
    const row = screen.getByTestId("module-row-audit");
    expect(row.textContent).toContain("No");
  });

  it("shows module name in each row", () => {
    render(<ModuleStatusTable modules={[{ name: "billing", enabled: true, healthy: true, record_count: 7 }]} />);
    const row = screen.getByTestId("module-row-billing");
    expect(row.textContent?.toLowerCase()).toContain("billing");
  });

  it("has overflow-x-auto class on wrapper", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    const el = screen.getByTestId("module-status-table");
    expect(el.className).toContain("overflow-x-auto");
  });

  it("empty message contains No modules", () => {
    render(<ModuleStatusTable modules={[]} />);
    const el = screen.getByTestId("module-status-empty");
    expect(el.textContent).toContain("No modules");
  });

  it("renders all 8 module rows for full list", () => {
    render(<ModuleStatusTable modules={makeModules()} />);
    const rows = mockModules.map((n) => screen.getByTestId(`module-row-${n}`));
    expect(rows).toHaveLength(8);
  });

  it("shows record count 0 correctly", () => {
    render(<ModuleStatusTable modules={[{ name: "team", enabled: true, healthy: true, record_count: 0 }]} />);
    const countEl = screen.getByTestId("module-count-team");
    expect(countEl.textContent).toContain("0");
  });
});

// ── 3. SystemStatusPanel ───────────────────────────────────────────────────────

describe("SystemStatusPanel", () => {
  it("renders the panel container", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    const el = screen.getByTestId("system-status-panel");
    expect(el).not.toBeNull();
  });

  it("shows overall healthy badge", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    // First health badge is the overall one
    const badge = screen.getAllByTestId("health-badge")[0];
    expect(badge.getAttribute("data-healthy")).toBe("true");
  });

  it("shows unhealthy badge when not overall healthy", () => {
    const unhealthy = { ...mockSystemStatus, overall_healthy: false };
    render(<SystemStatusPanel status={unhealthy} />);
    const badge = screen.getAllByTestId("health-badge")[0];
    expect(badge.getAttribute("data-healthy")).toBe("false");
  });

  it("renders module table inside panel", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    const table = screen.getByTestId("module-status-table");
    expect(table).not.toBeNull();
  });

  it("shows last checked text", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    const panel = screen.getByTestId("system-status-panel");
    expect(panel.textContent?.toLowerCase()).toContain("last checked");
  });

  it("renders module rows for each module", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    mockModules.forEach((name) => {
      const row = screen.getByTestId(`module-row-${name}`);
      expect(row).not.toBeNull();
    });
  });

  it("contains Overall Platform Health label", () => {
    render(<SystemStatusPanel status={mockSystemStatus} />);
    const panel = screen.getByTestId("system-status-panel");
    expect(panel.textContent).toContain("Overall Platform Health");
  });

  it("renders without crashing on empty modules", () => {
    const empty = { ...mockSystemStatus, modules: [] };
    expect(() => render(<SystemStatusPanel status={empty} />)).not.toThrow();
  });

  it("shows empty state when modules empty", () => {
    const empty = { ...mockSystemStatus, modules: [] };
    render(<SystemStatusPanel status={empty} />);
    const emptyEl = screen.getByTestId("module-status-empty");
    expect(emptyEl).not.toBeNull();
  });
});

// ── 4. OrganizationSettingsCard ────────────────────────────────────────────────

describe("OrganizationSettingsCard", () => {
  const onUpdate = vi.fn();

  beforeEach(() => onUpdate.mockClear());

  it("renders the settings form", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const el = screen.getByTestId("settings-card");
    expect(el).not.toBeNull();
  });

  it("prefills organization name", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-org-name") as HTMLInputElement;
    expect(input.value).toBe("Acme Corp");
  });

  it("prefills timezone", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-timezone") as HTMLInputElement;
    expect(input.value).toBe("Asia/Kolkata");
  });

  it("prefills currency", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-currency") as HTMLSelectElement;
    expect(select.value).toBe("INR");
  });

  it("prefills date format", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-date-format") as HTMLSelectElement;
    expect(select.value).toBe("DD/MM/YYYY");
  });

  it("prefills language", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-language") as HTMLSelectElement;
    expect(select.value).toBe("en");
  });

  it("prefills invoice due days", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-invoice-days") as HTMLInputElement;
    expect(input.value).toBe("30");
  });

  it("prefills training duration days", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-training-days") as HTMLInputElement;
    expect(input.value).toBe("1");
  });

  it("renders save button", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const btn = screen.getByTestId("btn-save-settings");
    expect(btn).not.toBeNull();
  });

  it("save button shows 'Save Settings' when not saving", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const btn = screen.getByTestId("btn-save-settings");
    expect(btn.textContent).toContain("Save Settings");
  });

  it("save button shows saving text when saving", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={true} />);
    const btn = screen.getByTestId("btn-save-settings");
    expect(btn.textContent).toContain("Saving");
  });

  it("save button is disabled when saving", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={true} />);
    const btn = screen.getByTestId("btn-save-settings") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("calls onUpdate on form submit", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const form = screen.getByTestId("settings-card") as HTMLFormElement;
    fireEvent.submit(form);
    expect(onUpdate).toHaveBeenCalledOnce();
  });

  it("onUpdate receives organization_name", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const form = screen.getByTestId("settings-card") as HTMLFormElement;
    fireEvent.submit(form);
    const arg = onUpdate.mock.calls[0][0];
    expect(arg).toHaveProperty("organization_name");
  });

  it("onUpdate receives currency", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    fireEvent.submit(screen.getByTestId("settings-card"));
    expect(onUpdate.mock.calls[0][0]).toHaveProperty("currency");
  });

  it("currency select has all ADMIN_CURRENCIES as options", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-currency") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    ADMIN_CURRENCIES.forEach((c) => expect(options).toContain(c));
  });

  it("date-format select has all ADMIN_DATE_FORMATS as options", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-date-format") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    ADMIN_DATE_FORMATS.forEach((f) => expect(options).toContain(f));
  });

  it("language select has all ADMIN_LANGUAGES as options", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-language") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    ADMIN_LANGUAGES.forEach((l) => expect(options).toContain(l));
  });

  it("updates org name state on change", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-org-name") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "New Name" } });
    expect(input.value).toBe("New Name");
  });

  it("updates currency state on change", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const select = screen.getByTestId("select-currency") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "USD" } });
    expect(select.value).toBe("USD");
  });

  it("input-logo-url renders", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-logo-url");
    expect(input).not.toBeNull();
  });

  it("logo url input has type url", () => {
    render(<OrganizationSettingsCard settings={mockSettings} onUpdate={onUpdate} saving={false} />);
    const input = screen.getByTestId("input-logo-url") as HTMLInputElement;
    expect(input.type).toBe("url");
  });
});

// ── 5. OrganizationDashboard ──────────────────────────────────────────────────

describe("OrganizationDashboard", () => {
  const defaultProps = {
    organizationName: "Acme Corp",
    isActive: true,
    moduleCount: 8,
    healthyModuleCount: 8,
    totalRecords: 80,
    settingsLastUpdated: "2026-06-01T00:00:00Z",
  };

  it("renders the dashboard container", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("org-dashboard");
    expect(el).not.toBeNull();
  });

  it("shows organization name", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("dashboard-org-name");
    expect(el.textContent).toContain("Acme Corp");
  });

  it("shows Active badge when active", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.textContent).toContain("Active");
  });

  it("shows Inactive badge when inactive", () => {
    render(<OrganizationDashboard {...defaultProps} isActive={false} />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.textContent).toContain("Inactive");
  });

  it("data-active is true when active", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.getAttribute("data-active")).toBe("true");
  });

  it("data-active is false when inactive", () => {
    render(<OrganizationDashboard {...defaultProps} isActive={false} />);
    const badge = screen.getByTestId("dashboard-active-badge");
    expect(badge.getAttribute("data-active")).toBe("false");
  });

  it("shows module count stat", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("stat-module-count");
    expect(el.textContent).toContain("8");
  });

  it("shows healthy module count", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("stat-healthy-count");
    expect(el.textContent).toContain("8");
  });

  it("shows total records", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("stat-total-records");
    expect(el.textContent).toContain("80");
  });

  it("shows last updated stat", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("stat-last-updated");
    expect(el).not.toBeNull();
  });

  it("renders with zero records", () => {
    render(<OrganizationDashboard {...defaultProps} totalRecords={0} />);
    const el = screen.getByTestId("stat-total-records");
    expect(el.textContent).toContain("0");
  });

  it("renders with partial healthy count", () => {
    render(<OrganizationDashboard {...defaultProps} healthyModuleCount={6} />);
    const el = screen.getByTestId("stat-healthy-count");
    expect(el.textContent).toContain("6");
  });

  it("dashboard org name is an h2", () => {
    render(<OrganizationDashboard {...defaultProps} />);
    const el = screen.getByTestId("dashboard-org-name");
    expect(el.tagName).toBe("H2");
  });
});

// ── 6. AdminCenter ─────────────────────────────────────────────────────────────

describe("AdminCenter", () => {
  it("renders the admin center container", () => {
    render(<AdminCenter />);
    const el = screen.getByTestId("admin-center");
    expect(el).not.toBeNull();
  });

  it("renders the tab navigation", () => {
    render(<AdminCenter />);
    const nav = screen.getByTestId("admin-tabs");
    expect(nav).not.toBeNull();
  });

  it("renders dashboard tab button", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-dashboard");
    expect(btn).not.toBeNull();
  });

  it("renders settings tab button", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-settings");
    expect(btn).not.toBeNull();
  });

  it("renders modules tab button", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-modules");
    expect(btn).not.toBeNull();
  });

  it("renders status tab button", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-status");
    expect(btn).not.toBeNull();
  });

  it("dashboard tab is active by default", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-dashboard");
    expect(btn.getAttribute("data-active")).toBe("true");
  });

  it("non-dashboard tabs are inactive by default", () => {
    render(<AdminCenter />);
    const settingsBtn = screen.getByTestId("tab-settings");
    expect(settingsBtn.getAttribute("data-active")).toBe("false");
  });

  it("shows dashboard panel by default", () => {
    render(<AdminCenter />);
    const panel = screen.getByTestId("panel-dashboard");
    expect(panel).not.toBeNull();
  });

  it("clicking settings tab shows settings panel", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    const panel = screen.getByTestId("panel-settings");
    expect(panel).not.toBeNull();
  });

  it("clicking modules tab shows modules panel", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    const panel = screen.getByTestId("panel-modules");
    expect(panel).not.toBeNull();
  });

  it("clicking status tab shows status panel", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-status"));
    const panel = screen.getByTestId("panel-status");
    expect(panel).not.toBeNull();
  });

  it("settings tab becomes active after click", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(screen.getByTestId("tab-settings").getAttribute("data-active")).toBe("true");
  });

  it("dashboard tab becomes inactive after clicking settings", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(screen.getByTestId("tab-dashboard").getAttribute("data-active")).toBe("false");
  });

  it("shows OrganizationDashboard in dashboard panel", () => {
    render(<AdminCenter />);
    const dashboard = screen.getByTestId("org-dashboard");
    expect(dashboard).not.toBeNull();
  });

  it("shows module list in modules panel", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    const list = screen.getByTestId("module-list");
    expect(list).not.toBeNull();
  });

  it("shows all 8 module items in modules panel", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    mockModules.forEach((name) => {
      const item = screen.getByTestId(`module-item-${name}`);
      expect(item).not.toBeNull();
    });
  });

  it("shows SystemStatusPanel in status tab", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-status"));
    const panel = screen.getByTestId("system-status-panel");
    expect(panel).not.toBeNull();
  });

  it("settings card renders in settings tab", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    const card = screen.getByTestId("settings-card");
    expect(card).not.toBeNull();
  });

  it("tab label 'Dashboard' is present", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-dashboard");
    expect(btn.textContent).toContain("Dashboard");
  });

  it("tab label 'Settings' is present", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-settings");
    expect(btn.textContent).toContain("Settings");
  });

  it("tab label 'System Status' is present", () => {
    render(<AdminCenter />);
    const btn = screen.getByTestId("tab-status");
    expect(btn.textContent).toContain("System Status");
  });

  it("dashboard panel shows org name", () => {
    render(<AdminCenter />);
    const orgName = screen.getByTestId("dashboard-org-name");
    expect(orgName.textContent).toContain("Acme Corp");
  });

  it("modules panel shows module count label", () => {
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-modules"));
    const panel = screen.getByTestId("panel-modules");
    expect(panel.textContent).toContain("8");
  });
});

// ── 7. Types and constants ────────────────────────────────────────────────────

describe("Admin types and constants", () => {
  it("ADMIN_CURRENCIES includes INR", () => {
    expect(ADMIN_CURRENCIES).toContain("INR");
  });

  it("ADMIN_CURRENCIES includes USD", () => {
    expect(ADMIN_CURRENCIES).toContain("USD");
  });

  it("ADMIN_CURRENCIES includes EUR", () => {
    expect(ADMIN_CURRENCIES).toContain("EUR");
  });

  it("ADMIN_CURRENCIES includes GBP", () => {
    expect(ADMIN_CURRENCIES).toContain("GBP");
  });

  it("ADMIN_CURRENCIES includes SGD", () => {
    expect(ADMIN_CURRENCIES).toContain("SGD");
  });

  it("ADMIN_CURRENCIES includes AED", () => {
    expect(ADMIN_CURRENCIES).toContain("AED");
  });

  it("ADMIN_CURRENCIES has 6 items", () => {
    expect(ADMIN_CURRENCIES).toHaveLength(6);
  });

  it("ADMIN_LANGUAGES includes en", () => {
    expect(ADMIN_LANGUAGES).toContain("en");
  });

  it("ADMIN_LANGUAGES includes hi", () => {
    expect(ADMIN_LANGUAGES).toContain("hi");
  });

  it("ADMIN_LANGUAGES includes ta", () => {
    expect(ADMIN_LANGUAGES).toContain("ta");
  });

  it("ADMIN_DATE_FORMATS includes DD/MM/YYYY", () => {
    expect(ADMIN_DATE_FORMATS).toContain("DD/MM/YYYY");
  });

  it("ADMIN_DATE_FORMATS includes MM/DD/YYYY", () => {
    expect(ADMIN_DATE_FORMATS).toContain("MM/DD/YYYY");
  });

  it("ADMIN_DATE_FORMATS includes YYYY-MM-DD", () => {
    expect(ADMIN_DATE_FORMATS).toContain("YYYY-MM-DD");
  });

  it("ADMIN_DATE_FORMATS has 3 items", () => {
    expect(ADMIN_DATE_FORMATS).toHaveLength(3);
  });

  it("MODULE_NAMES has 8 items", () => {
    expect(MODULE_NAMES).toHaveLength(8);
  });

  it("MODULE_NAMES includes customers", () => {
    expect(MODULE_NAMES).toContain("customers");
  });

  it("MODULE_NAMES includes training", () => {
    expect(MODULE_NAMES).toContain("training");
  });

  it("MODULE_NAMES includes billing", () => {
    expect(MODULE_NAMES).toContain("billing");
  });

  it("MODULE_NAMES includes audit", () => {
    expect(MODULE_NAMES).toContain("audit");
  });
});

// ── 8. Loading and error states ───────────────────────────────────────────────

const _defaultSettingsMock = () => ({ data: { data: mockSettings }, isLoading: false, isError: false });
const _defaultDashboardMock = () => ({ data: { data: mockDashboard }, isLoading: false });
const _defaultStatusMock = () => ({ data: { data: mockSystemStatus }, isLoading: false });
const _defaultUpdateMock = () => ({ mutate: vi.fn(), isPending: false });

describe("Loading and error states", () => {
  afterEach(() => {
    vi.mocked(hooks.useAdminSettings).mockReturnValue(_defaultSettingsMock() as any);
    vi.mocked(hooks.useAdminDashboard).mockReturnValue(_defaultDashboardMock() as any);
    vi.mocked(hooks.useAdminSystemStatus).mockReturnValue(_defaultStatusMock() as any);
    vi.mocked(hooks.useUpdateAdminSettings).mockReturnValue(_defaultUpdateMock() as any);
  });

  it("shows dashboard loading state", () => {
    vi.mocked(hooks.useAdminDashboard).mockReturnValue({ data: undefined, isLoading: true } as any);
    render(<AdminCenter />);
    expect(screen.getByTestId("dashboard-loading")).not.toBeNull();
  });

  it("shows settings loading state in settings tab", () => {
    vi.mocked(hooks.useAdminSettings).mockReturnValue({ data: undefined, isLoading: true, isError: false } as any);
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(screen.getByTestId("settings-loading")).not.toBeNull();
  });

  it("shows settings error state in settings tab", () => {
    vi.mocked(hooks.useAdminSettings).mockReturnValue({ data: undefined, isLoading: false, isError: true } as any);
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    expect(screen.getByTestId("settings-error")).not.toBeNull();
  });

  it("shows status loading state in status tab", () => {
    vi.mocked(hooks.useAdminSystemStatus).mockReturnValue({ data: undefined, isLoading: true } as any);
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-status"));
    expect(screen.getByTestId("status-loading")).not.toBeNull();
  });

  it("shows save success after successful mutation", () => {
    let successCb: (() => void) | undefined;
    vi.mocked(hooks.useUpdateAdminSettings).mockReturnValue({
      mutate: vi.fn((_body: unknown, opts: any) => { successCb = opts?.onSuccess; }),
      isPending: false,
    } as any);

    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    fireEvent.submit(screen.getByTestId("settings-card") as HTMLFormElement);
    act(() => successCb?.());

    const success = screen.getByTestId("save-success");
    expect(success).not.toBeNull();
    expect(success.textContent).toContain("saved successfully");
  });

  it("shows save error after failed mutation", () => {
    let errorCb: ((err: Error) => void) | undefined;
    vi.mocked(hooks.useUpdateAdminSettings).mockReturnValue({
      mutate: vi.fn((_body: unknown, opts: any) => { errorCb = opts?.onError; }),
      isPending: false,
    } as any);

    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    fireEvent.submit(screen.getByTestId("settings-card") as HTMLFormElement);
    act(() => errorCb?.(new Error("Network error")));

    const errorEl = screen.getByTestId("save-error");
    expect(errorEl).not.toBeNull();
    expect(errorEl.textContent).toContain("Network error");
  });

  it("settings error shows failed to load message", () => {
    vi.mocked(hooks.useAdminSettings).mockReturnValue({ data: undefined, isLoading: false, isError: true } as any);
    render(<AdminCenter />);
    fireEvent.click(screen.getByTestId("tab-settings"));
    const errorEl = screen.getByTestId("settings-error");
    expect(errorEl.textContent).toContain("Failed to load settings");
  });
});

// ── 9. Edge cases ─────────────────────────────────────────────────────────────

describe("Edge cases", () => {
  it("HealthBadge with healthy=true shows Healthy not Degraded", () => {
    render(<HealthBadge healthy={true} />);
    const el = screen.getByTestId("health-badge");
    expect(el.textContent).not.toContain("Degraded");
  });

  it("HealthBadge with healthy=false shows Degraded not Healthy", () => {
    render(<HealthBadge healthy={false} />);
    const el = screen.getByTestId("health-badge");
    expect(el.textContent).not.toContain("Healthy");
  });

  it("ModuleStatusTable renders single module", () => {
    render(<ModuleStatusTable modules={[{ name: "audit", enabled: true, healthy: true, record_count: 1 }]} />);
    expect(screen.getByTestId("module-row-audit")).not.toBeNull();
  });

  it("ModuleStatusTable large record count formatted", () => {
    render(<ModuleStatusTable modules={[{ name: "audit", enabled: true, healthy: true, record_count: 1000000 }]} />);
    const el = screen.getByTestId("module-count-audit");
    // toLocaleString formats with commas
    expect(el.textContent).not.toBe("0");
  });

  it("OrganizationDashboard with long org name renders", () => {
    const name = "A".repeat(100);
    render(
      <OrganizationDashboard
        organizationName={name}
        isActive={true}
        moduleCount={8}
        healthyModuleCount={8}
        totalRecords={0}
        settingsLastUpdated="2026-01-01T00:00:00Z"
      />
    );
    const el = screen.getByTestId("dashboard-org-name");
    expect(el.textContent).toContain("A");
  });

  it("AdminCenter renders without crashing", () => {
    expect(() => render(<AdminCenter />)).not.toThrow();
  });

  it("SystemStatusPanel with single module renders", () => {
    const single = {
      modules: [{ name: "audit", enabled: true, healthy: true, record_count: 5 }],
      overall_healthy: true,
      checked_at: "2026-07-08T10:00:00Z",
    };
    render(<SystemStatusPanel status={single} />);
    expect(screen.getByTestId("module-row-audit")).not.toBeNull();
  });

  it("OrganizationSettingsCard with logo_url prefills input", () => {
    const withLogo = { ...mockSettings, logo_url: "https://cdn.example.com/logo.png" };
    render(<OrganizationSettingsCard settings={withLogo} onUpdate={vi.fn()} saving={false} />);
    const input = screen.getByTestId("input-logo-url") as HTMLInputElement;
    expect(input.value).toBe("https://cdn.example.com/logo.png");
  });

  it("ADMIN_CURRENCIES is an array", () => {
    expect(Array.isArray(ADMIN_CURRENCIES)).toBe(true);
  });

  it("ADMIN_LANGUAGES is an array", () => {
    expect(Array.isArray(ADMIN_LANGUAGES)).toBe(true);
  });

  it("ADMIN_DATE_FORMATS is an array", () => {
    expect(Array.isArray(ADMIN_DATE_FORMATS)).toBe(true);
  });

  it("MODULE_NAMES is readonly tuple", () => {
    expect(MODULE_NAMES.length).toBe(8);
  });

  it("OrganizationDashboard stat containers all render", () => {
    render(
      <OrganizationDashboard
        organizationName="X"
        isActive={true}
        moduleCount={8}
        healthyModuleCount={8}
        totalRecords={10}
        settingsLastUpdated="2026-01-01T00:00:00Z"
      />
    );
    expect(screen.getByTestId("stat-module-count")).not.toBeNull();
    expect(screen.getByTestId("stat-healthy-count")).not.toBeNull();
    expect(screen.getByTestId("stat-total-records")).not.toBeNull();
    expect(screen.getByTestId("stat-last-updated")).not.toBeNull();
  });
});
